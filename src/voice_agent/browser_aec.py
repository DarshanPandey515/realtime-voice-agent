"""Browser-compatible echo cancellation.

For browser mode, there is no local speaker to provide a far-end reference.
This subclass allows AEC to bypass reference tracking when no speaker is present.
"""

import threading
import numpy as np
from voice_agent.aec import EchoCancellation


class BrowserAEC(EchoCancellation):
    """Echo cancellation that can operate without a far-end reference.

    In browser mode, there is no local speaker playing audio, so we cannot
    provide the far-end reference that AEC needs. This subclass allows the
    reference to be optional, passing audio through unchanged when no reference
    is available.
    """

    def __init__(self, sample_rate: int, reference_ms: int = 1000,
                 stream_delay_ms: int = 0, enable_reference: bool = False):
        super().__init__(sample_rate, reference_ms, stream_delay_ms)
        self._enable_reference = enable_reference

    def add_playback(self, pcm: bytes) -> None:
        """Record audio as far-end reference only if enabled."""
        if not self._enable_reference:
            return
        super().add_playback(pcm)

    def process(self, capture: bytes) -> bytes:
        """Return capture audio, with AEC if reference is enabled."""
        if not self._enable_reference:
            # No reference available, pass audio through unchanged
            return capture
        return super().process(capture)
