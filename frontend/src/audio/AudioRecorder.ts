/**
 * 音频采集：getUserMedia + AudioContext → PCM16 base64 帧
 */
export class AudioRecorder {
  private stream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private onAudioData: (base64: string) => void;
  private _recording = false;

  constructor(onAudioData: (base64: string) => void) {
    this.onAudioData = onAudioData;
  }

  get recording(): boolean {
    return this._recording;
  }

  async start(): Promise<void> {
    if (this._recording) return;

    // 在 await 之前创建 AudioContext，保持在用户手势上下文中
    this.audioContext = new AudioContext({ sampleRate: 16000 });

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
    const source = this.audioContext.createMediaStreamSource(this.stream);

    // 使用 ScriptProcessorNode 作为 PCM 采集（兼容性最好）
    const processor = this.audioContext.createScriptProcessor(4096, 1, 1);
    this._recording = true;

    processor.onaudioprocess = (event: AudioProcessingEvent) => {
      if (!this._recording) return;
      const float32 = event.inputBuffer.getChannelData(0);
      const pcm16 = this.float32ToPcm16(float32);
      const base64 = this.arrayBufferToBase64(pcm16);
      this.onAudioData(base64);
    };

    source.connect(processor);
    processor.connect(this.audioContext.destination);
    this.workletNode = processor as unknown as AudioWorkletNode;

    console.log('[AudioRecorder] 录音已开始');
  }

  stop(): void {
    this._recording = false;

    if (this.workletNode) {
      this.workletNode.disconnect();
      this.workletNode = null;
    }

    if (this.audioContext) {
      this.audioContext.close().catch(() => {});
      this.audioContext = null;
    }

    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }

    console.log('[AudioRecorder] 录音已停止');
  }

  private float32ToPcm16(float32: Float32Array): ArrayBuffer {
    const buffer = new ArrayBuffer(float32.length * 2);
    const view = new DataView(buffer);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i]));
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return buffer;
  }

  private arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }
}
