/**
 * AI 对话气泡 —— 底部居中半透明浮动气泡 + 点击展开输入框
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { bus, Events } from '../core/state';
import type { DialogLine } from '../core/types';

@customElement('yume-dialog-bubble')
export class YumeDialogBubble extends LitElement {
  static styles = css`
    :host {
      position: fixed;
      bottom: 70px;
      left: 50%;
      transform: translateX(-50%);
      z-index: var(--z-bubble);
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: var(--space-sm);
      pointer-events: none;
      -webkit-app-region: no-drag;
    }
    .bubble {
      max-width: 280px;
      min-width: 80px;
      padding: 10px var(--space-2xl);
      background: var(--bg-bubble);
      backdrop-filter: var(--blur-heavy);
      -webkit-backdrop-filter: var(--blur-heavy);
      border: 1px solid var(--border-light);
      border-radius: var(--radius-2xl);
      color: var(--text-primary);
      font-size: var(--font-size-base);
      font-family: var(--font-family);
      line-height: 1.5;
      text-align: center;
      word-break: break-word;
      opacity: 0.7;
      transition: opacity 0.25s ease-out, transform 0.25s ease-out;
      pointer-events: auto;
      cursor: default;
      user-select: text;
      -webkit-user-select: text;
      box-shadow: var(--shadow-bubble);
    }
    .bubble.thinking {
      color: var(--text-dim);
      font-style: italic;
    }
    .input-wrap {
      display: none;
    }
    .input-wrap.show {
      display: block;
    }
    input {
      width: 220px;
      padding: var(--space-sm) 14px;
      background: var(--bg-input);
      backdrop-filter: var(--blur-heavy);
      -webkit-backdrop-filter: var(--blur-heavy);
      border: 1px solid var(--border-focus);
      border-radius: 20px;
      color: var(--text-white);
      font-size: var(--font-size-base);
      font-family: var(--font-family);
      outline: none;
      pointer-events: auto;
      -webkit-app-region: no-drag;
      transition: border-color var(--transition-normal);
    }
    input:focus {
      border-color: var(--color-primary);
    }
  `;

  @state() private _text = '✨ 点击这里和我聊天...';
  @state() private _type: DialogLine['type'] = 'ai';
  @state() private _inputVisible = false;
  @state() private _faded = false;

  private _lines: DialogLine[] = [];
  private _hideTimer: ReturnType<typeof setTimeout> | null = null;

  connectedCallback(): void {
    super.connectedCallback();
    bus.addEventListener(Events.TEXT_CHUNK, this._onTextChunk as EventListener);
    bus.addEventListener(Events.TEXT_THINKING, this._onTextThinking as EventListener);
    bus.addEventListener(Events.INTERRUPT_ACK, this._onInterruptAck);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    bus.removeEventListener(Events.TEXT_CHUNK, this._onTextChunk as EventListener);
    bus.removeEventListener(Events.TEXT_THINKING, this._onTextThinking as EventListener);
    bus.removeEventListener(Events.INTERRUPT_ACK, this._onInterruptAck);
    this._clearHideTimer();
  }

  private _onTextChunk = (e: Event): void => {
    const text = (e as CustomEvent).detail as string;
    this._appendText(text, 'ai');
  };

  private _onTextThinking = (e: Event): void => {
    const text = (e as CustomEvent).detail as string;
    this._appendText(text, 'thinking');
  };

  private _onInterruptAck = (): void => {
    this._lines = [];
    this._text = '';
    this._faded = true;
    this._inputVisible = false;
  };

  private _appendText(text: string, type: DialogLine['type']): void {
    const last = this._lines[this._lines.length - 1];
    if (last && last.type === type) {
      last.text += text;
    } else {
      this._lines.push({ text, type });
    }
    const display = this._lines.filter(l => l.type === 'ai' || l.type === 'thinking').map(l => l.text).join('');
    const short = display.length > 80 ? display.slice(-80) + '...' : display;
    this._text = short || '...';
    this._type = type;
    this._faded = false;
    if (this._lines.length > 50) this._lines = this._lines.slice(-30);
    this._resetHideTimer();
  }

  private _resetHideTimer(): void {
    this._clearHideTimer();
    this._hideTimer = setTimeout(() => {
      this._faded = true;
    }, 8000);
  }

  private _clearHideTimer(): void {
    if (this._hideTimer !== null) {
      clearTimeout(this._hideTimer);
      this._hideTimer = null;
    }
  }

  private _onBubbleClick = (): void => {
    this._inputVisible = !this._inputVisible;
    if (this._inputVisible) {
      requestAnimationFrame(() => {
        this.shadowRoot?.querySelector('input')?.focus();
      });
    }
  };

  private _onInputKeydown = (e: KeyboardEvent): void => {
    const input = e.target as HTMLInputElement;
    if (e.key === 'Enter' && input.value.trim()) {
      const text = input.value.trim();
      this._lines.push({ text, type: 'user' });
      bus.emit(Events.TEXT_SEND, text);
      input.value = '';
      this._inputVisible = false;
    }
    if (e.key === 'Escape') {
      input.value = '';
      this._inputVisible = false;
      input.blur();
    }
  };

  private _onInputBlur = (): void => {
    setTimeout(() => {
      const input = this.shadowRoot?.querySelector('input');
      if (input && document.activeElement !== input) {
        this._inputVisible = false;
      }
    }, 200);
  };

  render() {
    return html`
      <div
        class="bubble ${this._type === 'thinking' ? 'thinking' : ''}"
        style="opacity:${this._faded ? '0' : '1'};transform:translateY(${this._faded ? '6px' : '0'})"
        @click=${this._onBubbleClick}
        @mouseenter=${this._clearHideTimer}
        @mouseleave=${this._resetHideTimer}
      >${this._text}</div>
      <div class="input-wrap ${this._inputVisible ? 'show' : ''}">
        <input type="text" placeholder="输入消息..."
          @keydown=${this._onInputKeydown}
          @blur=${this._onInputBlur}>
      </div>
    `;
  }
}
