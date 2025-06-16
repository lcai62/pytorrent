import hashlib
import unittest
from unittest.mock import Mock

from src.block import Block
from src.piece import Piece


class TestPiece(unittest.TestCase):
    def setUp(self):
        self.index = 0
        self.length = 32768
        self.block_size = 16384
        self.base_offset = 0
        self.sha1 = hashlib.sha1(b'a' * 16384 + b'b' * 16384).digest()

        self.mock_storage = Mock()
        self.piece = Piece(
            index=self.index,
            sha1=self.sha1,
            length=self.length,
            block_size=self.block_size,
            piece_storage=self.mock_storage,
            base_offset=self.base_offset
        )

    def test_initial_state(self):
        self.assertEqual(len(self.piece.blocks), 2)
        self.assertFalse(self.piece.is_complete)

    def test_next_block_returns_unrequested(self):
        block = self.piece.next_block()
        self.assertIsInstance(block, Block)
        self.assertTrue(block.is_requested)

    def test_next_block_returns_none_when_all_requested_or_received(self):
        for block in self.piece.blocks:
            block.is_requested = True
        self.assertIsNone(self.piece.next_block())

    def test_block_received_successful_completion(self):
        data1 = b'a' * 16384
        data2 = b'b' * 16384
        result1 = self.piece.block_received(0, data1)
        result2 = self.piece.block_received(16384, data2)
        self.assertFalse(result1)
        self.assertTrue(result2)
        self.assertTrue(self.piece.is_complete)

    def test_block_received_rejects_wrong_length(self):
        result = self.piece.block_received(0, b'too short')
        self.assertIsNone(result)
        self.assertEqual(self.piece._blocks_received, 0)

    def test_block_received_rejects_already_received(self):
        block = self.piece.blocks[0]
        block.is_received = True
        result = self.piece.block_received(block.offset, b'a' * block.length)
        self.assertIsNone(result)

    def test_block_received_resets_on_bad_hash(self):
        # tamper with data so that hash will fail
        self.piece.block_received(0, b'x' * 16384)
        result = self.piece.block_received(16384, b'y' * 16384)
        self.assertFalse(result)
        self.assertFalse(self.piece.is_complete)
        self.assertEqual(self.piece._blocks_received, 0)
        self.assertTrue(all(not b.is_received for b in self.piece.blocks))

    def test_block_received_no_matching_block(self):
        bad_offset = 99999
        result = self.piece.block_received(bad_offset, b'a' * self.block_size)
        self.assertIsNone(result)
