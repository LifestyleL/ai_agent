/**
 * 文字输入框 —— 底部常驻
 */
import { LitElement, html, css } from 'lit';
import { customElement } from 'lit/decorators.js';
import { bus, Events } from '../core/state';

@customElement('yume-text-input')
export class YumeTextInput extends LitElement {
  static styles = css`
    :host {
      display: flex;
      flex: 1;
    }
    input {
      width: 100%;
      padding: var(--space-sm) 14px;
      border: 1px solid var(--border-active);
      border-radius: var(--radius-2xl);
      background: var(--bg-button);
      color: var(--text-white);
      font-size: var(--font-size-base);
      font-family: var(--font-family);
      outline: none;
      backdrop-filter: var(--blur-medium);
      -webkit-backdrop-filter: var(--blur-medium);
      transition: border-color var(--transition-medium);
      pointer-events: auto;
      -webkit-app-region: no-drag;
    }
    input:focus {
      border-color: var(--color-primary);
    }
  `;

  private _onKeydown = (e: KeyboardEvent): void => {
    const input = e.target as HTMLInputElement;
    if (e.key === 'Enter' && input.value.trim()) {
      bus.emit(Events.TEXT_SEND, input.value.trim());
      input.value = '';
    }
  };

  render() {
    return html`<input type="text" placeholder="想说点什么..." @keydown=${this._onKeydown}>`;
  }
}
