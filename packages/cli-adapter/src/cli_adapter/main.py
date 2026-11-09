"""CLI adapter for voice agent using PyAudio."""

import asyncio
import logging

from voice_agent.main import VoiceAgent

logger = logging.getLogger(__name__)


async def run_cli_agent():
    """Run the CLI voice agent using the existing VoiceAgent."""
    agent = VoiceAgent()
    try:
        await agent.run()
    except KeyboardInterrupt:
        logger.info("Stopped by user")


def main():
    """Main entry point for CLI."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(run_cli_agent())


if __name__ == "__main__":
    main()
