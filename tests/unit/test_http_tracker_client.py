import hashlib
import unittest
from unittest.mock import patch, MagicMock

from src.http_tracker_client import HTTPTrackerClient, percent_encode_bytes
from src.peer_connection import PeerConnection


class DummyTorrentFile:
    def __init__(self):
        self.info = {'name': 'testfile', 'length': 1000, 'piece length': 512, 'pieces': b'abc'}
        self.total_length = 1000


class TestHTTPTrackerClient(unittest.TestCase):
    def setUp(self):
        self.torrent_file = DummyTorrentFile()
        self.peer_id = "-PC0001-abcdefghijklm"
        self.tracker_url = "http://tracker.example.com/announce"
        self.client = HTTPTrackerClient(self.torrent_file, self.peer_id, self.tracker_url)

    def test_percent_encode_bytes(self):
        result = percent_encode_bytes(b"abc")
        self.assertEqual(result, "%61%62%63")

    @patch("src.http_tracker_client.requests.get")
    @patch("src.http_tracker_client.bencodepy.decode")
    @patch("src.http_tracker_client.bencodepy.encode")
    def test_get_peers_success(self, mock_encode, mock_decode, mock_get):
        mock_encode.return_value = b"bencoded"
        peers_binary = b"\x7f\x00\x00\x01\x1a\xe1"  # 127.0.0.1:6881
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"mocked"
        mock_get.return_value = mock_response
        mock_decode.return_value = {
            b"interval": 1800,
            b"peers": peers_binary
        }

        peers, interval = self.client.get_peers("started")

        self.assertEqual(interval, 1800)
        self.assertEqual(len(peers), 1)
        self.assertIsInstance(peers[0], PeerConnection)
        self.assertEqual(peers[0].ip, "127.0.0.1")
        self.assertEqual(peers[0].port, 6881)

    @patch("src.http_tracker_client.requests.get")
    @patch("src.http_tracker_client.bencodepy.encode")
    def test_get_peers_failure(self, mock_encode, mock_get):
        mock_encode.return_value = b"bencoded"
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        with self.assertRaises(Exception) as context:
            self.client.get_peers("started")

        self.assertIn("tracker error", str(context.exception))

    def test_build_url(self):
        info_hash = hashlib.sha1(b"info").digest()
        url = self.client._build_url(info_hash, "started")
        self.assertIn("info_hash=", url)
        self.assertIn("peer_id=-PC0001-abcdefghijklm", url)
        self.assertIn("event=started", url)
        self.assertTrue(url.startswith("http://tracker.example.com/announce?"))
