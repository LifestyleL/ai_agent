/**
 * 打断按钮 —— 右上角
 */
import { LitElement, html, css } from 'lit';
import { customElement } from 'lit/decorators.js';
import { bus, Events } from '../core/state';

@customElement('yume-interrupt-button')
export class YumeInterruptButton extends LitElement {
  static styles = css`
    :host { display: inline-flex; }
    button {
      width: 36px;
      height: 36px;
      border: 1px solid var(--border-visible);
      border-radius: var(--radius-full);
      background: var(--bg-button-top);
      color: var(--text-white);
      font-size: var(--font-size-lg);
      cursor: pointer;
      backdrop-filter: var(--blur-light);
      -webkit-backdrop-filter: var(--blur-light);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background var(--transition-normal), transform 0.1s;
      user-select: none;
      -webkit-user-select: none;
      pointer-events: auto;
      -webkit-app-region: no-drag;
      outline: none;
      padding: 0;
    }
    button:hover {
      background: rgba(255, 255, 255, 0.1);
    }
  `;

  private _onClick = (): void => {
    bus.emit(Events.INTERRUPT);
    const btn = this.shadowRoot?.querySelector('button');
    if (btn) {
      btn.style.transform = 'scale(0.85)';
      setTimeout(() => { btn.style.transform = 'scale(1)'; }, 100);
    }
  };

  render() {
    return html`<button @click=${this._onClick} title="打断 (Space/Esc)">⏹</button>`;
  }
}
