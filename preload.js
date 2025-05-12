// preload.js
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electron', {
  selectTorrentFile: () => ipcRenderer.invoke('select-torrent-file'),
  selectDownloadFolder: () => ipcRenderer.invoke('select-download-folder'),
  getDefaultDownloadPath: () => ipcRenderer.invoke('get-default-download-path'),
  readFile: (path) => ipcRenderer.invoke('read-file', path),
  openFolder: (folderPath) => ipcRenderer.invoke('open-folder', folderPath),

});
