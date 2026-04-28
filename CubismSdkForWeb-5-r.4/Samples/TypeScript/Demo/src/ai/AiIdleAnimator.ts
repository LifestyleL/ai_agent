/**
 * AI 空闲动画调度器 —— 只管产生目标值，平滑交给 SDK 物理引擎
 *
 * 不做任何 lerp/平滑。只把原始目标写入 aiFaceParams，
 * lappmodel.update() 直接 setParameterValueById，SDK physics 负责惯性过渡。
 *
 * 两层输出：
 *   Layer A: 持续正弦漂移（头/身体大振幅）
 *   Layer B: 偶发 Burst 动作叠加
 *   定时推送 SDK Idle 动作到队列
 */
import { AI_WS } from "./AiWebSocket";

interface BurstTemplate {
  tag: string;
  target: Record<string, number>;
  attack: number;
  hold: number;
  decay: number;
}

const BURST_POOL: BurstTemplate[] = [
  { tag: 'quickLeft',   target: { ParamAngleX: -20, ParamAngleZ: 6 },                    attack: 0.25, hold: 0.3, decay: 0.7 },
  { tag: 'quickRight',  target: { ParamAngleX: 20,  ParamAngleZ: -4 },                    attack: 0.25, hold: 0.3, decay: 0.7 },
  { tag: 'tiltLeft',    target: { ParamAngleZ: -16, ParamAngleY: 5 },                     attack: 0.35, hold: 0.6, decay: 0.8 },
  { tag: 'tiltRight',   target: { ParamAngleZ: 16,  ParamAngleY: 4 },                     attack: 0.35, hold: 0.6, decay: 0.8 },
  { tag: 'lookUp',      target: { ParamAngleY: 14,  ParamBodyAngleY: 5 },                 attack: 0.30, hold: 0.5, decay: 0.9 },
  { tag: 'lookDown',    target: { ParamAngleY: -12, ParamBodyAngleY: 4 },                  attack: 0.30, hold: 0.5, decay: 0.9 },
  { tag: 'leanIn',      target: { ParamBodyAngleX: -6, ParamAngleX: 10 },                 attack: 0.40, hold: 0.8, decay: 1.2 },
  { tag: 'swayBody',    target: { ParamBodyAngleX: 7,  ParamAngleZ: 6, ParamAngleX: -10 }, attack: 0.50, hold: 1.0, decay: 1.2 },
];

export class AiIdleAnimator {
  private _time = 0;
  private _fadeFrame = 0;

  // Burst 状态机
  private _burst: BurstTemplate | null = null;
  private _burstPhase: 'idle' | 'attack' | 'hold' | 'decay' = 'idle';
  private _burstElapsed = 0;
  private _burstBase: Record<string, number> = {};
  private _burstOut: Record<string, number> = {};

  private _nextBurstIn = 3;
  private _idlePending = false;
  private _queueTimer = 0;

  private readonly RESET_THRESHOLD = 180;

  /** Idle 动作结束回调 → 自循环 */
  readonly onIdleFinished = () => {
    this._idlePending = false;
    this._queueTimer = 0.2 + Math.random() * 0.4;
  };

  update(dt: number): void {
    this._time += dt;
    this._fadeFrame++;
    const t = this._time;
    const params = AI_WS.aiFaceParams;
    const touched = AI_WS.backendTouched;

    if (this._fadeFrame > this.RESET_THRESHOLD) {
      touched.clear();
    }

    // ── Burst 状态机 ──
    this._tickBurst(dt);

    // ── 方法二：角度组合伪位移 — 侧倾+腰扭+头倾 模拟"重心压在一侧" ──
    const sway = Math.sin(t * 1.5) * 8;

    // 身体轻微旋转（向摆的方向带一点）
    if (!touched.has("ParamBodyAngleX")) {
      params.ParamBodyAngleX = sway * 0.3 + (this._burstOut.ParamBodyAngleX || 0);
    }
    // 身体侧倾（关键！让人感觉重心压在一侧腿上）
    if (!touched.has("ParamBodyAngleZ")) {
      params.ParamBodyAngleZ = sway * 0.9 + (this._burstOut.ParamBodyAngleZ || 0);
    }
    // 腰部旋转（骨盆顶出去的感觉）
    if (!touched.has("ParamWaistAngleZ")) {
      (params as any)["ParamWaistAngleZ"] = sway * 0.8;
    }
    // 头微微侧倾配合
    if (!touched.has("ParamAngleZ")) {
      params.ParamAngleZ = sway * 0.4 + (this._burstOut.ParamAngleZ || 0);
    }
    // 肩膀 — 重心侧的肩膀微耸（交替）
    if (!touched.has("ParamLeftShoulderUp")) {
      (params as any)["ParamLeftShoulderUp"] = Math.max(0, sway * 0.3);
    }
    if (!touched.has("ParamRightShoulderUp")) {
      (params as any)["ParamRightShoulderUp"] = Math.max(0, -sway * 0.3);
    }

    // 其余归零
    if (!touched.has("ParamBodyAngleY")) {
      params.ParamBodyAngleY = 0;
    }
    if (!touched.has("ParamAngleX")) {
      params.ParamAngleX = 0;
    }
    if (!touched.has("ParamAngleY")) {
      params.ParamAngleY = 0;
    }
    if (!touched.has("ParamArmAL01")) {
      (params as any)["ParamArmAL01"] = 0;
    }
    if (!touched.has("ParamArmAR01")) {
      (params as any)["ParamArmAR01"] = 0;
    }

    // ── SDK Idle 动作循环（暂时禁用，只看物理平滑效果） ──
    // if (this._fadeFrame < this.RESET_THRESHOLD && touched.size > 0) {
    //   return;
    // }
    // if (!this._idlePending) {
    //   this._queueTimer -= dt;
    //   if (this._queueTimer <= 0) {
    //     AI_WS.motionQueue.push({ group: 'Idle' });
    //     this._idlePending = true;
    //   }
    // }
  }

  // ── Burst 内部逻辑 ──
  private _tickBurst(dt: number): void {
    const touched = AI_WS.backendTouched;

    if (this._burstPhase === 'idle') {
      this._nextBurstIn -= dt;
      if (this._nextBurstIn <= 0) {
        const tpl = BURST_POOL[Math.floor(Math.random() * BURST_POOL.length)];
        const mainKeys = Object.keys(tpl.target);
        const blocked = mainKeys.every(k => touched.has(k));
        if (!blocked) {
          this._burst = tpl;
          this._burstPhase = 'attack';
          this._burstElapsed = 0;
          this._burstOut = {};
          const p = AI_WS.aiFaceParams;
          for (const k of mainKeys) {
            this._burstBase[k] = (p as any)[k] || 0;
          }
        }
        this._nextBurstIn = 3 + Math.random() * 5;
      }
      return;
    }

    if (!this._burst) return;
    const tpl = this._burst;
    const keys = Object.keys(tpl.target);
    this._burstElapsed += dt;

    if (this._burstPhase === 'attack') {
      const f = Math.min(this._burstElapsed / tpl.attack, 1.0);
      const ease = 1 - Math.pow(1 - f, 3); // easeOutCubic
      for (const k of keys) {
        if (!touched.has(k)) this._burstOut[k] = tpl.target[k] * ease;
      }
      if (f >= 1.0) { this._burstPhase = 'hold'; this._burstElapsed = 0; }
    } else if (this._burstPhase === 'hold') {
      for (const k of keys) {
        if (!touched.has(k)) this._burstOut[k] = tpl.target[k];
      }
      if (this._burstElapsed >= tpl.hold) { this._burstPhase = 'decay'; this._burstElapsed = 0; }
    } else if (this._burstPhase === 'decay') {
      const f = Math.min(this._burstElapsed / tpl.decay, 1.0);
      const ease = f < 0.5 ? 4 * f * f * f : 1 - Math.pow(-2 * f + 2, 3) / 2;
      for (const k of keys) {
        if (!touched.has(k)) {
          this._burstOut[k] = this._burstBase[k] + (tpl.target[k] - this._burstBase[k]) * (1 - ease);
        }
      }
      if (f >= 1.0) { this._burst = null; this._burstPhase = 'idle'; this._burstOut = {}; }
    }
  }

  markBackendActive(): void {
    this._fadeFrame = 0;
  }

  reset(): void {
    this._time = 0;
    this._fadeFrame = 0;
    this._idlePending = false;
    this._queueTimer = 0;
    this._burst = null;
    this._burstPhase = 'idle';
    this._burstOut = {};
    this._nextBurstIn = 3;
    AI_WS.backendTouched.clear();
  }
}

export const AI_IDLE = new AiIdleAnimator();
