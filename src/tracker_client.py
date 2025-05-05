import hashlib
import struct
from typing import List

import bencodepy
import requests

from peer_connection import PeerConnection
from torrent_file import TorrentFile


class TrackerClient:
    """
    handles communication with bittorrent tracker

    Attributes:
        torrent_file: the parsed TorrentFile object
        peer_id: the local peer's unique identifier
        port: the tcp port used by this client
    """

    def __init__(self, torrent_file: TorrentFile, peer_id: str, port=6881):
        """
        initializes TrackerClient

        Args:
            torrent_file: TorrentFile instance
            peer_id: local peer id
            port: local port number for peer connections
        """
        self.torrent_file = torrent_file
        self.peer_id = peer_id
        self.port = port

    def get_peers(self, event: str) -> List[PeerConnection]:
        """
        retrieve list of peers from tracker

        Args:
            event: a string representing the tracker event

        Returns:
            list of PeerConnections

        Raises:
            Exception: tracker response is not 200
        """
        info_bencoded = bencodepy.encode(self.torrent_file.info)
        info_hash = hashlib.sha1(info_bencoded, usedforsecurity=False).digest()

        url = self._build_url(info_hash, event)

        response = requests.get(url)

        if response.status_code != 200:
            raise Exception(f"tracker error: {response.status_code}")

        data = bencodepy.decode(response.content)

        peers_binary = data[b'peers']

        peers = []
        for i in range(0, len(peers_binary), 6):
            ip = ".".join(str(b) for b in peers_binary[i:i + 4])
            port = struct.unpack(">H", peers_binary[i + 4:i + 6])[0]
            peers.append(PeerConnection(ip, port, self.peer_id))

        return peers

    def _build_url(self, info_hash: bytes, event):
        """
        builds full tracker url with query parameters

        Args:
            info_hash: sha1 hash of info dictionary
            event: tracker event request type
        """
        params = {
            'info_hash': self.percent_encode_bytes(info_hash),
            'peer_id': self.peer_id,
            'port': str(self.port),
            'uploaded': 0,
            'downloaded': 0,
            'left': self.torrent_file.total_length,
            'compact': 1,
            'event': event
        }

        query = '&'.join(f"{key}={value}" for key, value in params.items())
        return f"{self.torrent_file.announce}?{query}"

    def percent_encode_bytes(self, b):
        """percent encodes a byte string"""
        return ''.join(f'%{byte:02X}' for byte in b)
