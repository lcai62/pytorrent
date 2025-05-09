from __future__ import annotations

import socket
import struct
import time
from typing import Optional, Dict, Any

import bitarray

PROTOCOL_STRING = b"BitTorrent protocol"
HANDSHAKE_LEN = 49 + len(PROTOCOL_STRING)
MAX_INFLIGHT = 40


class PeerConnection:
    """
    manages tcp connection and message exchange with one bittorrent peer
    handles sending / receiving protocol messages, handshakes, and connection states

    Attributes:
        peer_id: local peer's unique id
        remote_id: connected peers unique id
        ip: remote peer's ip
        port: remote peer's port
        sock: socket connection
        active: True if connection is open and active
        choked: True if remote peer has choked this client
        remote_choked: True if this client has choked the remote peer
        interested: True if this client is interested in peer's pieces
        remote_interested: True if remote peer is interested in this client's pieces
        bitmap: bitmap representing what pieces the peer has
    """

    def __init__(self, ip: str, port: int, peer_id: str) -> None:
        """
        initializes a PeerConnection

        Args:
            ip: ip address of remote peer
            port: port number of remote peer
            peer_id: local peer's unique id
        """

        # peer identification
        self.peer_id: bytes = peer_id.encode() if isinstance(peer_id, str) else peer_id
        self.remote_id = None

        # networking
        self.sock: Optional[socket.socket] = None

        self.ip: str = ip
        self.port: int = port

        # states
        self.active: bool = False

        self.choked: bool = True
        self.remote_choked: bool = True
        self.interested: bool = False
        self.remote_interested: bool = False

        # availability
        self.bitmap: bitarray = None

        # pipelining
        self._inflight: int = 0

        # incremental parsing
        self._recv_buffer: bytearray = bytearray()
        self._bytes_needed: Optional[int] = None

        # accounting
        self.total_downloaded = 0
        self.total_uploaded = 0
        self._rates = []  # timestamp, down, up

    def connect(self, info_hash: bytes, handshake_timeout: float = 1.0) -> None:
        """
        establishes tcp connection and perform handshake

        Args:
            info_hash: SHA1 hash of the torrents info dictionary
            handshake_timeout: timeout for handshake in seconds

        Raises:
            ConnectionError: if the handshake fails or socket closed
        """
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # sock stream = tcp
        self.sock.settimeout(handshake_timeout)
        self.sock.connect((self.ip, self.port))

        # send handshake
        reserved = b'\x00' * 8
        handshake = (
                bytes([len(PROTOCOL_STRING)]) +
                PROTOCOL_STRING +
                reserved +
                info_hash +
                self.peer_id
        )
        self.sock.sendall(handshake)

        # receiving handshake and validation
        response = self._recv_exact(HANDSHAKE_LEN, handshake_timeout)
        self._validate_handshake(response, info_hash)

        # completed, switch to non-blocking
        self.sock.setblocking(False)
        self.active = True

    def close(self) -> None:
        """closes peer connection and marks it invalid"""

        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                print(f"error closing socket: {self.ip}: {self.port} - {e}")

        self.active = False

    def send_interested(self) -> bool:
        """
        send peer an 'interested' message

        Returns:
            True on success, False otherwise
        """
        return self._safe_send(struct.pack(">IB", 1, 2))

    def send_choke(self) -> bool:
        """
        send peer a 'choke' message

        Returns:
            True on success, False otherwise
        """
        msg = struct.pack(">IB", 1, 0)
        return self._safe_send(msg)

    def send_unchoke(self) -> bool:
        """
        send peer an 'unchoke' message

        Returns:
            True on success, False otherwise
        """
        msg = struct.pack(">IB", 1, 1)
        return self._safe_send(msg)

    def send_have(self, index: int) -> bool:
        """
        send peer a 'have' message

        Returns:
            True on success, False otherwise
        """
        msg = struct.pack(">IBI", 5, 4, index)
        return self._safe_send(msg)

    def send_piece(self, index: int, start: int, data: bytes) -> bool:
        """
        send peer a 'piece' message containing file data

        Args:
            index: piece index
            start: byte offset in the piece
            data: block of data to send

        Returns:
            True on success, False otherwise
        """
        msg_length = 9 + len(data)
        msg = struct.pack(">IBII", msg_length, 7, index, start) + data
        self.record_upload(len(data))
        return self._safe_send(msg)

    def send_bitfield(self, bitfield: bytes) -> bool:
        """
        sends a 'bitfield' message representing our available pieces

        Args:
            bitfield: bitfield as bytes

        Returns:
            True if request was sent, False otherwise
        """
        msg_length = 1 + len(bitfield)
        msg = struct.pack(">IB", msg_length, 5) + bitfield
        return self._safe_send(msg)

    def send_request(self, index: int, start: int, length: int) -> bool:
        """
        sends a request for a block of data if total inflight under max

        Args:
            index: the piece index
            start: start byte offset in the piece
            length: length of the requested block

        Returns:
            True if request was sent, False otherwise
        """
        if self._inflight >= MAX_INFLIGHT or not self.active:
            return False

        msg = struct.pack(">IBIII", 13, 6, index, start, length)
        if self._safe_send(msg):
            self._inflight += 1
            return True

        return False

    def recv_message(self) -> Optional[Dict[str, Any]]:
        """
        non-blocking receive of the next message from this peer

        Returns:
            a dictionary with keys:
                - 'type': either 'keep-alive' or 'message'
                - 'id': message id (if type message)
                - 'payload': message payload (if applicable)

            returns none if no message is available

        Raises:
            ConnectionError: if remote peer closes the connection
        """
        if not self.active:
            return None

        try:
            received = self.sock.recv(4096)
            if received:
                self._recv_buffer.extend(received)
            else:
                raise ConnectionError("Socket closed by peer")

        except BlockingIOError:
            # no data
            pass

        message = self._parse_one()

        # we have to update self._inflight here
        if message and message.get("id") == 7:  # piece
            self._inflight = max(0, self._inflight - 1)

        elif message and message.get("id") == 0:  # choke
            # all pending requests are void
            self._inflight = 0

        return message

    def _parse_one(self) -> Optional[Dict[str, Any]]:
        """
        parses one message from the receive buffer (_recv_buffer)

        Returns:
            a dictionary with keys 'type', 'id', and 'payload', or None if message malformed
        """

        if self._bytes_needed is None:
            if len(self._recv_buffer) < 4:
                return None

            length, = struct.unpack(">I", self._recv_buffer[:4])
            del self._recv_buffer[:4]

            if length == 0:
                return {"type": "keep-alive"}

            self._bytes_needed = length

        if len(self._recv_buffer) < self._bytes_needed:
            return None  # need to wait for more bytes

        # received all
        payload = self._recv_buffer[:self._bytes_needed]
        del self._recv_buffer[:self._bytes_needed]
        self._bytes_needed = None

        msg_id = payload[0]
        return {"type": "message", "id": msg_id, "payload": payload[1:]}

    def _recv_exact(self, n: int, timeout: float) -> bytes:

        """
        receives exactly n bytes, blocks until complete or closed

        Args:
            n: number of bytes to receive
            timeout: timeout in seconds

        Returns:
            received bytes

        Raises:
            ConnectionError: if peer closes the connection
        """
        self.sock.settimeout(timeout)
        buffer = bytearray()

        while len(buffer) < n:
            part = self.sock.recv(n - len(buffer))
            if not part:
                raise ConnectionError("Socket closed")
            buffer.extend(part)

        return bytes(buffer)

    def _safe_send(self, payload: bytes) -> bool:
        """
        sends payload to peer, deactivates peer on error

        Args:
            payload: raw bytes to send
        Returns:
            True if payload was sent successfully, False otherwise
        """
        view = memoryview(payload)
        try:
            while view:
                sent = self.sock.send(view)
                view = view[sent:]
            return True

        except (BlockingIOError, BrokenPipeError, ConnectionResetError, OSError):
            self.active = False
            return False

    def _validate_handshake(self, response: bytes, info_hash: bytes) -> None:
        """
        validates the handshake response by checking info hash

        Args:
            response: the raw handshake response
            info_hash: the expected info hash
        Raises:
            ConnectionError: if the handshake response is invalid or incorrect

        """
        if len(response) != HANDSHAKE_LEN:
            raise ConnectionError("incomplete handshake")

        pstr_len = response[0]
        if pstr_len != len(PROTOCOL_STRING) or response[1:1 + pstr_len] != PROTOCOL_STRING:
            raise ConnectionError("protocol string mismatch")

        if response[1 + pstr_len + 8:1 + pstr_len + 8 + 20] != info_hash:
            raise ConnectionError("info hash wrong - wrong torrent")

        self.remote_id = response[-20:]  # last 20 bytes

    def ensure_bitmap(self, num_pieces: int):
        """
        ensures this peers bitmap is initialized and sized correctly

        Args:
            num_pieces: the total number of pieces in the torrent
        """
        if self.bitmap is None:
            self.bitmap = bitarray.bitarray(num_pieces)
            self.bitmap.setall(0)
        elif len(self.bitmap) < num_pieces:
            self.bitmap.extend([0] * (num_pieces - len(self.bitmap)))

    def record_download(self, n: int):
        """add downloaded bytes and speed sample"""
        self.total_downloaded += n
        now = time.time()
        self._rates.append((now, n, 0))
        self.trim_samples(now)

    def record_upload(self, n: int):
        """add uploaded bytes and speed sample"""
        self.total_uploaded += n
        now = time.time()
        self._rates.append((now, 0, n))
        self.trim_samples(now)

    def trim_samples(self, now, window=10):
        """keep at most 'window' seconds of samples"""
        while self._rates and now - self._rates[0][0] > window:
            self._rates.pop(0)

    def down_speed_bps(self) -> float:
        """average DL speed (bytes/s) over last 10s"""
        if not self._rates:
            return 0.0

        now = time.time()
        self.trim_samples(now)

        if len(self._rates) < 2:
            return 0.0

        oldest_time = self._rates[0][0]
        elapsed = now - oldest_time

        if elapsed < 2.0:
            return 0.0

        bytes_dl = sum(s[1] for s in self._rates)
        elapsed = max(1e-6, now - self._rates[0][0])
        return bytes_dl / elapsed

    def up_speed_bps(self) -> float:
        """average UL speed (bytes/s) over last 10s"""
        now = time.time()
        self.trim_samples(now)

        if not self._rates:
            return 0.0

        bytes_ul = sum(s[2] for s in self._rates)
        elapsed = max(1e-6, now - self._rates[0][0])
        return bytes_ul / elapsed

    @property
    def rates(self):
        return self._rates
