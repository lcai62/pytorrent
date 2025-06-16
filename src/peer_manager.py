import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from .peer_connection import PeerConnection
from .piece_manager import PieceManager
from .torrent_file import TorrentFile


class PeerManager:
    """
    handles tcp connections for one torrent download
    establishes, manages, removes connections and coordinates with piece manager

    Attributes:
        peers: a list of PeerConnection objects
        torrent_file: the associated TorrentFile object for this peer manager
        piece_manager: the associated PieceManager handling piece and block tracking
    """

    def __init__(self, peers: List[PeerConnection], torrent_file: TorrentFile, piece_manager: PieceManager) -> None:
        """
        initializes the peer manager

        Args:
            peers: a list of PeerConnection objects
            torrent_file: the associated TorrentFile object for this peer manager
            piece_manager: the associated PieceManager handling piece and block tracking
        """
        self.peers: List[PeerConnection] = peers
        self.torrent_file = torrent_file
        self.piece_manager = piece_manager

        self.failed_peers: Dict[PeerConnection, int] = {}  # peer -> fail count
        self.next_retry_time: Dict[PeerConnection, datetime] = {}  # peer -> next retry timestamp
        self.max_failures = 5
        self.base_retry_interval = 10  # seconds

        # threading
        self._stop_event: threading.Event = threading.Event()
        self._retry_thread: Optional[threading.Thread] = None

    def _connect(self, peer):
        try:
            peer.connect(self.torrent_file.info_hash)
            return peer
        except Exception as e:
            count = self.failed_peers.get(peer, 0) + 1
            self.failed_peers[peer] = count

            # exp backoff: base * 2^(#fail - 1)
            delay = self.base_retry_interval * (2 ** (count - 1))
            self.next_retry_time[peer] = datetime.now() + timedelta(seconds=delay)

            return None

    def connect_all(self) -> None:
        """
        attempts to connect to all known peers, filters active peers and tracks failed for retry
        """

        alive = []
        with ThreadPoolExecutor(max_workers=120) as pool:
            futures = {pool.submit(self._connect, peer) for peer in self.peers}
            for future in as_completed(futures):
                peer = future.result()
                if peer:
                    alive.append(peer)

        self.peers = alive

    def retry_failed_peers(self) -> None:
        """
        retries failed peers if their backoff time has passed
        """
        now = datetime.now()

        retry = [
            peer for peer, time in self.next_retry_time.items()
            if now >= time and self.failed_peers.get(peer, 0) < self.max_failures
        ]

        if not retry:
            return

        with ThreadPoolExecutor(max_workers=30) as pool:
            futures = {pool.submit(self._connect, peer) for peer in retry}
            for future in as_completed(futures):
                peer = future.result()
                if peer:
                    self.peers.append(peer)
                    self.failed_peers.pop(peer, None)
                    self.next_retry_time.pop(peer, None)

    def retry_worker(self, check_interval: int = 10):
        """background thread for retrying failed peers with backoff"""
        while not self._stop_event.is_set():
            self.retry_failed_peers()
            self._stop_event.wait(check_interval)

    def start_retry_worker(self):
        if self._retry_thread and self._retry_thread.is_alive():
            return  # already running
        self._stop_event.clear()
        self._retry_thread = threading.Thread(
            target=self.retry_worker,
            daemon=True
        )
        self._retry_thread.start()

    def stop_retry_worker(self):
        self._stop_event.set()
        if self._retry_thread:
            self._retry_thread.join()

    def add_peer(self, peer: PeerConnection):
        self.peers.append(peer)

    def remove_peer(self, peer: PeerConnection):
        self.peers.remove(peer)
        peer.close()
        if peer.bitmap is not None:
            self.piece_manager.peer_disconnect(peer.bitmap)

    def close_all(self) -> None:
        for peer in self.peers:
            peer.close()
            if peer.bitmap:
                self.piece_manager.peer_disconnect(peer.bitmap)
        self.peers.clear()
        self.failed_peers.clear()
        self.next_retry_time.clear()
