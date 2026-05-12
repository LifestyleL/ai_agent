/**
 * 对话气泡 —— 显示在模型下方的半透明浮动文字 + 输入框
 */

type DialogLine = { text: string; type: 'ai' | 'user' | 'thinking' };

class DialogBubbleImpl {
  private container: HTMLDivElement;
  private bubble: HTMLDivElement;
  private input: HTMLInputElement;
  private lines: DialogLine[] = [];
  private hideTimer: ReturnType<typeof setTimeout> | null = null;
  private _visible = true;
  private onSendText?: (text: string) => void;

  constructor() {
    this.container = this._buildContainer();
    this.bubble = this._buildBubble();
    this.input = this._buildInput();
    this.container.appendChild(this.bubble);
    this.container.appendChild(this.input);
    document.body.appendChild(this.container);
  }

  private _buildContainer(): HTMLDivElement {
    const el = document.createElement('div');
    el.id = 'yume-dialog-container';
    el.style.cssText = `
      position: fixed;
      bottom: var(--space-lg);
      left: 50%;
      transform: translateX(-50%);
      z-index: var(--z-bubble);
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: var(--space-sm);
      pointer-events: none;
      -webkit-app-region: no-drag;
      transition: opacity var(--transition-slow);
    `;
    return el;
  }

  private _buildBubble(): HTMLDivElement {
    const el = document.createElement('div');
    el.id = 'yume-dialog-bubble';
    el.style.cssText = `
      max-width: 280px;
      min-width: 80px;
      padding: 10px var(--space-2xl);
      background: var(--bg-bubble);
      backdrop-filter: var(--blur-heavy);
      -webkit-backdrop-filter: var(--blur-heavy);
      border: 1px solid var(--border-light);
      border-radius: var(--radius-2xl);
      color: var(--text-primary);
      font-family: var(--font-family);
      font-size: var(--font-size-base);
      line-height: 1.5;
      text-align: center;
      word-break: break-word;
      opacity: 0;
      transform: translateY(6px);
      transition: opacity 0.25s ease-out, transform 0.25s ease-out;
      pointer-events: auto;
      cursor: default;
      user-select: text;
      -webkit-user-select: text;
      box-shadow: var(--shadow-bubble);
    `;
    el.textContent = '✨ 点击这里和我聊天...';
    // 初始可见
    el.style.opacity = '0.7';
    el.style.transform = 'translateY(0)';

    // 点击气泡 → 显示/隐藏输入框
    el.addEventListener('click', () => {
      this.input.style.display = this.input.style.display === 'none' ? 'block' : 'none';
      if (this.input.style.display !== 'none') {
        this.input.focus();
      }
    });

    // hover 气泡时保持显示
    el.addEventListener('mouseenter', () => this._clearHideTimer());
    el.addEventListener('mouseleave', () => this._resetHideTimer());

    return el;
  }

  private _buildInput(): HTMLInputElement {
    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = '输入消息...';
    input.style.cssText = `
      display: none;
      width: 220px;
      padding: var(--space-sm) 14px;
      background: var(--bg-input);
      backdrop-filter: var(--blur-heavy);
      -webkit-backdrop-filter: var(--blur-heavy);
      border: 1px solid var(--border-focus);
      border-radius: 20px;
      color: var(--text-white);
      font-family: var(--font-family);
      font-size: var(--font-size-base);
      outline: none;
      pointer-events: auto;
      -webkit-app-region: no-drag;
      transition: border-color var(--transition-normal);
    `;
    input.addEventListener('focus', () => {
      input.style.borderColor = 'var(--color-primary)';
    });
    input.addEventListener('blur', () => {
      input.style.borderColor = 'rgba(255,255,255,0.2)';
      // 失焦后短暂延迟隐藏
      setTimeout(() => {
        if (document.activeElement !== input) {
          input.style.display = 'none';
        }
      }, 200);
    });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && input.value.trim()) {
        const text = input.value.trim();
        this.addLine({ text, type: 'user' });
        this.onSendText?.(text);
        input.value = '';
        input.style.display = 'none';
      }
      if (e.key === 'Escape') {
        input.value = '';
        input.style.display = 'none';
        input.blur();
      }
    });
    return input;
  }

  /** 添加对话行 */
  addLine(line: DialogLine): void {
    this.lines.push(line);
    // 只显示最后一条 AI/thinking 消息
    const lastAI = [...this.lines].reverse().find(l => l.type === 'ai' || l.type === 'thinking');
    if (lastAI) {
      this._showText(lastAI.text, lastAI.type);
    }
    // 限制历史
    if (this.lines.length > 50) {
      this.lines = this.lines.slice(-30);
    }
  }

  /** 追加文本（流式） */
  appendText(text: string, type: 'ai' | 'thinking' = 'ai'): void {
    // 找最后一条同类型或追加
    const lastLine = this.lines[this.lines.length - 1];
    if (lastLine && lastLine.type === type) {
      lastLine.text += text;
    } else {
      this.lines.push({ text, type });
    }
    this._showText(
      this.lines.filter(l => l.type === 'ai' || l.type === 'thinking').map(l => l.text).join(''),
      type
    );
    // 限制历史
    if (this.lines.length > 50) {
      this.lines = this.lines.slice(-30);
    }
  }

  private _showText(text: string, type: string): void {
    const display = text.length > 80 ? text.slice(-80) + '...' : text;
    this.bubble.textContent = display || '...';
    this.bubble.style.opacity = '1';
    this.bubble.style.transform = 'translateY(0)';
    if (type === 'thinking') {
      this.bubble.style.color = 'var(--text-dim)';
      this.bubble.style.fontStyle = 'italic';
    } else {
      this.bubble.style.color = 'var(--text-primary)';
      this.bubble.style.fontStyle = 'normal';
    }
    this._resetHideTimer();
  }

  private _resetHideTimer(): void {
    this._clearHideTimer();
    // 8 秒后自动淡出
    this.hideTimer = setTimeout(() => {
      this.bubble.style.opacity = '0';
      this.bubble.style.transform = 'translateY(6px)';
    }, 8000);
  }

  private _clearHideTimer(): void {
    if (this.hideTimer !== null) {
      clearTimeout(this.hideTimer);
      this.hideTimer = null;
    }
  }

  setOnSendText(fn: (text: string) => void): void {
    this.onSendText = fn;
  }

  show(): void {
    this.container.style.opacity = '1';
  }

  hide(): void {
    this.container.style.opacity = '0';
  }

  getElement(): HTMLDivElement {
    return this.container;
  }
}

export const DIALOG_BUBBLE = new DialogBubbleImpl();
