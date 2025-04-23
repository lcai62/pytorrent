import hashlib
import socket
import struct

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
        for peer in self.peers:
            try:
                peer.connect(self.torrent_file.info_hash)
            except Exception as e:
                print(f"connection failed {peer.ip}:{peer.port} — {e}")

    def add_peer(self, peer: PeerConnection):
        self.peers.append(peer)

    def remove_peer(self, peer: PeerConnection):
        self.peers.remove(peer)
