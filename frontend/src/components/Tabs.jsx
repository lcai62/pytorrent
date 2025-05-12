import React, {useState} from 'react';


function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${units[i]}`;
}

export default function Tabs({selected, onClose}) {
    const [tab, setTab] = useState("general");
    const {general, trackers, peers} = selected.details;

    const sortedPeers = [...peers].sort((a, b) => b.downSpeed - a.downSpeed);


    function formatSpeed(kbps) {
        const mbps = kbps / 1024;
        if (mbps >= 1) return `${mbps.toFixed(2)} MB/s`;
        return `${kbps.toFixed(2)} KB/s`;
    }


    return (
        <>
            <div className="flex mb-2 border-b">
                {["general", "trackers", "peers"].map(t => (
                    <button key={t}
                            onClick={() => setTab(t)}
                            className={`px-4 py-1 mr-2 ${tab === t ? 'border-b-2 border-blue-600 font-bold' : ''}`}>
                        {t.charAt(0).toUpperCase() + t.slice(1)}
                    </button>
                ))}
                <div className="ml-auto cursor-pointer text-gray-500" onClick={onClose}>✕</div>
            </div>

            {tab === "general" && (
                <table className="text-sm">
                    <tbody>
                    {Object.entries(general).map(([k, v]) => (
                        <tr key={k}>
                            <td className="pr-4 font-medium">{k}</td>
                            <td>{v ?? "—"}</td>
                        </tr>
                    ))}
                    </tbody>
                </table>
            )}

            {tab === "trackers" && (
                <table className="w-full text-sm">
                    <thead>
                    <tr>
                        <th className="text-left">URL</th>
                        <th className="text-left">Tier</th>
                        <th className="text-left">Status</th>
                        <th className="text-left">Peers</th>
                        <th className="text-left">Seeds</th>
                        <th className="text-left">Message</th>
                        <th className="text-left">Next announce</th>
                    </tr>
                    </thead>
                    <tbody>
                    {trackers.map((tr, i) => (
                        <tr key={i}>
                            <td className="truncate max-w-xs">{tr.url}</td>
                            <td>{tr.tier}</td>
                            <td>{tr.status}</td>
                            <td>{tr.peers}</td>
                            <td>{tr.seeds}</td>
                            <td>{tr.message ?? "—"}</td>
                            <td>{tr.nextAnnounce}s</td>
                        </tr>
                    ))}
                    </tbody>
                </table>
            )}


            {tab === "peers" && (
                <table className="w-full text-sm">
                    <thead>
                    <tr>
                        <th className="text-left">IP</th>
                        <th className="text-left">Port</th>
                        <th className="text-left">Flags</th>
                        <th className="text-left">Client</th>
                        <th className="text-left">Progress</th>
                        <th className="text-left">Down Speed</th>
                        <th className="text-left">Up Speed</th>
                        <th className="text-left">Downloaded</th>
                        <th className="text-left">Uploaded</th>
                    </tr>
                    </thead>
                    <tbody>
                    {sortedPeers.map((p, i) => (
                        <tr key={i}>
                            <td>{p.ip}</td>
                            <td>{p.port}</td>
                            <td>{p.flags}</td>
                            <td>{p.client}</td>
                            <td>{p.progress != null ? `${p.progress}%` : "?"}</td>
                            <td>{formatSpeed(p.downSpeed).toLocaleString()}</td>
                            <td>{formatSpeed(p.upSpeed).toLocaleString()}</td>
                            <td>{formatBytes(p.downloaded)}</td>
                            <td>{formatBytes(p.uploaded)}</td>
                        </tr>
                    ))}
                    </tbody>
                </table>
            )}
        </>
    );
}
