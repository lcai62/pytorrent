import unittest

from src.bencode import Bencode


class TestBencodeDecode(unittest.TestCase):
    def test_integer(self):
        self.assertEqual(Bencode.bencode_decode(b'i42e'), 42)
        self.assertEqual(Bencode.bencode_decode(b'i-15e'), -15)

    def test_string(self):
        self.assertEqual(Bencode.bencode_decode(b'4:spam'), 'spam')
        self.assertEqual(Bencode.bencode_decode(b'0:'), '')

    def test_list(self):
        self.assertEqual(Bencode.bencode_decode(b'l4:spam4:eggse'), ['spam', 'eggs'])
        self.assertEqual(Bencode.bencode_decode(b'le'), [])

    def test_dictionary(self):
        self.assertEqual(
            Bencode.bencode_decode(b'd3:cow3:moo4:spam4:eggse'),
            {'cow': 'moo', 'spam': 'eggs'}
        )
        self.assertEqual(Bencode.bencode_decode(b'de'), {})

    def test_nested_structures(self):
        data = b'd4:listl5:apple6:bananai42ee3:numi7ee'
        self.assertEqual(
            Bencode.bencode_decode(data),
            {'list': ['apple', 'banana', 42], 'num': 7}
        )

    def test_binary_string(self):
        raw = bytes([0xff, 0xfe, 0xfd])
        encoded = b'3:' + raw
        self.assertEqual(Bencode.bencode_decode(encoded), raw)

    def test_extra_data_raises(self):
        with self.assertRaises(ValueError) as cm:
            Bencode.bencode_decode(b'i1eextra')
        self.assertIn("Extra data", str(cm.exception))

    def test_invalid_token(self):
        with self.assertRaises(ValueError):
            Bencode.bencode_decode(b'z4:aaaa')

    def test_incomplete_integer(self):
        with self.assertRaises(ValueError):
            Bencode.bencode_decode(b'i42')

    def test_invalid_string_length(self):
        with self.assertRaises(ValueError):
            Bencode.bencode_decode(b'9999:ab')

    def test_incomplete_list(self):
        with self.assertRaises(ValueError):
            Bencode.bencode_decode(b'l4:aaaa')

    def test_incomplete_dict(self):
        with self.assertRaises(ValueError):
            Bencode.bencode_decode(b'd3:key4:val')
