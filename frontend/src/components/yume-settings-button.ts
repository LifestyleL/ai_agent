/**
 * 设置齿轮按钮 —— 右上角
 */
import { LitElement, html, css } from 'lit';
import { customElement } from 'lit/decorators.js';
import { bus, Events } from '../core/state';

@customElement('yume-settings-button')
export class YumeSettingsButton extends LitElement {
  static styles = css`
    :host { display: inline-flex; }
    button {
      width: 36px;
      height: 36px;
      border: 1px solid var(--border-visible);
      border-radius: var(--radius-full);
      background: var(--bg-button-top);
      color: var(--text-white);
      font-size: 18px;
      cursor: pointer;
      backdrop-filter: var(--blur-light);
      -webkit-backdrop-filter: var(--blur-light);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background var(--transition-normal);
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
    bus.emit(Events.SETTINGS_OPEN);
  };

  render() {
    return html`<button @click=${this._onClick} title="设置">⚙</button>`;
  }
}
