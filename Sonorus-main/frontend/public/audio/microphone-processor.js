/**
 * AudioWorkletProcessor for low-latency microphone capture and Float32 -> PCM16 encoding.
 * Runs in the Web Audio rendering thread to avoid UI thread blocking.
 *
 * Resampling support:
 * If Chrome is running the AudioContext at 48 kHz (which happens when the OS
 * audio device is 48 kHz), we downsample to the target 16 kHz before encoding
 * to PCM16. Without this, Gemini receives 3x too much audio data, which builds
 * up progressively as a backlog and causes voice response latency to grow with
 * each successive turn.
 *
 * Downsampling strategy: simple decimation with a small accumulation buffer.
 * This is accurate enough for voice (not music) and adds zero perceptible delay.
 */
class MicrophoneProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();

    // Target rate Gemini expects (16000). Actual rate = AudioContext.sampleRate.
    // processorOptions are passed from the main thread via AudioWorkletNode ctor.
    const opts = (options && options.processorOptions) || {};
    this._targetRate = opts.targetSampleRate || 16000;
    this._actualRate = opts.actualSampleRate || sampleRate; // sampleRate is a global in AudioWorkletGlobalScope

    // Compute the downsample ratio. If rates match, ratio = 1 (no decimation).
    this._ratio = this._actualRate / this._targetRate;

    // Output buffer accumulates downsampled samples before encoding.
    // 512 target-rate samples = ~32 ms of audio at 16 kHz — a good balance between
    // latency and WebSocket framing overhead.
    this._outputBufferSize = 512;
    this._outputBuffer = new Float32Array(this._outputBufferSize);
    this._outputIndex = 0;

    // Fractional accumulator for accurate rational resampling.
    this._inputAccumulator = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;

    const channelData = input[0];
    if (!channelData) return true;

    const length = channelData.length;

    if (this._ratio <= 1.0) {
      // No downsampling needed — fast path (actual rate == target rate or lower).
      for (let i = 0; i < length; i++) {
        this._outputBuffer[this._outputIndex++] = channelData[i];
        if (this._outputIndex >= this._outputBufferSize) {
          this._flush();
        }
      }
    } else {
      // Downsampling path — pick one sample per `ratio` input samples.
      // We use an accumulator to handle non-integer ratios correctly.
      for (let i = 0; i < length; i++) {
        this._inputAccumulator += 1;
        if (this._inputAccumulator >= this._ratio) {
          this._inputAccumulator -= this._ratio;
          this._outputBuffer[this._outputIndex++] = channelData[i];
          if (this._outputIndex >= this._outputBufferSize) {
            this._flush();
          }
        }
      }
    }

    return true;
  }

  _flush() {
    const chunk = this._outputBuffer.slice(0, this._outputIndex);
    const pcm16Buffer = this._floatTo16BitPCM(chunk);
    const rms = this._computeRMS(chunk);
    // Zero-copy transfer of the ArrayBuffer to the main thread. `rms` rides
    // alongside as a plain number (structured-clone, not transferred) — used
    // by the main thread for local, instant barge-in detection without
    // waiting on a round trip to Gemini's own interruption signal.
    this.port.postMessage({ pcm16: pcm16Buffer, rms }, [pcm16Buffer]);
    this._outputIndex = 0;
  }

  /**
   * Root-mean-square energy of a Float32 chunk — a cheap, standard proxy for
   * "is there real signal here" vs. silence/near-silence. Used by the main
   * thread with a threshold + debounce, NOT a bare "did a chunk arrive"
   * check (that naive approach previously caused a self-interruption
   * thrashing loop when it lived server-side).
   */
  _computeRMS(float32Array) {
    if (float32Array.length === 0) return 0;
    let sumSquares = 0;
    for (let i = 0; i < float32Array.length; i++) {
      sumSquares += float32Array[i] * float32Array[i];
    }
    return Math.sqrt(sumSquares / float32Array.length);
  }

  /**
   * Converts Float32 audio samples to little-endian 16-bit signed integer PCM.
   * @param {Float32Array} float32Array
   * @returns {ArrayBuffer}
   */
  _floatTo16BitPCM(float32Array) {
    const buffer = new ArrayBuffer(float32Array.length * 2);
    const view = new DataView(buffer);
    for (let i = 0; i < float32Array.length; i++) {
      // Clamp the sample value between -1.0 and 1.0
      const s = Math.max(-1, Math.min(1, float32Array[i]));
      // Scale to 16-bit signed integer range
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return buffer;
  }
}

registerProcessor('microphone-processor', MicrophoneProcessor);
