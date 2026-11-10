import asyncio
import logging
import threading
from typing import Callable, Optional

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

    def __init__(
        self,
        audio_callback: Optional[Callable[[bytes, int], None]] = None,
        playback_interrupt_callback: Optional[Callable[[int], None]] = None,
    ):
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
        self.tts = StreamingTTS(echo=self.echo, audio_callback=audio_callback)
        self._playback_interrupt_callback = playback_interrupt_callback
        self.is_running = False
        self._mic_error = None
        # Mic thread -> event loop. The pump drains this in the loop thread,
        # so asyncio.Queue is only ever touched from one side.
        self._frames = asyncio.Queue(maxsize=64)
        self._turns = asyncio.Queue(maxsize=1)
        self._vad = VoiceDetector()
        self._voice_frames = 0
        self._user_speech_active = False
        self._said_anything = False
        self._active_response_task: asyncio.Task | None = None
        self._active_turn_id: int | None = None
        self._current_turn_id: int | None = None
        self._playback_turn_id: int | None = None
        self._browser_playback_managed = playback_interrupt_callback is not None
        self._cancel_reasons: dict[int, str] = {}
        self._turn_id = 0

    def set_playback_state(self, active: bool, turn_id: int) -> None:
        """Record browser-confirmed playback, ignoring stale stop events."""
        self._browser_playback_managed = True
        if active:
            if turn_id == 0 or turn_id == self._current_turn_id:
                self._playback_turn_id = turn_id
        elif self._playback_turn_id == turn_id:
            self._playback_turn_id = None

    def is_turn_current(self, turn_id: int) -> bool:
        if turn_id == 0:
            return self._current_turn_id is None and turn_id not in self._cancel_reasons
        return turn_id == self._current_turn_id and turn_id not in self._cancel_reasons

    def _playing_turn_id(self) -> int | None:
        if self._browser_playback_managed:
            return self._playback_turn_id
        return self.tts.playing_turn_id

    def _interrupt_playback(self, turn_id: int) -> None:
        self.tts.interrupt()
        if self._playback_interrupt_callback is not None:
            self._playback_interrupt_callback(turn_id)
        if self._playback_turn_id == turn_id:
            self._playback_turn_id = None

    def _cancel_current_turn(self, reason: str, only_turn_id: int | None = None) -> None:
        turn_id = self._current_turn_id
        if turn_id is None or (only_turn_id is not None and turn_id != only_turn_id):
            # A greeting may be playing before the first conversational turn.
            turn_id = self._playing_turn_id()
            if turn_id is None and reason == "new_utterance" and self._browser_playback_managed:
                turn_id = 0
        if turn_id is None or (only_turn_id is not None and turn_id != only_turn_id):
            return

        playing_turn_id = self._playing_turn_id()
        if playing_turn_id == turn_id or (
            self._browser_playback_managed and reason == "new_utterance"
        ):
            self._interrupt_playback(turn_id)

        task = self._active_response_task
        if task is not None and not task.done() and self._active_turn_id == turn_id:
            self._cancel_reasons[turn_id] = reason
            task.cancel(reason)

        # Invalidating the generation prevents late TTS chunks from a
        # cancelled turn from being queued after the next turn starts.
        self._cancel_reasons.setdefault(turn_id, reason)

    def _offer(self, data: bytes) -> None:
        try:
            self._frames.put_nowait(data)
        except asyncio.QueueFull:
            self._frames.get_nowait()
            self._frames.put_nowait(data)

    def offer_audio(self, data: bytes) -> None:
        """Public interface for offering audio frames for processing."""
        self._offer(data)

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
                input_device_index=asr_config.input_device_index if asr_config.input_device_index >= 0 else None,
            )
            while self.is_running:
                data = stream.read(
                    asr_config.frames_per_buffer,
                    exception_on_overflow=False,
                )
                loop.call_soon_threadsafe(self._offer, data)
        except Exception as e:
            logger.error("Mic thread error: %s", e)
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
                playing_turn_id = self._playing_turn_id()
                if playing_turn_id is not None:
                    self._cancel_current_turn("vad_barge_in", only_turn_id=playing_turn_id)
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
            self._user_speech_active = False
            return False
        if self._user_speech_active:
            return False
        self._voice_frames += 1
        if self._voice_frames >= asr_config.vad_onset_frames:
            self._user_speech_active = True
            return True
        return False

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

            self._cancel_current_turn("new_utterance")
            try:
                self._turns.put_nowait(user_text)
            except asyncio.QueueFull:
                self._turns.get_nowait()
                self._turns.put_nowait(user_text)

    async def _on_sentence(self, sentence: str, turn_id: int | None = None) -> bool:
        if turn_id is not None and (
            turn_id != self._current_turn_id or turn_id in self._cancel_reasons
        ):
            return False
        # Never say "let me check that" out loud: it is a promise the model may
        # not keep, and dead air in front of a microphone reads as a hang.
        if is_intent_narration(sentence):
            logger.info("dropping intent narration: %s", sentence)
            return False
        self._said_anything = True
        await self.tts.speak(sentence, turn_id=turn_id)
        return True

    async def _process_turn(self, user_text: str, turn_id: int) -> None:
        self._said_anything = False

        async def on_sentence(sentence: str) -> None:
            await self._on_sentence(sentence, turn_id)

        try:
            async with asyncio.timeout(llm_config.turn_timeout_seconds):
                await self.llm.stream_into(user_text, on_sentence)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            logger.warning("response turn=%s exceeded %ss", turn_id, llm_config.turn_timeout_seconds)
            if turn_id == self._current_turn_id and turn_id not in self._cancel_reasons:
                await self.tts.speak(
                    "I'm having trouble checking that right now. Please try again.",
                    turn_id=turn_id,
                )
        except UsageLimitExceeded as e:
            logger.warning("turn=%s hit a tool-call cap: %s", turn_id, e)
            if turn_id == self._current_turn_id and turn_id not in self._cancel_reasons:
                await self.tts.speak(
                    "I went round in circles looking into that. "
                    "Can you narrow the question down?",
                    turn_id=turn_id,
                )
        except Exception as e:
            logger.warning("reply failed turn=%s: %s", turn_id, e)
            if turn_id == self._current_turn_id and turn_id not in self._cancel_reasons:
                await self.tts.speak("Something went wrong. Try asking again.", turn_id=turn_id)
        else:
            if (
                not self._said_anything
                and turn_id == self._current_turn_id
                and turn_id not in self._cancel_reasons
            ):
                logger.info("turn produced no answer turn=%s: %s", turn_id, user_text)
                await self.tts.speak(
                    "I couldn't find that. Try asking differently.",
                    turn_id=turn_id,
                )

    async def _respond_loop(self) -> None:
        while self.is_running:
            try:
                user_text = await self._turns.get()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Turn wait error: %s", e)
                continue

            self._turn_id += 1
            turn_id = self._turn_id
            self._current_turn_id = turn_id
            task = asyncio.create_task(self._process_turn(user_text, turn_id))
            self._active_response_task = task
            self._active_turn_id = turn_id
            logger.info("Starting response turn=%s", turn_id)
            try:
                await task
            except asyncio.CancelledError:
                if not self.is_running:
                    break
                logger.info(
                    "Cancelled stale response turn=%s reason=%s",
                    turn_id,
                    self._cancel_reasons.get(turn_id, "unknown"),
                )
            finally:
                if self._active_response_task is task:
                    self._active_response_task = None
                    self._active_turn_id = None

    def interrupt_playback(self):
        """Stop the currently playing response and its browser audio buffers."""
        turn_id = self._playing_turn_id()
        if turn_id is not None:
            self._cancel_current_turn("playback_interrupted", only_turn_id=turn_id)

    async def connect(self):
        """Connect to ASR."""
        self.is_running = True
        logger.info("Connecting to ASR")
        await self.asr.connect()
        logger.info("Connected to ASR")

    async def start_processing(self):
        """Start the audio processing loops."""
        pump = asyncio.create_task(self._pump_audio())
        turn_task = asyncio.create_task(self._turn_loop())
        respond_task = asyncio.create_task(self._respond_loop())
        self._tasks = (pump, turn_task, respond_task)

    async def stop_processing(self):
        """Stop the audio processing loops."""
        self.is_running = False
        if hasattr(self, '_tasks'):
            for t in self._tasks:
                t.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def disconnect(self):
        """Disconnect from ASR."""
        await self.asr.disconnect()

    async def run(self, use_mic: bool = True, speak_greeting: bool = True):
        """Run the agent with terminal defaults (mic thread and greeting)."""
        await self.connect()

        if speak_greeting:
            logger.info("Agent Greeting to user.")
            await self.tts.speak("Hi there, How can i help you today?")

        mic_thread = None
        if use_mic:
            loop = asyncio.get_running_loop()
            mic_thread = threading.Thread(target=self._mic_thread, args=(loop,), daemon=True)
            mic_thread.start()
            logger.info("Listening... Speak into your mic. Press Ctrl+C to stop.")

        await self.start_processing()

        try:
            while self.is_running:
                await asyncio.sleep(0.2)
                if self._mic_error:
                    raise self._mic_error
        finally:
            await self.stop_processing()
            if mic_thread:
                mic_thread.join(timeout=2)
            await self.disconnect()
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
