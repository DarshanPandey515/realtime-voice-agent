import asyncio
import logging
from dotenv import load_dotenv
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types import (
    ListenV1Metadata,
    ListenV1Results,
    ListenV1SpeechStarted,
    ListenV1UtteranceEnd,
)
from voice_agent.config import asr_config

load_dotenv()

logger = logging.getLogger(__name__)

ListenV1SocketClientResponse = type(
    "ListenV1SocketClientResponse",
    (ListenV1Results, ListenV1Metadata, ListenV1UtteranceEnd, ListenV1SpeechStarted),
    {},
)


class StreamingASR:

    def __init__(self):
        import os
        # Set the API key as environment variable for Deepgram
        os.environ["DEEPGRAM_API_KEY"] = asr_config.api_key
        self.client = AsyncDeepgramClient()
        self.connection = None
        self._connect_cm = None
        # maxsize=1, drop-oldest: someone talking over the agent should get
        # their newest turn answered, not a backlog of stale ones.
        self.turn_queue = asyncio.Queue(maxsize=1)
        self.is_running = False
        self._connected = asyncio.Event()

    async def on_message(self, message: ListenV1SocketClientResponse, *args, **kwargs) -> None:
        if isinstance(message, ListenV1Results):
            if message.channel and message.channel.alternatives:
                transcript = message.channel.alternatives[0].transcript
                if transcript and message.is_final:
                    logger.info("user: %s", transcript)
                    if self.turn_queue.full():
                        self.turn_queue.get_nowait()
                    await self.turn_queue.put(transcript)
        elif isinstance(message, ListenV1UtteranceEnd):
            logger.debug("Utterance ended")
        elif isinstance(message, ListenV1SpeechStarted):
            logger.debug("Speech started")
        elif isinstance(message, ListenV1Metadata):
            logger.debug("Metadata received: %s", message)

    async def on_error(self, error, *args, **kwargs) -> None:
        logger.error("ASR Error: %s", error)

    async def on_close(self, *args, **kwargs) -> None:
        logger.info("ASR connection closed")
        self.is_running = False
        self._connected.clear()

    async def on_open(self, *args, **kwargs) -> None:
        logger.info("Deepgram connection opened")
        self.is_running = True
        self._connected.set()

    async def connect(self, timeout: float = 30.0):
        try:
            # Deepgram's connect returns an async context manager
            self._connect_cm = self.client.listen.v1.connect(
                model=asr_config.model,
                language=asr_config.language_code,
                smart_format=True,
                interim_results=False,
                vad_events=True,
                sample_rate=asr_config.sample_rate,
                channels=1,
                encoding="linear16",
            )

            # Enter the context manager to get the connection
            self.connection = await self._connect_cm.__aenter__()

            self.connection.on(EventType.MESSAGE, self.on_message)
            self.connection.on(EventType.ERROR, self.on_error)
            self.connection.on(EventType.CLOSE, self.on_close)
            self.connection.on(EventType.OPEN, self.on_open)

            # Start listening in background
            asyncio.create_task(self.connection.start_listening())

            # Wait for connection to be established
            try:
                await asyncio.wait_for(self._connected.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                await self.disconnect()
                raise TimeoutError(
                    f"Deepgram connection did not open within {timeout}s"
                )

        except Exception as e:
            logger.error("Failed to connect to Deepgram: %s", e)
            raise

    async def get_next_turn(self):
        return await self.turn_queue.get()

    async def stream_audio(self, data):
        if self.is_running and self.connection:
            logger.debug("Sending audio chunk: %d bytes", len(data))
            await self.connection.send_media(data)
        else:
            logger.debug("Skipping audio: is_running=%s, connection=%s", self.is_running, self.connection is not None)

    async def disconnect(self):
        self.is_running = False
        self._connected.clear()
        if self._connect_cm:
            try:
                await self._connect_cm.__aexit__(None, None, None)
            except Exception as e:
                logger.debug("Error exiting context manager: %s", e)
            self._connect_cm = None
        if self.connection:
            self.connection = None
