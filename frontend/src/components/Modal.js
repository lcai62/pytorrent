import React, {useCallback, useEffect, useState} from "react";
import {BsFileEarmarkFill, BsFillFolderFill} from "react-icons/bs";

export default function Modal({open, onClose, onConfirm, torrentMeta, downloadPath, onSelectFolder}) {
    const formatBytes = (bytes) => {
        if (bytes === 0) return "0 Bytes";
        const k = 1024, sizes = ["Bytes", "KB", "MB", "GB", "TB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
    };

    const buildTree = (files = []) => {
        const root = {isFile: false, size: 0, checked: true, children: {}};
        files.forEach(({path, length}) => {
            const parts = path.split("/");
            let cur = root;
            cur.size += length;
            parts.forEach((p, idx) => {
                cur.children[p] ??= {
                    isFile: idx === parts.length - 1,
                    size: 0,
                    checked: true,
                    children: {},
                };
                cur = cur.children[p];
                cur.size += length;
            });
        });
        return root;
    };

    const [fileTree, setFileTree] = useState(() => buildTree(torrentMeta?.files));

    useEffect(() => {
        setFileTree(buildTree(torrentMeta?.files));
    }, [torrentMeta]);

    const toggleNode = useCallback((node, newChecked) => {
        const recurse = (n) => {
            n.checked = newChecked;
            if (!n.isFile) {
                Object.values(n.children).forEach(recurse);
            }
        };
        recurse(node);
        setFileTree((prev) => ({...prev}));
    }, []);


    const renderTree = (node, name = "", path = []) => {
        const rowKey = [...path, name].join("/") || "root";

        const renderRow = (icon, displayName, sizeText, onChange, checked) => (
            <div className="flex items-center space-x-2 py-1">
                <input
                    type="checkbox"
                    checked={checked}
                    onChange={onChange}
                />
                {icon}
                <div className="flex items-center w-full overflow-hidden">
                    <span className="truncate flex-1">{displayName}</span>
                    <span className="text-xs text-gray-500 ml-4 w-20 text-right flex-shrink-0">
            {sizeText}
          </span>
                </div>
            </div>
        );

        if (node.isFile) {
            return (
                <div key={rowKey} className="space-y-2">
                    {renderRow(
                        <BsFileEarmarkFill className="text-gray-600 flex-shrink-0"/>,
                        name,
                        formatBytes(node.size),
                        (e) => toggleNode(node, e.target.checked, path),
                        node.checked
                    )}
                </div>
            );
        }

        return (
            <div key={rowKey} className="ml-4 space-y-2">
                {renderRow(
                    <BsFillFolderFill className="text-blue-600 flex-shrink-0"/>,
                    name || torrentMeta?.name,
                    formatBytes(node.size),
                    (e) => toggleNode(node, e.target.checked, path),
                    node.checked
                )}
                <div className="ml-6 space-y-2">
                    {Object.entries(node.children).map(([childName, childNode]) =>
                        renderTree(childNode, childName, [...path, name])
                    )}
                </div>
            </div>
        );
    };

    if (!open || !torrentMeta) return null;

    return (
        <div className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-40 z-50">
            <div
                className="bg-white rounded-lg p-8 shadow-lg flex flex-col space-y-6 resize overflow-auto"
                style={{
                    width: "1000px",
                    height: "600px",
                    minWidth: "600px",
                    minHeight: "600px",
                    maxWidth: "90vw",
                    maxHeight: "90vh",
                }}
            >
                <h2 className="text-xl font-bold">{torrentMeta.name}</h2>

                {/* Torrent Information */}
                <p className="font-semibold">Torrent Information</p>
                <div className="flex flex-row w-full flex-1 overflow-hidden">
                    {/* LEFT panel (with draggable edge) */}
                    <div
                        className="flex flex-col overflow-hidden relative group"
                    >


                        {/* Torrent metadata */}
                        <div className="flex flex-col space-y-2 text-sm mb-5">
                            <div className="flex"><span
                                className="font-semibold w-28">Size:</span><span>{formatBytes(torrentMeta.total_size)}</span>
                            </div>
                            <div className="flex"><span
                                className="font-semibold w-28">Piece Size:</span><span>{formatBytes(torrentMeta.piece_length)}</span>
                            </div>
                            <div className="flex"><span
                                className="font-semibold w-28">Hash:</span><span>{torrentMeta.info_hash}</span></div>
                            <div className="flex"><span
                                className="font-semibold w-28">Comment:</span><span>{torrentMeta.comment || "No comment"}</span>
                            </div>
                            <div className="flex"><span
                                className="font-semibold w-28">Author:</span><span>{torrentMeta.created_by || "Unknown"}</span>
                            </div>
                            <div className="flex"><span
                                className="font-semibold w-28">Created:</span><span>{torrentMeta.creation_date ? new Date(torrentMeta.creation_date).toLocaleString() : "Unknown"}</span>
                            </div>
                        </div>

                        <div className="flex-grow"/>


                        {/* Download folder */}
                        <div className="flex flex-col mt-4">
                            <p className="mb-2 font-semibold">Select Download Folder</p>
                            <button
                                onClick={onSelectFolder}
                                className="block w-full bg-gray-100 border border-gray-300 rounded-lg px-3 py-2 text-gray-700 hover:bg-gray-200 text-sm"
                            >
                                Browse Folder
                            </button>
                            {downloadPath && (
                                <p className="text-xs mt-1 break-all text-gray-600">{downloadPath}</p>
                            )}
                        </div>
                    </div>

                    <div className="w-2"></div>

                    {/* RIGHT panel (File List) */}
                    <div className="flex flex-col flex-1 border rounded p-2 overflow-auto space-y-2 text-sm min-h-0">
                        {renderTree(fileTree)}
                    </div>
                </div>

                {/* Buttons */}
                <div className="flex justify-end space-x-4 pt-4">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 rounded bg-gray-300 hover:bg-gray-400"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={onConfirm}
                        disabled={!downloadPath}
                        className={`px-4 py-2 rounded ${
                            downloadPath
                                ? "bg-blue-600 hover:bg-blue-700 text-white"
                                : "bg-blue-300 cursor-not-allowed"
                        }`}
                    >
                        Add
                    </button>
                </div>
            </div>
        </div>
    );
}
