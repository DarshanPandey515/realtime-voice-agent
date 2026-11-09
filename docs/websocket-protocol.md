# WebSocket Protocol Specification

## Overview

This document defines the WebSocket protocol for the voice agent browser interface. The protocol enables real-time voice interaction between a browser client and the voice agent backend.

## Connection

- **Endpoint:** `ws://localhost:8000/ws/audio`
- **Protocol Version:** 1.0
- **Transport:** WebSocket (RFC 6455)

## Message Framing

### JSON Messages
- UTF-8 encoded JSON objects
- Used for control messages, status updates, transcripts, and metadata

### Binary Messages
- Raw PCM audio data
- Format: 16kHz, mono, signed 16-bit little-endian PCM
- Frame size: 1,600 bytes (50ms at 16kHz)

## Client → Server Messages

### Session Control

#### session_start
```json
{
  "type": "session_start",
  "session_id": "uuid-string"
}
```
Starts a new voice session. The client generates a unique session_id.

#### session_stop
```json
{
  "type": "session_stop",
  "session_id": "uuid-string"
}
```
Stops the current voice session and releases resources.

#### interrupt
```json
{
  "type": "interrupt",
  "turn_id": "uuid-string"
}
```
Interrupts TTS playback for the specified turn.

### Audio Input

Binary PCM frames sent continuously during session:
- **Format:** 16kHz, mono, signed 16-bit little-endian PCM
- **Frame size:** 1,600 bytes (50ms)
- **Rate:** 20 frames per second

Browser must resample audio to 16kHz before sending if getUserMedia() provides different sample rate.

## Server → Client Messages

### Session Status

#### session_started
```json
{
  "type": "session_started",
  "session_id": "uuid-string"
}
```
Session successfully initialized and ready for audio.

#### session_stopped
```json
{
  "type": "session_stopped",
  "session_id": "uuid-string"
}
```
Session has been terminated and resources cleaned up.

#### status
```json
{
  "type": "status",
  "state": "listening|speaking|processing",
  "turn_id": "uuid-string",
  "session_id": "uuid-string"
}
```
Current session state:
- `listening`: Waiting for user speech
- `speaking`: TTS is playing audio
- `processing`: LLM is generating response

### Transcription

#### transcript
```json
{
  "type": "transcript",
  "text": "transcribed text",
  "is_final": true,
  "turn_id": "uuid-string",
  "session_id": "uuid-string"
}
```
ASR transcription result:
- `is_final: false` - Partial/interim transcript
- `is_final: true` - Final transcript for the turn

### Audio Output

#### audio_start
```json
{
  "type": "audio_start",
  "turn_id": "uuid-string",
  "sample_rate": 16000,
  "format": "pcm_s16le",
  "channels": 1,
  "session_id": "uuid-string"
}
```
Signals the start of TTS audio stream for a turn. Followed by binary PCM frames.

#### audio_end
```json
{
  "type": "audio_end",
  "turn_id": "uuid-string",
  "session_id": "uuid-string"
}
```
Signals the end of TTS audio stream for a turn.

### Errors

#### error
```json
{
  "type": "error",
  "code": "SESSION_LIMIT|AUDIO_FORMAT|PROVIDER_ERROR|INTERNAL",
  "message": "error description",
  "session_id": "uuid-string"
}
```
Error codes:
- `SESSION_LIMIT`: Maximum concurrent sessions reached
- `AUDIO_FORMAT`: Invalid audio format or sample rate
- `PROVIDER_ERROR`: ASR/LLM/TTS provider failure
- `INTERNAL`: Internal server error

## Audio Configuration

### Input Audio
- **Sample Rate:** 16,000 Hz
- **Channels:** 1 (mono)
- **Encoding:** Signed 16-bit little-endian PCM
- **Frame Size:** 1,600 bytes (50ms)
- **Frame Rate:** 20 frames/second

### Output Audio
- **Sample Rate:** 16,000 Hz
- **Channels:** 1 (mono)
- **Encoding:** Signed 16-bit little-endian PCM
- **Source:** ElevenLabs TTS (pcm_16000 format)

### Browser Requirements
- Must resample microphone audio to 16kHz if necessary
- Must handle binary PCM frames for playback
- Must implement AudioWorklet for low-latency capture
- Must implement streaming playback buffer to avoid gaps

## Turn Identifiers

### turn_id
- Unique UUID generated for each user utterance
- All messages related to a turn include the same `turn_id`
- Used to associate audio, transcripts, and status updates
- Enables interruption safety and stale audio rejection

### Turn Lifecycle
1. User speaks → VAD detects speech → `turn_id` generated
2. ASR transcribes → transcript messages with `turn_id`
3. LLM generates → status messages with `turn_id`
4. TTS synthesizes → audio messages with `turn_id`
5. Turn completes or is interrupted

### Interruption
- User speaks during TTS playback → `interrupt` message with `turn_id`
- Backend marks turn as interrupted
- Stale audio chunks with invalid `turn_id` are discarded
- New turn begins with new `turn_id`

## Session Lifecycle States

```
CONNECTED → READY → STREAMING → INTERRUPTED → STOPPING → CLOSED
```

### State Descriptions

**CONNECTED**
- WebSocket connection established
- Session object created
- Waiting for session_start message

**READY**
- Session initialized
- ASR, LLM, TTS providers connected
- Ready to receive audio

**STREAMING**
- Actively processing audio
- User speech being transcribed
- LLM generating responses
- TTS playing audio

**INTERRUPTED**
- TTS playback interrupted by user speech
- Current turn marked as interrupted
- Waiting for new user turn

**STOPPING**
- Graceful shutdown in progress
- Cancelling background tasks
- Closing provider connections
- Clearing queues

**CLOSED**
- Session terminated
- All resources released
- WebSocket closed

### State Transitions

- **CONNECTED → READY:** After successful session_start
- **READY → STREAMING:** When first audio frame received
- **STREAMING → INTERRUPTED:** When user speaks during TTS
- **INTERRUPTED → STREAMING:** When new turn begins
- **STREAMING → STOPPING:** On session_stop or disconnect
- **STOPPING → CLOSED:** After cleanup complete

## Error Handling

### Client Errors
- Invalid JSON: Server ignores malformed messages
- Invalid audio format: Server sends `AUDIO_FORMAT` error
- Session not found: Server sends `INTERNAL` error

### Server Errors
- Provider failures: Server sends `PROVIDER_ERROR` with details
- Resource limits: Server sends `SESSION_LIMIT` error
- Internal errors: Server sends `INTERNAL` error

### Recovery
- Client should reconnect on `CLOSED` state
- Client should handle `PROVIDER_ERROR` gracefully
- Client should implement exponential backoff for reconnection

## Backpressure and Flow Control

### Server-Side
- All queues bounded (maxsize specified)
- Drop-oldest policy for audio input queue
- Reject-new policy for transcript queue
- Session manager monitors queue depths
- Rejects new sessions if system overloaded

### Client-Side
- Browser must handle backpressure from playback buffer
- Implement audio buffer underrun handling
- Drop audio frames if playback falls behind
- Implement jitter buffer for network variations

## Security Considerations

### Local Development
- No authentication required for localhost
- CORS enabled for development
- WebSocket origin validation recommended

### Production (Future)
- Authentication required
- Rate limiting per session
- Input validation and sanitization
- TLS/SSL encryption
- Session timeouts

## Implementation Notes

### Backend Implementation
- Use FastAPI WebSocket endpoints
- Implement session manager with isolation
- Use bounded asyncio queues
- Implement proper resource cleanup
- Handle provider failures gracefully

### Frontend Implementation
- Use AudioWorklet for low-latency capture
- Implement resampling to 16kHz
- Use streaming playback buffer
- Handle binary PCM frames
- Implement proper error handling
- Use Zustand for state management

### Testing
- Mock providers for deterministic tests
- Test protocol compliance
- Test session isolation
- Test interruption races
- Test disconnect cleanup
- Test concurrent sessions
