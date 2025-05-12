import React, {useEffect, useState} from 'react';
import {FaPause, FaPlay, FaSync, FaTrash} from 'react-icons/fa';
import Modal from './components/Modal';
import TopBar from "./components/TopBar";
import Sidebar from "./components/Sidebar";
import ContextMenu from "./components/ContextMenu";
import TorrentTable from "./components/TorrentTable";
import TorrentDetails from "./components/TorrentDetails";


function App() {
    const [torrents, setTorrents] = useState([]);
    const [filter, setFilter] = useState("All");
    const [showModal, setShowModal] = useState(false);

    const [torrentPath, setTorrentPath] = useState("");
    const [downloadPath, setDownloadPath] = useState("");
    const [torrentMeta, setTorrentMeta] = useState(null);

    const [contextMenu, setContextMenu] = useState({visible: false, x: 0, y: 0, torrent: null});

    const [selected, setSelected] = useState(null);


    useEffect(() => {
        async function loadDefaultDownloadPath() {
            const path = await window.electron.getDefaultDownloadPath();
            setDownloadPath(path);
        }

        loadDefaultDownloadPath();
    }, []);

    useEffect(() => {
        const handleClick = () => closeContextMenu();
        window.addEventListener('click', handleClick);
        return () => window.removeEventListener('click', handleClick);
    }, []);

    useEffect(() => {
        const interval = setInterval(async () => {
            try {
                const res = await fetch('http://localhost:8000/status');
                const data = await res.json();
                console.log(data)
                setTorrents(JSON.parse(JSON.stringify(data.torrents || [])));
            } catch (err) {
                console.error("failed to get status", err);
            }
        }, 1000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        if (!selected) return;

        const updated = torrents.find(t => t.id === selected.id);
        if (updated) {
            setSelected(updated);
        }
    }, [torrents, selected]);

    async function handleForceReannounce(torrent) {
        if (!torrent) return;
        await fetch('http://localhost:8000/reannounce', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: torrent.id}),
        });
        setContextMenu({visible: false, x: 0, y: 0, torrent: null});
    }

    async function handlePause(torrent) {
        if (!torrent) return;
        await fetch('http://localhost:8000/pause', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: torrent.id}),
        });
        setContextMenu({visible: false, x: 0, y: 0, torrent: null});
    }

    async function handleUnpause(torrent) {
        if (!torrent) return;
        await fetch('http://localhost:8000/resume', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: torrent.id}),
        });
        setContextMenu({visible: false, x: 0, y: 0, torrent: null});
    }

    function handleRowContextMenu(e, torrent) {
        e.preventDefault();

        const container = e.currentTarget.closest(".relative");
        const rect = container.getBoundingClientRect();

        setContextMenu({
            visible: true,
            x: e.clientX - rect.left,
            y: e.clientY - rect.top,
            torrent: torrent,
        });
    }

    function closeContextMenu() {
        setContextMenu({visible: false, x: 0, y: 0, torrent: null});
    }


    const filteredTorrents = torrents.filter(t => {
        if (filter === "All") return true;
        return t.status === filter.toLowerCase();
    });

    function handleRowDoubleClick(torrent) {
        if (!torrent.downloadPath) {
            console.warn("no download path available");
            return;
        }
        console.log(torrent.isMultiFile)
        if (torrent.isMultiFile) {
            // It's a folder
            window.electron.openFolder(torrent.downloadPath);
        } else {
            // It's a single file
            const filePath = torrent.downloadPath;
            window.electron.openFolder(filePath);
        }
    }


    async function handleAddTorrent() {
        const filePath = await window.electron.selectTorrentFile();
        if (!filePath) return;

        const arrayBuffer = await window.electron.readFile(filePath);
        const blob = new Blob([new Uint8Array(arrayBuffer)]);
        const fileName = filePath.split(/[\\/]/).pop();
        const file = new File([blob], fileName);

        const formData = new FormData();
        formData.append('file', file);

        const res = await fetch('http://localhost:8000/parse', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();

        setTorrentPath(filePath);
        setTorrentMeta(data);
        console.log(data)
        setShowModal(true);
    }

    function handleRemove(torrent) {
        fetch("http://localhost:8000/remove", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({id: torrent.id}),
        })
            .then(() => {
                console.log("removed", torrent.name);
                if (selected?.id === torrent.id) {
                    setSelected(null);
                }
            })
            .catch(err => console.error("remove failed", err));
    }

    async function handleSelectFolder() {
        const folder = await window.electron.selectDownloadFolder();
        if (folder) setDownloadPath(folder);
    }

    async function handleConfirmAdd() {
        if (!torrentPath || !downloadPath) return;

        try {
            const arrayBuffer = await window.electron.readFile(torrentPath);
            const blob = new Blob([new Uint8Array(arrayBuffer)]);
            const fileName = torrentPath.split(/[\\/]/).pop();
            const file = new File([blob], fileName);

            const formData = new FormData();
            formData.append('file', file);
            formData.append('downloadPath', downloadPath);

            const res = await fetch('http://localhost:8000/upload', {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) {
                const errorText = await res.text();
                console.error('upload failed:', errorText);
                return;
            }

            setShowModal(false);
            setTorrentPath("");
            setTorrentMeta(null);
        } catch (err) {
            console.error('upload error:', err);
        }
    }

    return (
        <div className="flex flex-col h-screen bg-gray-100">
            {/* Top Bar */}
            <TopBar handleAddTorrent={handleAddTorrent}/>

            {/* Content */}
            <div className="flex flex-1 overflow-hidden">
                <Sidebar
                    filter={filter}
                    setFilter={setFilter}
                />

                {/* Table */}
                <div className="flex-1 overflow-auto p-6 relative border-2">
                    <TorrentTable
                        torrents={filteredTorrents}
                        selected={selected}
                        setSelected={setSelected}
                        handleRowDoubleClick={handleRowDoubleClick}
                        handleRowContextMenu={handleRowContextMenu}
                    />

                    <TorrentDetails torrent={selected} onClose={() => setSelected(null)}/>


                    {contextMenu.visible && (
                        <ContextMenu
                            x={contextMenu.x}
                            y={contextMenu.y}
                            onClose={closeContextMenu}
                            actions={[
                                {
                                    label: "Force Reannounce",
                                    icon: FaSync,
                                    onClick: () => handleForceReannounce(contextMenu.torrent),
                                },
                                {
                                    label: "Pause",
                                    icon: FaPause,
                                    onClick: () => handlePause(contextMenu.torrent),
                                },
                                {
                                    label: "Unpause",
                                    icon: FaPlay,
                                    onClick: () => handleUnpause(contextMenu.torrent),
                                },
                                {
                                    label: "Remove",
                                    icon: FaTrash,
                                    color: "text-red-600",
                                    onClick: () => handleRemove(contextMenu.torrent),
                                },
                            ]}
                        />
                    )}

                </div>
            </div>

            <Modal
                open={showModal}
                onClose={() => setShowModal(false)}
                onConfirm={handleConfirmAdd}
                torrentMeta={torrentMeta}
                downloadPath={downloadPath}
                onSelectFolder={handleSelectFolder}
            />
        </div>
    );
}

export default App;
