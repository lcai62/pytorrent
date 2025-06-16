import hashlib
import struct
import time
import unittest
from unittest.mock import MagicMock, patch

import bitarray

from src.peer_connection import PeerConnection, PROTOCOL_STRING, HANDSHAKE_LEN


class TestPeerConnection(unittest.TestCase):
    def setUp(self):
        self.peer_id = b'-PC0001-abcdefghijkl'
        self.info_hash = hashlib.sha1(b"dummy_info").digest()
        reserved = b'\x00' * 8
        self.fake_handshake = (
                bytes([len(PROTOCOL_STRING)]) +
                PROTOCOL_STRING +
                reserved +
                self.info_hash +
                self.peer_id
        )

    @patch("socket.socket")
    def test_connect_success(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc._recv_exact = lambda n, timeout: self.fake_handshake
        pc.connect(self.info_hash)
        self.assertTrue(pc.active)
        self.assertEqual(pc.remote_id, self.peer_id)

    def test_close_socket(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc.sock = MagicMock()
        pc.active = True
        pc.close()
        pc.sock.close.assert_called_once()
        self.assertFalse(pc.active)

    def test_close_without_socket(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc.sock = None
        pc.close()
        self.assertFalse(pc.active)

    def test_close_socket_raises_exception(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        mock_sock = MagicMock()
        mock_sock.close.side_effect = Exception("mock error")
        pc.sock = mock_sock
        pc.active = True

        with patch("builtins.print") as mock_print:
            pc.close()
            mock_print.assert_called_once()
            self.assertFalse(pc.active)

    def test_safe_send_success(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        mock_sock = MagicMock()
        mock_sock.send.side_effect = lambda b: len(b)
        pc.sock = mock_sock
        result = pc._safe_send(b"hello")
        self.assertTrue(result)

    def test_safe_send_failure(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        mock_sock = MagicMock()
        mock_sock.send.side_effect = BrokenPipeError
        pc.sock = mock_sock
        result = pc._safe_send(b"hello")
        self.assertFalse(result)
        self.assertFalse(pc.active)

    def test_validate_handshake_success(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc._validate_handshake(self.fake_handshake, self.info_hash)
        self.assertEqual(pc.remote_id, self.peer_id)

    def test_validate_handshake_failure(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        with self.assertRaises(ConnectionError):
            pc._validate_handshake(b"short", self.info_hash)

    def test_validate_handshake_protocol_string_mismatch(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)

        bad_proto = (
                bytes([len(PROTOCOL_STRING)]) +
                b"BadProtocol" +  # wrong protocol string
                b'\x00' * 8 +
                self.info_hash +
                self.peer_id
        )

        bad_proto = bad_proto.ljust(HANDSHAKE_LEN, b'\x00')

        with self.assertRaises(ConnectionError) as cm:
            pc._validate_handshake(bad_proto, self.info_hash)

        self.assertIn("protocol string mismatch", str(cm.exception))

    def test_validate_handshake_info_hash_mismatch(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)

        # Create valid-looking handshake with incorrect info hash
        wrong_info_hash = hashlib.sha1(b"wrong").digest()
        valid_proto = (
                bytes([len(PROTOCOL_STRING)]) +
                PROTOCOL_STRING +
                b'\x00' * 8 +
                wrong_info_hash +  # wrong hash here
                self.peer_id
        )

        with self.assertRaises(ConnectionError) as cm:
            pc._validate_handshake(valid_proto, self.info_hash)

        self.assertIn("info hash wrong", str(cm.exception))

    def test_send_messages(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc.sock = MagicMock()
        pc._safe_send = MagicMock(return_value=True)
        self.assertTrue(pc.send_interested())
        self.assertTrue(pc.send_choke())
        self.assertTrue(pc.send_unchoke())
        self.assertTrue(pc.send_have(5))
        self.assertTrue(pc.send_piece(1, 0, b"abc"))
        self.assertTrue(pc.send_bitfield(b"\xFF"))

    def test_send_request(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc.active = True
        pc._inflight = 0
        pc._safe_send = MagicMock(return_value=True)
        self.assertTrue(pc.send_request(1, 0, 1024))
        self.assertEqual(pc._inflight, 1)

    def test_send_request_blocked(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc.active = False
        result = pc.send_request(1, 0, 1024)
        self.assertFalse(result)

    def test_send_request_safe_send_false(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc.active = True
        pc._inflight = 0
        pc._safe_send = MagicMock(return_value=False)
        result = pc.send_request(1, 0, 1024)
        self.assertFalse(result)

    def test_recv_message_piece_and_choke(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc.sock = MagicMock()
        pc.active = True

        # piece message
        msg = struct.pack(">I", 5) + struct.pack("B", 7) + b"data"
        pc.sock.recv = MagicMock(return_value=msg)
        pc._recv_buffer = bytearray()
        pc._bytes_needed = None
        result = pc.recv_message()
        self.assertEqual(result['id'], 7)

        # choke message
        msg = struct.pack(">I", 1) + struct.pack("B", 0)
        pc.sock.recv = MagicMock(return_value=msg)
        pc._recv_buffer = bytearray()
        pc._bytes_needed = None
        result = pc.recv_message()
        self.assertEqual(result['id'], 0)

    def test_recv_message_none(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc.active = False
        self.assertIsNone(pc.recv_message())

    def test_recv_message_blocking_io_error(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc.sock = MagicMock()
        pc.active = True
        pc.sock.recv.side_effect = BlockingIOError

        pc._parse_one = MagicMock(return_value=None)
        result = pc.recv_message()
        self.assertIsNone(result)

    def test_recv_message_socket_closed(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc.sock = MagicMock()
        pc.active = True
        pc.sock.recv.return_value = b""

        with self.assertRaises(ConnectionError):
            pc.recv_message()

    def test_parse_one(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc._recv_buffer = bytearray(struct.pack(">I", 0))
        result = pc._parse_one()
        self.assertEqual(result, {"type": "keep-alive"})

    def test_parse_one_buffer_too_short(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc._bytes_needed = None
        pc._recv_buffer = bytearray(b"\x00\x00\x00")
        result = pc._parse_one()
        self.assertIsNone(result)

    def test_parse_one_incomplete_payload(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc._recv_buffer = bytearray(struct.pack(">I", 5))
        pc._recv_buffer += b"\x07"
        result = pc._parse_one()
        self.assertIsNone(result)

        result = pc._parse_one()
        self.assertIsNone(result)

    def test_recv_exact(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"ab", b"cd"]
        pc.sock = mock_sock
        result = pc._recv_exact(4, 1.0)
        self.assertEqual(result, b"abcd")

    def test_recv_exact_socket_closed(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b''
        pc.sock = mock_sock

        with self.assertRaises(ConnectionError) as cm:
            pc._recv_exact(4, 1.0)

        self.assertIn("Socket closed", str(cm.exception))

    def test_ensure_bitmap(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc.ensure_bitmap(10)
        self.assertEqual(len(pc.bitmap), 10)
        pc.ensure_bitmap(20)
        self.assertEqual(len(pc.bitmap), 20)

    def test_ensure_bitmap_extend(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc.bitmap = bitarray.bitarray(5)
        pc.bitmap.setall(0)
        pc.ensure_bitmap(10)
        self.assertEqual(len(pc.bitmap), 10)

    def test_record_download_and_upload(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc.record_download(100)
        pc.record_upload(50)
        self.assertGreaterEqual(pc.total_downloaded, 100)
        self.assertGreaterEqual(pc.total_uploaded, 50)

    def test_down_up_speed_bps(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        now = time.time()
        pc._rates = [(now - 5, 100, 50), (now, 200, 100)]
        self.assertGreaterEqual(pc.down_speed_bps(), 0)
        self.assertGreaterEqual(pc.up_speed_bps(), 0)

    def test_down_speed_bps_empty_rates(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc._rates = []
        self.assertEqual(pc.down_speed_bps(), 0.0)

    def test_down_speed_bps_less_than_two_rates(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc._rates = [(time.time(), 100, 0)]
        self.assertEqual(pc.down_speed_bps(), 0.0)

    def test_down_speed_bps_elapsed_less_than_2s(self):
        now = time.time()
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc._rates = [(now - 1, 100, 0), (now, 200, 0)]
        self.assertEqual(pc.down_speed_bps(), 0.0)

    def test_up_speed_bps_empty_rates(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc._rates = []
        self.assertEqual(pc.up_speed_bps(), 0.0)

    def test_trim_samples(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        now = time.time()
        pc._rates = [(now - 15, 100, 100), (now - 5, 50, 50)]
        pc.trim_samples(now)
        self.assertEqual(len(pc._rates), 1)

    def test_rates_property(self):
        pc = PeerConnection("127.0.0.1", 6881, self.peer_id)
        pc._rates = [(time.time(), 100, 100)]
        self.assertEqual(pc.rates, pc._rates)
