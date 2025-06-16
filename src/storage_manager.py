import mmap
import os
import pathlib
import shutil

from .torrent_file import TorrentFile


class PieceStorage:
    """
    handles all disk accesses for a torrent

    Attributes:
        torrent_file: associated TorrentFile object
        download_dir: directory where downloaded files go
        output_dir: sub-folder where downloaded files go for multi-torrents
        part_path: path to the temporary .part during downloading
        final_path: final path for single file torrents, None for multi-file
        _fd: open file descriptor
        _mmap: memory mapped file
        _read_only: True if mmap is in read only mode
    """

    def __init__(self, torrent_file: TorrentFile, download_dir: str):
        """
        initializes PieceStorage

        Args:
            torrent_file: associated TorrentFile object
            download_dir: directory to store downloaded torrent
        """
        self.torrent_file = torrent_file
        self.download_dir = download_dir

        # paths
        if self.torrent_file.is_multifile:
            self.output_dir = str(os.path.join(download_dir, self.torrent_file.name))
            pathlib.Path(self.output_dir).mkdir(parents=True, exist_ok=True)
            self.part_path = pathlib.Path(self.output_dir) / (self.torrent_file.name + ".part")
            self.final_path = None  # multi-file has no single final path
        else:
            self.output_dir = str(download_dir)
            self.part_path = pathlib.Path(self.output_dir) / (self.torrent_file.name + ".part")
            self.final_path = pathlib.Path(self.output_dir) / self.torrent_file.name

        # create part file if it doesn't exist
        if not self.part_path.exists():
            with open(self.part_path, "wb") as f:
                f.truncate(self.torrent_file.total_length)

        self._fd = open(self.part_path, "r+b")
        self._mmap = mmap.mmap(self._fd.fileno(),
                               self.torrent_file.total_length,
                               access=mmap.ACCESS_WRITE)

        self._read_only = False

    def write(self, piece_index: int, piece_offset: int, data: bytes) -> None:
        """
        writes a block of data to the correct location in mmap

        Args:
            piece_index: index of the piece containing the block
            piece_offset: offset where the block starts
            data: the data to write
        """
        start = piece_index * self.torrent_file.piece_length + piece_offset
        self._mmap[start: start + len(data)] = data

    def read(self, global_offset: int, length: int) -> bytes:
        """
        reads data from the mmap

        Args:
            global_offset: offset in the full torrent to start reading
            length: number of bytes to read

        Returns:
            the requested bytes
        """
        return self._mmap[global_offset: global_offset + length]

    def switch_to_seeding(self):
        """
        flushes and closes the mmap, moves data into correct files, and reopens a read only mmap
        """
        if self._read_only:
            return

        # flush and close mmap and fd
        self._mmap.flush()
        self._mmap.close()
        self._fd.close()

        if self.torrent_file.is_multifile:
            self._scatter_into_files()
            # keep .part file
            reopen_path = self.part_path

        else:
            # rename the .part file to its proper filename
            if self.part_path.exists():
                shutil.move(self.part_path, self.final_path)
            reopen_path = self.final_path

        # open the file in read only for seeding
        self._fd = open(reopen_path, "rb")
        self._mmap = mmap.mmap(self._fd.fileno(),
                               self.torrent_file.total_length,
                               access=mmap.ACCESS_READ)
        self._read_only = True

    def cleanup(self):
        """
        Called when the torrent is removed / program exits
        """
        try:
            self._mmap.close()
        except Exception:
            pass
        try:
            self._fd.close()
        except Exception:
            pass

    def _scatter_into_files(self):
        """
        takes .part file and scatters bytes into corresponding target files
        """
        global_off = 0
        piece_length = self.torrent_file.piece_length

        with open(self.part_path, "rb") as src:

            # loop over each file in the torrent metadata
            for path_components, file_len, _ in self.torrent_file.file_layout():
                full_path = os.path.join(self.output_dir, *path_components)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)  # ensure parent exists

                # create target writing file
                with open(full_path, "wb") as dst:
                    remaining = file_len  # number of bytes that belong to this file
                    while remaining:
                        # read from .part file up to piece size or remaining length
                        piece = src.read(min(remaining, piece_length))
                        dst.write(piece)

                        remaining -= len(piece)
                        global_off += len(piece)
