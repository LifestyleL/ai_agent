/**
 * 按住说话按钮 —— 底部圆形按钮，press 态 pulse 动画
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { bus, Events } from '../core/state';
import { AudioRecorder } from '../audio/AudioRecorder';

@customElement('yume-voice-button')
export class YumeVoiceButton extends LitElement {
  static styles = css`
    :host {
      display: flex;
      flex-shrink: 0;
    }
    button {
      width: 44px;
      height: 44px;
      border: 1px solid var(--border-active);
      border-radius: var(--radius-full);
      background: var(--bg-button);
      color: var(--text-white);
      font-size: var(--font-size-xl);
      cursor: pointer;
      backdrop-filter: var(--blur-medium);
      -webkit-backdrop-filter: var(--blur-medium);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background var(--transition-normal), box-shadow var(--transition-normal);
      user-select: none;
      -webkit-user-select: none;
      pointer-events: auto;
      -webkit-app-region: no-drag;
      outline: none;
    }
    button.pressed {
      background: var(--bg-voice-active);
      box-shadow: 0 0 16px rgba(255, 119, 170, 0.5);
    }
  `;

  @state() private _pressed = false;
  private _recorder: AudioRecorder | null = null;
  private _listening = false;

  private _onMouseDown = (e: Event): void => {
    e.preventDefault();
    this._pressed = true;
    if (this._listening) return;
    this._recorder = new AudioRecorder((base64: string) => {
      bus.emit(Events.TEXT_SEND, base64); // 走 audio_frame 通道
    });
    this._recorder.start();
    this._listening = true;
  };

  private _onMouseUp = (e: Event): void => {
    e.preventDefault();
    this._pressed = false;
    this._stopRecorder();
  };

  private _onMouseLeave = (): void => {
    if (this._pressed) {
      this._pressed = false;
      this._stopRecorder();
    }
  };

  private _stopRecorder(): void {
    if (this._recorder) {
      this._recorder.stop();
      this._recorder = null;
      this._listening = false;
    }
  }

  render() {
    return html`
      <button
        class="${this._pressed ? 'pressed' : ''}"
        @mousedown=${this._onMouseDown}
        @mouseup=${this._onMouseUp}
        @mouseleave=${this._onMouseLeave}
        @touchstart=${this._onMouseDown}
        @touchend=${this._onMouseUp}
        title="按住说话"
      >🎤</button>
    `;
  }
}
