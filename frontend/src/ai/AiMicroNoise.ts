/**
 * 微表情噪声层 —— "活气系统"
 *
 * 真人面部永远不会完全静止：眉毛有心跳级起伏、眼球做微颤动、
 * 嘴角有无意识牵引。本模块用极慢随机游走模拟这些"下意识动作"。
 *
 * 数据流位置：SDK breath → 微表情噪声 → AiIdleAnimator 正弦 → 后端指令
 * 幅度全部极小（0.01~0.03），不抢戏，只消除"面具感"。
 */

class MicroNoise {
  value = 0;
  private target = 0;

  /** @param speed 目标重选频率，约每秒 speed 次（默认 0.3） */
  constructor(private speed: number = 0.003) {}

  update(dt: number): number {
    if (Math.random() < this.speed * dt) {
      this.target = (Math.random() - 0.5) * 2; // [-1, 1]
    }
    this.value += (this.target - this.value) * 0.015;
    return this.value;
  }
}

class MicroExpressionLayer {
  private browLY = new MicroNoise(0.002);
  private browRY = new MicroNoise(0.002);
  private eyeballX = new MicroNoise(0.004);
  private eyeballY = new MicroNoise(0.003);
  private mouthForm = new MicroNoise(0.002);
  private cheek = new MicroNoise(0.001);
  private eyeSmile = new MicroNoise(0.001);

  /**
   * 每帧调用，返回 { paramId: offsetValue } 映射。
   * 调用方负责通过 setParameterValueById 应用到模型。
   * 所有偏移值以 0 为基线（叠加到表情默认值上）。
   */
  apply(dt: number, backendTouched: Set<string>): Record<string, number> {
    const out: Record<string, number> = {};

    // 眉毛上下 ±0.025 — 消除眉毛"冻结感"
    if (!backendTouched.has("ParamBrowLY")) {
      out["ParamBrowLY"] = this.browLY.update(dt) * 0.025;
      out["ParamBrowRY"] = this.browRY.update(dt) * 0.022;
    }

    // 眼球微颤 ±0.03 — 模拟注视时的微型颤动
    if (!backendTouched.has("ParamEyeBallX")) {
      out["ParamEyeBallX"] = this.eyeballX.update(dt) * 0.03;
    }
    if (!backendTouched.has("ParamEyeBallY")) {
      out["ParamEyeBallY"] = this.eyeballY.update(dt) * 0.025;
    }

    // 嘴角无意识牵引 ±0.015 — 只在没说话时（mouth 未被后端控制）
    if (!backendTouched.has("ParamMouthOpenY")) {
      out["ParamMouthForm"] = this.mouthForm.update(dt) * 0.015;
    }

    // 脸颊微浮动 ±0.01
    if (!backendTouched.has("ParamCheek")) {
      out["ParamCheek"] = this.cheek.update(dt) * 0.01;
    }

    // 眼笑形态极微浮动 ±0.012
    if (!backendTouched.has("ParamEyeLSmile")) {
      out["ParamEyeLSmile"] = this.eyeSmile.update(dt) * 0.012;
      out["ParamEyeRSmile"] = this.eyeSmile.update(dt) * 0.01;
    }

    return out;
  }
}

export const MICRO_EXPRESSION = new MicroExpressionLayer();
