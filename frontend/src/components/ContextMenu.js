import React from 'react';

export default function ContextMenu({x, y, actions, onClose}) {
    return (
        <div
            className="absolute bg-white shadow-lg rounded border w-48 p-2 space-y-2"
            style={{top: y, left: x, zIndex: 100}}
            onClick={onClose}
        >
            {actions.map(({label, icon: Icon, onClick, color = 'text-blue-600'}, index) => (
                <div
                    key={index}
                    onClick={(e) => {
                        e.stopPropagation();
                        onClick();
                    }}
                    className="flex items-center space-x-2 hover:bg-gray-100 p-2 rounded cursor-pointer"
                >
                    <Icon className={color}/>
                    <span>{label}</span>
                </div>
            ))}
        </div>
    );
}
