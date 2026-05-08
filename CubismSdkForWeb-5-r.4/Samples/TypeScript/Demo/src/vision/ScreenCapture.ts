/**
 * 屏幕截图 —— 调用 Electron desktopCapturer，返回 base64 JPEG
 */
export class ScreenCapture {
  /** 截图并返回 base64 字符串，非 Electron 环境返回 null */
  static async capture(): Promise<string | null> {
    const api = (window as any).electronAPI;
    if (!api?.captureScreen) {
      console.warn('[ScreenCapture] electronAPI.captureScreen 不可用（非 Electron 环境？）');
      return null;
    }
    try {
      const base64 = await api.captureScreen();
      if (!base64) {
        console.warn('[ScreenCapture] 截图返回空');
        return null;
      }
      return base64;
    } catch (e) {
      console.error('[ScreenCapture] 截图失败:', e);
      return null;
    }
  }
}
