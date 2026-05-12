/**
 * Electron 主进程 —— 桌宠窗口 + 系统托盘 + 设置窗口管理
 */
import { app, BrowserWindow, ipcMain, screen, Tray, Menu } from 'electron';
import path from 'path';

let petWindow: BrowserWindow | null = null;
let settingsWindow: BrowserWindow | null = null;
let tray: Tray | null = null;

const DEV_SERVER = 'http://localhost:5000';
const USE_DEV_SERVER = process.env.VITE_DEV_SERVER === '1';

function createPetWindow(): void {
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().workAreaSize;

  petWindow = new BrowserWindow({
    width: 400,
    height: 500,
    x: screenW - 420,
    y: screenH - 520,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: false,
    resizable: true,
    hasShadow: true,
    title: 'Yume AI',
    icon: path.join(__dirname, '../public/icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // 默认加载本地构建产物，设置 VITE_DEV_SERVER=1 使用开发服务器
  if (USE_DEV_SERVER) {
    petWindow.loadURL(DEV_SERVER);
  } else {
    petWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  // 渲染进程日志输出到终端（方便调试）
  petWindow.webContents.on('console-message', (event, level, message) => {
    const prefix = ['V', 'I', 'W', 'E'][level] || 'L';
    console.log(`[web] ${prefix}: ${message}`);
  });

  petWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
}

function createSettingsWindow(): void {
  if (settingsWindow) {
    settingsWindow.focus();
    return;
  }

  settingsWindow = new BrowserWindow({
    width: 600,
    height: 500,
    parent: petWindow!,
    modal: false,
    title: 'Yume 设置',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (USE_DEV_SERVER) {
    settingsWindow.loadURL(DEV_SERVER + '/#/settings');
  } else {
    settingsWindow.loadFile(path.join(__dirname, '../dist/index.html'), {
      hash: '/settings',
    });
  }

  settingsWindow.on('closed', () => {
    settingsWindow = null;
  });
}

function createTray(): void {
  // 使用 16x16 的简单图标（运行时若不存在则静默失败）
  const iconPath = path.join(__dirname, '../public/icon.png');
  try {
    tray = new Tray(iconPath);
    const contextMenu = Menu.buildFromTemplate([
      { label: '显示/隐藏', click: () => {
        if (petWindow?.isVisible()) {
          petWindow?.hide();
        } else {
          petWindow?.show();
        }
      }},
      { label: '设置', click: () => createSettingsWindow() },
      { type: 'separator' },
      { label: '退出', click: () => app.quit() },
    ]);
    tray.setToolTip('Yume AI');
    tray.setContextMenu(contextMenu);
  } catch {
    // 图标不存在时跳过托盘
    console.log('[Electron] 托盘图标未找到，跳过系统托盘');
  }
}

// IPC
ipcMain.on('set-always-on-top', (_, flag: boolean) => {
  petWindow?.setAlwaysOnTop(flag);
});

ipcMain.on('open-settings', () => {
  createSettingsWindow();
});

ipcMain.on('window-minimize', () => {
  petWindow?.minimize();
});

ipcMain.on('window-maximize', () => {
  if (petWindow?.isMaximized()) {
    petWindow.unmaximize();
  } else {
    petWindow?.maximize();
  }
});

ipcMain.on('window-close', () => {
  petWindow?.close();
});

// 应用生命周期
app.whenReady().then(() => {
  createPetWindow();
  createTray();
});

app.on('window-all-closed', () => {
  // macOS 下不退出
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (!petWindow) {
    createPetWindow();
  }
});
