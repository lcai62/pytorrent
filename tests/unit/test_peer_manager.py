import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.peer_manager import PeerManager


class TestPeerManager(unittest.TestCase):
    def setUp(self):
        self.peer1 = MagicMock()
        self.peer2 = MagicMock()
        self.peer3 = MagicMock()

        self.torrent_file = MagicMock()
        self.torrent_file.info_hash = b"fakehash"

        self.piece_manager = MagicMock()
        self.manager = PeerManager([self.peer1, self.peer2], self.torrent_file, self.piece_manager)

    def tearDown(self):
        self.manager.stop_retry_worker()

    def test_connect_success(self):
        self.peer1.connect.return_value = None
        result = self.manager._connect(self.peer1)
        self.assertEqual(result, self.peer1)

    def test_connect_failure(self):
        self.peer1.connect.side_effect = Exception("fail")
        result = self.manager._connect(self.peer1)
        self.assertIsNone(result)
        self.assertIn(self.peer1, self.manager.failed_peers)
        self.assertIn(self.peer1, self.manager.next_retry_time)

    @patch("src.peer_manager.ThreadPoolExecutor")
    @patch("src.peer_manager.as_completed")
    def test_connect_all(self, mock_as_completed, mock_pool):
        future1 = MagicMock()
        future1.result.return_value = self.peer1
        future2 = MagicMock()
        future2.result.return_value = None

        mock_pool.return_value.__enter__.return_value.submit.side_effect = [future1, future2]
        mock_as_completed.return_value = [future1, future2]

        self.manager.connect_all()

        self.assertEqual(self.manager.peers, [self.peer1])

    @patch("src.peer_manager.ThreadPoolExecutor")
    @patch("src.peer_manager.as_completed")
    def test_retry_failed_peers_mixed(self, mock_as_completed, mock_pool):
        # one peer fails, one succeeds
        peer1 = self.peer1
        peer2 = self.peer2
        self.manager.failed_peers = {peer1: 1, peer2: 1}
        self.manager.next_retry_time = {
            peer1: datetime.now() - timedelta(seconds=1),
            peer2: datetime.now() - timedelta(seconds=1),
        }

        future1 = MagicMock()
        future1.result.return_value = peer1
        future2 = MagicMock()
        future2.result.return_value = None

        mock_pool.return_value.__enter__.return_value.submit.side_effect = [future1, future2]
        mock_as_completed.return_value = [future1, future2]

        self.manager.retry_failed_peers()

        self.assertIn(peer1, self.manager.peers)
        self.assertNotIn(peer1, self.manager.failed_peers)
        self.assertNotIn(peer1, self.manager.next_retry_time)

        self.assertIn(peer2, self.manager.failed_peers)
        self.assertIn(peer2, self.manager.next_retry_time)

    def test_retry_failed_peers_nothing_due(self):
        self.manager.failed_peers = {self.peer1: 1}
        self.manager.next_retry_time = {self.peer1: datetime.now() + timedelta(seconds=100)}
        original_peers = list(self.manager.peers)
        self.manager.retry_failed_peers()
        self.assertEqual(self.manager.peers, original_peers)

    def test_add_peer(self):
        self.manager.add_peer(self.peer3)
        self.assertIn(self.peer3, self.manager.peers)

    def test_remove_peer_with_bitmap(self):
        self.peer1.bitmap = "bitmap"
        self.manager.remove_peer(self.peer1)
        self.piece_manager.peer_disconnect.assert_called_once()

    def test_remove_peer_without_bitmap(self):
        self.peer1.bitmap = None
        self.manager.remove_peer(self.peer1)
        self.piece_manager.peer_disconnect.assert_not_called()

    def test_close_all(self):
        self.peer1.bitmap = "bitmap"
        self.peer2.bitmap = None
        self.manager.close_all()
        self.assertEqual(self.manager.peers, [])
        self.assertEqual(self.manager.failed_peers, {})
        self.assertEqual(self.manager.next_retry_time, {})

    def test_start_stop_retry_worker(self):
        self.manager.start_retry_worker()
        self.assertTrue(self.manager._retry_thread.is_alive())
        self.manager.stop_retry_worker()
        self.assertFalse(self.manager._retry_thread.is_alive())

    def test_start_retry_worker_when_already_running(self):
        self.manager._retry_thread = MagicMock()
        self.manager._retry_thread.is_alive.return_value = True
        self.manager.start_retry_worker()
        self.manager._retry_thread.start.assert_not_called()
