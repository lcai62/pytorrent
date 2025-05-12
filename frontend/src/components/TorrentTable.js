export default function TorrentTable({torrents, selected, setSelected, handleRowDoubleClick, handleRowContextMenu}) {

    return (
        <table
            className="min-w-full bg-white shadow rounded-lg overflow-hidden table-fixed border-separate border-spacing-0">
            <thead className="bg-gray-200">
            <tr>
                <th className="text-left p-3 border-r border-gray-300">Name</th>
                <th className="text-left p-3 border-r border-gray-300">Size</th>
                <th className="text-left p-3 border-r border-gray-300">Progress</th>
                <th className="text-left p-3 border-r border-gray-300">Status</th>
                <th className="text-left p-3 border-r border-gray-300">Speed</th>
                <th className="text-left p-3 border-r border-gray-300">Seeds</th>
                <th className="text-left p-3 border-r border-gray-300">Peers</th>
                <th className="text-left p-3 border-r border-gray-300">ETA</th>
                <th className="text-left p-3 border-r border-gray-300">Reannounce In</th>
            </tr>
            </thead>
            <tbody>
            {torrents.map(torrent => (
                <tr
                    key={torrent.id}
                    className={`border-t cursor-pointer ${
                        selected?.id === torrent.id ? 'bg-blue-50' : 'hover:bg-gray-100'
                    }`}
                    onDoubleClick={() => handleRowDoubleClick(torrent)}
                    onContextMenu={(e) => handleRowContextMenu(e, torrent)}
                    onClick={() => setSelected(torrent)}
                >
                    <td className="p-3 border-r border-gray-200 max-w-xs truncate"
                        title={torrent.name}>{torrent.name}</td>
                    <td className="p-3 border-r border-gray-200">{torrent.size}</td>
                    <td className="p-3 border-r border-gray-200">
                        <div className="relative w-full bg-gray-300 rounded-full h-6 overflow-hidden">
                            {/* Blue progress fill */}
                            <div
                                className="absolute top-0 left-0 bg-blue-600 h-full"
                                style={{width: `${torrent.progress}%`}}
                            ></div>

                            {/* Centered percentage text */}
                            <div
                                className="absolute top-0 left-0 w-full h-full flex items-center justify-center text-xs font-bold text-white"
                            >
                                {torrent.progress}%
                            </div>
                        </div>
                    </td>
                    <td className="p-3 border-r border-gray-200 capitalize">{torrent.status}</td>
                    <td className="p-3 border-r border-gray-200">{torrent.speed}</td>
                    <td className="p-3 border-r border-gray-200">{torrent.transmitting_seeds} ({torrent.seeds})</td>
                    <td className="p-3 border-r border-gray-200">{torrent.transmitting_peers} ({torrent.peers})</td>
                    <td className="p-3 border-r border-gray-200">{torrent.eta}</td>
                    <td className="p-3 border-r border-gray-200">
                        {torrent.reannounceIn !== null
                            ? `${Math.floor(torrent.reannounceIn / 60)}m ${torrent.reannounceIn % 60}s`
                            : "N/A"}
                    </td>
                </tr>
            ))}
            </tbody>

        </table>
    )

}