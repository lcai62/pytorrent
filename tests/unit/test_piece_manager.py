import time
import unittest
from unittest.mock import MagicMock

from bitarray import bitarray

from src.block import Block
from src.piece_manager import PieceManager, _calculate_pieces_lengths, REQUEST_TIMEOUT


class TestPieceManager(unittest.TestCase):
    def setUp(self):
        self.mock_torrent = MagicMock()
        self.mock_torrent.total_length = 1024 * 3
        self.mock_torrent.piece_length = 1024
        self.mock_torrent.pieces = b"x" * 60  # 3 pieces

        self.mock_storage = MagicMock()
        self.manager = PieceManager(self.mock_torrent, self.mock_storage)

    def test_calculate_pieces_lengths(self):
        self.assertEqual(_calculate_pieces_lengths(3072, 1024), [1024, 1024, 1024])
        self.assertEqual(_calculate_pieces_lengths(2500, 1000), [1000, 1000, 500])

    def test_add_have_increases_availability(self):
        self.manager.add_have(1)
        self.assertEqual(self.manager.availability[1], 1)

    def test_add_bitmap(self):
        bitmap = bitarray("101")
        self.manager.add_bitmap(bitmap)
        self.assertEqual(self.manager.availability[0], 1)
        self.assertEqual(self.manager.availability[1], 0)
        self.assertEqual(self.manager.availability[2], 1)

    def test_peer_disconnect(self):
        bitmap = bitarray("111")
        self.manager.add_bitmap(bitmap)
        self.manager.peer_disconnect(bitmap)
        self.assertEqual(self.manager.availability[0], 0)

    def test_peer_disconnect_all_false(self):
        bitmap = bitarray("000")
        self.manager.peer_disconnect(bitmap)
        self.assertEqual(self.manager.availability, {})

    def test_on_choke_resets_blocks(self):
        peer = MagicMock()
        block = MagicMock()
        self.manager.inflight_by_peer[peer] = [block]
        self.manager.on_choke(peer)
        block.reset.assert_called_once()
        self.assertNotIn(peer, self.manager.inflight_by_peer)

    def test_next_request_returns_block(self):
        peer_bitmap = bitarray("111")

        # Disable all pieces
        for piece in self.manager.pieces:
            piece.is_complete = True
            piece.next_block = lambda: None

        # Enable only piece 1
        piece = self.manager.pieces[1]
        piece.is_complete = False
        block = Block(piece_index=1, offset=0, length=16)
        block.is_requested = False
        block.is_received = False
        block.request_time = None
        piece.blocks = [block]
        piece.next_block = lambda: block

        result = self.manager.next_request(peer_bitmap)
        self.assertEqual((result.piece_index, result.offset, result.length),
                         (block.piece_index, block.offset, block.length))

    def test_next_request_none(self):
        peer_bitmap = bitarray("000")
        result = self.manager.next_request(peer_bitmap)
        self.assertIsNone(result)

    def test_next_request_block_is_none(self):
        peer_bitmap = bitarray("111")
        for piece in self.manager.pieces:
            piece.is_complete = False
            piece.next_block = MagicMock(return_value=None)  # forces line 120 to skip return

        result = self.manager.next_request(peer_bitmap)
        self.assertIsNone(result)

    def test_next_request_rarest_first(self):
        peer_bitmap = bitarray("111")
        for i, piece in enumerate(self.manager.pieces):
            piece.is_complete = False
            piece.next_block = MagicMock(return_value=Block(i, 0, 16))
            self.manager.availability[i] = 3 - i

        result = self.manager.next_request_rarest_first(peer_bitmap)
        self.assertIsInstance(result, Block)

    def test_next_request_rarest_first_all_requested(self):
        peer_bitmap = bitarray("111")
        for i, piece in enumerate(self.manager.pieces):
            piece.is_complete = False
            piece.next_block = MagicMock(return_value=None)
            self.manager.availability[i] = i

        result = self.manager.next_request_rarest_first(peer_bitmap)
        self.assertIsNone(result)

    def test_next_request_rarest_first_none(self):
        peer_bitmap = bitarray("000")
        result = self.manager.next_request_rarest_first(peer_bitmap)
        self.assertIsNone(result)

    def test_next_request_rarest_first_fallback_loop(self):
        peer_bitmap = bitarray("111")
        for i, piece in enumerate(self.manager.pieces):
            piece.is_complete = False
            self.manager.availability[i] = 1

            if i == 0:
                piece.next_block = MagicMock(return_value=None)
            else:
                block = Block(i, 0, 16)
                piece.next_block = MagicMock(return_value=block if i == 1 else None)

        block = self.manager.next_request_rarest_first(peer_bitmap)
        self.assertIsInstance(block, Block)
        self.assertEqual(block.piece_index, 1)

    def test_block_received(self):
        piece = self.manager.pieces[0]
        piece.block_received = MagicMock(return_value=True)
        result = self.manager.block_received(0, 0, b"data")
        self.assertTrue(result)
        self.assertEqual(self.manager.downloaded_bytes, len(b"data"))

    def test_block_received_none(self):
        piece = self.manager.pieces[0]
        piece.block_received = MagicMock(return_value=None)
        result = self.manager.block_received(0, 0, b"data")
        self.assertIsNone(result)

    def test_is_finished(self):
        for piece in self.manager.pieces:
            piece.is_complete = True
        self.assertTrue(self.manager.is_finished())
        self.manager.pieces[1].is_complete = False
        self.assertFalse(self.manager.is_finished())

    def test_tick_resets_timed_out_requests(self):
        for piece in self.manager.pieces:
            piece.is_complete = False
            block = Block(piece.index, 0, 16)
            block.is_requested = True
            block.is_received = False
            block.request_time = time.time() - (REQUEST_TIMEOUT + 1)  # Force timeout
            piece.blocks = [block]

        self.manager.tick()

        for piece in self.manager.pieces:
            b = piece.blocks[0]
            self.assertFalse(b.is_requested)
            self.assertIsNone(b.request_time)
