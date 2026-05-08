/**
 * Electron API exposed via contextBridge (preload.ts)
 */
interface ElectronAPI {
  setAlwaysOnTop: (flag: boolean) => void;
  openSettings: () => void;
  minimize: () => void;
  maximize: () => void;
  close: () => void;
  captureScreen: () => Promise<string | null>;
}

interface Window {
  electronAPI?: ElectronAPI;
  AI_WS?: any;
  AI_AUDIO?: any;
  webkitAudioContext?: typeof AudioContext;
  AudioContext?: typeof AudioContext;
}
