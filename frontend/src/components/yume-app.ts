/**
 * Root Application Shell
 * 挂载所有 UI 组件，管理全局键盘快捷键，连接 Live2D delegate
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { bus, Events } from '../core/state';
import type { AIFaceParams, MemoryCard, DiaryEntry } from '../core/types';
import { AI_WS } from '../ai/AiWebSocket';
import { AI_AUDIO } from '../ai/AiAudioManager';
import { AudioRecorder } from '../audio/AudioRecorder';

import './yume-launcher';
import './yume-context-menu';
import './yume-dialog-bubble';
import './yume-subtitle';
import './yume-interrupt-button';
import './yume-settings-button';
import './yume-text-input';
import './yume-voice-button';
import './yume-settings-drawer';

@customElement('yume-app')
export class YumeApp extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      height: 100%;
    }
    /* ---- Drag Bar ---- */
    .drag-bar {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      height: 32px;
      z-index: var(--z-dragbar);
      -webkit-app-region: drag;
      pointer-events: auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 6px;
      background: var(--bg-dragbar);
      transition: background var(--transition-medium);
    }
    .drag-bar:hover {
      background: var(--bg-dragbar-hover);
    }
    .drag-bar .win-title {
      font-size: var(--font-size-xs);
      color: rgba(255, 255, 255, 0.6);
      font-family: var(--font-family);
      margin-left: 6px;
      user-select: none;
      -webkit-user-select: none;
    }
    .win-ctrls {
      display: flex;
      gap: var(--space-xs);
      -webkit-app-region: no-drag;
    }
    .win-ctrl {
      width: 28px;
      height: 22px;
      border: none;
      border-radius: var(--radius-sm);
      background: transparent;
      color: rgba(255, 255, 255, 0.7);
      font-size: var(--font-size-xs);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background var(--transition-fast);
      line-height: 1;
      font-family: var(--font-family);
      padding: 0;
    }
    .win-ctrl:hover {
      background: rgba(255, 255, 255, 0.12);
      color: var(--text-white);
    }
    .win-ctrl.close:hover {
      background: var(--color-danger);
      color: var(--text-white);
    }
    /* ---- Top Bar ---- */
    .top-bar {
      position: fixed;
      top: var(--space-lg);
      right: var(--space-lg);
      z-index: var(--z-toolbar);
      display: flex;
      gap: var(--space-sm);
    }
    /* ---- Bottom Toolbar ---- */
    .bottom-toolbar {
      position: fixed;
      bottom: var(--space-md);
      left: var(--space-md);
      right: var(--space-md);
      z-index: var(--z-toolbar);
      display: flex;
      gap: var(--space-sm);
      align-items: center;
      opacity: 0.6;
      transition: opacity var(--transition-medium);
    }
    .bottom-toolbar:hover {
      opacity: 0.95;
    }
    /* ---- Sound Btn ---- */
    .sound-btn {
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      z-index: var(--z-sound-btn);
      padding: 10px 20px;
      background: var(--color-primary);
      color: var(--text-white);
      border: none;
      border-radius: var(--radius-md);
      cursor: pointer;
      font-size: var(--font-size-lg);
      font-weight: bold;
      box-shadow: var(--shadow-button);
      font-family: var(--font-family);
      display: none;
    }
    .sound-btn.show { display: block; }
  `;

  @state() private _bgVisible = false;
  @state() private _showSoundBtn = false;
  private _recorder: AudioRecorder | null = null;
  private _asrListening = false;
  private _audioResumed = false;

  connectedCallback(): void {
    super.connectedCallback();

    // 暴露给 Live2D 管线（launcher 轮询用）
    (window as any).AI_WS = AI_WS;
    (window as any).AI_AUDIO = AI_AUDIO;

    // 事件总线监听
    bus.addEventListener(Events.TEXT_SEND, this._onTextSend as EventListener);
    bus.addEventListener(Events.INTERRUPT, this._onInterrupt);
    bus.addEventListener(Events.ASR_TOGGLE, this._onAsrToggle as EventListener);
    bus.addEventListener(Events.BG_TOGGLE, this._onBgToggle as EventListener);
    bus.addEventListener(Events.AUDIO_UNLOCKED, this._onAudioUnlock);

    // 键盘快捷键
    document.addEventListener('keydown', this._onKeydown);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    bus.removeEventListener(Events.TEXT_SEND, this._onTextSend as EventListener);
    bus.removeEventListener(Events.INTERRUPT, this._onInterrupt);
    bus.removeEventListener(Events.ASR_TOGGLE, this._onAsrToggle as EventListener);
    bus.removeEventListener(Events.BG_TOGGLE, this._onBgToggle as EventListener);
    bus.removeEventListener(Events.AUDIO_UNLOCKED, this._onAudioUnlock);
    document.removeEventListener('keydown', this._onKeydown);
  }

  private _onKeydown = (e: KeyboardEvent): void => {
    if (e.code === 'Space' || e.code === 'Escape') {
      e.preventDefault();
      bus.emit(Events.INTERRUPT);
      bus.emit(Events.SUBTITLE_CLEAR);
    }
    if (e.ctrlKey && e.code === 'KeyB') {
      e.preventDefault();
      bus.emit(Events.BG_TOGGLE, !this._bgVisible);
    }
    if (e.ctrlKey && e.code === 'KeyM') {
      e.preventDefault();
      bus.emit(Events.ASR_TOGGLE, !this._asrListening);
    }
  };

  private _onTextSend = (e: Event): void => {
    const text = (e as CustomEvent).detail as string;
    AI_WS.sendText(text);
  };

  private _onInterrupt = (): void => {
    AI_WS.sendInterrupt();
  };

  private _onAsrToggle = (e: Event): void => {
    this._asrListening = (e as CustomEvent).detail as boolean;
    if (this._asrListening) {
      this._recorder = new AudioRecorder((base64: string) => AI_WS.sendAudioFrame(base64));
      this._recorder.start();
      AI_WS.sendAsrControl('start');
    } else {
      this._recorder?.stop();
      this._recorder = null;
      AI_WS.sendAsrControl('stop');
    }
  };

  private _onBgToggle = (e: Event): void => {
    this._bgVisible = (e as CustomEvent).detail as boolean;
    document.body.style.background = this._bgVisible
      ? 'var(--bg-base)'
      : 'var(--bg-transparent)';
  };

  private _onAudioUnlock = (): void => {
    if (this._audioResumed) return;
    if (AI_AUDIO.resumeAudioContext) {
      AI_AUDIO.resumeAudioContext();
      this._audioResumed = true;
      this._showSoundBtn = false;
    }
  };

  private _onSoundBtnClick = (): void => {
    bus.emit(Events.AUDIO_UNLOCKED);
  };

  private _onWinMinimize = (): void => {
    window.electronAPI?.minimize();
  };
  private _onWinMaximize = (): void => {
    window.electronAPI?.maximize();
  };
  private _onWinClose = (): void => {
    window.electronAPI?.close();
  };

  render() {
    const api = window.electronAPI;
    return html`
      ${api ? html`
        <div class="drag-bar">
          <span class="win-title">Yume AI</span>
          <div class="win-ctrls">
            <button class="win-ctrl" @click=${this._onWinMinimize}>─</button>
            <button class="win-ctrl" @click=${this._onWinMaximize}>□</button>
            <button class="win-ctrl close" @click=${this._onWinClose}>✕</button>
          </div>
        </div>
      ` : ''}

      <yume-launcher></yume-launcher>

      <button class="sound-btn ${this._showSoundBtn ? 'show' : ''}" @click=${this._onSoundBtnClick}>
        点击启动声音
      </button>

      <div class="top-bar">
        <yume-interrupt-button></yume-interrupt-button>
        <yume-settings-button></yume-settings-button>
      </div>

      <yume-dialog-bubble></yume-dialog-bubble>
      <yume-subtitle></yume-subtitle>

      <div class="bottom-toolbar">
        <yume-text-input></yume-text-input>
        <yume-voice-button></yume-voice-button>
      </div>

      <yume-settings-drawer></yume-settings-drawer>
      <yume-context-menu></yume-context-menu>
    `;
  }
}
