import logger from '../utils/logger';
import { v4 as uuidv4 } from 'uuid';
import { AudioWorkletManager } from './audio-worklet-manager';

/**
 * NegotiationWebSocket
 * Bridges the AudioWorkletManager streams with the backend WebSocket.
 *
 * Handles bidirectional separation of text (JSON control signals)
 * and binary (raw PCM audio) frames.
 */
export class NegotiationWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private audioManager: AudioWorkletManager;
  private messageListeners: Set<(message: any) => void> = new Set();
  private closeListeners: Set<() => void> = new Set();
  private errorListeners: Set<(error: any) => void> = new Set();
  private pendingConnection: { resolve: () => void, reject: (reason?: any) => void } | null = null;
  private correlationId: string = '';

  constructor(url: string, audioManager: AudioWorkletManager) {
    this.url = url;
    this.audioManager = audioManager;
    this.audioManager.setPlaybackCallbacks({
      onPlaybackStopped: () => {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
          this.sendControl('AI_PLAYBACK_DONE', {});
        }
      },
    });
  }

  get isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  get isConnecting(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.CONNECTING;
  }

  connect(): Promise<void> {
    if (this.pendingConnection) {
      return Promise.reject(new Error('WebSocket connection already pending'));
    }
    if (this.isConnected) {
      return Promise.resolve();
    }

    this.correlationId = uuidv4();
    logger.info({ correlationId: this.correlationId }, 'WebSocket connecting');

    return new Promise((resolve, reject) => {
      this.pendingConnection = { resolve, reject };
      this.ws = new WebSocket(this.url);

      // We expect binary data for audio
      this.ws.binaryType = 'arraybuffer';

      this.ws.onopen = () => {
        logger.info({ correlationId: this.correlationId }, 'WebSocket connected');
        if (this.pendingConnection) {
          this.pendingConnection.resolve();
          this.pendingConnection = null;
        }
      };

      this.ws.onerror = (error) => {
        logger.error({ correlationId: this.correlationId, error }, 'WebSocket error');
        if (this.pendingConnection) {
          this.pendingConnection.reject(error);
          this.pendingConnection = null;
        } else {
          // Propagate errors occurring after initial connection
          this.errorListeners.forEach(listener => listener(error));
        }
      };

      this.ws.onclose = () => {
        logger.info({ correlationId: this.correlationId }, 'WebSocket closed');
        if (this.pendingConnection) {
          this.pendingConnection.reject(new Error('WebSocket closed before connection established'));
          this.pendingConnection = null;
        }
        this.closeListeners.forEach(listener => listener());
      };

      this.ws.onmessage = (event: MessageEvent) => {
        if (event.data instanceof ArrayBuffer || event.data instanceof Blob) {
          // BINARY frame = PCM audio from Gemini (24kHz Int16)
          const size = event.data instanceof ArrayBuffer ? event.data.byteLength : event.data.size;
          logger.debug({ correlationId: this.correlationId, size }, 'WebSocket received binary message');
          if (event.data instanceof Blob) {
            event.data.arrayBuffer().then(buf => this.audioManager.playChunk(buf));
          } else {
            this.audioManager.playChunk(event.data as ArrayBuffer);
          }
        } else {
          // TEXT frame = JSON control message
          try {
            const message = JSON.parse(event.data as string);
            logger.debug({ correlationId: this.correlationId, message }, 'WebSocket received text message');
            this.messageListeners.forEach(listener => listener(message));
          } catch (e) {
            logger.error({ correlationId: this.correlationId, error: e }, 'Failed to parse WebSocket message');
          }
        }
      };
    });
  }

  disconnect(): void {
    if (this.pendingConnection) {
      this.pendingConnection = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  /**
   * Send a raw 16kHz Int16 PCM ArrayBuffer directly as a binary frame
   */
  sendAudioChunk(buffer: ArrayBuffer): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      // Reduced logging during enrollment to prevent resource exhaustion
      // logger.debug({ correlationId: this.correlationId, size: buffer.byteLength }, 'WebSocket sending audio chunk');
      this.ws.send(buffer);
    } else {
      logger.warn({ correlationId: this.correlationId }, 'WebSocket not open, cannot send audio');
    }
  }

  /**
   * Send a standard JSON control message (e.g. strategy choices, start commands)
   */
  sendControl(type: string, payload: any): void {
    // Skip verbose logging for high-frequency vision frames to avoid console flooding
    if (type !== 'VISION_FRAME') {
      console.log('[WebSocket] sendControl called:', type, payload);
    }
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const message = { type, payload };
      if (type !== 'VISION_FRAME') {
        console.log('[WebSocket] Sending:', JSON.stringify(message));
        logger.debug({ correlationId: this.correlationId, message }, 'WebSocket sending control message');
      }
      this.ws.send(JSON.stringify(message));
    } else {
      logger.warn({ correlationId: this.correlationId, type }, `Cannot send ${type} - WebSocket not open (readyState: ${this.ws?.readyState})`);
    }
  }

  sendUtteranceEnd(payload: {
    utterance_id: string;
    started_at: number;
    ended_at: number;
    duration_ms: number;
    rms: number;
  }): void {
    this.sendControl('UTTERANCE_END', payload);
  }

  onMessage(listener: (message: any) => void): () => void {
    this.messageListeners.add(listener);
    return () => this.messageListeners.delete(listener);
  }

  onClose(listener: () => void): () => void {
    this.closeListeners.add(listener);
    return () => this.closeListeners.delete(listener);
  }

  onError(listener: (error: any) => void): () => void {
    this.errorListeners.add(listener);
    return () => this.errorListeners.delete(listener);
  }

  /**
   * Resume audio contexts (needed after user gestures to prevent corrupted frames)
   */
  async resumeAudioContexts(): Promise<void> {
    if (this.audioManager) {
      await this.audioManager.resumeContexts();
    }
  }
}
