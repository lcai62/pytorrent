import hashlib
import struct

import bencodepy
import requests
from peer_connection import PeerConnection

from torrent_file import TorrentFile


class TrackerClient:
    """
    handles retrieving tracker information
    """

    def __init__(self, torrent_file: TorrentFile, peer_id: str, port=6881):
        self.torrent_file = torrent_file
        self.peer_id = peer_id
        self.port = port

    def get_peers(self):
        info_bencoded = bencodepy.encode(self.torrent_file.info)
        info_hash = hashlib.sha1(info_bencoded).digest()

        url = self._build_url(info_hash)

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

    def _build_url(self, info_hash: bytes):
        params = {
            'info_hash': self.percent_encode_bytes(info_hash),
            'peer_id': self.peer_id,
            'port': str(self.port),
            'uploaded': 0,
            'downloaded': 0,
            'left': 0,
            'compact': 1,
        }

        query = '&'.join(f"{key}={value}" for key, value in params.items())
        return f"{self.torrent_file.announce}?{query}"

    def percent_encode_bytes(self, b):
        return ''.join(f'%{byte:02X}' for byte in b)

