import { MicVAD, type RealTimeVADOptions } from '@ricky0123/vad-web';

export type Speaker = 'USER' | 'COUNTERPARTY';

export type CaptureState = 'idle' | 'starting' | 'capturing' | 'stopping' | 'error';
export type PlaybackState = 'idle' | 'initializing' | 'ready' | 'error';

export interface AudioManagerConfig {
  silenceDebounceMs?: number;
  captureSampleRate?: number;
  playbackSampleRate?: number;
  vadOptions?: Partial<RealTimeVADOptions>;
}

export interface CaptureCallbacks {
  onChunk: (buffer: ArrayBuffer) => void;
  onSilence?: () => void;
  onSpeech?: () => void;
  onUtteranceStart?: (utterance: { utteranceId: string; startedAt: number }) => void;
  onUtteranceEnd?: (utterance: {
    utteranceId: string;
    startedAt: number;
    endedAt: number;
    durationMs: number;
    rms: number;
  }) => void;
  onStateChange?: (state: CaptureState) => void;
  onError?: (error: AudioManagerError) => void;
}

export interface PlaybackCallbacks {
  onPlaybackStarted?: () => void;
  onPlaybackStopped?: () => void;
}

export class AudioManagerError extends Error {
  constructor(
    message: string,
    public readonly code: AudioErrorCode,
    public readonly cause?: unknown
  ) {
    super(message);
    this.name = 'AudioManagerError';
  }
}

export enum AudioErrorCode {
  CONTEXT_CREATION_FAILED = 'CONTEXT_CREATION_FAILED',
  WORKLET_LOAD_FAILED = 'WORKLET_LOAD_FAILED',
  MIC_ACCESS_DENIED = 'MIC_ACCESS_DENIED',
  CAPTURE_NOT_STARTED = 'CAPTURE_NOT_STARTED',
  PLAYBACK_NOT_INITIALIZED = 'PLAYBACK_NOT_INITIALIZED',
  INVALID_STATE = 'INVALID_STATE',
  CONTEXT_SUSPENDED = 'CONTEXT_SUSPENDED',
}

export class AudioWorkletManager {
  private readonly cfg: Required<AudioManagerConfig> = {
    silenceDebounceMs: 800,
    captureSampleRate: 16000,
    playbackSampleRate: 24000,
    vadOptions: {},
  };

  private captureState: CaptureState = 'idle';
  private playbackState: PlaybackState = 'idle';
  private _bypassVAD = false;

  // Pre-speech ring buffer — stores the last PRE_SPEECH_FRAMES audio frames so
  // they can be flushed at the start of a new utterance, preventing first-word clipping.
  private preSpeechBuffer: ArrayBuffer[] = [];
  private readonly PRE_SPEECH_FRAMES = 16; // ~480ms at 30ms frames

  private captureCtx: AudioContext | null = null;
  private captureNode: AudioWorkletNode | null = null;
  private micStream: MediaStream | null = null;
  private browserVad: MicVAD | null = null;
  private isSpeaking = false;
  private currentUtteranceId: string | null = null;
  private currentUtteranceStartedAt: number | null = null;
  private currentUtteranceRms = 0;

  private playbackCtx: AudioContext | null = null;
  private playbackNode: AudioWorkletNode | null = null;
  private playbackCallbacks: PlaybackCallbacks | null = null;

  private callbacks: CaptureCallbacks | null = null;

  constructor(config: AudioManagerConfig = {}) {
    Object.assign(this.cfg, config);
  }

  setPlaybackCallbacks(callbacks: PlaybackCallbacks | null): void {
    this.playbackCallbacks = callbacks;
  }

  async startCapture(callbacks: CaptureCallbacks): Promise<void> {
    if (this.captureState !== 'idle' && this.captureState !== 'error') {
      throw new AudioManagerError(
        `Cannot start capture in state "${this.captureState}"`,
        AudioErrorCode.INVALID_STATE
      );
    }

    this.callbacks = callbacks;
    this.setCaptureState('starting');

    try {
      this.captureCtx = await this.createAudioContext(this.cfg.captureSampleRate);
      await this.loadWorklet(this.captureCtx, '/worklets/pcm-processor.js');

      this.micStream = await this.requestMicrophone();
      if (!this._bypassVAD) {
        this.browserVad = await this.createBrowserVad(this.micStream);
      }

      const source = this.captureCtx.createMediaStreamSource(this.micStream);
      this.captureNode = new AudioWorkletNode(this.captureCtx, 'pcm-capture-processor');
      this.captureNode.port.onmessage = this.handleCaptureMessage;

      source.connect(this.captureNode);
      this.captureNode.connect(this.captureCtx.destination);

      this.browserVad?.start();
      this.setCaptureState('capturing');
    } catch (err) {
      this.setCaptureState('error');
      const wrapped = this.wrapError(err);
      this.callbacks?.onError?.(wrapped);
      await this.cleanupCaptureResources();
      throw wrapped;
    }
  }

  stopCapture(): void {
    if (this.captureState === 'idle') {
      return;
    }
    this.setCaptureState('stopping');
    void this.cleanupCaptureResources().finally(() => {
      this.setCaptureState('idle');
    });
  }

  async startRecording(durationMs: number): Promise<ArrayBuffer | null> {
    if (this.captureState !== 'idle') {
      console.error('Cannot start one-shot recording while another capture is active.');
      return null;
    }

    return new Promise(async (resolve, reject) => {
      const recordedChunks: ArrayBuffer[] = [];

      const tempCallbacks: CaptureCallbacks = {
        onChunk: (chunk) => {
          recordedChunks.push(chunk);
        },
        onError: (error) => {
          this.stopCapture();
          reject(error);
        },
      };

      try {
        await this.startCapture(tempCallbacks);

        setTimeout(() => {
          this.stopCapture();

          const totalLength = recordedChunks.reduce((acc, chunk) => acc + chunk.byteLength, 0);
          const combined = new Uint8Array(totalLength);
          let offset = 0;
          for (const chunk of recordedChunks) {
            combined.set(new Uint8Array(chunk), offset);
            offset += chunk.byteLength;
          }

          resolve(combined.buffer);
        }, durationMs);
      } catch (error) {
        reject(error);
      }
    });
  }

  async initPlayback(): Promise<void> {
    if (this.playbackState === 'ready') {
      return;
    }
    if (this.playbackState === 'initializing') {
      throw new AudioManagerError(
        'Playback initialization already in progress',
        AudioErrorCode.INVALID_STATE
      );
    }

    this.playbackState = 'initializing';

    try {
      this.playbackCtx = await this.createAudioContext(this.cfg.playbackSampleRate);
      await this.loadWorklet(this.playbackCtx, '/worklets/pcm-playback-processor.js');

      this.playbackNode = new AudioWorkletNode(this.playbackCtx, 'pcm-playback-processor');
      this.playbackNode.port.onmessage = this.handlePlaybackMessage;
      this.playbackNode.connect(this.playbackCtx.destination);
      this.playbackState = 'ready';
    } catch (err) {
      this.playbackState = 'error';
      throw this.wrapError(err);
    }
  }

  playChunk(chunk: ArrayBuffer): void {
    if (!this.playbackNode || this.playbackState !== 'ready') {
      console.warn('[AudioManager] playChunk ignored - playback not ready');
      return;
    }
    if (!(chunk instanceof ArrayBuffer) || chunk.byteLength === 0) {
      console.warn('[AudioManager] playChunk received empty or invalid buffer');
      return;
    }
    this.playbackNode.port.postMessage(chunk, [chunk]);
  }

  clearQueue(): void {
    if (!this.playbackNode || this.playbackState !== 'ready') {
      return;
    }
    this.playbackNode.port.postMessage({ type: 'clear' });
  }

  async resumeContexts(): Promise<void> {
    await Promise.allSettled([
      this.captureCtx?.state === 'suspended' ? this.captureCtx.resume() : Promise.resolve(),
      this.playbackCtx?.state === 'suspended' ? this.playbackCtx.resume() : Promise.resolve(),
    ]);
  }

  async cleanup(): Promise<void> {
    await this.cleanupCaptureResources();
    await this.teardownPlayback();
    this.callbacks = null;
  }

  get isCapturing(): boolean {
    return this.captureState === 'capturing';
  }

  setBypassVAD(bypass: boolean): void {
    this._bypassVAD = bypass;
    this.preSpeechBuffer = [];
    if (bypass) {
      this.isSpeaking = true;
      this.currentUtteranceId = null;
      this.currentUtteranceStartedAt = null;
      this.currentUtteranceRms = 0;
      return;
    }
    this.isSpeaking = false;
    this.currentUtteranceId = null;
    this.currentUtteranceStartedAt = null;
    this.currentUtteranceRms = 0;
  }

  get isPlaybackReady(): boolean {
    return this.playbackState === 'ready';
  }

  get currentCaptureState(): CaptureState {
    return this.captureState;
  }

  get currentPlaybackState(): PlaybackState {
    return this.playbackState;
  }

  private handleCaptureMessage = (event: MessageEvent): void => {
    const buffer = event.data as ArrayBuffer;
    if (!buffer || buffer.byteLength === 0) {
      return;
    }

    const int16 = new Int16Array(buffer);
    let isAllZeros = true;
    for (let i = 0; i < int16.length; i++) {
      if (int16[i] !== 0) {
        isAllZeros = false;
        break;
      }
    }
    if (isAllZeros) {
      return;
    }

    const frameRms = this.calculateRms(int16);
    this.currentUtteranceRms = Math.max(this.currentUtteranceRms, frameRms);

    if (!this._bypassVAD && !this.isSpeaking) {
      // Keep a rolling pre-speech buffer so handleVadSpeechStart can replay it,
      // preventing the first word from being clipped.
      this.preSpeechBuffer.push(buffer.slice(0));
      if (this.preSpeechBuffer.length > this.PRE_SPEECH_FRAMES) {
        this.preSpeechBuffer.shift();
      }
    }

    if (this._bypassVAD || this.isSpeaking) {
      this.callbacks?.onChunk(buffer);
    }
  };

  private handlePlaybackMessage = (event: MessageEvent): void => {
    const message = event.data as { type?: string } | undefined;
    if (!message || typeof message !== 'object') {
      return;
    }

    if (message.type === 'playback_started') {
      this.playbackCallbacks?.onPlaybackStarted?.();
      return;
    }

    if (message.type === 'playback_stopped') {
      this.playbackCallbacks?.onPlaybackStopped?.();
    }
  };

  private handleVadSpeechStart = (): void => {
    if (this._bypassVAD || this.isSpeaking) {
      return;
    }

    this.isSpeaking = true;
    this.currentUtteranceId = crypto.randomUUID();
    // Back-date start to the beginning of the pre-speech buffer so duration is accurate.
    this.currentUtteranceStartedAt = Date.now() - this.preSpeechBuffer.length * 30;
    this.currentUtteranceRms = 0;

    // Flush pre-speech ring buffer so the first word is not clipped.
    for (const frame of this.preSpeechBuffer) {
      this.callbacks?.onChunk(frame);
    }
    this.preSpeechBuffer = [];

    this.callbacks?.onSpeech?.();
    this.callbacks?.onUtteranceStart?.({
      utteranceId: this.currentUtteranceId,
      startedAt: this.currentUtteranceStartedAt,
    });
  };

  private handleVadSpeechEnd = (): void => {
    if (this._bypassVAD) {
      return;
    }

    if (!this.isSpeaking) {
      this.preSpeechBuffer = [];
      this.callbacks?.onSilence?.();
      return;
    }

    const endedAt = Date.now();
    const utteranceId = this.currentUtteranceId;
    const startedAt = this.currentUtteranceStartedAt;
    const durationMs = startedAt ? endedAt - startedAt : 0;

    this.isSpeaking = false;
    this.preSpeechBuffer = [];

    if (utteranceId && startedAt) {
      this.callbacks?.onUtteranceEnd?.({
        utteranceId,
        startedAt,
        endedAt,
        durationMs,
        rms: this.currentUtteranceRms,
      });
    }

    this.currentUtteranceId = null;
    this.currentUtteranceStartedAt = null;
    this.currentUtteranceRms = 0;
    this.callbacks?.onSilence?.();
  };

  private async createBrowserVad(stream: MediaStream): Promise<MicVAD> {
    const evalVadOptions =
      typeof window !== 'undefined'
        ? (window as typeof window & { __audioEvalVadOptions?: Partial<RealTimeVADOptions> })
            .__audioEvalVadOptions
        : undefined;

    return MicVAD.new({
      stream,
      baseAssetPath: '/vad/',
      onnxWASMBasePath: '/onnx/',
      positiveSpeechThreshold: 0.55,
      negativeSpeechThreshold: 0.35,
      redemptionFrames: 6,
      preSpeechPadFrames: 12,
      minSpeechFrames: 3,
      ...this.cfg.vadOptions,
      ...(evalVadOptions || {}),
      onSpeechStart: this.handleVadSpeechStart,
      onSpeechEnd: () => {
        this.handleVadSpeechEnd();
      },
      onVADMisfire: () => {
        this.handleVadSpeechEnd();
      },
    });
  }

  private calculateRms(samples: Int16Array): number {
    let sum = 0;
    for (let i = 0; i < samples.length; i++) {
      sum += samples[i] * samples[i];
    }
    return Math.sqrt(sum / samples.length);
  }

  private async createAudioContext(sampleRate: number): Promise<AudioContext> {
    const Ctor: typeof AudioContext =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;

    if (!Ctor) {
      throw new AudioManagerError('AudioContext not supported', AudioErrorCode.CONTEXT_CREATION_FAILED);
    }

    const ctx = new Ctor({ sampleRate, latencyHint: 'interactive' });

    if (ctx.state === 'suspended') {
      await ctx.resume();
    }

    return ctx;
  }

  private async loadWorklet(ctx: AudioContext, url: string): Promise<void> {
    try {
      await ctx.audioWorklet.addModule(url);
    } catch (err) {
      throw new AudioManagerError(
        `Failed to load worklet: ${url}`,
        AudioErrorCode.WORKLET_LOAD_FAILED,
        err
      );
    }
  }

  private async requestMicrophone(): Promise<MediaStream> {
    try {
      return await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
        video: false,
      });
    } catch (err) {
      throw new AudioManagerError(
        'Microphone access denied or unavailable',
        AudioErrorCode.MIC_ACCESS_DENIED,
        err
      );
    }
  }

  private async cleanupCaptureResources(): Promise<void> {
    this._bypassVAD = false;
    this.preSpeechBuffer = [];
    this.browserVad?.destroy();
    this.browserVad = null;
    this.isSpeaking = false;
    this.currentUtteranceId = null;
    this.currentUtteranceStartedAt = null;
    this.currentUtteranceRms = 0;

    this.captureNode?.disconnect();
    this.captureNode = null;

    this.micStream?.getTracks().forEach((track) => track.stop());
    this.micStream = null;

    if (this.captureCtx) {
      await this.captureCtx.close();
    }
    this.captureCtx = null;
  }

  private async teardownPlayback(): Promise<void> {
    if (this.playbackNode) {
      this.playbackNode.port.onmessage = null;
    }
    this.playbackNode?.disconnect();
    this.playbackNode = null;
    if (this.playbackCtx) {
      await this.playbackCtx.close();
    }
    this.playbackCtx = null;
    this.playbackState = 'idle';
  }

  private setCaptureState(state: CaptureState): void {
    this.captureState = state;
    this.callbacks?.onStateChange?.(state);
  }

  private wrapError(err: unknown): AudioManagerError {
    if (err instanceof AudioManagerError) {
      return err;
    }
    const message = err instanceof Error ? err.message : String(err);
    return new AudioManagerError(message, AudioErrorCode.CONTEXT_CREATION_FAILED, err);
  }
}

function int16ToFloat32(int16: Int16Array): Float32Array {
  const out = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    out[i] = int16[i] / 32768.0;
  }
  return out;
}
