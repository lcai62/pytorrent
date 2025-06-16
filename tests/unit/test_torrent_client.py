import unittest
from unittest.mock import MagicMock, patch

from src.torrent_client import TorrentClient


class TestTorrentClientInit(unittest.TestCase):
    @patch("src.torrent_client.TorrentFile")
    @patch("src.torrent_client.PieceStorage")
    @patch("src.torrent_client.PieceManager")
    @patch("src.torrent_client.TrackerManager")
    @patch("src.torrent_client._generate_peer_id", return_value="-PC0001-123456abcdef")
    def test_init_with_was_finished_false(self, mock_peer_id, mock_tracker, mock_piece_manager,
                                          mock_storage, mock_torrent_file):
        mock_torrent_file.return_value.total_length = 999
        mock_piece_manager.return_value.pieces = [MagicMock(index=i) for i in range(3)]
        client = TorrentClient("dummy.torrent")

        mock_torrent_file.return_value.parse.assert_called_once()
        mock_tracker.assert_called_once()
        self.assertEqual(client.peer_id, "-PC0001-123456abcdef")
        self.assertEqual(client.download_dir, ".")
        self.assertIsNone(client.peer_manager)
        self.assertEqual(client.num_pieces, 3)
        self.assertFalse(client.paused)
        self.assertIsNotNone(client._paused_cond)
        self.assertIsNone(client.added_on)
        self.assertIsNone(client.completed_on)

    @patch("src.torrent_client.TorrentFile")
    @patch("src.torrent_client.PieceStorage")
    @patch("src.torrent_client.PieceManager")
    @patch("src.torrent_client.TrackerManager")
    def test_init_with_was_finished_true(self, mock_tracker, mock_piece_manager,
                                         mock_storage, mock_torrent_file):
        mock_piece1 = MagicMock()
        mock_piece2 = MagicMock()
        pieces = [mock_piece1, mock_piece2]

        mock_manager = MagicMock()
        mock_manager.pieces = pieces
        mock_manager.downloaded_bytes = 0
        mock_piece_manager.return_value = mock_manager
        mock_torrent_file.return_value.total_length = 2048

        client = TorrentClient("dummy.torrent", peer_id="peer123", download_dir="/path", was_finished=True)

        self.assertEqual(client.peer_id, "peer123")
        for p in pieces:
            self.assertTrue(p.is_complete)
        self.assertEqual(mock_manager.downloaded_bytes, 2048)
