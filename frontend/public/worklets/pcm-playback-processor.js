/**
 * PCM Playback Processor
 * Runs on dedicated AudioWorklet thread.
 * Receives Int16 PCM chunks from main thread and plays them at 24kHz.
 * Implements a queue with overflow protection and continuous playback.
 */
class PCMPlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._queue = [];
    // Increase max buffer to 60 seconds to handle fast AI generation
    this._maxQueueBytes = 24000 * 2 * 60; // max 60 seconds of audio buffered
    this._minBufferSamples = 1200; // 50ms minimum buffer - start playing quickly
    this._isPlaying = false;
    this._silenceFrames = 0;
    this._maxSilenceFrames = 240; // about 1.3s of silence tolerance at 24kHz

    this.port.onmessage = (event) => {
      if (event.data && typeof event.data === 'object' && event.data.type === 'clear') {
        const wasPlaying = this._isPlaying || this._queue.length > 0;
        this._queue = [];
        this._isPlaying = false;
        this._silenceFrames = 0;
        if (wasPlaying) {
          this.port.postMessage({ type: 'playback_stopped' });
        }
        return;
      }

      const totalQueued = this._queue.reduce((sum, buf) => sum + buf.length, 0);
      if (totalQueued * 2 > this._maxQueueBytes) {
        // Drop oldest chunk to prevent unbounded queue growth
        this._queue.shift();
      }
      const chunk = new Int16Array(event.data);
      this._queue.push(chunk);
      
      // Start playing as soon as we have any audio
      const queuedSamples = this._queue.reduce((sum, buf) => sum + buf.length, 0);
      if (!this._isPlaying && queuedSamples >= this._minBufferSamples) {
        this._isPlaying = true;
        this._silenceFrames = 0;
        this.port.postMessage({ type: 'playback_started' });
      }
    };
  }

  process(inputs, outputs, parameters) {
    const output = outputs[0][0]; // mono channel
    
    // Don't start playing until we have minimum buffer
    if (!this._isPlaying) {
      output.fill(0);
      return true;
    }
    
    let offset = 0;

    while (offset < output.length && this._queue.length > 0) {
      const chunk = this._queue[0];
      const remaining = output.length - offset;
      const toCopy = Math.min(chunk.length, remaining);

      for (let i = 0; i < toCopy; i++) {
        // Convert Int16 → Float32
        output[offset + i] = chunk[i] / (chunk[i] < 0 ? 0x8000 : 0x7fff);
      }

      if (toCopy === chunk.length) {
        this._queue.shift();
      } else {
        this._queue[0] = chunk.subarray(toCopy);
      }

      offset += toCopy;
    }

    // Fill remaining output with silence if queue is empty
    if (offset < output.length) {
      for (let i = offset; i < output.length; i++) {
        output[i] = 0;
      }
      this._silenceFrames++;
      
      // Only stop playing after sustained silence
      // This keeps playback running between chunks that arrive with gaps
      if (this._silenceFrames > this._maxSilenceFrames) {
        this._isPlaying = false;
        this._silenceFrames = 0;
        this.port.postMessage({ type: 'playback_stopped' });
      }
    } else {
      // Reset silence counter when we have audio
      this._silenceFrames = 0;
    }

    return true;
  }
}

registerProcessor('pcm-playback-processor', PCMPlaybackProcessor);
