# piece_manager.py

import hashlib
import math
from typing import Optional, List

from src.torrent_file import TorrentFile

BLOCK_SIZE = 2 ** 16


class PieceManager:
    def __init__(self, torrent_file: TorrentFile, block_size=BLOCK_SIZE):
        self.torrent_file = torrent_file
        self.block_size = block_size

        self._hashes = [
            torrent_file.pieces[i:i + 20]
            for i in range(0, len(torrent_file.pieces), 20)
        ]

        self._lengths = self._calculate_pieces_lengths(
            torrent_file.length, torrent_file.piece_length
        )

        self.pieces: list[Piece] = [
            Piece(i, self._hashes[i], self._lengths[i], block_size)
            for i in range(len(self._hashes))
        ]

    def next_request(self, peer_bitmap) -> Optional["Block"]:
        """
        returns next block that this peer can serve
        """
        for piece in self.pieces:
            if piece.is_complete or not peer_bitmap[piece.index]:
                continue
            block = piece.next_block()
            if block is not None:
                return block

        return None

    def block_received(self, piece_index, offset, data):
        self.pieces[piece_index].block_received(offset, data)

    def is_finished(self):
        return all(piece.is_complete for piece in self.pieces)

    def _calculate_pieces_lengths(self, total_length: int, piece_length: int) -> List[int]:
        full, remainder = divmod(total_length, piece_length)
        lengths = [piece_length] * full
        if remainder:
            lengths.append(remainder)
        return lengths


class Piece:
    def __init__(self, index: int, sha1: bytes, length: int, block_size: int):
        self.index = index
        self.sha1 = sha1
        self.length = length
        self.block_size = block_size
        self.is_complete = False

        # slice piece into blocks
        self.blocks: List[Block] = [

            Block(index, offset, min(block_size, length - offset))
            for offset in range(0, length, block_size)

        ]

        self.buffer = bytearray(length)

    def next_block(self) -> Optional["Block"]:
        for block in self.blocks:
            if not block.is_requested and not block.is_received:
                block.is_requested = True
                return block
        return None

    def block_received(self, offset: int, data: bytes):
        # find matching block
        blk = None
        for block in self.blocks:
            if block.offset == offset:
                blk = block
                break

        if blk is None or len(data) != blk.length:
            return

        if blk.is_received:
            return

        blk.data = data
        blk.is_received = True
        self.buffer[offset:offset + len(data)] = data

        # if last block, verify hash
        if all(block.is_received for block in self.blocks):
            if hashlib.sha1(self.buffer).digest() == self.sha1:
                self.is_complete = True

            else:
                # bad hash, redownload
                for block in self.blocks:
                    block.is_requested = block.is_received = False
                    block.data = None
                self.buffer[:] = b'\x00' * self.length


class Block:
    def __init__(self, piece_index, offset, length):
        self.piece_index = piece_index
        self.offset = offset
        self.length = length
        self.data = None
        self.is_requested = False
        self.is_received = False
