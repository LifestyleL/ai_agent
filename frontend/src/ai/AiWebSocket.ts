/**
 * AI WebSocket 桥接 —— 连接后端，收发 LIVE2D_CMD / TTS_AUDIO / 参数消息
 */
import { AiAudioManager } from "./AiAudioManager";
import { AI_IDLE } from "./AiIdleAnimator";
import { bus, Events } from "../core/state";

export class AiWebSocket {
  private static _instance: AiWebSocket;
  private _ws: WebSocket | null = null;
  private _connected = false;

  /** 后端已主动设置的参数名（空闲动画会跳过这些） */
  public backendTouched: Set<string> = new Set();

  public aiFaceParams = {
    ParamEyeLOpen: 1.0,
    ParamEyeROpen: 1.0,
    ParamMouthOpenY: 0.0,
    ParamAngleX: 0.0,
    ParamAngleY: 0.0,
    ParamAngleZ: 0.0,
    ParamHairAhoge: 0.0,
    ParamBodyAngleX: 0.0,
    ParamBodyAngleY: 0.0,
    ParamBodyAngleZ: 0.0,
    PartArmA: 0,
    PartArmB: 0,
    ParamArmLA: 1.0,
    ParamArmRA: 1.0,
    ParamArmLB: 1.0,
    ParamArmRB: 1.0,
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
  };

  public expressionQueue: string[] = [];
  public motionQueue: Array<{ group: string; no?: number }> = [];

  private static readonly EMOTION_EXPRESSION_MAP: Record<string, string> = {
    happy: 'F01',
    sad: 'F04',
    angry: 'F03',
    fear: 'F02',
    gentle: 'F01',
    serious: 'F05',
    neutral: 'F01',
  };

  private _handleCommand(d: any): void {
    if (d.cmd === 'emotion') {
      const expId = AiWebSocket.EMOTION_EXPRESSION_MAP[d.emotion] || 'F01';
      this.expressionQueue.push(expId);
      const s = d.strength || 0.5;
      // 先清空体态
      this.aiFaceParams.ParamBodyAngleX = 0;
      this.aiFaceParams.ParamBodyAngleY = 0;
      switch (d.emotion) {
        case 'sad':
          this.aiFaceParams.ParamBodyAngleY = -3.0 * s;
          break;
        case 'angry':
          this.aiFaceParams.ParamBodyAngleX = 2.0 * s;
          break;
        case 'happy':
          this.aiFaceParams.ParamBodyAngleX = 1.0 * s;
          break;
      }
      this.backendTouched.add("ParamBodyAngleX");
      this.backendTouched.add("ParamBodyAngleY");
    } else if (d.cmd === 'motion') {
      this.motionQueue.push({ group: d.motion || 'idle' });
    }
  }

  public static getInstance(): AiWebSocket {
    if (!this._instance) this._instance = new AiWebSocket();
    return this._instance;
  }

  public connect(wsUrl = "ws://localhost:8765"): void {
    try {
      console.log("[AI_WS] 正在连接 WebSocket:", wsUrl);
      this._ws = new WebSocket(wsUrl);
      this._ws.onopen = () => {
        this._connected = true;
        console.log("[AI_WS] 连接成功");
        bus.emit(Events.WS_CONNECTED);
      };
      this._ws.onmessage = (e) => this._onMessage(e.data);
      this._ws.onerror = () => {
        console.error("[AI_WS] WebSocket 连接失败，请确保后端服务已启动: python main.py");
      };
      this._ws.onclose = (event) => {
        this._connected = false;
        console.log("[AI_WS] 连接关闭, code:", event.code);
        bus.emit(Events.WS_DISCONNECTED);
      };
    } catch (e) {
      console.error("[AI_WS] 连接失败", e);
    }
  }

  private _onMessage(data: string): void {
    try {
      // 收到后端消息 → 通知空闲动画器后端在线
      AI_IDLE.markBackendActive();
      const d = JSON.parse(data);

      // 调试：打印收到的消息类型
      const msgType = d.type || (d.jsonrpc ? 'JSONRPC' : 'UNKNOWN');
      if (msgType === 'TTS_AUDIO') {
        console.log(`[AI_WS] 收到 TTS_AUDIO: audio=${d.audio_base64?.length || 0}B, visemes=${d.visemes?.length || 0}frames`);
      } else if (msgType === 'JSONRPC') {
        console.log(`[AI_WS] 收到 JSON-RPC 包装: method=${d.method}`);
      } else if (msgType === 'UNKNOWN') {
        console.log(`[AI_WS] 收到未知类型消息, keys:`, Object.keys(d));
      }

      if (d.type === "TTS_AUDIO") {
        AiAudioManager.getInstance().playTTS(d.audio_base64, d.visemes, d.text || "");
        return;
      }

      // 文本消息 → 事件总线
      if (d.type === "TEXT_CHUNK") {
        bus.emit(Events.TEXT_CHUNK, d.text || "");
        return;
      }
      if (d.type === "TEXT_THINKING") {
        bus.emit(Events.TEXT_THINKING, d.text || "");
        return;
      }

      // 记忆 / 日记数据
      if (d.type === "MEMORY_CARDS") {
        bus.emit(Events.MEMORY_CARDS, d.cards || []);
        return;
      }
      if (d.type === "DIARY_LIST") {
        bus.emit(Events.DIARY_LIST, d.entries || []);
        return;
      }

      // 打断确认
      if (d.type === "INTERRUPT_ACK") {
        bus.emit(Events.INTERRUPT_ACK);
        return;
      }

      if (d.type === "LIVE2D_CMD") {
        this._handleCommand(d);
        return;
      }

      let params = d;
      if (d.type === "PARAMS" && d.data) {
        params = d.data;
      } else if (!d.type) {
        params = d;
      }

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

      this.aiFaceParams.ParamEyeLOpen = this._clamp(eyeLeft, 0, 1);
      this.aiFaceParams.ParamEyeROpen = this._clamp(eyeRight, 0, 1);
      this.aiFaceParams.ParamMouthOpenY = this._clamp(mouth, 0, 1);
      this.aiFaceParams.ParamAngleX = this._clamp(headX, -30, 30);
      this.aiFaceParams.ParamAngleY = this._clamp(headY, -30, 30);
      this.aiFaceParams.ParamAngleZ = this._clamp(headZ, -30, 30);
      this.aiFaceParams.ParamBodyAngleX = this._clamp(bodyX, -10, 10);
      this.aiFaceParams.ParamBodyAngleY = this._clamp(bodyY, -10, 10);
      this.aiFaceParams.ParamBodyAngleZ = this._clamp(bodyZ, -10, 10);
      this.aiFaceParams.ParamHairAhoge = this._clamp(hair, -3, 3);

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

      this.aiFaceParams.ParamArmLA = this._clamp(params.ParamArmLA ?? params.armLA ?? 1, 0, 1);
      this.aiFaceParams.ParamArmRA = this._clamp(params.ParamArmRA ?? params.armRA ?? 1, 0, 1);
      this.aiFaceParams.ParamArmLB = this._clamp(params.ParamArmLB ?? params.armLB ?? 1, 0, 1);
      this.aiFaceParams.ParamArmRB = this._clamp(params.ParamArmRB ?? params.armRB ?? 1, 0, 1);

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

      // 标记后端已控制的参数（空闲动画会跳过这些）
      const paramKeys = ["ParamAngleX", "ParamAngleY", "ParamAngleZ",
        "ParamBodyAngleX", "ParamBodyAngleY", "ParamBodyAngleZ", "ParamHairAhoge",
        "ParamEyeLOpen", "ParamEyeROpen",
        "ParamArmLA", "ParamArmRA", "ParamArmLB", "ParamArmRB"];
      for (const k of paramKeys) {
        if (params[k] !== undefined) this.backendTouched.add(k);
      }
    } catch (e) {
      // ignore parse errors
    }
  }

  private _clamp(v: number, min = 0, max = 1): number {
    return Math.max(min, Math.min(max, v));
  }

  public get isConnected(): boolean { return this._connected; }

  public close(): void {
    this._ws?.close();
    this._connected = false;
  }

  // ===== 发送方法（channel + params 格式，与后端 message_router 对齐） =====

  private _send(channel: string, params: Record<string, any>): void {
    if (this._ws?.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ channel, ...params }));
    } else {
      console.warn("[AI_WS] WebSocket 未连接，无法发送");
    }
  }

  /** 发送文本消息 */
  sendText(text: string): void {
    this._send("control", { text });
  }

  /** 发送音频帧 (base64 PCM16) */
  sendAudioFrame(base64: string): void {
    this._send("audio", { type: "ASR_AUDIO", audio_base64: base64 });
  }

  /** 发送 ASR 控制 (start / stop) */
  sendAsrControl(action: "start" | "stop"): void {
    this._send("audio", { type: "ASR_CONTROL", action });
  }

  /** 发送打断指令 */
  sendInterrupt(): void {
    this._send("control", { type: "INTERRUPT" });
  }
}

export const AI_WS = AiWebSocket.getInstance();
