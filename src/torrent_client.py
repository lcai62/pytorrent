import hashlib
import random
import selectors
import struct
import threading
import time
from time import sleep
from typing import Optional

import bitarray

from peer_connection import PeerConnection
from peer_manager import PeerManager
from piece_manager import PieceManager
from storage import PieceStorage
from torrent_file import TorrentFile
from tracker_client import TrackerClient
from udp_tracker_client import UDPTrackerClient


class TorrentClient:
    """
    manages the downloading and seeding for one torrent

    Attributes:
        torrent_file: TorrentFile instance
        peer_id: unique id for this torrent client
        tracker: TrackerClient instance
        download_dir: directory where files should be stored
        peers: list of PeerConnection objects
        peer_manager: PeerManager object
        select: i/o selector for non blocking peer communication
        piece_storage: PieceStorage object that handles all disk storage
        piece_manager: PieceManager object that handles piece and block details
        num_pieces: total number of pieces in the torrent
        paused: True if the torrent is paused
        _paused_cond: condition variable to control pause/resume
    """

    def __init__(self, torrent_path: str, peer_id: Optional[str] = None, download_dir: str = ".",
                 was_finished: bool = False):
        """
        initializes torrent client

        Attributes:
            torrent_path: path to .torrent file
            peer_id: unique id for this torrent client
            download_dir: directory where files should be stored
            was_finished: if True, verify existing file and mark pieces complete
        """

        # parse torrent
        self.torrent_file: TorrentFile = TorrentFile(torrent_path)
        self.torrent_file.parse()

        # trackers
        self.peer_id: str = peer_id or self._generate_peer_id()
        if self.torrent_file.announce.startswith("udp://"):
            self.tracker = UDPTrackerClient(self.torrent_file, self.peer_id)
        else:
            self.tracker = TrackerClient(self.torrent_file, self.peer_id)

        self.download_dir: str = download_dir

        # peers
        self.peer_manager: Optional[PeerManager] = None

        # select
        self.select = selectors.DefaultSelector()

        # piece storage
        self.piece_storage: PieceStorage = PieceStorage(self.torrent_file, download_dir)
        self.piece_manager: PieceManager = PieceManager(self.torrent_file, piece_storage=self.piece_storage)

        # verify existing download
        if was_finished:
            for piece in self.piece_manager.pieces:
                piece.is_complete = True
            self.piece_manager.downloaded_bytes = self.torrent_file.total_length

        else:
            self._verify_existing()

        self.num_pieces: int = len(self.piece_manager.pieces)

        self.paused: bool = False
        self._paused_cond = threading.Condition()

        self.start_time: float = time.time()

    def download(self) -> None:
        """starts main download"""

        # ask tracker for peers, connect, and send interested
        self._setup_peers()

        # start retry worker
        self.peer_manager.start_retry_worker()

        self._event_loop()

    def pause(self) -> None:
        """pauses the download"""
        with self._paused_cond:
            self.paused = True

    def resume(self) -> None:
        """resumes the download"""
        with self._paused_cond:
            self.paused = False
            self._paused_cond.notify_all()

    def announce_now(self, event: str = "") -> None:
        """forces a re-announce to the tracker"""

        try:
            new_peers = self.tracker.get_peers(event=event)
            known_peer_ips = {peer.ip for peer in self.peer_manager.peers}
            fresh_peers = [p for p in new_peers if p.ip not in known_peer_ips]

            if fresh_peers:
                new_peer_manager = PeerManager(fresh_peers, self.torrent_file, self.piece_manager)
                new_peer_manager.connect_all()

                for peer in new_peer_manager.peers:
                    if peer.active:
                        self.select.register(peer.sock, selectors.EVENT_READ, data=peer)
                        peer.send_interested()
                        self.peer_manager.add_peer(peer)

                print(f"Added {len(fresh_peers)} new peers")
            else:
                print("No new peers from tracker")

        except Exception as e:
            print(f"Error during reannounce: {e}")

    def _setup_peers(self):
        """fetches peers from trackers, connects, add to selector and send initial messages"""
        peers = self.tracker.get_peers(event="started")
        self.peer_manager = PeerManager(peers, self.torrent_file, self.piece_manager)
        self.peer_manager.connect_all()

        bitfield = self._generate_bitfield()
        for peer in self.peer_manager.peers:
            if peer.active:
                self.select.register(peer.sock, selectors.EVENT_READ, data=peer)
                peer.send_interested()
                peer.send_bitfield(bitfield)

    def _event_loop(self):
        while not self.piece_manager.is_finished():
            with self._paused_cond:
                while self.paused:
                    self._paused_cond.wait()

            self.piece_manager.tick()

            if not self.select.get_map():
                # no active peers
                sleep(1.0)
                continue

            events = self.select.select(timeout=1.0)
            if not events:
                continue

            for key, _ in events:
                peer: PeerConnection = key.data
                if not peer.active:
                    continue

                try:
                    msg = peer.recv_message()
                except ConnectionError:
                    print(f"[{peer.ip}:{peer.port}] disconnected")
                    self.peer_manager.remove_peer(peer)
                    self.select.unregister(peer.sock)

                    continue

                if msg is None:
                    continue

                if msg["type"] == "timeout" or msg["type"] == "keep-alive":
                    continue

                message_id = msg["id"]
                payload = msg["payload"]

                if message_id == 0:
                    peer.choked = True

                elif message_id == 1:
                    peer.choked = False

                elif message_id == 2:
                    peer.remote_interested = True
                    if peer.remote_choked:
                        peer.send_unchoke()

                elif message_id == 3:
                    peer.remote_interested = False
                    if not peer.remote_choked:
                        peer.send_choke()
                        peer.remote_choked = True

                elif message_id == 4:
                    piece_index = struct.unpack(">I", payload)[0]
                    peer.ensure_bitmap(self.num_pieces)
                    peer.bitmap[piece_index] = 1

                elif message_id == 5:
                    peer.bitmap = bitarray.bitarray()
                    peer.bitmap.frombytes(payload)
                    peer.ensure_bitmap(self.num_pieces)

                elif message_id == 6:
                    index, start, length = struct.unpack(">III", payload)
                    if (not peer.remote_choked and
                            0 <= index < self.num_pieces and
                            self.piece_manager.pieces[index].is_complete):
                        global_off = index * self.torrent_file.piece_length + start
                        block = self.piece_storage.read(global_off, length)
                        peer.send_piece(index, start, block)

                elif message_id == 7:
                    index = struct.unpack(">I", payload[:4])[0]
                    begin = struct.unpack(">I", payload[4:8])[0]
                    block = payload[8:]

                    completed = self.piece_manager.block_received(index, begin, block)
                    if completed:
                        for p in self.peer_manager.peers:
                            if p.active:
                                p.send_have(index)

                        if self.piece_manager.is_finished():
                            self.piece_storage.switch_to_seeding()

                if (not peer.choked) and peer.bitmap:
                    block = self.piece_manager.next_request_rarest_first(peer.bitmap)
                    if block:
                        peer.send_request(block.piece_index, block.offset, block.length)

    def _generate_bitfield(self) -> bitarray:
        """creates our clients bitfield"""
        bits = bitarray.bitarray(len(self.piece_manager.pieces))
        for piece in self.piece_manager.pieces:
            bits[piece.index] = piece.is_complete
        return bits.tobytes()

    def _generate_peer_id(self) -> str:
        """generates a random peer id string"""
        return "-PC0001-" + ''.join(random.choice("0123456789abcdef")
                                    for _ in range(12))

    def _verify_existing(self) -> None:
        """
        checks disk pieces to see which are already completed, appropriately
        marks pieces and blocks in the piece manager
        """

        verified_count = 0

        for piece in self.piece_manager.pieces:
            start = piece.index * self.torrent_file.piece_length
            end = start + piece.length
            data = self.piece_storage.read(start, end - start)

            actual_hash = hashlib.sha1(data, usedforsecurity=False).digest()
            expected_hash = piece.sha1

            if actual_hash == expected_hash:
                piece.is_complete = True
                for block in piece.blocks:
                    block.is_received = True
                    block.data = None
                self.piece_manager.downloaded_bytes += piece.length
                verified_count += 1

        print(f"[verify] Verified {verified_count}/{len(self.piece_manager.pieces)} pieces")

        if self.piece_manager.is_finished():
            print(f"[verify] All pieces complete for {self.torrent_file.name}")
            self.piece_storage.switch_to_seeding()
        else:
            print(f"[verify] Not all pieces complete for {self.torrent_file.name}")

    def cleanup(self):
        """cleans up storage resources"""
        self.piece_storage.cleanup()
        self.peer_manager.close_all()
        self.peer_manager.stop_retry_worker()
