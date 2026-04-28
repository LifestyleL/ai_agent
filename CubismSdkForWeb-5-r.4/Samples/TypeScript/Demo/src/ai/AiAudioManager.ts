/**
 * AI 音频管理器 —— TTS 音频队列播放 + 口型同步
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

    private audioQueue: Array<{ audio: string; visemes: any[] }> = [];
    private isProcessingQueue: boolean = false;

    public currentViseme = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 };

    private constructor() {
        this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();

        if (this.audioContext.state === 'suspended') {
            const resumeAudio = () => {
                this.audioContext.resume();
                document.removeEventListener('click', resumeAudio);
                document.removeEventListener('touchstart', resumeAudio);
            };
            document.addEventListener('click', resumeAudio);
            document.addEventListener('touchstart', resumeAudio);
        }
    }

    public async playTTS(base64Data: string, visemes: any[]) {
        this.audioQueue.push({ audio: base64Data, visemes: visemes });
        if (!this.isProcessingQueue) {
            this.processAudioQueue();
        }
    }

    private async processAudioQueue() {
        this.isProcessingQueue = true;
        while (this.audioQueue.length > 0) {
            const item = this.audioQueue.shift();
            if (item) {
                await this.playSingleAudio(item.audio, item.visemes);
                await new Promise(resolve => setTimeout(resolve, 500));
            }
        }
        this.isProcessingQueue = false;
    }

    private async playSingleAudio(base64Data: string, visemes: any[]): Promise<void> {
        return new Promise((resolve) => {
            this.killCurrentSource();
            try {
                const binaryString = atob(base64Data);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                const sampleRate = 24000;
                const numSamples = bytes.length / 2;
                const audioBuffer = this.audioContext.createBuffer(1, numSamples, sampleRate);
                const channelData = audioBuffer.getChannelData(0);
                const dataView = new DataView(bytes.buffer);
                for (let i = 0; i < numSamples; i++) {
                    channelData[i] = dataView.getInt16(i * 2, true) / 32768;
                }
                this.currentSource = this.audioContext.createBufferSource();
                this.currentSource.buffer = audioBuffer;
                this.currentSource.connect(this.audioContext.destination);

                this.visemeTimeline = visemes;
                this.playStartTime = this.audioContext.currentTime;
                this._isPlaying = true;

                this.currentSource.onended = () => {
                    this._isPlaying = false;
                    this.currentViseme = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 };
                    this.currentSource = null;
                    resolve();
                };
                this.currentSource.start(0);
            } catch (e) {
                console.error("[AI_AUDIO] 播放失败:", e);
                this._isPlaying = false;
                this.currentSource = null;
                resolve();
            }
        });
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
}

export const AI_AUDIO = AiAudioManager.getInstance();
