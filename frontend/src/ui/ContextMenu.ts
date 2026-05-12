/**
 * 右键丝滑下拉菜单
 */
export interface MenuItem {
  id: string;
  label: string;
  type: 'toggle' | 'action' | 'separator';
  checked?: boolean;
  action?: () => void;
}

export class ContextMenu {
  private el: HTMLDivElement;
  private items: MenuItem[] = [];
  private visible = false;
  private hideTimeout: number | null = null;

  constructor(items: MenuItem[]) {
    this.items = items;
    this.el = this._build();
    // 菜单自身拦截 contextmenu，防止冒泡到 document 被全局关闭器误关
    this.el.addEventListener('contextmenu', (e) => e.stopPropagation());
    document.body.appendChild(this.el);
    this._bindGlobalClose();
  }

  private _build(): HTMLDivElement {
    const menu = document.createElement('div');
    menu.id = 'yume-context-menu';
    menu.style.cssText = `
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
    `;
    this._renderItems(menu);
    return menu;
  }

  private _renderItems(container: HTMLDivElement): void {
    container.innerHTML = '';
    this.items.forEach((item) => {
      if (item.type === 'separator') {
        const sep = document.createElement('div');
        sep.style.cssText = `
          height: 1px;
          background: var(--border-subtle);
          margin: var(--space-xs) var(--space-md);
        `;
        container.appendChild(sep);
        return;
      }

      const row = document.createElement('div');
      row.style.cssText = `
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 10px var(--space-lg);
        cursor: pointer;
        transition: background var(--transition-fast);
        white-space: nowrap;
      `;
      row.addEventListener('mouseenter', () => {
        row.style.background = 'rgba(255,255,255,0.08)';
      });
      row.addEventListener('mouseleave', () => {
        row.style.background = 'transparent';
      });

      const label = document.createElement('span');
      label.textContent = item.label;
      row.appendChild(label);

      if (item.type === 'toggle') {
        const toggle = this._createToggle(item);
        row.appendChild(toggle);
      }

      row.addEventListener('click', (e) => {
        e.stopPropagation();
        if (item.type === 'toggle') {
          item.checked = !item.checked;
          this._renderItems(container);
        }
        item.action?.();
        this.hide();
      });

      container.appendChild(row);
    });
  }

  private _createToggle(item: MenuItem): HTMLSpanElement {
    const track = document.createElement('span');
    const on = item.checked;
    track.style.cssText = `
      display: inline-block;
      width: 36px;
      height: 20px;
      border-radius: 10px;
      background: ${on ? 'var(--color-primary)' : 'rgba(255,255,255,0.15)'};
      position: relative;
      transition: background var(--transition-medium);
      flex-shrink: 0;
      margin-left: var(--space-lg);
    `;
    const knob = document.createElement('span');
    knob.style.cssText = `
      position: absolute;
      top: 2px;
      left: ${on ? '18px' : '2px'};
      width: 16px;
      height: 16px;
      border-radius: var(--radius-full);
      background: #fff;
      transition: left var(--transition-medium);
    `;
    track.appendChild(knob);
    return track;
  }

  private _bindGlobalClose(): void {
    const close = (e: Event) => {
      if (!this.visible) return;
      if (e.target && this.el.contains(e.target as Node)) return;
      if (e.target && (e.target as HTMLElement).tagName === 'CANVAS') return;
      this.hide();
    };
    document.addEventListener('click', close);
    // 滚轮关闭（用户开始滚动页面时收起菜单）
    document.addEventListener('wheel', close, { passive: true });
  }

  show(x: number, y: number): void {
    // 重新渲染以反映最新状态
    this._renderItems(this.el);

    // 先放到正确位置
    const menuW = this.el.offsetWidth || 180;
    const menuH = this.el.offsetHeight || 200;
    const maxX = window.innerWidth - menuW - 8;
    const maxY = window.innerHeight - menuH - 8;
    this.el.style.left = `${Math.min(x, maxX)}px`;
    this.el.style.top = `${Math.min(y, maxY)}px`;

    // 动画从鼠标位置方向展开
    this.el.style.transformOrigin = 'top center';
    this.el.style.opacity = '1';
    this.el.style.transform = 'scale(1)';
    this.visible = true;
  }

  hide(): void {
    if (!this.visible) return;
    this.el.style.opacity = '0';
    this.el.style.transform = 'scale(0.85)';
    this.visible = false;
  }

  updateItems(items: MenuItem[]): void {
    this.items = items;
    if (this.visible) {
      this._renderItems(this.el);
    }
  }

  isVisible(): boolean {
    return this.visible;
  }
}
