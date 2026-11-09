"""FastAPI WebSocket server for browser-based voice agent testing."""

import asyncio
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from backend.browser_agent import BrowserVoiceAgent

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
        session_started = False
        try:
            loop = asyncio.get_running_loop()
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
            def queue_audio(chunk: bytes):
                if audio_queue.full():
                    audio_queue.get_nowait()
                audio_queue.put_nowait(chunk)

            def audio_callback(chunk: bytes):
                try:
                    loop.call_soon_threadsafe(queue_audio, chunk)
                except Exception as e:
                    logger.debug("Failed to queue audio chunk: %s", e)

            # Create agent instance for this session
            agent = BrowserVoiceAgent(audio_callback)
            self.active_connections[websocket] = agent

            # Receive both JSON control messages and binary audio frames.
            while True:
                try:
                    message = await websocket.receive()
                    if message.get("type") == "websocket.disconnect":
                        break

                    audio_data = message.get("bytes")
                    if audio_data is not None:
                        agent.offer_audio(audio_data)
                        continue

                    text = message.get("text")
                    if text is None:
                        continue

                    import json

                    try:
                        command = json.loads(text)
                    except json.JSONDecodeError as e:
                        await websocket.send_json({"type": "error", "message": "Invalid JSON control message"})
                        logger.warning("Ignoring invalid WebSocket JSON: %s", e)
                        continue

                    command_type = command.get("type")
                    if command_type == "session_start":
                        if not session_started:
                            await agent.start_session()
                            session_started = True
                            await websocket.send_json({"type": "session_started"})
                            asyncio.create_task(agent.greet())
                        continue
                    if command_type == "session_stop":
                        if session_started:
                            await agent.stop_session()
                            session_started = False
                        await websocket.send_json({"type": "session_ended"})
                        break
                    if command_type == "interrupt" and session_started:
                        agent.interrupt_playback()
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
            if agent and session_started:
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
