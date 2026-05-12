/**
 * 右键丝滑菜单 —— 开关项 + 动作项 + 分隔线
 */
import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { bus, Events } from '../core/state';

export interface MenuItem {
  id: string;
  label: string;
  type: 'toggle' | 'action' | 'separator';
  checked?: boolean;
  action?: () => void;
}

@customElement('yume-context-menu')
export class YumeContextMenu extends LitElement {
  static styles = css`
    :host {
      display: none;
      position: fixed;
      z-index: var(--z-menu);
      min-width: 180px;
      background: var(--bg-menu);
      backdrop-filter: var(--blur-xheavy);
      -webkit-backdrop-filter: var(--blur-xheavy);
      border: 1px solid var(--border-light);
      border-radius: var(--radius-xl);
      padding: 6px 0;
      box-shadow: var(--shadow-menu);
      opacity: 0;
      transform: scale(0.85);
      transition: opacity 0.18s ease-out, transform 0.18s ease-out;
      pointer-events: auto;
      user-select: none;
      -webkit-user-select: none;
      -webkit-app-region: no-drag;
      font-family: var(--font-family);
      font-size: var(--font-size-base);
      color: var(--text-secondary);
    }
    :host(.visible) {
      display: block;
      opacity: 1;
      transform: scale(1);
    }
    .sep {
      height: 1px;
      background: var(--border-subtle);
      margin: var(--space-xs) var(--space-md);
    }
    .row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px var(--space-lg);
      cursor: pointer;
      transition: background var(--transition-fast);
      white-space: nowrap;
    }
    .row:hover {
      background: rgba(255, 255, 255, 0.08);
    }
    .row:active {
      background: rgba(255, 255, 255, 0.04);
    }
    .toggle-track {
      display: inline-block;
      width: 36px;
      height: 20px;
      border-radius: 10px;
      position: relative;
      transition: background var(--transition-medium);
      flex-shrink: 0;
      margin-left: var(--space-lg);
    }
    .toggle-track.on { background: var(--color-primary); }
    .toggle-track.off { background: rgba(255, 255, 255, 0.15); }
    .toggle-knob {
      position: absolute;
      top: 2px;
      width: 16px;
      height: 16px;
      border-radius: var(--radius-full);
      background: #fff;
      transition: left var(--transition-medium);
    }
    .toggle-knob.on { left: 18px; }
    .toggle-knob.off { left: 2px; }
  `;

  @property({ type: Array }) items: MenuItem[] = [];
  @state() private _visible = false;
  private _asrListening = false;
  private _bgVisible = false;
  private _alwaysOnTop = true;

  connectedCallback(): void {
    super.connectedCallback();
    document.addEventListener('contextmenu', this._onGlobalContextMenu);
    document.addEventListener('click', this._onGlobalClick);
    document.addEventListener('wheel', this._onGlobalWheel, { passive: true });
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener('contextmenu', this._onGlobalContextMenu);
    document.removeEventListener('click', this._onGlobalClick);
    document.removeEventListener('wheel', this._onGlobalWheel);
  }

  private _onGlobalContextMenu = (e: Event): void => {
    const settingsUI = document.getElementById('settings-ui');
    if (settingsUI && settingsUI.style.display !== 'none') return;
    e.preventDefault();
    e.stopPropagation();
    const me = e as MouseEvent;
    this.show(me.clientX, me.clientY);
  };

  private _onGlobalClick = (): void => {
    if (this._visible) this.hide();
  };

  private _onGlobalWheel = (): void => {
    if (this._visible) this.hide();
  };

  show(x: number, y: number): void {
    this._visible = true;
    this.classList.add('visible');
    this.style.left = `${Math.min(x, window.innerWidth - 180 - 8)}px`;
    this.style.top = `${Math.min(y, window.innerHeight - 200 - 8)}px`;
    this.style.transformOrigin = 'top center';
  }

  hide(): void {
    this._visible = false;
    this.classList.remove('visible');
  }

  get isVisible(): boolean {
    return this._visible;
  }

  private _toggleAsr = (): void => {
    this._asrListening = !this._asrListening;
    bus.emit(Events.ASR_TOGGLE, this._asrListening);
  };

  private _toggleBg = (): void => {
    this._bgVisible = !this._bgVisible;
    bus.emit(Events.BG_TOGGLE, this._bgVisible);
  };

  private _toggleAlwaysOnTop = (): void => {
    this._alwaysOnTop = !this._alwaysOnTop;
    if (window.electronAPI?.setAlwaysOnTop) {
      window.electronAPI.setAlwaysOnTop(this._alwaysOnTop);
    }
  };

  render() {
    return html`
      <div class="row" @click=${() => { this._toggleAsr(); this.hide(); }}>
        <span>🎤 语音监听</span>
        <span class="toggle-track ${this._asrListening ? 'on' : 'off'}">
          <span class="toggle-knob ${this._asrListening ? 'on' : 'off'}"></span>
        </span>
      </div>
      <div class="row" @click=${() => { this._toggleBg(); this.hide(); }}>
        <span>🖼 显示背景</span>
        <span class="toggle-track ${this._bgVisible ? 'on' : 'off'}">
          <span class="toggle-knob ${this._bgVisible ? 'on' : 'off'}"></span>
        </span>
      </div>
      <div class="row" @click=${() => { this._toggleAlwaysOnTop(); this.hide(); }}>
        <span>📌 窗口置顶</span>
        <span class="toggle-track ${this._alwaysOnTop ? 'on' : 'off'}">
          <span class="toggle-knob ${this._alwaysOnTop ? 'on' : 'off'}"></span>
        </span>
      </div>
      <div class="sep"></div>
      <div class="row" @click=${() => { bus.emit(Events.SETTINGS_OPEN); this.hide(); }}>
        <span>⚙ 对话设置</span>
      </div>
      <div class="row" @click=${() => { this.hide(); }}>
        <span>🧠 记忆管理</span>
      </div>
      <div class="row" @click=${() => { this.hide(); }}>
        <span>📅 查看日记</span>
      </div>
      <div class="sep"></div>
      <div class="row" @click=${() => { window.close(); }}>
        <span>退出</span>
      </div>
    `;
  }
}
