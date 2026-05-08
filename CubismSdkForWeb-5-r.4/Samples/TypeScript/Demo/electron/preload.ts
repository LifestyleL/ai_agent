/**
 * Electron 预加载脚本 —— 暴露安全 IPC 接口给渲染进程
 */
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  setAlwaysOnTop: (flag: boolean) => ipcRenderer.send('set-always-on-top', flag),
  openSettings: () => ipcRenderer.send('open-settings'),
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),
  captureScreen: (): Promise<string | null> => ipcRenderer.invoke('capture-screen'),
});
