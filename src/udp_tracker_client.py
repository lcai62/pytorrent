import random
import socket
import struct
from typing import List, Tuple
from urllib.parse import urlparse

from .peer_connection import PeerConnection
from .torrent_file import TorrentFile

MAGIC_CONSTANT = 0x41727101980


def _generate_transaction_id():
    return random.randint(0, 0xFFFFFFFF)


class UDPTrackerClient:
    """
    handles communication with bittorrent tracker

    Attributes:
        torrent_file: the parsed TorrentFile object
        peer_id: the local peer's unique identifier
        port: the tcp port used by this client
    """

    def __init__(self, torrent_file: TorrentFile, peer_id: str, tracker_url, port=6881):
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
        self.transaction_id = _generate_transaction_id()

        self.tracker_url = tracker_url

        self.event_map = {'completed': 1, 'started': 2, 'stopped': 3}

    def get_peers(self, event: str) -> Tuple[List[PeerConnection], int]:
        """
        retrieve list of peers from tracker

        Args:
            event: a string representing the tracker event

        Returns:
            list of PeerConnections

        Raises:
            Exception: tracker response is not 200
        """
        if not self.tracker_url.startswith("udp://"):
            raise ValueError("invalid udp tracker")

        # connection request

        parsed = urlparse(self.tracker_url)
        host = parsed.hostname
        port = parsed.port

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3)

        action = 0

        payload = struct.pack(">QLL", MAGIC_CONSTANT, action, self.transaction_id)

        sock.sendto(payload, (host, port))

        # print(f"sending to {host}, {port}")

        data = sock.recv(16)
        # print(data)

        action, transaction_id, connection_id = struct.unpack(">LLQ", data)
        if transaction_id != self.transaction_id:
            raise Exception("transaction id mismatch")

        # announce req

        action = 1
        downloaded = 0
        left = self.torrent_file.total_length
        uploaded = 0
        event = 0 if event is None else self.event_map[event]
        ip = 0
        key = random.randint(0, 0xFFFFFFFF)
        num_want = 0xFFFFFFFF

        payload = struct.pack(">QLL20s20sQQQLLLLH", connection_id, action, self.transaction_id,
                              self.torrent_file.info_hash, self.peer_id.encode(), downloaded, left, uploaded,
                              event, ip, key, num_want, self.port)

        sock.sendto(payload, (host, port))

        data, _ = sock.recvfrom(4096)

        action, transaction_id, interval, num_leechers, num_seeders = struct.unpack(">LLLLL", data[:20])
        peer_data = data[20:]

        peers = []
        for i in range(0, len(peer_data), 6):
            ip = socket.inet_ntoa(peer_data[i:i + 4])
            port = struct.unpack(">H", peer_data[i + 4:i + 6])[0]
            peers.append(PeerConnection(ip, port, self.peer_id))

        return peers, interval
