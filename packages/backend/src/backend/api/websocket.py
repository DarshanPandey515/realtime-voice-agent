"""WebSocket endpoint for voice agent."""

import asyncio
import logging
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect
from backend.sessions.manager import SessionManager
from backend.protocol.messages import (
    SessionStart, SessionStop, Interrupt,
    SessionStarted, SessionStopped, Status, Transcript,
    AudioStart, AudioEnd, Error
)

logger = logging.getLogger(__name__)


class WebSocketHandler:
    """Handles WebSocket connections for voice sessions."""
    
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
    
    async def handle_connection(self, websocket: WebSocket):
        """Handle a WebSocket connection."""
        await websocket.accept()
        session = None
        lifecycle = None
        
        try:
            # Wait for session_start message
            data = await websocket.receive_json()
            msg = SessionStart(**data)
            
            # Create session
            session, lifecycle = await self.session_manager.create_session(websocket)
            
            # Send session started
            await websocket.send_json(SessionStarted(session_id=session.session_id).dict())
            
            # Start session lifecycle
            await lifecycle.start()
            
            # Main message loop
            while True:
                try:
                    # Receive message (JSON or binary)
                    message = await websocket.receive()
                    
                    if message.get("type") == "websocket.disconnect":
                        break
                    
                    if "bytes" in message:
                        # Binary audio data
                        await self._handle_audio(session, message["bytes"])
                    elif "text" in message:
                        # JSON message
                        await self._handle_json(session, lifecycle, message["text"])
                        
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error("Error handling message: %s", e)
                    await websocket.send_json(Error(
                        code="INTERNAL",
                        message=str(e),
                        session_id=session.session_id
                    ).dict())
        
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error("WebSocket error: %s", e)
        finally:
            # Cleanup
            if session and lifecycle:
                await lifecycle.stop()
                await self.session_manager.remove_session(session.session_id)
    
    async def _handle_audio(self, session, audio_data: bytes):
        """Handle incoming audio data."""
        # This will be implemented to feed audio to the pipeline
        pass
    
    async def _handle_json(self, session, lifecycle, text: str):
        """Handle JSON messages."""
        import json
        data = json.loads(text)
        msg_type = data.get("type")
        
        if msg_type == "session_stop":
            msg = SessionStop(**data)
            await lifecycle.stop()
            await self.session_manager.remove_session(session.session_id)
        elif msg_type == "interrupt":
            msg = Interrupt(**data)
            await lifecycle.interrupt(msg.turn_id)
        else:
            logger.warning("Unknown message type: %s", msg_type)
