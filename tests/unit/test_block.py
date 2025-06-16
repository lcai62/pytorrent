import unittest

from src.block import Block


class TestBlock(unittest.TestCase):
    def test_initial_state(self):
        block = Block(piece_index=0, offset=0, length=16384)
        self.assertFalse(block.is_requested)
        self.assertFalse(block.is_received)
        self.assertIsNone(block.request_time)

    def test_set_requested(self):
        block = Block(0, 0, 16384)
        block.set_requested()
        self.assertTrue(block.is_requested)
        self.assertIsNotNone(block.request_time)

    def test_reset(self):
        block = Block(0, 0, 16384)
        block.set_requested()
        block.reset()
        self.assertFalse(block.is_requested)
        self.assertFalse(block.is_received)
        self.assertIsNone(block.request_time)
