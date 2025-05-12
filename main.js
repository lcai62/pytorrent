const {app, BrowserWindow, ipcMain, dialog} = require('electron');
const path = require('path');
const isDev = process.env.ELECTRON_DEV === 'true';
const waitOn = require('wait-on');
const {shell} = require('electron');
let win;

async function createWindow() {
    if (isDev) {
        await waitOn({resources: ['http://localhost:3000']});
    }

    win = new BrowserWindow({
        width: 1200,
        height: 800,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });

    const URL = isDev
        ? 'http://localhost:3000'
        : `file://${path.join(__dirname, 'frontend/build/index.html')}`;

    win.loadURL(URL);

    win.webContents.openDevTools();

    win.on('closed', () => {
        win = null;
    });
}

app.whenReady().then(createWindow);

ipcMain.handle('get-default-download-path', async () => {
    return app.getPath('downloads');
});

ipcMain.handle('select-torrent-file', async () => {
    const result = await dialog.showOpenDialog(win, {
        properties: ['openFile'],
        filters: [{name: 'Torrent Files', extensions: ['torrent']}],
    });
    if (result.canceled) return null;
    return result.filePaths[0];
});

ipcMain.handle('open-folder', async (event, folderPath) => {
    if (folderPath) {
        shell.openPath(folderPath);
    }
});

ipcMain.handle('select-download-folder', async () => {
    const result = await dialog.showOpenDialog(win, {
        properties: ['openDirectory'],
    });
    if (result.canceled) return null;
    return result.filePaths[0];
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});

ipcMain.handle('read-file', async (event, filePath) => {
    const fs = require('fs').promises;
    return await fs.readFile(filePath);
});