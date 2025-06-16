import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.storage_manager import PieceStorage


class TestPieceStorage(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.mock_torrent = MagicMock()
        self.mock_torrent.name = "testfile.txt"
        self.mock_torrent.total_length = 1024
        self.mock_torrent.piece_length = 512
        self.mock_torrent.is_multifile = False
        self.storage = PieceStorage(self.mock_torrent, self.tmp_dir.name)

    def tearDown(self):
        try:
            self.storage.cleanup()
        except Exception:
            pass
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_write_and_read(self):
        data = b"abcd" * 10
        self.storage.write(0, 0, data)
        result = self.storage.read(0, len(data))
        self.assertEqual(result, data)

    def test_switch_to_seeding_single_file(self):
        self.storage.write(0, 0, b"seedtest")
        self.storage.switch_to_seeding()
        result = self.storage.read(0, 8)
        self.assertEqual(result, b"seedtest")
        self.assertTrue(self.storage._read_only)

    @patch("src.storage_manager.os.makedirs")
    def test_switch_to_seeding_multifile(self, mock_makedirs):
        self.mock_torrent.is_multifile = True
        self.mock_torrent.name = "testfolder"
        self.mock_torrent.file_layout.return_value = [["f1.txt"], 512, 0], [["f2.txt"], 512, 512]
        self.storage = PieceStorage(self.mock_torrent, self.tmp_dir.name)
        self.storage.write(0, 0, b"a" * 512)
        self.storage.write(1, 0, b"b" * 512)
        self.storage.switch_to_seeding()

        f1_path = os.path.join(self.tmp_dir.name, "testfolder", "f1.txt")
        f2_path = os.path.join(self.tmp_dir.name, "testfolder", "f2.txt")

        with open(f1_path, "rb") as f:
            self.assertEqual(f.read(), b"a" * 512)
        with open(f2_path, "rb") as f:
            self.assertEqual(f.read(), b"b" * 512)

    def test_cleanup_handles_exceptions(self):
        self.storage._mmap.close()
        self.storage._fd.close()
        self.storage.cleanup()

    def test_part_file_created_on_init(self):
        part_path = os.path.join(self.tmp_dir.name, "testfile.txt.part")
        self.assertTrue(os.path.exists(part_path))

    def test_part_file_already_exists(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            part_path = os.path.join(tmp_dir, "testfile.txt.part")
            with open(part_path, "wb") as f:
                f.write(b"\x00" * 1024)

            mock_torrent = MagicMock()
            mock_torrent.name = "testfile.txt"
            mock_torrent.total_length = 1024
            mock_torrent.piece_length = 512
            mock_torrent.is_multifile = False

            storage = PieceStorage(mock_torrent, tmp_dir)
            self.assertTrue(os.path.exists(part_path))
            storage.cleanup()
        finally:
            try:
                os.remove(part_path)
                os.rmdir(tmp_dir)
            except Exception:
                pass

    def test_switch_to_seeding_noop_if_already_read_only(self):
        self.storage._read_only = True
        try:
            self.storage.switch_to_seeding()
        except Exception as e:
            self.fail(f"Should not raise exception when already read-only: {e}")

    def test_switch_to_seeding_renames_file(self):
        self.mock_torrent.is_multifile = False
        self.mock_torrent.name = "testfile.txt"
        self.mock_torrent.total_length = 1024
        self.mock_torrent.piece_length = 512

        self.storage.cleanup()
        part_path = os.path.join(self.tmp_dir.name, "testfile.txt.part")
        with open(part_path, "wb") as f:
            f.write(b"x" * 1024)

        self.storage = PieceStorage(self.mock_torrent, self.tmp_dir.name)
        self.assertTrue(os.path.exists(part_path))

        self.storage.switch_to_seeding()

        final_path = os.path.join(self.tmp_dir.name, "testfile.txt")
        self.assertTrue(os.path.exists(final_path))
        with open(final_path, "rb") as f:
            self.assertEqual(f.read(1024), b"x" * 1024)
        self.assertTrue(self.storage._read_only)

    def test_scatter_into_files_executes_all_branches(self):
        self.mock_torrent.is_multifile = True
        self.mock_torrent.name = "multitest"
        layout = [(["a.txt"], 256, 0), (["b.txt"], 768, 256)]
        self.mock_torrent.file_layout.return_value = layout
        self.storage = PieceStorage(self.mock_torrent, self.tmp_dir.name)
        self.storage.write(0, 0, b"x" * 1024)
        self.storage._mmap.flush()
        self.storage._mmap.close()
        self.storage._fd.close()
        self.storage._scatter_into_files()

        a_path = os.path.join(self.tmp_dir.name, "multitest", "a.txt")
        b_path = os.path.join(self.tmp_dir.name, "multitest", "b.txt")

        with open(a_path, "rb") as f:
            self.assertEqual(f.read(), b"x" * 256)
        with open(b_path, "rb") as f:
            self.assertEqual(f.read(), b"x" * 768)

    def test_cleanup_when_already_closed(self):
        try:
            self.storage.cleanup()
            self.storage.cleanup()
        except Exception as e:
            self.fail(f"cleanup should not raise on double call: {e}")

    def test_cleanup_mmap_and_fd_close_exceptions(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            mock_torrent = MagicMock()
            mock_torrent.name = "testfile.txt"
            mock_torrent.total_length = 1024
            mock_torrent.piece_length = 512
            mock_torrent.is_multifile = False

            storage = PieceStorage(mock_torrent, tmp_dir)
            storage._mmap.close()

            class FaultyMmap:
                def close(self): raise RuntimeError("mocked mmap close failure")

            class FaultyFD:
                def close(self): raise RuntimeError("mocked fd close failure")

            storage._mmap = FaultyMmap()
            storage._fd = FaultyFD()

            try:
                storage.cleanup()
            except Exception as e:
                self.fail(f"cleanup should not raise: {e}")
        finally:
            try:
                part_path = os.path.join(tmp_dir, "testfile.txt.part")
                os.remove(part_path)
                os.rmdir(tmp_dir)
            except Exception:
                pass
