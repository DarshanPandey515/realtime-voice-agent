class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.phase = 0
    this.samples = []
  }

  process(inputs) {
    const input = inputs[0]?.[0]
    if (!input) return true

    const step = sampleRate / 16000
    for (let i = 0; i < input.length; i += 1) {
      if (this.phase <= 0) {
        const sample = Math.max(-1, Math.min(1, input[i]))
        this.samples.push(sample < 0 ? Math.round(sample * 32768) : Math.round(sample * 32767))
      }
      this.phase -= 1
      if (this.phase <= 0) this.phase += step
    }

    while (this.samples.length >= 320) {
      const frame = Int16Array.from(this.samples.splice(0, 320))
      this.port.postMessage(frame.buffer, [frame.buffer])
    }
    return true
  }
}

registerProcessor('pcm-capture', PcmCaptureProcessor)
