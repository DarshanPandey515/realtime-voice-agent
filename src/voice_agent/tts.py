import asyncio
import threading
import pyaudio
from elevenlabs.client import ElevenLabs
from voice_agent.config import tts_config
from dotenv import load_dotenv

load_dotenv()


class StreamingTTS:

    def __init__(self):
        self.client = ElevenLabs(
            api_key=tts_config.api_key
        )
        # Set from any thread (including a turn callback) to cut playback short.
        self._cancel = threading.Event()


    async def speak(self, text: str) -> None:
        # Clear here, on the loop thread, so clear-then-interrupt ordering is
        # deterministic. The playback worker only ever reads the flag.
        self._cancel.clear()
        # Synthesis reads a blocking HTTP stream and playback blocks the
        # speaker, so neither belongs on the event loop.
        await asyncio.to_thread(self._play_blocking, text)


    def _play_blocking(self, text: str) -> None:
        p = pyaudio.PyAudio()
        stream = None
        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=tts_config.sample_rate,
                output=True,
                frames_per_buffer=1024,
            )
            for chunk in self.client.text_to_speech.stream(
                text=text,
                voice_id=tts_config.voice_id,
                model_id=tts_config.model_id,
                output_format=tts_config.output_format,
            ):
                if self._cancel.is_set():
                    break
                stream.write(chunk)
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            p.terminate()


    def interrupt(self) -> None:
        self._cancel.set()