import asyncio
import difflib
import threading
import time
from collections import deque

import pyaudio
from elevenlabs.client import ElevenLabs
from voice_agent.config import aec_config, tts_config
from dotenv import load_dotenv

load_dotenv()


class StreamingTTS:

    def __init__(self, echo=None):
        self.client = ElevenLabs(
            api_key=tts_config.api_key
        )
        # Set from any thread (including a turn callback) to cut playback short.
        self._cancel = threading.Event()
        self._echo = echo
        # Two output streams on one device interleave at the speaker, and they
        # also scramble the far-end reference the echo canceller depends on.
        self._play_lock = threading.Lock()
        self._spoken = deque(maxlen=aec_config.echo_history)
        self._playback_started_at = 0.0


    def is_self_echo(self, text: str, now: float | None = None) -> bool:
        """True if `text` is more likely the agent hearing itself.

        Two guards, because echo cancellation alone is not enough to stop the
        feedback loop. The first window after playback starts is the leakiest,
        since AEC has no converged reference yet. After that, the guard is
        literal: does this transcript match something we just said?

        ponytail: a ratio threshold, not an acoustic test. A user who says
        something close to the agent's last sentence gets dropped and has to
        repeat themselves. Raise aec_config.echo_match_ratio to be stricter.
        """
        now = time.monotonic() if now is None else now
        if self._playback_started_at and \
                (now - self._playback_started_at) * 1000 < aec_config.warmup_ms:
            return True

        spoken = " ".join(self._spoken).lower()
        if not spoken:
            return False
        return difflib.SequenceMatcher(None, text.lower(), spoken).ratio() > \
            aec_config.echo_match_ratio


    async def speak(self, text: str) -> None:
        # Synthesis reads a blocking HTTP stream and playback blocks the
        # speaker, so neither belongs on the event loop.
        await asyncio.to_thread(self._play_blocking, text)


    def _play_blocking(self, text: str) -> None:
        # Wait for any interrupted playback to tear down before opening a
        # second stream on the same device.
        with self._play_lock:
            # Clear here, not in speak(): holding the lock means nobody else is
            # playing, so an interrupt() can no longer race this clear.
            self._cancel.clear()
            self._playback_started_at = time.monotonic()
            self._spoken.append(text)
            p = pyaudio.PyAudio()
            stream = None
            try:
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=tts_config.sample_rate,
                    output=True,
                    frames_per_buffer=tts_config.output_frames_per_buffer,
                )
                for chunk in self.client.text_to_speech.stream(
                    text=text,
                    voice_id=tts_config.voice_id,
                    model_id=tts_config.model_id,
                    output_format=tts_config.output_format,
                ):
                    if self._cancel.is_set():
                        break
                    # Tee to the echo canceller *before* writing. write() blocks
                    # for the whole chunk, so recording afterwards timestamps
                    # the reference to when playback ended rather than when it
                    # started, which pushes the far end out of the canceller's
                    # delay search and it stops subtracting anything.
                    if self._echo is not None:
                        self._echo.add_playback(chunk)
                    stream.write(chunk)
            finally:
                if stream is not None:
                    stream.stop_stream()
                    stream.close()
                p.terminate()


    def interrupt(self) -> None:
        self._cancel.set()