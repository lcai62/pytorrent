import {FaCheckCircle, FaDownload, FaList, FaTimesCircle} from "react-icons/fa";

export default function Sidebar({filter, setFilter}) {

    const filters = [
        {name: "All", icon: <FaList/>},
        {name: "Downloading", icon: <FaDownload/>},
        {name: "Done", icon: <FaCheckCircle/>},
        {name: "Stalled", icon: <FaTimesCircle/>},
    ];

    return (
        <div className="w-64 bg-white shadow-md p-4 flex flex-col">
            {filters.map(f => (
                <div
                    key={f.name}
                    className={`cursor-pointer flex items-center space-x-3 p-2 mb-2 rounded hover:bg-gray-100 ${
                        filter === f.name ? 'text-blue-600 font-bold' : ''
                    }`}
                    onClick={() => setFilter(f.name)}
                >
                    {f.icon}
                    <span>{f.name}</span>
                </div>
            ))}
        </div>
    )

}