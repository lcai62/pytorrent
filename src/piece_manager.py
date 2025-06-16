# piece_manager.py

import random
import time
from collections import Counter, defaultdict
from typing import Optional, List

from bitarray import bitarray

from .block import Block
from .peer_connection import PeerConnection
from .piece import Piece
from .storage_manager import PieceStorage
from .torrent_file import TorrentFile

BLOCK_SIZE = 1 << 14
REQUEST_TIMEOUT = 10


def _calculate_pieces_lengths(total_length: int, piece_length: int) -> List[int]:
    full, remainder = divmod(total_length, piece_length)
    lengths = [piece_length] * full
    if remainder:
        lengths.append(remainder)
    return lengths


class PieceManager:
    """
    manages pieces, blocks, and download state in a bittorrent session

    Attributes:
        torrent_file: instance of TorrentFile object
        block_size: size of individual blocks
        piece_storage: piece storage manager
        pieces: list of Piece objects representing the torrent pieces
        availability: counter tracking how many peers have each piece
        inflight_by_peer: maps each PeerConnection to the blocks currently in-flight
        downloaded_bytes: total number of bytes downloaded
    """

    def __init__(self, torrent_file: TorrentFile, piece_storage: PieceStorage, block_size: int = BLOCK_SIZE) -> None:
        """
        initializes a PieceManager

        Args:
            torrent_file: instance of TorrentFile object
            block_size: size of individual blocks
            piece_storage: piece storage manager
        """
        self.torrent_file = torrent_file
        self.block_size = block_size

        self.piece_storage = piece_storage

        self._hashes = [
            torrent_file.pieces[i:i + 20]
            for i in range(0, len(torrent_file.pieces), 20)
        ]

        self._lengths = _calculate_pieces_lengths(
            torrent_file.total_length, torrent_file.piece_length
        )

        self.pieces: list[Piece] = [
            Piece(i, self._hashes[i], self._lengths[i], block_size, self.piece_storage,
                  base_offset=i * torrent_file.piece_length)
            for i in range(len(self._hashes))
        ]

        self.availability = Counter()

        self.inflight_by_peer: dict[PeerConnection, List[Block]] = defaultdict(list)

        self.downloaded_bytes = 0

    def add_have(self, index: int) -> None:
        """
        gets called for every "have", updates piece availability
        """
        self.availability[index] += 1

    def add_bitmap(self, bitmap: bitarray) -> None:
        """
        called for initial bitmap for each peer, updates availability from full bitmap
        """
        for idx, have in enumerate(bitmap):
            if have:
                self.availability[idx] += 1

    def peer_disconnect(self, bitmap: bitarray) -> None:
        """
        called when peer disconnects, updates availability from last known bitmap
        """
        for idx, have in enumerate(bitmap):
            if have:
                self.availability[idx] = max(0, self.availability[idx] - 1)

    def on_choke(self, peer: PeerConnection) -> None:
        """
        called when peer chokes this client, handles state reset
        """
        for block in self.inflight_by_peer.pop(peer, []):
            block.reset()

    def next_request(self, peer_bitmap: bitarray) -> Optional[Block]:
        """
        returns next block that can be requested from a peer

        Args:
            peer_bitmap: bitmap of corresponding peer

        Returns:
            Block instance ready to be requested, or None of no blocks are available
        """
        for piece in self.pieces:
            if piece.is_complete or not peer_bitmap[piece.index]:
                continue
            block = piece.next_block()
            if block is not None:
                return block

        return None

    def next_request_rarest_first(self, peer_bitmap: bitarray) -> Optional[Block]:
        """
        returns next block that can be requested from a peer
        follows the rarest piece first algorithm

        Args:
            peer_bitmap: bitmap of corresponding peer

        Returns:
            Block instance ready to be requested, or None of no blocks are available
        """
        choices = [
            piece for piece in self.pieces
            if (not piece.is_complete) and peer_bitmap[piece.index]
        ]
        if not choices:
            return None

        # find the lowest avail
        min_avail = min(self.availability.get(piece.index, 0) for piece in choices)

        rarest = [
            piece for piece in choices if self.availability.get(piece.index, 0) == min_avail
        ]

        random.shuffle(rarest)
        for piece in rarest:
            block = piece.next_block()
            if block:
                return block

        # every rare piece is requested already
        for piece in choices:
            block = piece.next_block()
            if block:
                return block

        return None

    def block_received(self, piece_index: int, offset: int, data: bytes) -> Optional[bool]:
        """
        called when a block is received, updates state

        Args:
            piece_index: index of block containing the block
            offset: offset of block in the piece
            data: the block data

        Returns:
            True if the piece is completed and passed verification
            False if block accepted, but piece not complete
            None if block was invalid or already received
        """
        result = self.pieces[piece_index].block_received(offset, data)
        if result in (True, False):
            self.downloaded_bytes += len(data)

        return result

    def is_finished(self) -> bool:
        """
        checks if all pieces have been downloaded

        Returns:
            True if all pieces are downloaded, False otherwise.
        """
        return all(piece.is_complete for piece in self.pieces)

    def tick(self) -> None:
        """resets timed-out requests"""
        now = time.time()
        for piece in self.pieces:
            if piece.is_complete:
                continue
            for block in piece.blocks:
                if block.is_requested and not block.is_received:
                    if block.request_time is not None and (now - block.request_time >= REQUEST_TIMEOUT):
                        block.is_requested = False
                        block.request_time = None
