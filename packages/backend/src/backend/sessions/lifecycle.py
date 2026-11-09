"""Session lifecycle management for backend."""

import asyncio
import logging
from typing import Optional
from voice_agent.engine.session import VoiceSession, SessionState
from backend.protocol.messages import SessionStarted, SessionStopped, Status, Error

logger = logging.getLogger(__name__)


class SessionLifecycle:
    """Manages session lifecycle and cleanup."""
    
    def __init__(self, session: VoiceSession):
        self.session = session
    
    async def start(self) -> SessionStarted:
        """Start the session."""
        self.session.set_state(SessionState.READY)
        return SessionStarted(session_id=self.session.session_id)
    
    async def stop(self) -> SessionStopped:
        """Stop the session and cleanup resources."""
        logger.info("Stopping session %s", self.session.session_id)
        await self.session.cleanup()
        return SessionStopped(session_id=self.session.session_id)
    
    async def interrupt(self, turn_id: str) -> None:
        """Interrupt current turn."""
        self.session.interrupt_turn(turn_id)
        if self.session.tts:
            await self.session.tts.interrupt()
    
    async def send_status(self, state: str, turn_id: Optional[str] = None) -> Status:
        """Send status update."""
        return Status(
            state=state,
            turn_id=turn_id,
            session_id=self.session.session_id
        )
    
    async def send_error(self, code: str, message: str) -> Error:
        """Send error message."""
        return Error(
            code=code,
            message=message,
            session_id=self.session.session_id
        )
