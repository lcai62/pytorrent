import argparse

from src.torrent_client import TorrentClient
from torrent_file import TorrentFile
from tracker_client import TrackerClient
from peer_connection import PeerConnection
from peer_manager import PeerManager
from piece_manager import PieceManager

# torrent_file = TorrentFile("small.torrent")
# torrent_file.parse()

# client = TrackerClient(torrent_file, "aieoriwpcisjkfjdcisf")
# peers = client.get_peers()
# print(peers)

# peer_manager = PeerManager(peers, torrent_file)
# peer_manager.connect_all()

# piece_manager = PieceManager(torrent_file)


# for ip, port in peers:
#     conn = PeerConnection(ip, port, "aieoriwpcisjkfjdcisf")
#     conn.connect(info_hash)



# main.py



if __name__ == "__main__":
    # small.torrent must sit next to this script (or run from that folder).
    torrent_path = "small.torrent"
    output_dir   = "."            # current directory

    client = TorrentClient(torrent_path, output_dir)
    client.download()
