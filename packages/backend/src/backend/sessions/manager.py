"""Session manager for concurrent browser sessions."""

import asyncio
import logging
from typing import Dict, Optional
from fastapi import WebSocket
from voice_agent.engine.session import VoiceSession
from backend.sessions.lifecycle import SessionLifecycle
from backend.protocol.messages import SessionStarted, SessionStopped, Status, Error

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages multiple concurrent voice sessions."""
    
    def __init__(self, max_sessions: int = 10):
        self.sessions: Dict[str, VoiceSession] = {}
        self.max_sessions = max_sessions
        self._lock = asyncio.Lock()
    
    async def create_session(self, websocket: WebSocket) -> tuple[VoiceSession, SessionLifecycle]:
        """Create a new voice session.
        
        Args:
            websocket: WebSocket connection
            
        Returns:
            tuple: (VoiceSession, SessionLifecycle)
        """
        async with self._lock:
            if len(self.sessions) >= self.max_sessions:
                raise RuntimeError("Maximum sessions reached")
            
            import uuid
            session_id = str(uuid.uuid4())
            session = VoiceSession(session_id)
            lifecycle = SessionLifecycle(session)
            self.sessions[session_id] = session
            logger.info("Created session %s", session_id)
            return session, lifecycle
    
    async def get_session(self, session_id: str) -> Optional[VoiceSession]:
        """Get session by ID."""
        return self.sessions.get(session_id)
    
    async def remove_session(self, session_id: str) -> None:
        """Remove session."""
        async with self._lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info("Removed session %s", session_id)
    
    async def cleanup_all(self) -> None:
        """Cleanup all sessions."""
        async with self._lock:
            for session_id, session in list(self.sessions.items()):
                try:
                    await session.cleanup()
                except Exception as e:
                    logger.error("Error cleaning up session %s: %s", session_id, e)
                del self.sessions[session_id]
