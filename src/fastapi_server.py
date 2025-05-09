import hashlib
import json
import os
import threading
import time
from datetime import datetime
from typing import List, Any, Dict, cast, Optional

import bencodepy
from fastapi import FastAPI
from fastapi import Form
from fastapi import UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from torrent_client import TorrentClient

SESSION_FILE = "./session.json"

app = FastAPI()
torrents: List[TorrentClient] = []  # TorrentClient instances

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def parse_peer_id(peer_id: str) -> str:
    # azureus style
    if len(peer_id) < 8 or peer_id[0] != '-':
        return peer_id

    code = peer_id[1:3]
    version = peer_id[3:7]

    client_map = {
        "qB": "qBittorrent",
        "UT": "uTorrent",
        "TR": "Transmission",
        "DE": "Deluge",
        "LT": "libtorrent",
        "AZ": "Azureus",
        "BW": "BitComet",
        "UW": "uTorrent Web",
        "lt": "libTorrent",
    }

    name = client_map.get(code, "Unknown")
    if name != "Unknown":
        version_str = '.'.join(str(int(c, 36)) if c.isalpha() else c for c in version)
        return f"{name} {version_str}"
    return peer_id


def save_session() -> None:
    """saves current torrent session states to disk"""
    data = []
    for torrent in torrents:
        data.append({
            "torrent_path": torrent.torrent_file.path,
            "download_dir": torrent.download_dir,
            "paused": getattr(torrent, "paused", False),
            "is_finished": torrent.piece_manager.is_finished(),
            "added_on": torrent.added_on,
            "completed_on": torrent.completed_on
        })
    with open(SESSION_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[session] Saved {len(data)} torrents to session.json")


def load_session() -> None:
    """loads torrent session state from disk"""
    if not os.path.exists(SESSION_FILE):
        print("[session] No session file found, skipping")
        return

    with open(SESSION_FILE, "r") as f:
        data = json.load(f)

    print(f"[session] Loading {len(data)} torrents from session file")
    for entry in data:
        print("[session] entry ->", entry)
        try:
            client = TorrentClient(
                entry["torrent_path"],
                download_dir=entry["download_dir"],
                was_finished=entry.get("is_finished", False)
            )
            client.start_time = time.time()
            client.added_on = entry.get("added_on", time.time())
            client.completed_on = entry.get("completed_on", None)
            torrents.append(client)

            if entry.get("paused", False):
                continue

            threading.Thread(target=client.download, daemon=True).start()

            if entry.get("is_finished", False):
                print(f"[session] Seeding torrent {entry['torrent_path']}")
            else:
                print(f"[session] Resumed torrent {entry['torrent_path']}")

        except Exception as e:
            print(f"[session] Failed to load {entry['torrent_path']}: {e}")


class ReannounceRequest(BaseModel):
    """reannounce endpoint model"""
    id: Optional[int] = None  # optional torrent index; if missing => all


@app.post("/reannounce")
def force_reannounce(req: ReannounceRequest):
    """forces a tracker reannounce for a torrent"""
    if not torrents:
        raise HTTPException(404, "no active torrents")

    targets = torrents if req.id is None else [
        t for i, t in enumerate(torrents) if i == req.id
    ]
    if not targets:
        raise HTTPException(404, f"torrent id {req.id} not found")

    for torrent in targets:
        # call the helper you added in step-3 earlier
        threading.Thread(
            target=lambda: torrent.announce_now(event=""), daemon=True
        ).start()

    return {"status": "ok", "count": len(targets)}


@app.post("/upload")
async def upload_torrent(file: UploadFile = File(...), downloadPath: str = Form(...)):
    """
    upload and starts a new torrent

    Args:
        file: bytes of .torrent file
        downloadPath: directory where files should be saved
    """
    os.makedirs(downloadPath, exist_ok=True)
    save_path = os.path.join(downloadPath, file.filename)

    contents = await file.read()
    with open(save_path, "wb") as f:
        f.write(contents)

    client = TorrentClient(save_path, download_dir=downloadPath)
    client.start_time = time.time()  # Start tracking download time
    client.added_on = time.time()
    threading.Thread(target=client.download, daemon=True).start()

    torrents.append(client)
    save_session()

    return {"status": "started", "torrent": file.filename}


@app.post("/parse")
async def parse_torrent(file: UploadFile = File(...)) -> dict[str, Any]:
    """
    parses a .torrent file and return the metadata

    Args:
        file: bytes of .torrent file

    Returns:
        dictionary containing torrent metadata
    """
    contents = await file.read()
    metadata = cast(Dict[bytes, Any], bencodepy.decode(contents))

    info = metadata[b'info']

    name = info[b'name'].decode()
    piece_length = info[b'piece length']

    if b'files' in info:
        length = sum(f[b'length'] for f in info[b'files'])
        files = []
        for f in info[b'files']:
            path = "/".join(p.decode() for p in f[b'path'])
            files.append({
                "path": path,
                "length": f[b'length'],
            })
    else:
        length = info[b'length']
        files = [{
            "path": name,
            "length": length,
        }]

    # --- extract optional fields ---

    comment = metadata.get(b'comment', b'').decode('utf-8', errors='ignore') if b'comment' in metadata else None
    created_by = metadata.get(b'created by', b'').decode('utf-8',
                                                         errors='ignore') if b'created by' in metadata else None
    creation_date = metadata.get(b'creation date', None)
    if isinstance(creation_date, (int, float)):
        creation_date = datetime.fromtimestamp(creation_date).strftime('%Y-%m-%d %H:%M:%S %Z')
    else:
        creation_date = None

    info_bencoded = bencodepy.encode(info)
    info_hash = hashlib.sha1(info_bencoded).hexdigest()

    return {
        "name": name,
        "piece_length": piece_length,
        "total_size": length,
        "files": files,
        "comment": comment,
        "created_by": created_by,
        "creation_date": creation_date,
        "info_hash": info_hash,
    }


def get_progress(peer, num_pieces):
    if not peer.bitmap:
        return 0.0
    return round(100 * peer.bitmap.count(1) / num_pieces, 2)


@app.get("/status")
def get_status():
    """
    gives a summary on all active torrents and their progress

    Returns:
        list of dictionaries providing statuses on each torrent
    """
    if not torrents:
        return {"torrents": []}  # No torrents yet, return empty list

    torrent_infos = []

    for idx, torrent in enumerate(torrents):
        total_size = torrent.torrent_file.total_length
        done_size = torrent.piece_manager.downloaded_bytes
        percent_done = min((done_size / total_size) * 100 if total_size > 0 else 0, 100)

        if torrent.peer_manager and torrent.peer_manager.peers:
            speed_mbps = sum(p.down_speed_bps() for p in torrent.peer_manager.peers if p.active) / 1_000_000
        else:
            speed_mbps = 0.0

        if speed_mbps > 0 and percent_done < 100:
            left_bytes = torrent.torrent_file.total_length * (1 - percent_done / 100)
            eta_seconds = (left_bytes * 8) / (speed_mbps * 1_000_000)
            eta = time.strftime('%Hh %Mm %Ss', time.gmtime(eta_seconds))
        else:
            eta = "Done" if percent_done == 100 else "Stalled"

        if percent_done == 100:
            speed_mbps = 0

        is_multi = hasattr(torrent.torrent_file, 'files') and len(torrent.torrent_file.files) > 1

        active_peers = []
        if torrent.peer_manager:
            active_peers = [peer for peer in torrent.peer_manager.peers if peer.active]

        seeds = []
        peers = []

        for peer in active_peers:
            if peer.bitmap and peer.bitmap.count(1) == torrent.num_pieces:
                seeds.append(peer)
            else:
                peers.append(peer)

        transmitting_seeds = sum(1 for peer in seeds if not peer.choked)
        transmitting_peers = sum(1 for peer in peers if not peer.choked)

        is_complete = torrent.piece_manager.is_finished()

        if is_complete:
            speed_mbps = 0  # optional
            status = "done"
        elif speed_mbps > 0:
            status = "downloading"
        else:
            status = "stalled"

        if torrent.paused:
            status = "paused"

        min_next_announce = None
        for tracker in torrent.tracker_manager.trackers:
            if hasattr(tracker, 'next_announce'):
                if min_next_announce is None or tracker.next_announce < min_next_announce:
                    min_next_announce = tracker.next_announce

        if min_next_announce:
            reannounce_in = max(0, int(min_next_announce - time.time()))
        else:
            reannounce_in = None

        general = {
            "Total Size": f"{torrent.torrent_file.total_length / 1_000_000:.1f} MB",
            "Pieces": f"{torrent.num_pieces} × {torrent.torrent_file.piece_length // 1024} KiB",
            "Added On": datetime.fromtimestamp(torrent.added_on).strftime(
                '%Y-%m-%d %H:%M:%S %Z') if torrent.added_on else None,
            "Completed On": datetime.fromtimestamp(torrent.completed_on).strftime(
                '%Y-%m-%d %H:%M:%S %Z') if torrent.completed_on else None,
            "Created On": (
                datetime.fromtimestamp(torrent.torrent_file.metadata.get('creation date')).strftime(
                    '%Y-%m-%d %H:%M:%S %Z'))
            if torrent.torrent_file.metadata.get("creation date") else None,
            "Hash": torrent.torrent_file.info_hash.hex(),
            "Saved at": torrent.download_dir,
            "Comment": torrent.torrent_file.metadata.get(b'comment', b'')
            .decode('utf-8', errors='ignore') if b'comment' in torrent.torrent_file.metadata else None
        }

        tracker_rows = [{
            "url": tracker.client.tracker_url,
            "tier": i,
            "status": tracker.last_status,
            "peers": tracker.last_peers,
            "seeds": tracker.last_seeds,
            "message": tracker.last_msg,
            "nextAnnounce": int(tracker.next_announce - time.time())
        } for i, tracker in enumerate(torrent.tracker_manager.trackers)]

        peer_rows = []
        if torrent.peer_manager:
            for peer in torrent.peer_manager.peers:
                peer_rows.append({
                    "ip": peer.ip,
                    "port": peer.port,
                    "client": parse_peer_id(peer.remote_id.decode(errors='ignore') if peer.remote_id else ""),
                    "progress": get_progress(peer, torrent.num_pieces),
                    "flags": ("S" if peer.choked is False else "") + ("I" if peer.interested else ""),
                    "downSpeed": round(peer.down_speed_bps() / 1024, 2),
                    "upSpeed": round(peer.up_speed_bps() / 1024, 2),
                    "downloaded": peer.total_downloaded,
                    "uploaded": peer.total_uploaded
                })

        torrent_infos.append({
            "id": idx,
            "name": torrent.torrent_file.name,
            "size": f"{torrent.torrent_file.total_length / 1_000_000:.1f} MB",
            "progress": round(percent_done, 2),
            "status": status,
            "speed": "0 B/s" if torrent.paused else f"{speed_mbps:.2f} Mbps",
            "transmitting_peers": transmitting_peers,
            "transmitting_seeds": transmitting_seeds,
            "peers": len(peers),
            "seeds": len(seeds),
            "eta": "∞" if torrent.paused else eta,
            "infoHash": torrent.torrent_file.info_hash.hex(),
            "downloadPath": torrent.download_dir,
            "isMultiFile": is_multi,
            "reannounceIn": reannounce_in,
            "details": {
                "general": general,
                "trackers": tracker_rows,
                "peers": peer_rows
            }
        })

    return {"torrents": torrent_infos}


class TorrentActionRequest(BaseModel):
    id: int


@app.post("/pause")
def pause_torrent(req: TorrentActionRequest):
    """pauses a torrent from its id"""
    try:
        torrent = torrents[req.id]
        torrent.pause()
        save_session()
        return {"status": "paused"}
    except IndexError:
        return {"status": "error", "detail": "Invalid torrent ID"}


@app.post("/resume")
def resume_torrent(req: TorrentActionRequest):
    """resumes a torrent from its id"""
    try:
        torrent = torrents[req.id]
        torrent.resume()
        save_session()
        return {"status": "resumed"}
    except IndexError:
        return {"status": "error", "detail": "Invalid torrent ID"}


@app.post("/remove")
def remove_torrent(req: TorrentActionRequest):
    """removes a torrent from its id"""
    try:
        torrent = torrents.pop(req.id)
        torrent.pause()  # ensure paused

        torrent.cleanup()

        print(f"[remove] Removed torrent: {torrent.torrent_file.path}")
        save_session()
        return {"status": "removed"}

    except IndexError:
        return {"status": "error", "detail": "Invalid torrent ID"}


@app.on_event("shutdown")
def on_shutdown():
    """saves session on shutdown"""
    save_session()


load_session()
