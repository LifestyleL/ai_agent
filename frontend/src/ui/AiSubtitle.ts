/**
 * AI 字幕组件 —— 与 TTS 音频同步的逐字淡入字幕
 * 通过 requestAnimationFrame 轮询 AiAudioManager.getSubtitleState()
 */
import { AiAudioManager } from "../ai/AiAudioManager";

export class AiSubtitle {
  private container: HTMLDivElement;
  private charSpans: HTMLSpanElement[] = [];
  private currentText: string = "";
  private rafId: number = 0;
  private visible: boolean = false;

  constructor() {
    this.container = this._buildContainer();
    document.body.appendChild(this.container);
    console.log('[AiSubtitle] 初始化完成, container:', this.container.id);
    this._startLoop();
  }

  private _buildContainer(): HTMLDivElement {
    const el = document.createElement('div');
    el.id = 'yume-subtitle';
    el.style.cssText = `
      position: fixed;
      bottom: 80px;
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
    `;
    return el;
  }

  private _startLoop(): void {
    let tickCount = 0;
    const tick = (): void => {
      const state = AiAudioManager.getInstance().getSubtitleState();
      tickCount++;

      if (!state) {
        if (this.visible) {
          console.log('[AiSubtitle] 隐藏字幕');
          this.visible = false;
          this.container.style.opacity = '0';
        }
      } else if (state.text !== this.currentText) {
        console.log(`[AiSubtitle] 新字幕: "${state.text.slice(0, 30)}..." (${state.text.length}字, ${this.charSpans.length} spans, tick#${tickCount})`);
        this.currentText = state.text;
        this._buildSpans(state.text);
        this.container.style.opacity = '1';
        this.visible = true;
        this._updateProgress(state.progress);
      } else {
        this._updateProgress(state.progress);
      }

      this.rafId = requestAnimationFrame(tick);
    };
    this.rafId = requestAnimationFrame(tick);
    console.log('[AiSubtitle] rAF 循环已启动');
  }

  private _buildSpans(text: string): void {
    this.container.innerHTML = '';
    this.charSpans = [];
    for (const ch of text) {
      const span = document.createElement('span');
      span.textContent = ch;
      span.style.cssText = 'opacity:0.25; transition:opacity 0.08s ease-in;';
      this.container.appendChild(span);
      this.charSpans.push(span);
    }
  }

  private _updateProgress(progress: number): void {
    const count = Math.floor(progress * this.charSpans.length);
    for (let i = 0; i < this.charSpans.length; i++) {
      const target = i < count ? '1' : '0.25';
      if (this.charSpans[i].style.opacity !== target) {
        this.charSpans[i].style.opacity = target;
      }
    }
  }

  /** 立即清除字幕 */
  public clear(): void {
    this.currentText = "";
    this.container.innerHTML = '';
    this.charSpans = [];
    this.container.style.opacity = '0';
    this.visible = false;
  }

  /** 销毁组件 */
  public destroy(): void {
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = 0;
    }
    this.container.remove();
  }
}
