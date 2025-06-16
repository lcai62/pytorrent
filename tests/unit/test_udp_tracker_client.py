import socket
import struct
import unittest
from unittest.mock import patch, MagicMock

from src.peer_connection import PeerConnection
from src.udp_tracker_client import UDPTrackerClient


class DummyTorrentFile:
    def __init__(self):
        self.total_length = 1000
        self.info_hash = b"\x01" * 20


class TestUDPTrackerClient(unittest.TestCase):
    def setUp(self):
        self.peer_id = "-PC0001-abcdefghijklm"
        self.tracker_url = "udp://tracker.example.com:80"
        self.torrent_file = DummyTorrentFile()
        self.client = UDPTrackerClient(self.torrent_file, self.peer_id, self.tracker_url)

    @patch("socket.socket")
    def test_get_peers_success(self, mock_socket_class):
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        # mock connection_id response
        transaction_id = self.client.transaction_id
        connection_id = 0x1122334455667788
        conn_resp = struct.pack(">LLQ", 0, transaction_id, connection_id)
        mock_sock.recv.side_effect = [conn_resp]

        # mock announce response
        interval = 1800
        num_leechers = 10
        num_seeders = 5
        peer_ip = socket.inet_aton("127.0.0.1")
        peer_port = struct.pack(">H", 6881)
        peer_data = peer_ip + peer_port
        announce_resp = struct.pack(">LLLLL", 1, transaction_id, interval, num_leechers, num_seeders) + peer_data
        mock_sock.recvfrom.return_value = (announce_resp, ("tracker.example.com", 80))

        peers, returned_interval = self.client.get_peers("started")

        self.assertEqual(returned_interval, interval)
        self.assertEqual(len(peers), 1)
        self.assertIsInstance(peers[0], PeerConnection)
        self.assertEqual(peers[0].ip, "127.0.0.1")
        self.assertEqual(peers[0].port, 6881)

    def test_invalid_tracker_url(self):
        with self.assertRaises(ValueError):
            bad_client = UDPTrackerClient(self.torrent_file, self.peer_id, "http://tracker.example.com:80")
            bad_client.get_peers("started")

    @patch("socket.socket")
    def test_transaction_id_mismatch(self, mock_socket_class):
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        wrong_tid = self.client.transaction_id + 1
        conn_resp = struct.pack(">LLQ", 0, wrong_tid, 0x12345678)
        mock_sock.recv.side_effect = [conn_resp]

        with self.assertRaises(Exception) as cm:
            self.client.get_peers("started")

        self.assertIn("transaction id mismatch", str(cm.exception))
