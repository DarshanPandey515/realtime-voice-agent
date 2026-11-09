"""FastAPI backend for voice agent."""

import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from backend.web_server import web_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Voice Agent Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def get_ui():
    """Serve a minimal status page (React app is served separately by Vite)."""
    return {"status": "Voice Agent backend running", "websocket": "/ws/audio"}


@app.websocket("/ws/audio")
async def websocket_audio(websocket: WebSocket):
    """WebSocket endpoint for voice sessions."""
    await web_server.handle_websocket(websocket)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "sessions": len(web_server.active_connections)}


def main():
    """Run the backend server."""
    import uvicorn
    logger.info("Starting Voice Agent backend on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
