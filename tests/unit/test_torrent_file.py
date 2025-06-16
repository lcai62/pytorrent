import hashlib
import unittest
from unittest.mock import patch, mock_open

from src.torrent_file import TorrentFile


class TestTorrentFile(unittest.TestCase):

    def setUp(self):
        self.single_file_dict = {
            'announce': 'http://tracker.example.com/announce',
            'info': {
                'name': 'testfile.txt',
                'length': 12345,
                'piece length': 512,
                'pieces': b'12345678901234567890'
            }
        }
        self.multi_file_dict = {
            'announce': 'http://tracker.example.com/announce',
            'info': {
                'name': 'testfolder',
                'piece length': 512,
                'pieces': b'12345678901234567890',
                'files': [
                    {'length': 1000, 'path': ['file1.txt']},
                    {'length': 2000, 'path': ['file2.txt']}
                ]
            },
            'announce-list': [['http://tracker.example.com/announce']]
        }

    @patch("builtins.open", new_callable=mock_open, read_data=b'fake_bencoded_data')
    @patch("src.torrent_file.Bencode.bencode_decode")
    @patch("src.torrent_file.bencodepy.encode")
    def test_parse_single_file(self, mock_encode, mock_decode, mock_file):
        mock_decode.return_value = self.single_file_dict
        mock_encode.return_value = b'encoded_info'

        tf = TorrentFile("dummy.torrent")
        tf.parse()

        self.assertEqual(tf.announce, 'http://tracker.example.com/announce')
        self.assertEqual(tf.name, 'testfile.txt')
        self.assertEqual(tf.total_length, 12345)
        self.assertFalse(tf.is_multifile)
        self.assertEqual(tf.files[0]["path"], ['testfile.txt'])
        self.assertEqual(tf.info_hash, hashlib.sha1(b'encoded_info', usedforsecurity=False).digest())

    @patch("builtins.open", new_callable=mock_open, read_data=b'fake_bencoded_data')
    @patch("src.torrent_file.Bencode.bencode_decode")
    @patch("src.torrent_file.bencodepy.encode")
    def test_parse_multi_file(self, mock_encode, mock_decode, mock_file):
        mock_decode.return_value = self.multi_file_dict
        mock_encode.return_value = b'encoded_info'

        tf = TorrentFile("dummy.torrent")
        tf.parse()

        self.assertTrue(tf.is_multifile)
        self.assertEqual(len(tf.files), 2)
        self.assertEqual(tf.total_length, 3000)
        self.assertEqual(tf.announce_list, [['http://tracker.example.com/announce']])

    def test_file_layout(self):
        tf = TorrentFile("dummy.torrent")
        tf.files = [
            {"length": 100, "path": ["a"]},
            {"length": 200, "path": ["b"]}
        ]
        layout = list(tf.file_layout())

        self.assertEqual(layout[0], (["a"], 100, 0))
        self.assertEqual(layout[1], (["b"], 200, 100))
