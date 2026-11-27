class NovaMic extends AudioWorkletProcessor {
  constructor() {
    super();
    this.frame = new Int16Array(320);
    this.index = 0;
    this.phase = 0;
    this.sum = 0;
    this.samples = 0;
  }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;
    for (const sample of input) {
      this.sum += sample;
      this.samples += 1;
      this.phase += 16000;
      if (this.phase < sampleRate) continue;
      this.phase -= sampleRate;
      const value = this.sum / this.samples;
      this.frame[this.index++] = Math.max(-1, Math.min(1, value)) * 32767;
      this.sum = 0;
      this.samples = 0;
      if (this.index === this.frame.length) {
        this.port.postMessage(this.frame.buffer, [this.frame.buffer]);
        this.frame = new Int16Array(320);
        this.index = 0;
      }
    }
    return true;
  }
}
registerProcessor("nova-mic", NovaMic);
