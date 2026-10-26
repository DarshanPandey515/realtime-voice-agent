import asyncio
import logging
from dotenv import load_dotenv
from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents, LiveOptions
from voice_agent.config import asr_config

load_dotenv()

logger = logging.getLogger(__name__)


class StreamingASR:

    def __init__(self):
        deepgram_options = DeepgramClientOptions(
            options={"keepalive": "true"}
        )
        self.client = DeepgramClient(asr_config.api_key, deepgram_options)
        self.connection = None
        # maxsize=1, drop-oldest: someone talking over the agent should get
        # their newest turn answered, not a backlog of stale ones.
        self.turn_queue = asyncio.Queue(maxsize=1)
        self.is_running = False
        self._connected = asyncio.Event()

    async def on_message(self, *args, **kwargs):
        result = kwargs.get('result')
        if not result:
            return

        # Deepgram sends results with is_final=True when a complete utterance is detected
        sentence = result.channel.alternatives[0].transcript
        if result.is_final and sentence.strip():
            logger.info("user: %s", sentence)
            if self.turn_queue.full():
                self.turn_queue.get_nowait()
            await self.turn_queue.put(sentence)

    async def on_error(self, *args, **kwargs):
        error = kwargs.get('error')
        logger.error("ASR Error: %s", error)

    async def on_metadata(self, *args, **kwargs):
        metadata = kwargs.get('metadata')
        logger.debug("ASR Metadata: %s", metadata)

    async def on_close(self, *args, **kwargs):
        logger.info("ASR connection closed")
        self.is_running = False
        self._connected.clear()

    async def connect(self, timeout: float = 30.0):
        try:
            self.connection = self.client.listen.websocket.v("1")

            self.connection.on(LiveTranscriptionEvents.Transcript, self.on_message)
            self.connection.on(LiveTranscriptionEvents.Error, self.on_error)
            self.connection.on(LiveTranscriptionEvents.Metadata, self.on_metadata)
            self.connection.on(LiveTranscriptionEvents.Close, self.on_close)

            options = LiveOptions(
                model="nova-2",
                language=asr_config.language_code,
                smart_format=True,
                interim_results=False,
                vad_events=True,
                sample_rate=asr_config.sample_rate,
                channels=1,
                encoding="linear16",
            )

            if await self.connection.start(options):
                self.is_running = True
                self._connected.set()
                logger.info("Deepgram connection started")
            else:
                raise RuntimeError("Failed to start Deepgram connection")

        except Exception as e:
            logger.error("Failed to connect to Deepgram: %s", e)
            raise

    async def get_next_turn(self):
        return await self.turn_queue.get()

    async def stream_audio(self, data):
        if self.is_running and self.connection:
            await self.connection.send(data)

    async def disconnect(self):
        self.is_running = False
        self._connected.clear()
        if self.connection:
            await self.connection.finish()
            self.connection = None
