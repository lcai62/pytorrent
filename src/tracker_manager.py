import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

from http_tracker_client import HTTPTrackerClient
from peer_connection import PeerConnection
from torrent_file import TorrentFile
from udp_tracker_client import UDPTrackerClient


class TrackerEntry:
    def __init__(self, client):
        self.last_status: str = "unknown"  # working | error
        self.last_msg: str | None = None
        self.last_peers: int = 0
        self.last_seeds: int = 0

        self.client = client
        self.interval = 1800
        self.next_announce = time.time() + self.interval


class TrackerManager:
    """
    manages state of all trackers, handles reannouncing and updating peers list

    Attributes:
        torrent_file: the parsed TorrentFile object
        trackers: list of all trackers
    """

    def __init__(self, torrent_file: TorrentFile, peer_id: str, port=6881):

        self.torrent_file = torrent_file

        self.trackers: List[TrackerEntry] = []

        all_trackers = [[torrent_file.announce]]
        if torrent_file.announce_list:
            parsed = [[url for url in tier] for tier in torrent_file.announce_list]
            all_trackers.extend(parsed)

        print(f"torrent annnounce list: {torrent_file.announce_list}")
        print(f"all trackers: {all_trackers}")

        for tier in all_trackers:
            for tracker_url in tier:
                if tracker_url.startswith("udp://"):
                    client = UDPTrackerClient(torrent_file, peer_id, tracker_url, port)
                elif tracker_url.startswith("http://") or tracker_url.startswith("https://"):
                    client = HTTPTrackerClient(torrent_file, peer_id, tracker_url, port)
                else:
                    print(f"[tracker] Unsupported tracker scheme: {tracker_url}")
                    continue
                self.trackers.append(TrackerEntry(client))

    def get_all_peers(self, event: str = "") -> Tuple[List[PeerConnection], int]:
        all_peers = []
        seen = set()
        min_interval = 1800  # fallback interval

        print(f"[get_all_peers] Announcing to {len(self.trackers)} trackers with event='{event}'")

        with ThreadPoolExecutor(max_workers=min(10, len(self.trackers))) as pool:
            futures = {pool.submit(tracker.client.get_peers, event): tracker for tracker in self.trackers}

            for future in as_completed(futures):
                tracker = futures[future]
                try:
                    peers, interval = future.result()
                    tracker.last_status = "working"
                    tracker.last_msg = None
                    tracker.last_seeds = sum(
                        1 for p in peers if p.bitmap and p.bitmap.count(1) == len(self.torrent_file.pieces)
                    )
                    tracker.last_peers = len(peers) - tracker.last_seeds

                    min_interval = min(min_interval, interval)
                    for peer in peers:
                        if (peer.ip, peer.port) not in seen:
                            all_peers.append(peer)
                            seen.add((peer.ip, peer.port))
                except Exception as e:
                    print(f"[tracker] Failed to get peers from {tracker.client.tracker_url}: {e}")
                    tracker.last_status = "error"
                    tracker.last_msg = str(e)
        return all_peers, min_interval
