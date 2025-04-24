import hashlib
import socket
import struct
from concurrent.futures import ThreadPoolExecutor, as_completed

import bencodepy
import requests

from torrent_file import TorrentFile
from peer_connection import PeerConnection


class PeerManager:
    """
    handles tcp connections for one download
    """

    def __init__(self, peers, torrent_file: TorrentFile):
        self.peers: list[PeerConnection] = peers
        self.torrent_file = torrent_file

    def connect_all(self):

        def _connect(peer):
            try:
                peer.connect(self.torrent_file.info_hash)
                return peer
            except Exception as e:
                print(f"connection failed {peer.ip}:{peer.port} — {e}")

        alive = []
        with ThreadPoolExecutor(max_workers=120) as pool:
            futures = {pool.submit(_connect, peer) for peer in self.peers}
            for future in as_completed(futures):
                peer = future.result()
                if peer is not None:
                    alive.append(peer)

        self.peers = alive

    def add_peer(self, peer: PeerConnection):
        self.peers.append(peer)

    def remove_peer(self, peer: PeerConnection):
        self.peers.remove(peer)
