import asyncio
import logging
import threading

import numpy as np
import pyaudio
from pywebrtc_audio import VoiceDetector
from pydantic_ai.exceptions import UsageLimitExceeded

from voice_agent.aec import EchoCancellation
from voice_agent.asr import StreamingASR
from voice_agent.config import asr_config, llm_config, tts_config
from voice_agent.llm import LLMAgent, is_intent_narration
from voice_agent.tts import StreamingTTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

logger = logging.getLogger(__name__)


class VoiceAgent:

    def __init__(self):
        self.echo = EchoCancellation(
            asr_config.sample_rate,
            # Playback buffer is the delay between us handing audio to the
            # speaker and it reaching the room; AEC3 converges faster when told.
            stream_delay_ms=round(
                tts_config.output_frames_per_buffer
                / tts_config.sample_rate * 1000
            ),
        )
        self.asr = StreamingASR()
        self.llm = LLMAgent()
        self.tts = StreamingTTS(echo=self.echo)
        self.is_running = False
        self._mic_error = None
        # Mic thread -> event loop. The pump drains this in the loop thread,
        # so asyncio.Queue is only ever touched from one side.
        self._frames = asyncio.Queue(maxsize=64)
        self._turns = asyncio.Queue(maxsize=1)
        self._barge_in = asyncio.Event()
        self._vad = VoiceDetector()
        self._voice_frames = 0
        self._said_anything = False

    def _offer(self, data: bytes) -> None:
        try:
            self._frames.put_nowait(data)
        except asyncio.QueueFull:
            self._frames.get_nowait()
            self._frames.put_nowait(data)

    def _mic_thread(self, loop) -> None:
        p = pyaudio.PyAudio()
        stream = None
        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=asr_config.sample_rate,
                input=True,
                frames_per_buffer=asr_config.frames_per_buffer,
            )
            while self.is_running:
                data = stream.read(
                    asr_config.frames_per_buffer,
                    exception_on_overflow=False,
                )
                loop.call_soon_threadsafe(self._offer, data)
        except Exception as e:
            self._mic_error = e
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            p.terminate()

    async def _pump_audio(self) -> None:
        while self.is_running:
            frame = await self._frames.get()
            # Strip the agent's own voice before ASR ever sees it, otherwise it
            # transcribes itself and interrupts itself.
            clean = self.echo.process(frame)
            # VAD on the *cleaned* audio. On raw input the agent's own voice
            # reads as the user talking and cuts itself off again.
            if self._is_user_speech(clean):
                self.tts.interrupt()
                self._barge_in.set()
            await self.asr.stream_audio(clean)

    def _is_user_speech(self, pcm: bytes) -> bool:
        """Sustained speech on the mic, independent of turn detection.

        Waiting for ASR to close a turn means the agent finishes its sentence
        before it can be cut off, which is not what interrupting someone feels
        like. This is deliberately independent of the transcript.
        """
        probability = self._vad.process(np.frombuffer(pcm, dtype=np.int16))
        if probability < asr_config.vad_threshold:
            self._voice_frames = 0
            return False
        self._voice_frames += 1
        return self._voice_frames >= asr_config.vad_onset_frames

    async def _turn_loop(self) -> None:
        """Take finished turns and hand them to the responder.

        Kept separate from responding so a new turn can interrupt playback
        while the agent is still talking.
        """
        while self.is_running:
            try:
                user_text = await self.asr.get_next_turn()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Turn error: %s", e)
                continue

            if self.tts.is_self_echo(user_text):
                logger.info("ignoring probable self-echo: %s", user_text)
                continue

            self.tts.interrupt()
            self._barge_in.set()
            try:
                self._turns.put_nowait(user_text)
            except asyncio.QueueFull:
                self._turns.get_nowait()
                self._turns.put_nowait(user_text)

    async def _on_sentence(self, sentence: str) -> None:
        if self._barge_in.is_set():
            return
        # Never say "let me check that" out loud: it is a promise the model may
        # not keep, and dead air in front of a microphone reads as a hang.
        if is_intent_narration(sentence):
            logger.info("dropping intent narration: %s", sentence)
            return
        self._said_anything = True
        await self.tts.speak(sentence)

    async def _respond_loop(self) -> None:
        while self.is_running:
            try:
                user_text = await self._turns.get()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Turn wait error: %s", e)
                continue

            self._barge_in.clear()
            self._said_anything = False
            try:
                await self.llm.stream_into(user_text, self._on_sentence)
            except asyncio.CancelledError:
                break
            except UsageLimitExceeded:
                logger.warning("turn hit the %d tool-call cap",
                               llm_config.tool_call_limit)
                await self.tts.speak(
                    "I went round in circles looking into that. "
                    "Can you narrow the question down?")
            except Exception as e:
                logger.warning("reply failed: %s", e)
                await self.tts.speak("Something went wrong. Try asking again.")
            else:
                # Every sentence was narration, or the model produced nothing:
                # either way the user is owed an answer, not a promise.
                if not self._said_anything:
                    logger.info("turn produced no answer: %s", user_text)
                    await self.tts.speak(
                        "I couldn't find that. Try asking differently.")

    async def run(self):
        self.is_running = True
        logger.info("Connecting to ASR")
        await self.asr.connect()
        logger.info("Connected to ASR")

        logger.info("Agent Greeting to user.")
        await self.tts.speak("Hi there, How can i help you today?")

        loop = asyncio.get_running_loop()
        mic = threading.Thread(target=self._mic_thread, args=(loop,), daemon=True)
        mic.start()

        logger.info("Listening... Speak into your mic. Press Ctrl+C to stop.")

        pump = asyncio.create_task(self._pump_audio())
        turn_task = asyncio.create_task(self._turn_loop())
        respond_task = asyncio.create_task(self._respond_loop())

        try:
            while self.is_running:
                await asyncio.sleep(0.2)
                if self._mic_error:
                    raise self._mic_error
        finally:
            self.is_running = False
            # Cancel before awaiting: the pump is parked on _frames.get() and
            # would never notice is_running flipping on its own.
            tasks = (pump, turn_task, respond_task)
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            mic.join(timeout=2)
            await self.asr.disconnect()
            if self._mic_error:
                raise self._mic_error


def main():
    agent = VoiceAgent()
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        logger.info("Stopped.")


if __name__ == "__main__":
    main()