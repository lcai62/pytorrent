import hashlib
from typing import List, Optional

from .block import Block
from .storage_manager import PieceStorage


class Piece:
    """
    represents a single piece in the torrent

    Attributes:
        index: the piece index
        sha1: the expected sha1 hash
        length: length of the piece in bytes
        block_size: size of each block within the piece
        is_complete: True if this piece is downloaded and verified
        blocks: List of Block instances in this piece
        piece_storage: PieceStorage instance
        base_offset: the start offset of the piece in the stream

    """

    def __init__(self, index: int, sha1: bytes, length: int, block_size: int, piece_storage: PieceStorage,
                 base_offset: int) -> None:
        """
        initializes
        Attributes:
            index: the piece index
            sha1: the expected sha1 hash
            length: length of the piece in bytes
            block_size: size of each block within the piece
            piece_storage: PieceStorage instance
            base_offset: the start offset of the piece in the stream
        """
        self.index: int = index
        self.sha1: bytes = sha1
        self.length: int = length
        self.block_size: int = block_size
        self.is_complete: bool = False

        self.piece_storage: PieceStorage = piece_storage
        self.base_offset: int = base_offset

        # slice piece into blocks
        self.blocks: List[Block] = [

            Block(index, offset, min(block_size, length - offset))
            for offset in range(0, length, block_size)

        ]

        self._buffer: bytearray = bytearray(length)  # in memory storage for sha1 verification
        self._blocks_received: int = 0  # tracks how many blocks we've received

    def next_block(self) -> Optional[Block]:
        """
        find next unrequested block

        Returns:
            a Block ready for request, or None if none are available
        """
        for block in self.blocks:
            if not block.is_requested and not block.is_received:
                block.set_requested()
                return block
        return None

    def block_received(self, offset: int, data: bytes) -> Optional[bool]:
        """
        verifies a received block

        Args:
            offset: offset within the piece
            data: received block data

        Returns:
            True if the piece is completed and passed verification
            False if block accepted, but piece not complete
            None if block was invalid or already received
        """
        # find matching block
        block = None
        for b in self.blocks:
            if b.offset == offset:
                block = b
                break

        if block is None or len(data) != block.length:
            return

        if block.is_received:
            return

        self.piece_storage.write(self.index, offset, data)

        # store into our buffer
        self._buffer[offset:offset + block.length] = data
        block.is_received = True
        self._blocks_received += 1

        if self._blocks_received == len(self.blocks):  # piece complete
            if hashlib.sha1(self._buffer, usedforsecurity=False).digest() == self.sha1:
                self.is_complete = True
                # free buffer to save space
                self._buffer = bytearray()
                return True
            else:
                # bad hash – reset state
                self.is_complete = False
                self._blocks_received = 0
                for b in self.blocks:
                    b.reset()

        return False
