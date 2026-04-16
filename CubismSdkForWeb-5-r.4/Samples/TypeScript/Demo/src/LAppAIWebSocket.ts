import { LAppAudioManager } from "./LAppAudioManager";

// LAppAIWebSocket.ts
export class LAppAIWebSocket {
  private static _instance: LAppAIWebSocket;
  private _ws: WebSocket | null = null;
  private _connected = false;

  // AI 面部参数（全局实时状态）
    public aiFaceParams = {
    ParamEyeLOpen: 1.0,
    ParamEyeROpen: 1.0,
    ParamMouthOpenY: 0.0,  // 仅保留模型原生嘴部参数，删除ParamMouthOpen
    ParamAngleX: 0.0,
    ParamAngleY: 0.0,
    ParamAngleZ: 0.0,   // 新增：头部歪斜
    ParamHairAhoge: 0.0,   // 头发飘动参数
    ParamBodyAngleX: 0.0,  // 身体左右摇摆
    ParamBodyAngleY: 0.0,  // 身体上下俯仰
    ParamBodyAngleZ: 0.0,
    PartArmA: 0,   // 左手
    PartArmB: 0,   // 右手
    ParamArmLA: 1.0,   // 新版参数：左手A
    ParamArmRA: 1.0,   // 新版参数：右手A
    ParamArmLB: 1.0,   // 新版参数：左手B
    ParamArmRB: 1.0,   // 新版参数：右手B
    // 原始后端参数字段（与 animator.py 返回字典一致）
    eyeLeft: 1.0,
    eyeRight: 1.0,
    mouth: 0.0,
    headX: 0.0,
    headY: 0.0,
    headZ: 0.0,
    hair: 0.0,
    bodyX: 0.0,
    bodyY: 0.0,
    bodyZ: 0.0,
      // 身体轻微歪转
    };

  public static getInstance(): LAppAIWebSocket {
    if (!this._instance) this._instance = new LAppAIWebSocket();
    return this._instance;
  }

  // 连接 AI 服务
  public connect(wsUrl = "ws://localhost:8765"): void {
    try {
      console.log("[AI_WS] 正在连接 WebSocket:", wsUrl);
      this._ws = new WebSocket(wsUrl);
      this._ws.onopen = () => {
        this._connected = true;
        console.log("✅ AI WebSocket 连接成功");
      };
      this._ws.onmessage = (e) => this._onMessage(e.data);
      this._ws.onerror = (err) => {
        console.error("❌ WS 错误", err);
        console.error("[AI_WS] WebSocket 连接失败，请确保后端服务已启动: python main.py");
      };
      this._ws.onclose = (event) => {
        this._connected = false;
        console.log("[AI_WS] WebSocket 连接关闭，code:", event.code, "reason:", event.reason);
      };
    } catch (e) {
      console.error("❌ WS 连接失败", e);
    }
  }

  // 接收 AI 数据
  private _onMessage(data: string): void {
    // 调试日志：显示收到的消息
    // console.log("[AI_WS] 收到消息:", data.substring(0, 200) + (data.length > 200 ? "..." : ""));

    try {
      const d = JSON.parse(data);

      // 如果是音频指令，转交给全局的音频管理器
      if (d.type === "TTS_AUDIO") {
        // console.log("[AI_WS] 处理 TTS_AUDIO 消息");
        LAppAudioManager.getInstance().playTTS(d.audio_base64, d.visemes);
        return;
      }

      // 处理参数消息（可能来自PARAMS消息的data字段，或直接是参数对象）
      let params = d;
      if (d.type === "PARAMS" && d.data) {
        // console.log("[AI_WS] 处理 PARAMS 消息，参数:", JSON.stringify(d.data));
        params = d.data;
      } else if (!d.type) {
        // console.log("[AI_WS] 处理无类型参数消息，参数:", JSON.stringify(d));
        params = d;
      }

      // 参数映射，空值赋默认值，数值限制避免动作夸张
      // 优先使用新参数名（Param*），否则使用旧参数名
      const eyeLeft = params.ParamEyeLOpen ?? params.eyeLeft ?? 1;
      const eyeRight = params.ParamEyeROpen ?? params.eyeRight ?? 1;
      const mouth = params.ParamMouthOpenY ?? params.mouth ?? 0;
      const headX = params.ParamAngleX ?? params.headX ?? 0;
      const headY = params.ParamAngleY ?? params.headY ?? 0;
      const headZ = params.ParamAngleZ ?? params.headZ ?? 0;
      const hair = params.ParamHairAhoge ?? params.hair ?? 0;
      const bodyX = params.ParamBodyAngleX ?? params.bodyX ?? 0;
      const bodyY = params.ParamBodyAngleY ?? params.bodyY ?? 0;
      const bodyZ = params.ParamBodyAngleZ ?? params.bodyZ ?? 0;

      // 设置 Param* 字段（模型原生参数）
      this.aiFaceParams.ParamEyeLOpen = this._clamp(eyeLeft, 0, 1);
      this.aiFaceParams.ParamEyeROpen = this._clamp(eyeRight, 0, 1);
      this.aiFaceParams.ParamMouthOpenY = this._clamp(mouth, 0, 1);
      this.aiFaceParams.ParamAngleX = this._clamp(headX, -30, 30);   // 匹配后端范围
      this.aiFaceParams.ParamAngleY = this._clamp(headY, -30, 30);
      this.aiFaceParams.ParamAngleZ = this._clamp(headZ, -30, 30);
      this.aiFaceParams.ParamBodyAngleX = this._clamp(bodyX, -10, 10);
      this.aiFaceParams.ParamBodyAngleY = this._clamp(bodyY, -10, 10);
      this.aiFaceParams.ParamBodyAngleZ = this._clamp(bodyZ, -10, 10);
      this.aiFaceParams.ParamHairAhoge = this._clamp(hair, -3, 3);

      // 原始后端参数字段（与 animator.py 返回字典一致，使用旧参数名）
      this.aiFaceParams.eyeLeft = this._clamp(eyeLeft, 0, 1);
      this.aiFaceParams.eyeRight = this._clamp(eyeRight, 0, 1);
      this.aiFaceParams.mouth = this._clamp(mouth, 0, 1);
      this.aiFaceParams.headX = this._clamp(headX, -30, 30);
      this.aiFaceParams.headY = this._clamp(headY, -30, 30);
      this.aiFaceParams.headZ = this._clamp(headZ, -30, 30);
      this.aiFaceParams.hair = this._clamp(hair, -3, 3);
      this.aiFaceParams.bodyX = this._clamp(bodyX, -10, 10);
      this.aiFaceParams.bodyY = this._clamp(bodyY, -10, 10);
      this.aiFaceParams.bodyZ = this._clamp(bodyZ, -10, 10);

      // 【手臂控制 - 新版参数】
      // 支持直接发送ParamArmLA/ParamArmRA等参数
      this.aiFaceParams.ParamArmLA = this._clamp(params.ParamArmLA ?? params.armLA ?? 1, 0, 1);
      this.aiFaceParams.ParamArmRA = this._clamp(params.ParamArmRA ?? params.armRA ?? 1, 0, 1);
      this.aiFaceParams.ParamArmLB = this._clamp(params.ParamArmLB ?? params.armLB ?? 1, 0, 1);
      this.aiFaceParams.ParamArmRB = this._clamp(params.ParamArmRB ?? params.armRB ?? 1, 0, 1);

      // 【旧版兼容】仅在后端明确传了 PartArmA/B 时才覆盖
      if (params.PartArmA !== undefined && params.PartArmA !== null) {
        const partArmA = this._clamp(params.PartArmA, 0, 1);
        this.aiFaceParams.PartArmA = partArmA;
        this.aiFaceParams.ParamArmLA = partArmA;
        this.aiFaceParams.ParamArmLB = partArmA;
      }
      if (params.PartArmB !== undefined && params.PartArmB !== null) {
        const partArmB = this._clamp(params.PartArmB, 0, 1);
        this.aiFaceParams.PartArmB = partArmB;
        this.aiFaceParams.ParamArmRA = partArmB;
        this.aiFaceParams.ParamArmRB = partArmB;
      }

      // console.log("[AI_WS] 更新参数:", JSON.stringify(this.aiFaceParams));

    } catch (e) {
      // console.error("[AI_WS] 解析消息失败:", e, "原始数据:", data);
    }
  }

  private _clamp(v: number, min = 0, max = 1): number {
    return Math.max(min, Math.min(max, v));
  }

  public close(): void {
    this._ws?.close();
    this._connected = false;
  }
}

export const AI_WS = LAppAIWebSocket.getInstance();

(window as any).AI_WS = AI_WS;