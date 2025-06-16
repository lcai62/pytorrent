import concurrent.futures
import unittest
from concurrent.futures import Future
from unittest.mock import MagicMock, patch

from src.peer_connection import PeerConnection
from src.torrent_file import TorrentFile
from src.tracker_manager import TrackerManager


class TestTrackerManager(unittest.TestCase):
    def setUp(self):
        self.torrent_file = MagicMock(spec=TorrentFile)
        self.torrent_file.announce = "http://tracker.example.com/announce"
        self.torrent_file.announce_list = [["http://tracker2.com/announce"], ["udp://tracker3.com:6969"]]
        self.torrent_file.pieces = [b'x'] * 3
        self.peer_id = "-PC0001-testid"

    @patch("src.tracker_manager.UDPTrackerClient")
    @patch("src.tracker_manager.HTTPTrackerClient")
    def test_init_tracker_manager(self, mock_http_client, mock_udp_client):
        mock_http_client.return_value.tracker_url = "http://mocked"
        mock_udp_client.return_value.tracker_url = "udp://mocked"
        mgr = TrackerManager(self.torrent_file, self.peer_id)
        self.assertEqual(len(mgr.trackers), 3)

    def test_no_announce_list(self):
        self.torrent_file.announce_list = None
        with patch("src.tracker_manager.HTTPTrackerClient") as mock_http_client:
            mock_http_client.return_value.tracker_url = "http://mocked"
            mgr = TrackerManager(self.torrent_file, self.peer_id)
            self.assertEqual(len(mgr.trackers), 1)

    def test_unsupported_tracker_scheme(self):
        self.torrent_file.announce_list = [["ftp://tracker.bad"]]
        with patch("src.tracker_manager.HTTPTrackerClient") as mock_http_client:
            mock_http_client.return_value.tracker_url = "http://mocked"
            mgr = TrackerManager(self.torrent_file, self.peer_id)
            self.assertEqual(len(mgr.trackers), 1)  # only the original HTTP one

    @patch("src.tracker_manager.ThreadPoolExecutor")
    def test_get_all_peers_success(self, mock_pool):
        mock_tracker = MagicMock()
        mock_tracker.client.get_peers.return_value = (
            [self._fake_peer(True, ip_suffix="1"), self._fake_peer(False, ip_suffix="2")],
            900
        )
        mock_tracker.client.tracker_url = "http://example.com"

        manager = TrackerManager(self.torrent_file, self.peer_id)
        manager.trackers = [mock_tracker]

        future = concurrent.futures.Future()
        future.set_result(mock_tracker.client.get_peers("started"))

        executor = MagicMock()
        executor.submit.return_value = future
        mock_pool.return_value.__enter__.return_value = executor

        peers, interval = manager.get_all_peers("started")

        self.assertEqual(interval, 900)
        self.assertEqual(len(peers), 2)

    @patch("src.tracker_manager.ThreadPoolExecutor")
    def test_get_all_peers_with_exception(self, mock_pool):
        mock_tracker = MagicMock()
        mock_tracker.client.tracker_url = "http://badtracker.com"
        mock_tracker.client.get_peers.side_effect = Exception("failed")

        manager = TrackerManager(self.torrent_file, self.peer_id)
        manager.trackers = [mock_tracker]

        future = concurrent.futures.Future()
        future.set_exception(Exception("failed"))

        executor = MagicMock()
        executor.submit.return_value = future
        mock_pool.return_value.__enter__.return_value = executor

        peers, interval = manager.get_all_peers("started")

        self.assertEqual(interval, 1800)
        self.assertEqual(len(peers), 0)
        self.assertEqual(manager.trackers[0].last_status, "error")

    @patch("src.tracker_manager.UDPTrackerClient")
    @patch("src.tracker_manager.HTTPTrackerClient")
    def test_get_all_peers_duplicate_peer_skipped(self, mock_http_client, mock_udp_client):
        mock_tracker = MagicMock()
        peer = self._fake_peer(True, ip_suffix="1", port=6881)
        mock_tracker.client.tracker_url = "http://example.com"
        mock_tracker.client.get_peers.return_value = ([peer, peer], 900)

        manager = TrackerManager(self.torrent_file, self.peer_id)
        manager.trackers = [mock_tracker]

        future = Future()
        future.set_result(([peer, peer], 900))

        with patch("src.tracker_manager.ThreadPoolExecutor") as mock_executor:
            mock_executor.return_value.__enter__.return_value.submit.return_value = future
            mock_executor.return_value.__enter__.return_value.__iter__.return_value = iter([future])

            peers, interval = manager.get_all_peers("started")
            self.assertEqual(len(peers), 1)
            self.assertEqual(interval, 900)

    def _fake_peer(self, complete, ip_suffix="1", port=6881):
        peer = MagicMock(spec=PeerConnection)
        peer.ip = f"127.0.0.{ip_suffix}"
        peer.port = port
        peer.bitmap = MagicMock()
        peer.bitmap.count.return_value = 3 if complete else 1
        return peer
