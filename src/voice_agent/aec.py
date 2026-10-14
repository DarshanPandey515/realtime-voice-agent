"""Echo cancellation, so the mic stops hearing the agent's own speaker.

Without this the agent transcribes itself, interrupts itself, and barge-in
becomes actively worse than having none at all.
"""

import threading

import numpy as np
from pywebrtc_audio import AudioProcessor


class EchoCancellation:
    """Subtracts what we are playing from what the mic hears.

    Needs the playback audio as a far-end reference, so `StreamingTTS` tees
    every chunk it writes to the speaker into `add_playback`. Capture and
    reference then advance in lockstep, one capture chunk per call, which
    keeps them roughly time-aligned; AEC3's own delay estimator copes with
    the rest.

    The reference is popped rather than peeked, so it must advance at the
    capture rate. Playback is bursty, hence the zero padding when the buffer
    runs dry.
    """

    def __init__(self, sample_rate: int, reference_ms: int = 1000,
                 stream_delay_ms: int = 0):
        self.sample_rate = sample_rate
        # Keep more reference than one chunk so AEC3 has history to estimate
        # delay against, even if playback pauses.
        self._capacity = sample_rate * reference_ms // 1000
        self._lock = threading.Lock()
        self._reference = np.zeros(0, dtype=np.int16)
        self._processor = AudioProcessor(
            sample_rate=sample_rate,
            num_channels=1,
            echo_cancellation=True,
            noise_suppression=False,
            high_pass_filter=True,
            auto_gain_control=False,
            stream_delay_ms=stream_delay_ms,
        )

    def add_playback(self, pcm: bytes) -> None:
        """Record audio on its way to the speaker as the far-end reference."""
        chunk = np.frombuffer(pcm, dtype=np.int16)
        with self._lock:
            self._reference = np.concatenate((self._reference, chunk))
            if len(self._reference) > self._capacity:
                self._reference = self._reference[-self._capacity:]

    def _take_reference(self, samples: int) -> np.ndarray:
        with self._lock:
            ref = self._reference
            if len(ref) < samples:
                ref = np.pad(ref, (0, samples - len(ref)))
                self._reference = ref
            else:
                self._reference = ref[samples:]
            return ref[:samples]

    def process(self, capture: bytes) -> bytes:
        """Return `capture` with the agent's own voice removed."""
        mic = np.frombuffer(capture, dtype=np.int16)
        cleaned = self._processor.process(mic, self._take_reference(len(mic)))
        return cleaned.astype(np.int16).tobytes()

    def reset(self) -> None:
        with self._lock:
            self._reference = np.zeros(0, dtype=np.int16)
        self._processor.reset()