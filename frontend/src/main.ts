/**
 * Entry point —— Live2D WebGL + LitElement App Shell
 * 最小化入口：初始化 Live2D delegate，然后挂载 <yume-app>
 */
import { LAppDelegate } from './lappdelegate';
import './components/yume-app';

window.addEventListener(
  'load',
  (): void => {
    if (!LAppDelegate.getInstance().initialize()) return;
    LAppDelegate.getInstance().run();

    // 挂载 LitElement 根组件（替代旧的散落 DOM + inline script）
    const app = document.createElement('yume-app');
    document.body.appendChild(app);
  },
  { passive: true }
);

window.addEventListener(
  'beforeunload',
  (): void => LAppDelegate.releaseInstance(),
  { passive: true }
);
