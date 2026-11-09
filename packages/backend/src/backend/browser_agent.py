"""Browser-compatible adapter for VoiceAgent.

This adapter uses the existing VoiceAgent with browser-specific AEC and TTS routing.
"""

import logging
from deepgram.listen.v1.types import ListenV1Results
from voice_agent.aec import EchoCancellation
from backend.browser_aec import BrowserAEC
from voice_agent.config import tts_config
from voice_agent.main import VoiceAgent

logger = logging.getLogger(__name__)


class BrowserVoiceAgent:
    """VoiceAgent adapter for browser-based testing.

    Uses the existing VoiceAgent with:
    - BrowserAEC (no far-end reference) instead of EchoCancellation
    - Audio callback for WebSocket transmission instead of local speaker
    - Reuses all ASR, LLM, VAD, and turn-processing logic unchanged
    """

    def __init__(self, audio_callback, transcript_callback=None):
        """Initialize browser agent with audio callback for WebSocket transmission."""
        self._audio_callback = audio_callback
        self._transcript_callback = transcript_callback
        self._agent = None

    def _create_agent(self):
        """Create VoiceAgent with browser-specific configuration."""
        def internal_audio_callback(chunk: bytes):
            """Internal callback that also feeds AEC reference if needed."""
            # Browser mode: no local speaker, so no far-end reference needed
            # Just send to browser via WebSocket
            self._audio_callback(chunk)

        # Create VoiceAgent with audio callback
        agent = VoiceAgent(audio_callback=internal_audio_callback)

        if self._transcript_callback:
            original_asr_handler = agent.asr.on_message

            async def on_asr_message(message, *args, **kwargs):
                if isinstance(message, ListenV1Results) and message.channel and message.channel.alternatives:
                    text = message.channel.alternatives[0].transcript
                    if text:
                        await self._transcript_callback({
                            "type": "transcript",
                            "speaker": "user",
                            "text": text,
                            "is_final": message.is_final,
                        })
                await original_asr_handler(message, *args, **kwargs)

            agent.asr.on_message = on_asr_message

            original_sentence_handler = agent._on_sentence

            async def on_agent_sentence(sentence):
                await self._transcript_callback({
                    "type": "transcript",
                    "speaker": "agent",
                    "text": sentence,
                    "is_final": True,
                })
                await original_sentence_handler(sentence)

            agent._on_sentence = on_agent_sentence

        # Replace EchoCancellation with BrowserAEC (no far-end reference)
        agent.echo = BrowserAEC(
            tts_config.sample_rate,
            stream_delay_ms=round(
                tts_config.output_frames_per_buffer
                / tts_config.sample_rate * 1000
            ),
            enable_reference=False,  # No local speaker in browser mode
        )

        # Re-link TTS to the new AEC
        agent.tts._echo = agent.echo

        self._agent = agent
        return agent

    @property
    def agent(self):
        """Get the underlying VoiceAgent instance."""
        if self._agent is None:
            self._agent = self._create_agent()
        return self._agent

    async def start_session(self):
        """Start the agent session (connect ASR, start processing loops)."""
        logger.info("Starting browser session")
        await self.agent.connect()
        await self.agent.start_processing()
        logger.info("Browser session started")

    async def stop_session(self):
        """Stop the agent session (cancel loops, disconnect ASR)."""
        logger.info("Stopping browser session")
        await self.agent.stop_processing()
        await self.agent.disconnect()
        logger.info("Browser session stopped")

    async def greet(self):
        """Welcome the browser user after the session is ready."""
        if self._transcript_callback:
            await self._transcript_callback({
                "type": "transcript",
                "speaker": "agent",
                "text": "Hi there, how can I help you today?",
                "is_final": True,
            })
        await self.agent.tts.speak("Hi there, how can I help you today?")

    def offer_audio(self, data: bytes):
        """Offer audio data for processing (called from WebSocket handler)."""
        self.agent.offer_audio(data)

    def interrupt_playback(self):
        """Interrupt current TTS playback."""
        self.agent.interrupt_playback()
