import hashlib
from typing import List, Optional, Dict, Generator, Tuple

import bencodepy

from .bencode import Bencode


class TorrentFile:
    """
    represents a parsed .torrent file for single or multi file downloads

    Attributes:
        path: file system path to the .torrent file
        raw_data: raw binary content of .torrent file
        metadata: decoded metadata dictionary
        info: decoded metadata info dictionary
        info_hash: sha1 hash of encoded info dictionary
        announce: the tracker url
        name: torrent name
        piece_length: length of each piece in bytes
        pieces: concatenated sha1 hashes of each piece
        total_length: total length of all files combined
        files: list of file dictionaries, each has 'length' and 'path'
        is_multifile: True if torrent contains multiple files, false otherwise
    """

    def __init__(self, path):
        """
        initializes a TorrentFile

        Args:
            path: system path to the .torrent file
        """

        self.path: str = path
        self.raw_data: Optional[bytes] = None
        self.metadata: Optional[Dict] = None
        self.info: Optional[Dict] = None
        self.info_hash: Optional[bytes] = None
        self.announce: Optional[str] = None
        self.name: Optional[str] = None
        self.piece_length: Optional[int] = None
        self.pieces: Optional[bytes] = None
        self.total_length: Optional[int] = None

        self.files: Optional[List[dict]] = None
        self.is_multifile: bool = False

        self.announce_list: Optional[List[List[str]]] = None

    def parse(self):
        """
        parses the .torrent file and populates class attributes

        Raises:
            FileNotFoundError: if the provided path does not exist
            KeyError: if some fields in the torrent file are missing
        """
        with open(self.path, 'rb') as f:
            self.raw_data = f.read()

        self.metadata = Bencode.bencode_decode(self.raw_data)
        self.info = self.metadata['info']
        self.announce = self.metadata['announce']
        self.name = self.info['name']
        self.piece_length = self.info['piece length']
        self.pieces = self.info['pieces']

        bencoded_info = bencodepy.encode(self.info)
        self.info_hash = hashlib.sha1(bencoded_info, usedforsecurity=False).digest()

        if "files" in self.info:
            self.is_multifile = True
            self.files = self.info["files"]
            self.total_length = sum(file["length"] for file in self.files)
        else:
            self.files = [{"length": self.info["length"],
                           "path": [self.name]
                           }]
            self.total_length = self.info["length"]

        if 'announce-list' in self.metadata:
            self.announce_list = self.metadata['announce-list']

    def file_layout(self) -> Generator[Tuple[List[str], int, int], None, None]:
        """
        return iterable of tuples

        Yields:
            tuples of (path, length, start offset) for each file
                - path: file path
                - length: file length in bytes
                - start_offset: byte offset in global torrent stream
        """
        offset = 0
        for file in self.files:
            yield file["path"], file["length"], offset
            offset += file["length"]
