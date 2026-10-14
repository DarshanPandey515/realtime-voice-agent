import asyncio
import threading
import pyaudio
from elevenlabs.client import ElevenLabs
from voice_agent.config import tts_config
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