// LAppAudioManager.ts
export class LAppAudioManager {
    private static _instance: LAppAudioManager;

    public static getInstance(): LAppAudioManager {
        if (!this._instance) this._instance = new LAppAudioManager();
        return this._instance;
    }

    public static releaseInstance(): void {
        if (LAppAudioManager._instance) {
            LAppAudioManager._instance.stop();
            LAppAudioManager._instance = null;
        }
    }

    private audioContext: AudioContext;
    private currentSource: AudioBufferSourceNode | null = null;
    private visemeTimeline: any[] = [];
    private playStartTime: number = 0;
    private _isPlaying: boolean = false;
    
    // 🌟 新增：音频队列与状态锁
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

    // 🌟 修改：不再直接播放，而是入队
    public async playTTS(base64Data: string, visemes: any[]) {
        this.audioQueue.push({
            audio: base64Data,
            visemes: visemes
        });

        // 如果当前没有在处理队列，则启动处理循环
        if (!this.isProcessingQueue) {
            this.processAudioQueue();
        }
    }

    // 🌟 新增：队列处理引擎（严格顺序执行）
    private async processAudioQueue() {
        this.isProcessingQueue = true;

        while (this.audioQueue.length > 0) {
            const item = this.audioQueue.shift();
            if (item) {
                // 等待这一句播放完毕，再播下一句
                await this.playSingleAudio(item.audio, item.visemes);
                // 句子和句子之间稍微留一点呼吸感（100ms）
                await new Promise(resolve => setTimeout(resolve, 500));
            }
        }

        this.isProcessingQueue = false;
    }

    // 🌟 新增：真正的单句播放逻辑（返回 Promise）
    private async playSingleAudio(base64Data: string, visemes: any[]): Promise<void> {
        return new Promise((resolve) => {
            // 先干掉上一句（防抖机制）
            this.killCurrentSource();

            try {
                // 1. base64 → Uint8Array (你原来的完美解码逻辑)
                const binaryString = atob(base64Data);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }

                // 2. PCM 16bit 单声道 22050Hz → AudioBuffer
                const sampleRate = 24000;//适配，已修改
                const numSamples = bytes.length / 2;
                const audioBuffer = this.audioContext.createBuffer(1, numSamples, sampleRate);
                const channelData = audioBuffer.getChannelData(0);
                const dataView = new DataView(bytes.buffer);
                for (let i = 0; i < numSamples; i++) {
                    channelData[i] = dataView.getInt16(i * 2, true) / 32768;
                }

                // 3. 挂载音频源
                this.currentSource = this.audioContext.createBufferSource();
                this.currentSource.buffer = audioBuffer;
                this.currentSource.connect(this.audioContext.destination);
                
                // 4. 绑定口型数据
                this.visemeTimeline = visemes;
                this.playStartTime = this.audioContext.currentTime;
                this._isPlaying = true;

                // 5. 播放结束回调：关闭当前状态，并让 Promise 放行，触发下一句
                this.currentSource.onended = () => {
                    this._isPlaying = false;
                    this.currentViseme = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 };
                    this.currentSource = null;
                    resolve(); // 🌟 通知队列：这句播完了，播下一句
                };

                // 6. 开播
                this.currentSource.start(0);
                
            } catch (e) {
                console.error("❌ [前端] 音频解码/播放失败:", e);
                this._isPlaying = false;
                this.currentSource = null;
                resolve(); // 出错了也要放行，不然队列会卡死
            }
        });
    }

    // 🌟 抽离：纯粹的停止当前发声源（不碰队列）
    private killCurrentSource() {
        if (this.currentSource) {
            try { 
                this.currentSource.onended = null; // 防止触发假结束
                this.currentSource.stop(); 
            } catch(e) {}
            this.currentSource = null;
        }
        this._isPlaying = false; 
        this.currentViseme = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 };
    }

    // 对外暴露的彻底停止方法（例如用户打断时调用）
    public stop() {
        this.killCurrentSource();
        // 停止时清空所有排队等待的音频
        this.audioQueue = [];
        this.isProcessingQueue = false;
    }

    public getIsPlaying(): boolean {
        return this._isPlaying;
    }

    /**
     * 每帧调用，按真实时间从口型表中取值 (保留你原来优秀的二分查找)
     */
    public updateViseme() {
        if (!this._isPlaying || this.visemeTimeline.length === 0) {
            this.currentViseme.aa *= 0.5;
            if (this.currentViseme.aa < 0.01) this.currentViseme.aa = 0;
            return;
        }

        const elapsed = this.audioContext.currentTime - this.playStartTime;

        // 二分查找当前时间对应的口型帧
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

        // 简单平滑，防抖动
        this.currentViseme.aa += (targetAa - this.currentViseme.aa) * 0.5;
    }
}
