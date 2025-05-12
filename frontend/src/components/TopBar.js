export default function TopBar({handleAddTorrent}) {

    return (
        <div className="bg-white p-4 flex items-center shadow">
            <h1 className="text-2xl font-bold mr-auto">pytorrent</h1>
            <button
                onClick={handleAddTorrent}
                className="cursor-pointer bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
            >
                Add Torrent
            </button>
        </div>
    )

}