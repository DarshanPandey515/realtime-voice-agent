import asyncio

import pytest
from deepgram.listen.v1.types import ListenV1Results

from voice_agent.asr import StreamingASR


@pytest.mark.asyncio
async def test_final_asr_segments_are_combined_at_speech_final():
    asr = StreamingASR.__new__(StreamingASR)
    asr.turn_queue = asyncio.Queue(maxsize=1)
    asr._transcript_segments = []
    asr.on_utterance = None

    def result(text, speech_final):
        return ListenV1Results.model_construct(
            is_final=True,
            speech_final=speech_final,
            channel={"alternatives": [{"transcript": text}]},
        )

    await asr.on_message(result("Can you check", False))
    await asr.on_message(result("which desktop", False))
    assert asr.turn_queue.empty()

    await asr.on_message(result("this is?", True))
    assert await asr.get_next_turn() == "Can you check which desktop this is?"
    assert asr._transcript_segments == []
