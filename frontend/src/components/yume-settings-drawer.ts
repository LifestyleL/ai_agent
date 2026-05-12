/**
 * 设置抽屉 —— 右侧滑出面板，3 个 tab 子视图
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { bus, Events } from '../core/state';
import type { ProfileType, MemoryCard, DiaryEntry } from '../core/types';

type Tab = 'settings' | 'memory' | 'diary';

@customElement('yume-settings-drawer')
export class YumeSettingsDrawer extends LitElement {
  static styles = css`
    :host {
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      width: 280px;
      z-index: var(--z-settings);
      background: var(--bg-panel);
      backdrop-filter: var(--blur-heavy);
      -webkit-backdrop-filter: var(--blur-heavy);
      border-left: 1px solid var(--border-light);
      transform: translateX(100%);
      transition: transform 0.25s ease-out;
      pointer-events: none;
      -webkit-app-region: no-drag;
      display: flex;
      flex-direction: column;
      color: var(--text-secondary);
      font-family: var(--font-family);
      font-size: var(--font-size-base);
    }
    :host(.open) {
      transform: translateX(0);
      pointer-events: auto;
    }
    .tabs {
      display: flex;
      border-bottom: 1px solid var(--border-subtle);
      flex-shrink: 0;
      position: relative;
      z-index: 1;
    }
    .tab-btn {
      flex: 1;
      padding: var(--space-md) var(--space-sm);
      border: none;
      background: transparent;
      color: var(--text-muted);
      font-size: var(--font-size-sm);
      cursor: pointer;
      transition: color var(--transition-fast);
      font-family: var(--font-family);
    }
    .tab-btn.active {
      color: var(--color-primary);
      border-bottom: 2px solid var(--color-primary);
    }
    .panel {
      display: none;
      flex: 1;
      overflow-y: auto;
      padding: var(--space-lg);
      position: relative;
      z-index: 1;
    }
    .panel.active { display: block; }
    h2 {
      margin: 0 0 var(--space-md);
      color: var(--color-primary);
      font-size: var(--font-size-lg);
      font-family: var(--font-family);
    }
    /* ---- Profile Cards ---- */
    .profile-cards {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--space-sm);
      margin-bottom: var(--space-lg);
    }
    .card {
      padding: var(--space-md);
      border-radius: var(--radius-lg);
      background: var(--bg-card);
      border: 2px solid transparent;
      cursor: pointer;
      transition: border-color var(--transition-medium), background var(--transition-medium);
    }
    .card:hover { background: var(--bg-card-hover); }
    .card.selected {
      border-color: var(--color-primary);
      background: rgba(255, 119, 170, 0.12);
    }
    .card h3 { margin: 0 0 var(--space-xs); font-size: var(--font-size-sm); }
    .card p { margin: 0; font-size: var(--font-size-xs); color: var(--text-dim); }
    /* ---- Advanced ---- */
    .advanced { margin-bottom: var(--space-lg); }
    .advanced label {
      display: block;
      margin-bottom: var(--space-sm);
      font-size: var(--font-size-sm);
    }
    .advanced input[type="range"] { width: 100%; accent-color: var(--color-primary); }
    .btn {
      padding: var(--space-sm) 22px;
      border: none;
      border-radius: var(--radius-md);
      font-size: var(--font-size-base);
      cursor: pointer;
      font-family: var(--font-family);
      position: relative;
      z-index: 2;
    }
    .btn-primary { background: var(--color-primary); color: var(--text-white); }
    .btn-secondary { background: rgba(255,255,255,0.1); color: var(--text-muted); }
    /* ---- Memory ---- */
    .search-input {
      width: 100%;
      padding: var(--space-sm) var(--space-md);
      border-radius: var(--radius-md);
      border: 1px solid var(--border-default);
      background: rgba(255,255,255,0.05);
      color: var(--text-white);
      font-size: var(--font-size-base);
      outline: none;
      margin-bottom: var(--space-lg);
      box-sizing: border-box;
      font-family: var(--font-family);
      position: relative;
      z-index: 1;
    }
    .memory-grid { display: grid; gap: var(--space-sm); }
    .memory-card {
      padding: var(--space-md);
      border-radius: var(--radius-md);
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      font-size: var(--font-size-sm);
    }
    .memory-card .tags { margin-top: var(--space-xs); display: flex; gap: var(--space-xs); flex-wrap: wrap; }
    .memory-card .tag {
      font-size: var(--font-size-xs);
      padding: 2px 6px;
      border-radius: var(--radius-sm);
      background: rgba(255, 119, 170, 0.15);
      color: var(--color-primary);
    }
    /* ---- Diary ---- */
    .diary-timeline { display: flex; flex-direction: column; gap: var(--space-md); }
    .diary-entry {
      padding: var(--space-md);
      border-radius: var(--radius-md);
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      font-size: var(--font-size-sm);
    }
    .diary-entry .date { font-size: var(--font-size-xs); color: var(--text-subtle); }
    /* ---- Empty ---- */
    .empty {
      text-align: center;
      color: var(--text-subtle);
      padding: 40px var(--space-lg);
      font-size: var(--font-size-sm);
    }
    /* ---- Backdrop (click-outside-to-close) ---- */
    .backdrop {
      display: none;
    }
    :host(.open) .backdrop {
      display: block;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      z-index: -1;
      pointer-events: auto;
    }
  `;

  @state() private _open = false;
  @state() private _activeTab: Tab = 'settings';
  @state() private _profile: ProfileType = 'auto';
  @state() private _frequency = 3;
  @state() private _followUp = 3;
  @state() private _nightMode = false;
  @state() private _searchQuery = '';
  @state() private _memoryCards: MemoryCard[] = [];
  @state() private _diaryEntries: DiaryEntry[] = [];

  connectedCallback(): void {
    super.connectedCallback();
    bus.addEventListener(Events.SETTINGS_OPEN, this._openDrawer);
    bus.addEventListener(Events.SETTINGS_CLOSE, this._closeDrawer);
    bus.addEventListener(Events.MEMORY_CARDS, this._onMemoryCards as EventListener);
    bus.addEventListener(Events.DIARY_LIST, this._onDiaryList as EventListener);
    document.addEventListener('keydown', this._onEsc);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    bus.removeEventListener(Events.SETTINGS_OPEN, this._openDrawer);
    bus.removeEventListener(Events.SETTINGS_CLOSE, this._closeDrawer);
    bus.removeEventListener(Events.MEMORY_CARDS, this._onMemoryCards as EventListener);
    bus.removeEventListener(Events.DIARY_LIST, this._onDiaryList as EventListener);
    document.removeEventListener('keydown', this._onEsc);
  }

  private _onEsc = (e: KeyboardEvent): void => {
    if (e.key === 'Escape' && this._open) this._closeDrawer();
  };

  private _openDrawer = (): void => {
    this._open = true;
    this.classList.add('open');
  };

  private _closeDrawer = (): void => {
    this._open = false;
    this.classList.remove('open');
  };

  private _onMemoryCards = (e: Event): void => {
    this._memoryCards = (e as CustomEvent).detail as MemoryCard[];
  };

  private _onDiaryList = (e: Event): void => {
    this._diaryEntries = (e as CustomEvent).detail as DiaryEntry[];
  };

  private _switchTab(tab: Tab): void {
    this._activeTab = tab;
  }

  private _selectProfile(type: ProfileType): void {
    this._profile = type;
  }

  private _saveSettings(): void {
    console.log('[Settings] 保存:', {
      type: this._profile,
      frequency: this._frequency,
      followUp: this._followUp,
      nightMode: this._nightMode,
    });
    this._closeDrawer();
  }

  private get _filteredCards(): MemoryCard[] {
    if (!this._searchQuery) return this._memoryCards;
    const q = this._searchQuery.toLowerCase();
    return this._memoryCards.filter(c =>
      c.content.toLowerCase().includes(q) ||
      c.tags.some(t => t.toLowerCase().includes(q))
    );
  }

  render() {
    return html`
      <div class="backdrop" @click=${this._closeDrawer}></div>
      <div class="tabs">
        <button class="tab-btn ${this._activeTab === 'settings' ? 'active' : ''}" @click=${() => this._switchTab('settings')}>对话设置</button>
        <button class="tab-btn ${this._activeTab === 'memory' ? 'active' : ''}" @click=${() => this._switchTab('memory')}>记忆</button>
        <button class="tab-btn ${this._activeTab === 'diary' ? 'active' : ''}" @click=${() => this._switchTab('diary')}>日记</button>
      </div>
      ${this._renderSettings()} ${this._renderMemory()} ${this._renderDiary()}
    `;
  }

  private _renderSettings() {
    return html`
      <div class="panel ${this._activeTab === 'settings' ? 'active' : ''}">
        <h2>对话设置</h2>
        <div class="profile-cards">
          <div class="card ${this._profile === 'social' ? 'selected' : ''}" @click=${() => this._selectProfile('social')}>
            <h3>社交活跃型</h3><p>AI 会更主动地聊天分享</p>
          </div>
          <div class="card ${this._profile === 'busy' ? 'selected' : ''}" @click=${() => this._selectProfile('busy')}>
            <h3>忙碌型</h3><p>减少打扰，只在被呼唤时出现</p>
          </div>
          <div class="card ${this._profile === 'auto' ? 'selected' : ''}" @click=${() => this._selectProfile('auto')}>
            <h3>自动识别</h3><p>根据互动习惯自动调整</p>
          </div>
          <div class="card ${this._profile === 'quiet' ? 'selected' : ''}" @click=${() => this._selectProfile('quiet')}>
            <h3>安静陪伴型</h3><p>很少说话，静静待在旁边</p>
          </div>
        </div>
        <div class="advanced">
          <label>说话频率 <input type="range" min="0" max="5" .value=${String(this._frequency)} @input=${(e: Event) => this._frequency = Number((e.target as HTMLInputElement).value)}></label>
          <label>追问间隔 <input type="range" min="1" max="5" .value=${String(this._followUp)} @input=${(e: Event) => this._followUp = Number((e.target as HTMLInputElement).value)}></label>
          <label><input type="checkbox" .checked=${this._nightMode} @change=${(e: Event) => this._nightMode = (e.target as HTMLInputElement).checked}> 深夜勿扰</label>
        </div>
        <button class="btn btn-primary" @click=${this._saveSettings}>保存设置</button>
        <button class="btn btn-secondary" @click=${this._closeDrawer} style="margin-left:8px;">返回</button>
      </div>
    `;
  }

  private _renderMemory() {
    return html`
      <div class="panel ${this._activeTab === 'memory' ? 'active' : ''}">
        <h2>记忆管理</h2>
        <input class="search-input" type="text" placeholder="搜索记忆..." .value=${this._searchQuery} @input=${(e: Event) => this._searchQuery = (e.target as HTMLInputElement).value}>
        <div class="memory-grid">
          ${this._filteredCards.length === 0
            ? html`<div class="empty">${this._memoryCards.length === 0 ? '暂无记忆，多和 AI 聊天吧~' : '未找到匹配的记忆'}</div>`
            : this._filteredCards.map(c => html`
              <div class="memory-card">
                <div>${c.content.length > 80 ? c.content.slice(0, 80) + '...' : c.content}</div>
                <div class="tags">${c.tags.map(t => html`<span class="tag">${t}</span>`)}</div>
              </div>
            `)}
        </div>
      </div>
    `;
  }

  private _renderDiary() {
    return html`
      <div class="panel ${this._activeTab === 'diary' ? 'active' : ''}">
        <h2>日记</h2>
        <div class="diary-timeline">
          ${this._diaryEntries.length === 0
            ? html`<div class="empty">暂无日记记录</div>`
            : this._diaryEntries.map(e => html`
              <div class="diary-entry">
                <div class="date">${e.date} ${e.mood}</div>
                <div>${e.summary}</div>
              </div>
            `)}
        </div>
      </div>
    `;
  }
}
