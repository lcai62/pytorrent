import time
from typing import Optional


class Block:
    """
    represents a block within a torrent piece

    Attributes:
        piece_index: index of the parent piece
        offset: offset within the parent piece
        length: length of this block in bytes
        is_requested: True if this block has been requested
        is_received: True if this block has been received
        request_time: timestamp of when this block was requested
    """

    def __init__(self, piece_index: int, offset: int, length: int):
        """
        initializes the Block

        Args:
            piece_index: index of the parent piece
            offset: offset within the parent piece
            length: length of this block in bytes
        """
        self.piece_index: int = piece_index
        self.offset: int = offset
        self.length: int = length
        self.is_requested: bool = False
        self.is_received: bool = False
        self.request_time: Optional[bool] = None

    def set_requested(self):
        """marks as requested, sets timestamp"""
        self.is_requested = True
        self.request_time = time.time()

    def reset(self):
        """resets block state"""
        self.is_requested = False
        self.is_received = False
        self.request_time = None
