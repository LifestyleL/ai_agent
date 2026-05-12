/**
 * 轻量 EventBus —— 替代 window 全局变量
 * 所有跨模块通信通过此总线进行
 */
class AppBus extends EventTarget {
  emit(event: string, detail?: unknown): void {
    this.dispatchEvent(new CustomEvent(event, { detail }));
  }
}

export const bus = new AppBus();

/** 事件名常量 */
export const Events = {
  // WebSocket 生命周期
  WS_CONNECTED: 'ws:connected',
  WS_DISCONNECTED: 'ws:disconnected',
  WS_ERROR: 'ws:error',

  // 消息流
  TEXT_CHUNK: 'text:chunk',
  TEXT_THINKING: 'text:thinking',
  TEXT_SEND: 'text:send',
  INTERRUPT: 'interrupt',
  INTERRUPT_ACK: 'interrupt:ack',

  // 音频
  TTS_PLAYING: 'tts:playing',
  TTS_ENDED: 'tts:ended',
  AUDIO_UNLOCKED: 'audio:unlocked',

  // Live2D 命令
  LIVE2D_PARAMS: 'live2d:params',
  LIVE2D_EMOTION: 'live2d:emotion',
  LIVE2D_MOTION: 'live2d:motion',

  // UI 控制
  ASR_TOGGLE: 'asr:toggle',
  BG_TOGGLE: 'bg:toggle',
  SETTINGS_OPEN: 'settings:open',
  SETTINGS_CLOSE: 'settings:close',
  LAUNCHER_DONE: 'launcher:done',
  LAYOUT_RESIZE: 'layout:resize',
  SUBTITLE_CLEAR: 'subtitle:clear',

  // 数据面板
  MEMORY_CARDS: 'memory:cards',
  DIARY_LIST: 'diary:list',
} as const;
