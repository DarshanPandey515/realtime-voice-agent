import asyncio
import logging
from dotenv import load_dotenv
from assemblyai.streaming.v3 import (
    AsyncRealTimeTranscriber,
    RealTimeTranscriberOptions,
    RealTimeParameters,
    RealTimeEvents,
    TurnEvent,
    BeginEvent,
    RealTimeError,
)
from voice_agent.config import asr_config

load_dotenv()


logger = logging.getLogger(__name__)


class StreamingASR:

    def __init__(self):
        self.transcriber = AsyncRealTimeTranscriber(
            options=RealTimeTranscriberOptions(),
            api_key=asr_config.api_key
        )
        # maxsize=1, drop-oldest: someone talking over the agent should get
        # their newest turn answered, not a backlog of stale ones.
        self.turn_queue = asyncio.Queue(maxsize=1)
        self.is_running = False
        self._connected = asyncio.Event()

        self.transcriber.on(RealTimeEvents.Begin, self.on_open)
        self.transcriber.on(RealTimeEvents.Turn, self.on_turn)
        self.transcriber.on(RealTimeEvents.Error, self.on_error)


    async def on_open(self, client, event: BeginEvent):
        self.is_running = True
        self._connected.set()
        logger.info("session: %s started", event.id)


    async def on_turn(self, client, event: TurnEvent):
        if not (event.transcript and event.end_of_turn):
            return
        logger.info("user: %s", event.transcript)
        if self.turn_queue.full():
            self.turn_queue.get_nowait()
        await self.turn_queue.put(event.transcript)


    async def on_error(self, client, error: RealTimeError):
        logger.info("ASR Error: %s", error)


    async def connect(self, timeout: float = 30.0):
        params = RealTimeParameters(
            sample_rate=asr_config.sample_rate,
            speech_model=asr_config.model,
            language_codes=[asr_config.language_code]
        )
        self._connected.clear()
        await self.transcriber.connect(params)
        # connect() dispatches the error event and returns quietly when the
        # handshake is rejected, so waiting for Begin is the real success check.
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            await self.disconnect()
            raise TimeoutError(
                f"ASR session did not open within {timeout}s"
            )


    async def get_next_turn(self):
        return await self.turn_queue.get()


    async def stream_audio(self, data):
        if self.is_running:
            await self.transcriber.stream(data)


    async def disconnect(self):
        self.is_running = False
        self._connected.clear()
        await self.transcriber.disconnect(terminate=True)