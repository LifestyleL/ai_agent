/**
 * 启动器遮罩 —— 连接状态机驱动
 * 状态: idle → connecting → connected → fadeOut
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { bus, Events } from '../core/state';
import { AI_WS } from '../ai/AiWebSocket';

type LauncherState = 'idle' | 'connecting' | 'connected' | 'done';

@customElement('yume-launcher')
export class YumeLauncher extends LitElement {
  static styles = css`
    :host {
      position: fixed;
      inset: 0;
      z-index: var(--z-launcher);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background: var(--bg-launcher);
      backdrop-filter: var(--blur-xheavy);
      -webkit-backdrop-filter: var(--blur-xheavy);
      -webkit-app-region: drag;
      pointer-events: auto;
      transition: opacity 0.5s ease-out, transform 0.5s ease-out;
    }
    :host(.done) {
      opacity: 0;
      transform: scale(1.05);
      pointer-events: none;
    }
    .brand {
      font-size: var(--font-size-2xl);
      font-weight: 700;
      color: var(--color-primary);
      margin-bottom: var(--space-sm);
      letter-spacing: 4px;
      font-family: var(--font-family);
    }
    .subtitle {
      font-size: var(--font-size-base);
      color: var(--text-subtle);
      margin-bottom: var(--space-2xl);
      font-family: var(--font-family);
    }
    .connect-btn {
      padding: var(--space-md) 48px;
      font-size: var(--font-size-lg);
      background: var(--color-primary);
      color: var(--text-white);
      border: none;
      border-radius: var(--radius-3xl);
      cursor: pointer;
      font-weight: 600;
      letter-spacing: 2px;
      transition: background var(--transition-medium), transform var(--transition-normal);
      -webkit-app-region: no-drag;
      pointer-events: auto;
    }
    .connect-btn:hover {
      background: var(--color-primary-hover);
      transform: scale(1.04);
    }
    .connect-btn:disabled {
      background: var(--text-very-subtle);
      cursor: default;
      transform: none;
    }
    .status {
      margin-top: var(--space-lg);
      font-size: var(--font-size-sm);
      color: var(--text-very-subtle);
      font-family: var(--font-family);
      min-height: 20px;
    }
    .status.ok { color: #4caf50; }
    .status.error { color: #f44336; }
  `;

  @state() private _state: LauncherState = 'idle';
  @state() private _statusText = '等待后端连接 ws://localhost:8765';
  @state() private _statusClass = '';
  @state() private _btnText = '✨ 连接启动';
  @state() private _btnDisabled = false;
  @state() private _audioUnlocked = false;

  private _checkInterval = 0;
  private _audioRetries = 0;
  private _audioResumed = false;

  connectedCallback(): void {
    super.connectedCallback();
    bus.addEventListener(Events.WS_CONNECTED, this._onWsConnected);
    bus.addEventListener(Events.AUDIO_UNLOCKED, this._onAudioUnlocked);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    bus.removeEventListener(Events.WS_CONNECTED, this._onWsConnected);
    bus.removeEventListener(Events.AUDIO_UNLOCKED, this._onAudioUnlocked);
    clearInterval(this._checkInterval);
  }

  private _onWsConnected = (): void => {
    this._state = 'connected';
    this._statusText = '后端已连接';
    this._statusClass = 'ok';
    this._btnText = '已连接';
    clearInterval(this._checkInterval);
    this._tryResumeAudio();
    setTimeout(() => this._finish(), 600);
  };

  private _onAudioUnlocked = (): void => {
    this._audioUnlocked = true;
    this._audioResumed = true;
  };

  private _tryResumeAudio(): void {
    if (this._audioResumed) return;
    bus.emit(Events.AUDIO_UNLOCKED);
    this._audioResumed = true;
    this._audioUnlocked = true;
  }

  private _finish(): void {
    this.classList.add('done');
    setTimeout(() => {
      this._state = 'done';
      bus.emit(Events.LAUNCHER_DONE);
    }, 500);
  }

  private _onConnect = (): void => {
    this._tryResumeAudio();
    this._state = 'connecting';
    this._btnDisabled = true;
    this._btnText = '连接中...';
    this._statusText = '正在连接 ws://localhost:8765 ...';
    this._statusClass = '';

    // 轮询等待 WebSocket 连接
    this._checkInterval = window.setInterval(() => {
      if (AI_WS.isConnected) {
        bus.emit(Events.WS_CONNECTED);
      }
    }, 300);

    // 15 秒超时
    setTimeout(() => {
      if (this._state === 'connecting') {
        clearInterval(this._checkInterval);
        this._btnDisabled = false;
        this._btnText = '重试连接';
        this._statusText = '连接超时，请确认后端已启动 (python main.py)';
        this._statusClass = 'error';
        this._state = 'idle';
      }
    }, 15000);

    // 触发连接
    if (!AI_WS.isConnected) {
      AI_WS.connect();
    }
  };

  render() {
    if (this._state === 'done') return html``;
    return html`
      <div class="brand">YUME</div>
      <div class="subtitle">你的 AI 桌宠伙伴</div>
      <button class="connect-btn" ?disabled=${this._btnDisabled} @click=${this._onConnect}>
        ${this._btnText}
      </button>
      <div class="status ${this._statusClass}">${this._statusText}</div>
    `;
  }
}
