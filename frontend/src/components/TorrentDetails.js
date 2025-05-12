import React, {useEffect, useRef, useState} from "react";
import Tabs from "./Tabs";

export default function TorrentDetails({torrent, onClose}) {
    // store height as a number for easier math
    const [height, setHeight] = useState(300);
    const startY = useRef(0);
    const startH = useRef(0);
    const resizing = useRef(false);

    const onMouseDown = e => {
        e.preventDefault();
        resizing.current = true;
        startY.current = e.clientY;
        startH.current = height;
    };

    useEffect(() => {
        const onMove = e => {
            if (!resizing.current) return;
            const delta = startY.current - e.clientY;
            const newHeight = Math.min(
                Math.max(startH.current + delta, 200),
                window.innerHeight * 0.8
            );
            setHeight(newHeight);
        };

        const onUp = () => (resizing.current = false);

        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
        return () => {
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
        };
    }, [height]);

    if (!torrent) return null;

    return (
        <div
            className="absolute inset-x-0 bottom-0 bg-white border-t border-gray-300 shadow-inner overflow-hidden"
            style={{height}}
        >
            <div
                className="h-1 cursor-row-resize bg-gray-200 hover:bg-gray-300"
                onMouseDown={onMouseDown}
            />
            <div className="h-full overflow-auto max-h-full px-8 py-4">
                <Tabs selected={torrent} onClose={onClose}/>
            </div>
        </div>
    );
}
