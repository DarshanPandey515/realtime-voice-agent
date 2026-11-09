"""WebSocket protocol message definitions."""

import uuid
from typing import Optional, Literal
from pydantic import BaseModel


class SessionStart(BaseModel):
    """Client message to start a session."""
    type: Literal["session_start"] = "session_start"
    session_id: str = str(uuid.uuid4())


class SessionStop(BaseModel):
    """Client message to stop a session."""
    type: Literal["session_stop"] = "session_stop"
    session_id: str


class Interrupt(BaseModel):
    """Client message to interrupt playback."""
    type: Literal["interrupt"] = "interrupt"
    turn_id: str


class SessionStarted(BaseModel):
    """Server message: session started."""
    type: Literal["session_started"] = "session_started"
    session_id: str


class SessionStopped(BaseModel):
    """Server message: session stopped."""
    type: Literal["session_stopped"] = "session_stopped"
    session_id: str


class Status(BaseModel):
    """Server message: session status."""
    type: Literal["status"] = "status"
    state: Literal["listening", "speaking", "processing"]
    turn_id: Optional[str] = None
    session_id: str


class Transcript(BaseModel):
    """Server message: transcription result."""
    type: Literal["transcript"] = "transcript"
    text: str
    is_final: bool
    turn_id: str
    session_id: str


class AudioStart(BaseModel):
    """Server message: start of audio stream."""
    type: Literal["audio_start"] = "audio_start"
    turn_id: str
    sample_rate: int = 16000
    format: str = "pcm_s16le"
    channels: int = 1
    session_id: str


class AudioEnd(BaseModel):
    """Server message: end of audio stream."""
    type: Literal["audio_end"] = "audio_end"
    turn_id: str
    session_id: str


class Error(BaseModel):
    """Server message: error."""
    type: Literal["error"] = "error"
    code: Literal["SESSION_LIMIT", "AUDIO_FORMAT", "PROVIDER_ERROR", "INTERNAL"]
    message: str
    session_id: str
