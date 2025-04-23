import hashlib

import bencodepy

from bencode import Bencode


class TorrentFile:
    """
    for single file downloads
    """

    def __init__(self, path):
        self.path = path
        self.raw_data = None
        self.metadata = None
        self.info = None
        self.info_hash = None
        self.announce = None
        self.name = None
        self.piece_length = None
        self.pieces = None
        self.length = None

    def parse(self):
        with open(self.path, 'rb') as f:
            self.raw_data = f.read()

        self.metadata = Bencode.bencode_decode(self.raw_data)
        self.info = self.metadata['info']
        self.announce = self.metadata['announce']
        self.name = self.info['name']
        self.piece_length = self.info['piece length']
        self.pieces = self.info['pieces']
        self.length = self.info['length']

        bencoded_info = bencodepy.encode(self.info)
        self.info_hash = hashlib.sha1(bencoded_info).digest()

