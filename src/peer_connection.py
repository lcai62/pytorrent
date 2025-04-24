import struct

import bitarray
import socket


class PeerConnection:
    """
    handles one tcp connection
    """

    def __init__(self, ip: str, port: int, peer_id: str):
        self.active: bool = False
        self.ip: str = ip
        self.port: int = port
        self.peer_id = peer_id
        self.remote_id = None
        self.sock = None
        self.choked = True
        self.remote_choked = True
        self.interested = False
        self.remote_interested = False

        self.bitmap: bitarray = None

    def connect(self, info_hash, conn_timeout = 2.0, handshake_timeout = 1.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # tcp
        self.sock.settimeout(conn_timeout)
        self.sock.connect((self.ip, self.port))

        self.sock.settimeout(handshake_timeout)
        self._handshake(info_hash)

        self.sock.settimeout(0.5)

    def _handshake(self, info_hash):
        pstr = b"BitTorrent protocol"
        reserved = b'\x00' * 8
        handshake = (
                bytes([len(pstr)]) +
                pstr +
                reserved +
                info_hash +
                self.peer_id.encode("utf-8")
        )
        self.sock.sendall(handshake)

        # receiving handshake
        response = self.sock.recv(68)

        if len(response) != 68:
            raise Exception("incomplete handshake ")

        # validate protocol string
        if response[0] != len(pstr) or response[1:20] != pstr:
            raise Exception("invalid protocol in handshake")

        # validate info hash
        received_info_hash = response[28:48]
        if received_info_hash != info_hash:
            raise Exception("info hash wrong — wrong torrent")

        # get peer ID
        self.remote_id = response[48:68]

        print(f"connected to peer: {self.remote_id.decode(errors='ignore')}")

        self.active = True

    def send_interested(self):
        self._safe_send(struct.pack(">IB", 1, 2))

    def send_request(self, index, begin, length):
        msg = struct.pack(">IBIII", 13, 6, index, begin, length)
        self._safe_send(msg)

    def recv_message(self):
        try:
            length_bytes = self._recv_exact(4)
            length = struct.unpack(">I", length_bytes)[0]
            if length == 0:
                return {'type': 'keep-alive'}
            msg_id = self._recv_exact(1)[0]
            payload = self._recv_exact(length - 1)
            return {'type': 'message', 'id': msg_id, 'payload': payload}
        except socket.timeout:
            return {'type': 'timeout'}

    def _recv_exact(self, n):
        data = b''
        while len(data) < n:
            part = self.sock.recv(n - len(data))
            if not part:
                raise ConnectionError("Socket closed")
            data += part
        return data

    def _safe_send(self, payload: bytes) -> bool:
        """
        true on success, false otherwise
        """
        try:
            self.sock.sendall(payload)
            return True
        except (BrokenPipeError,
                ConnectionResetError,
                OSError):  # covers [WinError 10054] etc.
            self.active = False
            return False