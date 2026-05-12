/**
 * AI 音频管理器 —— TTS 音频队列播放 + 口型同步
 * AudioContext 立即创建，在首次用户手势中 resume。
 */
export class AiAudioManager {
    private static _instance: AiAudioManager;

    public static getInstance(): AiAudioManager {
        if (!this._instance) this._instance = new AiAudioManager();
        return this._instance;
    }

    public static releaseInstance(): void {
        if (AiAudioManager._instance) {
            AiAudioManager._instance.stop();
            AiAudioManager._instance = null;
        }
    }

    private audioContext: AudioContext;
    private currentSource: AudioBufferSourceNode | null = null;
    private visemeTimeline: any[] = [];
    private playStartTime: number = 0;
    private _isPlaying: boolean = false;

    private audioQueue: Array<{ audio: string; visemes: any[]; text: string }> = [];
    private isProcessingQueue: boolean = false;

    public currentViseme = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 };

    // 字幕同步
    public subtitleText: string = "";
    public subtitleStartTime: number = 0;
    public subtitleDuration: number = 0;

    private constructor() {
        this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
        console.log('[AI_AUDIO] AudioContext 创建，初始状态:', this.audioContext.state);

        // 在首次用户手势时 resume
        const resumeOnGesture = () => {
            if (this.audioContext.state === 'suspended') {
                this.audioContext.resume().then(() => {
                    console.log('[AI_AUDIO] AudioContext 已通过用户手势解锁');
                }).catch((e) => {
                    console.warn('[AI_AUDIO] AudioContext resume 失败:', e);
                });
            }
            document.removeEventListener('click', resumeOnGesture);
            document.removeEventListener('touchstart', resumeOnGesture);
        };
        document.addEventListener('click', resumeOnGesture);
        document.addEventListener('touchstart', resumeOnGesture);
    }

    public async playTTS(base64Data: string, visemes: any[], text: string = "") {
        console.log(`[AI_AUDIO] playTTS: audio=${base64Data?.length || 0}B, visemes=${visemes?.length || 0}frames, text="${text.slice(0,20)}...", queue=${this.audioQueue.length}`);
        this.audioQueue.push({ audio: base64Data, visemes: visemes, text: text });
        if (!this.isProcessingQueue) {
            this.processAudioQueue();
        }
    }

    private async processAudioQueue() {
        console.log('[AI_AUDIO] processAudioQueue 开始, ctx.state=' + this.audioContext.state);
        this.isProcessingQueue = true;
        while (this.audioQueue.length > 0) {
            const item = this.audioQueue.shift();
            if (item) {
                await this.playSingleAudio(item.audio, item.visemes, item.text);
                await new Promise(resolve => setTimeout(resolve, 500));
            }
        }
        console.log('[AI_AUDIO] processAudioQueue 结束');
        this.isProcessingQueue = false;
    }

    public resumeAudioContext(): void {
        console.log('[AI_AUDIO] resumeAudioContext 调用, state=' + this.audioContext.state);
        if (this.audioContext.state === 'suspended') {
            this.audioContext.resume().then(() => {
                console.log('[AI_AUDIO] resume 成功, state=' + this.audioContext.state);
            }).catch((e) => {
                console.warn('[AI_AUDIO] resume 失败:', e);
            });
        }
    }

    public getAudioContextState(): string {
        return this.audioContext.state;
    }

    private async playSingleAudio(base64Data: string, visemes: any[], text: string = ""): Promise<void> {
        return new Promise((resolve) => {
            this.killCurrentSource();

            // 确保 AudioContext 是 running 状态
            if (this.audioContext.state === 'suspended') {
                console.log('[AI_AUDIO] ctx suspended, resume...');
                this.audioContext.resume().then(() => {
                    console.log('[AI_AUDIO] resume 成功, 开始 _doPlay');
                    this._doPlay(base64Data, visemes, text, resolve);
                }).catch((e) => {
                    console.error('[AI_AUDIO] resume 失败:', e);
                    resolve();
                });
            } else {
                console.log('[AI_AUDIO] ctx state=' + this.audioContext.state + ', 直接 _doPlay');
                this._doPlay(base64Data, visemes, text, resolve);
            }
        });
    }

    private _doPlay(base64Data: string, visemes: any[], text: string, resolve: () => void): void {
        try {
            const binaryString = atob(base64Data);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            const sampleRate = 24000;
            const numSamples = bytes.length / 2;
            console.log(`[AI_AUDIO] _doPlay: bytes=${bytes.length}, numSamples=${numSamples}`);

            if (numSamples < 1) {
                console.warn('[AI_AUDIO] _doPlay: 样本数0, 跳过');
                resolve();
                return;
            }

            const audioBuffer = this.audioContext.createBuffer(1, numSamples, sampleRate);
            const channelData = audioBuffer.getChannelData(0);
            const dataView = new DataView(bytes.buffer);
            let maxSample = 0;
            for (let i = 0; i < numSamples; i++) {
                const sample = dataView.getInt16(i * 2, true) / 32768;
                channelData[i] = sample;
                if (Math.abs(sample) > maxSample) maxSample = Math.abs(sample);
            }
            console.log(`[AI_AUDIO] _doPlay: maxSample=${maxSample.toFixed(4)}, duration=${audioBuffer.duration.toFixed(2)}s`);

            this.currentSource = this.audioContext.createBufferSource();
            this.currentSource.buffer = audioBuffer;
            this.currentSource.connect(this.audioContext.destination);

            this.visemeTimeline = visemes;
            this.playStartTime = this.audioContext.currentTime;
            this._isPlaying = true;

            // 字幕同步状态
            this.subtitleText = text;
            this.subtitleStartTime = this.audioContext.currentTime;
            this.subtitleDuration = audioBuffer.duration;

            console.log('[AI_AUDIO] _doPlay: source.start(0)');
            this.currentSource.onended = () => {
                console.log('[AI_AUDIO] _doPlay: onended');
                this._isPlaying = false;
                this.currentViseme = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 };
                this.currentSource = null;
                // 字幕留 500ms 后清除（让淡出动画有时间播放）
                setTimeout(() => { this.subtitleText = ""; }, 500);
                resolve();
            };
            this.currentSource.start(0);
        } catch (e) {
            console.error("[AI_AUDIO] _doPlay 异常:", e);
            this._isPlaying = false;
            this.currentSource = null;
            this.subtitleText = "";
            resolve();
        }
    }

    private killCurrentSource() {
        if (this.currentSource) {
            try {
                this.currentSource.onended = null;
                this.currentSource.stop();
            } catch(e) {}
            this.currentSource = null;
        }
        this._isPlaying = false;
        this.currentViseme = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 };
        this.subtitleText = "";
    }

    public stop() {
        this.killCurrentSource();
        this.audioQueue = [];
        this.isProcessingQueue = false;
    }

    public getIsPlaying(): boolean {
        return this._isPlaying;
    }

    public updateViseme() {
        if (!this._isPlaying || this.visemeTimeline.length === 0) {
            this.currentViseme.aa *= 0.5;
            if (this.currentViseme.aa < 0.01) this.currentViseme.aa = 0;
            return;
        }
        const elapsed = this.audioContext.currentTime - this.playStartTime;

        let left = 0;
        let right = this.visemeTimeline.length - 1;
        while (left < right) {
            const mid = (left + right + 1) >> 1;
            if (this.visemeTimeline[mid].t <= elapsed) {
                left = mid;
            } else {
                right = mid - 1;
            }
        }
        const frame = this.visemeTimeline[left];
        const targetAa = (typeof frame.v === 'number') ? frame.v : (frame.v?.aa || 0);
        this.currentViseme.aa += (targetAa - this.currentViseme.aa) * 0.5;
    }

    /** 获取字幕同步状态：{ text, progress } 或 null */
    public getSubtitleState(): { text: string; progress: number } | null {
        if (!this.subtitleText || this.subtitleDuration <= 0) return null;
        const elapsed = this.audioContext.currentTime - this.subtitleStartTime;
        const progress = Math.min(elapsed / this.subtitleDuration, 1);
        return { text: this.subtitleText, progress };
    }
}

export const AI_AUDIO = AiAudioManager.getInstance();
