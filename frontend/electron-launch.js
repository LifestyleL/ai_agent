/**
 * Electron 启动脚本 —— 解决 VS Code 注入 ELECTRON_RUN_AS_NODE=1 导致 Electron 以纯 Node.js 运行的问题
 * 用法: node electron-launch.js
 */
const { spawn } = require('child_process');
const path = require('path');

// 从环境中剥离 ELECTRON_RUN_AS_NODE，防止 Electron 退化为普通 Node.js
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;

const electronPath = require('electron');
const appDir = path.resolve(__dirname);

console.log('[launcher] 启动 Electron:', electronPath);
console.log('[launcher] 应用目录:', appDir);

const child = spawn(electronPath, [appDir], {
  stdio: 'inherit',
  env,
  windowsHide: false,
});

child.on('close', (code, signal) => {
  if (signal) {
    console.error(`[launcher] Electron 被信号终止: ${signal}`);
    process.exit(1);
  }
  process.exit(code ?? 0);
});

['SIGINT', 'SIGTERM', 'SIGUSR2'].forEach((sig) => {
  process.on(sig, () => {
    if (!child.killed) {
      child.kill(sig);
    }
  });
});
