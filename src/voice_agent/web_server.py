"""FastAPI WebSocket server for browser-based voice agent testing."""

import asyncio
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from voice_agent.browser_agent import BrowserVoiceAgent

logger = logging.getLogger(__name__)


class WebServer:
    """WebSocket server for browser voice agent sessions."""

    def __init__(self):
        self.active_connections: dict[WebSocket, BrowserVoiceAgent] = {}

    async def handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket connection for a browser session."""
        await websocket.accept()
        agent = None
        sender = None
        try:
            # Create queue for audio chunks from TTS thread to event loop
            audio_queue = asyncio.Queue(maxsize=100)

            # Start task to send audio chunks to browser
            async def send_audio_task():
                while True:
                    try:
                        chunk = await audio_queue.get()
                        await websocket.send_bytes(chunk)
                    except Exception as e:
                        logger.debug("Failed to send audio to browser: %s", e)
                        break

            sender = asyncio.create_task(send_audio_task())

            # Create audio callback for this session (synchronous, called from TTS thread)
            def audio_callback(chunk: bytes):
                try:
                    loop = asyncio.get_running_loop()
                    loop.call_soon_threadsafe(audio_queue.put_nowait, chunk)
                except Exception as e:
                    logger.debug("Failed to queue audio chunk: %s", e)

            # Create agent instance for this session
            agent = BrowserVoiceAgent(audio_callback)
            self.active_connections[websocket] = agent

            # Send session started message
            await websocket.send_json({"type": "session_started"})

            # Start the agent session
            await agent.start_session()

            # Receive audio from browser
            while True:
                try:
                    # Receive audio data (bytes)
                    data = await websocket.receive_bytes()
                    # Offer audio to agent for processing
                    agent.offer_audio(data)
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error("Error receiving audio: %s", e)
                    await websocket.send_json({"type": "error", "message": str(e)})
                    break

        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error("WebSocket error: %s", e)
            await websocket.send_json({"type": "error", "message": str(e)})
        finally:
            # Cleanup
            if agent:
                await agent.stop_session()
            if websocket in self.active_connections:
                del self.active_connections[websocket]
            if sender:
                sender.cancel()
                try:
                    await sender
                except:
                    pass
            logger.info("Session cleaned up")

    async def interrupt_playback(self, websocket: WebSocket):
        """Interrupt current TTS playback."""
        agent = self.active_connections.get(websocket)
        if agent:
            agent.interrupt_playback()
            await websocket.send_json({"type": "playback_interrupted"})


# Global server instance
web_server = WebServer()
