# client.py
import os
import random
import selectors
import struct
import time
from typing import Optional, List

import bitarray

from src.peer_manager import PeerManager
from src.torrent_file import TorrentFile
from tracker_client import TrackerClient
from peer_connection import PeerConnection
from piece_manager import PieceManager


class TorrentClient:
    def __init__(self, torrent_path: str, download_dir: str = ".", peer_id: Optional[str] = "aieoriwpcisjkfjdcisf"):
        # parse torrent
        self.torrent_file = TorrentFile(torrent_path)
        self.torrent_file.parse()

        # trackers
        self.peer_id = peer_id or self._generate_peer_id()
        self.tracker = TrackerClient(self.torrent_file, self.peer_id)

        # piece manager for one file
        self.piece_manager = PieceManager(self.torrent_file)
        self.download_dir = download_dir
        self.output_path = os.path.join(download_dir, self.torrent_file.name)

        self.num_pieces = len(self.piece_manager.pieces)

        # peers
        self.peers: List[PeerConnection] = []
        self.peer_manager = None

        # select
        self.select = selectors.DefaultSelector()

    def download(self):

        # ask tracker for peers, connect, and send interested
        self._bootstrap_peers()
        print(self.peers)
        print("bootstrapping peers done")
        print("starting event loop")

        # TODO: what if no peers connect

        # event loop
        self._event_loop()

        # flush to buffer when done
        self._write_to_disk()
        print("written to disk")

    def _bootstrap_peers(self):
        self.peers = self.tracker.get_peers()
        self.peer_manager = PeerManager(self.peers, self.torrent_file)
        self.peer_manager.connect_all()

        self.peers = self.peer_manager.peers
        for peer in self.peers:
            if peer.active:
                # add to selector
                self.select.register(peer.sock, selectors.EVENT_READ, data=peer)
                peer.send_interested()

    def _event_loop(self):
        """
        iterate over connected peers,
            reads one message (if any)
            update piece manager
            sends more request messages while peer unchoked
        """
        while not self.piece_manager.is_finished():
            self.piece_manager.tick()

            # print("================================")
            # print("peer statuses")
            # for idx, peer in enumerate(self.peers):
            #     print(f"peer {idx}, choked: {peer.choked}")
            # print("================================")

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
                    peer.active = False
                    self.select.unregister(peer.sock)
                    peer.sock.close()
                    continue

                if msg is None:
                    continue

                if msg["type"] == "timeout":
                    print(f"timeout received")
                    continue
                if msg["type"] == "keep-alive":
                    print(f"keep alive received")
                    continue

                # otherwise, type is message
                message_id = msg["id"]
                payload = msg["payload"]

                # 0 = choke
                if message_id == 0:
                    print(f"choke received")
                    peer.choked = True

                # 1 = unchoke
                elif message_id == 1:
                    print(f"unchoke received")
                    peer.choked = False

                # 4 = have, update bitmap
                elif message_id == 4:
                    print(f"have received")
                    piece_index = struct.unpack(">I", payload)[0]
                    self._ensure_bitmap(peer, self.num_pieces)
                    peer.bitmap[piece_index] = 1


                # 5 = bitfield
                elif message_id == 5:
                    print(f"bitfield received")
                    peer.bitmap = bitarray.bitarray()
                    peer.bitmap.frombytes(payload)
                    self._ensure_bitmap(peer, self.num_pieces)


                # 7 = piece
                elif message_id == 7:

                    index = struct.unpack(">I", payload[:4])[0]
                    begin = struct.unpack(">I", payload[4:8])[0]
                    block = payload[8:]

                    print(f"piece received, index: {index}, begin: {begin}, block length: {len(block)}")

                    self.piece_manager.block_received(index, begin, block)

                # send request for next block after message
                if (not peer.choked) and peer.bitmap:
                    block = self.piece_manager.next_request(peer.bitmap)
                    if block:
                        print(
                            f"sending request for index: {block.piece_index}, offset: {block.offset}, length: {block.length}")
                        peer.send_request(
                            block.piece_index,
                            block.offset,
                            block.length
                        )

    def _ensure_bitmap(self, peer: PeerConnection, num_pieces: int):
        if peer.bitmap is None:
            # first time we hear from this peer

            peer.bitmap = bitarray.bitarray(num_pieces)
            peer.bitmap.setall(0)

        elif len(peer.bitmap) < num_pieces:
            peer.bitmap.extend([0] * (num_pieces - len(peer.bitmap)))

    def _generate_peer_id(self) -> str:
        # “-PC0001-” + 12 random hex chars (common convention)
        return "-PC0001-" + ''.join(random.choice("0123456789abcdef")
                                    for _ in range(12))

    def _write_to_disk(self):
        with open(self.output_path, "wb") as f:
            for piece in self.piece_manager.pieces:
                f.write(piece.buffer)
