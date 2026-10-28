"""Entry point for browser-based voice agent testing."""

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from voice_agent.web_server import web_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Voice Agent Web Client")


@app.get("/")
async def get_web_ui():
    """Serve the browser UI."""
    ui_path = Path(__file__).parent / "web_ui.html"
    return HTMLResponse(ui_path.read_text())


@app.websocket("/ws/audio")
async def websocket_audio(websocket: WebSocket):
    """WebSocket endpoint for audio streaming."""
    await web_server.handle_websocket(websocket)


@app.post("/interrupt")
async def interrupt_playback():
    """Interrupt current TTS playback (for future use)."""
    # This would need to identify which connection to interrupt
    # For now, this is a placeholder
    return {"status": "not_implemented"}


def main():
    """Run the web server."""
    import uvicorn
    logger.info("Starting Voice Agent web server on http://localhost:8000")
    logger.info("Open http://localhost:8000 in your browser to test the agent")
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
