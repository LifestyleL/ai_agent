/**
 * AI 字幕 —— TTS 同步逐字淡入高亮
 * 通过 requestAnimationFrame 轮询 AiAudioManager.getSubtitleState()
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { AiAudioManager } from '../ai/AiAudioManager';
import { bus, Events } from '../core/state';

@customElement('yume-subtitle')
export class YumeSubtitle extends LitElement {
  static styles = css`
    :host {
      position: fixed;
      bottom: 110px;
      left: 50%;
      transform: translateX(-50%);
      z-index: var(--z-subtitle);
      max-width: 340px;
      padding: var(--space-sm) 0;
      text-align: center;
      font-size: var(--font-size-lg);
      font-family: var(--font-family);
      letter-spacing: 2px;
      line-height: 1.8;
      color: #f0f0f0;
      opacity: 0;
      transition: opacity var(--transition-medium) ease-out;
      pointer-events: none;
      -webkit-app-region: no-drag;
      user-select: none;
      word-break: keep-all;
      text-shadow: 0 0 8px rgba(255,255,255,0.4), 0 0 2px rgba(0,0,0,0.6);
    }
    .char {
      opacity: 0.25;
      transition: opacity 0.08s ease-in;
    }
    .char.lit {
      opacity: 1;
    }
  `;

  @state() private _chars: string[] = [];
  private _currentText = '';
  private _rafId = 0;
  private _visible = false;

  connectedCallback(): void {
    super.connectedCallback();
    this._startLoop();
    bus.addEventListener(Events.SUBTITLE_CLEAR, this.clear);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this._rafId) cancelAnimationFrame(this._rafId);
    bus.removeEventListener(Events.SUBTITLE_CLEAR, this.clear);
  }

  private _startLoop(): void {
    const tick = (): void => {
      const state = AiAudioManager.getInstance().getSubtitleState();
      if (!state) {
        if (this._visible) {
          this._visible = false;
          this.style.opacity = '0';
        }
      } else if (state.text !== this._currentText) {
        this._currentText = state.text;
        this._chars = [...state.text];
        this.style.opacity = '1';
        this._visible = true;
      }
      this._rafId = requestAnimationFrame(tick);
    };
    this._rafId = requestAnimationFrame(tick);
  }

  clear = (): void => {
    this._currentText = '';
    this._chars = [];
    this.style.opacity = '0';
    this._visible = false;
  };

  /** 由外部 (lappmodel) 每帧调用以更新进度 */
  updateProgress(progress: number): void {
    if (!this.shadowRoot) return;
    const spans = this.shadowRoot.querySelectorAll<HTMLSpanElement>('.char');
    const count = Math.floor(progress * spans.length);
    spans.forEach((s, i) => {
      s.classList.toggle('lit', i < count);
    });
  }

  render() {
    return html`${this._chars.map(ch => html`<span class="char">${ch === ' ' ? ' ' : ch}</span>`)}`;
  }
}
