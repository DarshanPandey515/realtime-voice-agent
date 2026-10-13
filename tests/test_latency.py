import asyncio
import logging
import os
import statistics
import time

import pytest

from voice_agent.config import asr_config, llm_config, tts_config
from voice_agent.llm import LLMAgent

logger = logging.getLogger(__name__)

LLM_ITERATIONS = int(os.getenv("LLM_LATENCY_ITERATIONS", "5"))
TTS_ITERATIONS = int(os.getenv("TTS_LATENCY_ITERATIONS", "5"))
ASR_ITERATIONS = int(os.getenv("ASR_LATENCY_ITERATIONS", "3"))
# This test issues two LLM calls per iteration, so it burns the token budget
# twice as fast as the rest of the suite.
PIPELINE_ITERATIONS = int(os.getenv("PIPELINE_LATENCY_ITERATIONS", "3"))

PROMPT = "What is 2 + 2? Answer in one short sentence."
LONG_PROMPT = (
    "Explain, in a conversational spoken style, what a neural network is, "
    "why depth matters, and give one everyday analogy. Aim for 4-5 sentences."
)
TTS_SENTENCE = "The quick brown fox jumps over the lazy dog."


def _ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


def _measure_real_asr_turn(audio_file: str) -> tuple[float, str | None]:
    """Stream a wav file through real ASR and time speech-end -> transcript.

    Shared by test_asr_turn_latency and the e2e test so both use the exact
    same measurement path. Returns (turn_ms, transcript_or_None).
    """
    import queue as _queue
    import threading
    import wave
    from assemblyai.streaming.v3 import (
        RealTimeEvents,
        RealTimeParameters,
        RealTimeTranscriber,
        RealTimeTranscriberOptions,
    )

    with wave.open(audio_file, "rb") as wf:
        assert wf.getsampwidth() == 2, "expected 16-bit PCM wav"
        frames = wf.readframes(wf.getnframes())
    chunk_size = asr_config.frames_per_buffer * 2
    chunks = [frames[i:i + chunk_size] for i in range(0, len(frames), chunk_size)]

    turns: "_queue.Queue[str]" = _queue.Queue()
    transcriber = RealTimeTranscriber(
        options=RealTimeTranscriberOptions(),
        api_key=asr_config.api_key,
    )
    transcriber.on(RealTimeEvents.Turn, lambda c, e: turns.put(e.transcript))

    begin = threading.Event()
    transcriber.on(RealTimeEvents.Begin, lambda c, e: begin.set())
    transcriber.connect(
        RealTimeParameters(
            sample_rate=asr_config.sample_rate,
            speech_model=asr_config.model,
        )
    )
    if not begin.wait(timeout=30):
        transcriber.disconnect(terminate=True)
        pytest.skip("ASR session did not begin; skipping")

    # Pace chunks against the wall clock. Firing the whole clip as fast as the
    # socket accepts hands AssemblyAI compressed speech, so the turn time we
    # measure back is an artifact of how we fed it, not a latency number.
    chunk_seconds = asr_config.frames_per_buffer / asr_config.sample_rate
    wall_start = time.perf_counter()
    for i, chunk in enumerate(chunks):
        delay = wall_start + (i + 1) * chunk_seconds - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        transcriber.stream(chunk)
    speech_end = time.perf_counter()

    transcript = None
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            transcript = turns.get(timeout=1.0)
            if transcript:
                break
        except _queue.Empty:
            continue
    transcriber.disconnect(terminate=True)

    if not transcript:
        pytest.skip("No transcript produced from audio file")

    # Measured from end of speech, which is what "turn latency" means.
    return _ms(speech_end), transcript


# ---------------------------------------------------------------- LLM

class TestLLMLatency:
    @pytest.mark.latency
    @pytest.mark.asyncio
    async def test_llm_latency(self, latency_results, require_keys):
        require_keys(["GROQ_API_KEY"])
        llm = LLMAgent()

        for i in range(LLM_ITERATIONS):
            start = time.perf_counter()
            async with llm.agent.run_stream(PROMPT) as result:
                ttft = None
                async for chunk in result.stream_text():
                    if ttft is None:
                        ttft = _ms(start)
                        latency_results.record(
                            component="llm", model=llm_config.model,
                            metric="llm_ttft", ms=ttft,
                        )
                total = _ms(start)
            latency_results.record(
                component="llm", model=llm_config.model,
                metric="llm_total", ms=total,
            )
            output = await result.get_output()
            assert output, "LLM produced no output"
            logger.info(
                "LLM iter %d: ttft=%.1fms total=%.1fms output=%s",
                i, ttft, total, output,
            )

    @pytest.mark.latency
    @pytest.mark.asyncio
    async def test_llm_latency_long(self, latency_results, require_keys):
        """Longer response so TTFT and total have room to diverge.

        On the short PROMPT, ttft ~= total simply because Groq generates
        a 1-3 sentence reply faster than the first network chunk arrives,
        not because timing is broken. This test uses a longer response to
        verify the streaming split is actually working.
        """
        require_keys(["GROQ_API_KEY"])
        llm = LLMAgent()

        for i in range(LLM_ITERATIONS):
            start = time.perf_counter()
            async with llm.agent.run_stream(LONG_PROMPT) as result:
                ttft = None
                async for chunk in result.stream_text():
                    if ttft is None:
                        ttft = _ms(start)
                        latency_results.record(
                            component="llm_long", model=llm_config.model,
                            metric="llm_ttft", ms=ttft,
                        )
                total = _ms(start)
            latency_results.record(
                component="llm_long", model=llm_config.model,
                metric="llm_total", ms=total,
            )
            output = await result.get_output()
            assert output, "LLM produced no output"
            gap = total - ttft if ttft is not None else None
            logger.info(
                "LLM long iter %d: ttft=%.1fms total=%.1fms gap=%.1fms",
                i, ttft, total, gap,
            )

    @pytest.mark.latency
    @pytest.mark.asyncio
    async def test_model_latency(self, latency_results, require_keys):
        require_keys(["GROQ_API_KEY"])
        llm = LLMAgent()
        start = time.perf_counter()
        response = await llm.generate_response(PROMPT)
        total = _ms(start)
        latency_results.record(
            component="model", model=llm_config.model,
            metric="llm_total", ms=total,
        )
        assert response
        logger.info("Model latency: %s total=%.1fms", llm_config.model, total)


# ---------------------------------------------------------------- TTS

class TestTTSLatency:
    @pytest.mark.latency
    def test_tts_latency(self, latency_results, require_keys):
        require_keys(["ELEVENLABS_API_KEY"])
        from voice_agent.tts import StreamingTTS

        tts = StreamingTTS()

        for i in range(TTS_ITERATIONS):
            start = time.perf_counter()
            stream = tts.client.text_to_speech.stream(
                text=TTS_SENTENCE,
                voice_id=tts_config.voice_id,
                model_id=tts_config.model_id,
                output_format=tts_config.output_format,
            )
            first_chunk = None
            total_bytes = 0
            for chunk in stream:
                if first_chunk is None:
                    first_chunk = _ms(start)
                    latency_results.record(
                        component="tts", model=tts_config.model_id,
                        metric="tts_first_chunk", ms=first_chunk,
                    )
                total_bytes += len(chunk)
            total = _ms(start)
            latency_results.record(
                component="tts", model=tts_config.model_id,
                metric="tts_total", ms=total,
            )
            audio_seconds = total_bytes / 2 / tts_config.sample_rate
            latency_results.record(
                component="tts", model=tts_config.model_id,
                metric="tts_audio_rate",
                ms=total / audio_seconds if audio_seconds else 0.0,
            )
            assert total_bytes > 0, "TTS produced no audio"
            logger.info(
                "TTS iter %d: first_chunk=%.1fms total=%.1fms bytes=%d",
                i, first_chunk, total, total_bytes,
            )


# ---------------------------------------------------------------- ASR

class TestASRLatency:
    @pytest.mark.latency
    def test_asr_connect_latency(self, latency_results, require_keys):
        require_keys(["ASSEMBLYAI_API_KEY"])
        import threading
        from assemblyai.streaming.v3 import (
            RealTimeEvents,
            RealTimeParameters,
            RealTimeTranscriber,
            RealTimeTranscriberOptions,
        )

        connect_times = []
        for i in range(ASR_ITERATIONS):
            begin = threading.Event()

            transcriber = RealTimeTranscriber(
                options=RealTimeTranscriberOptions(),
                api_key=asr_config.api_key,
            )
            transcriber.on(RealTimeEvents.Begin, lambda c, e: begin.set())

            start = time.perf_counter()
            transcriber.connect(
                RealTimeParameters(
                    sample_rate=asr_config.sample_rate,
                    speech_model=asr_config.model,
                )
            )
            if not begin.wait(timeout=30):
                transcriber.disconnect(terminate=True)
                pytest.skip("ASR session did not begin; skipping")
            connect_ms = _ms(start)
            connect_times.append(connect_ms)
            latency_results.record(
                component="asr", model=asr_config.model,
                metric="asr_connect", ms=connect_ms,
            )
            transcriber.disconnect(terminate=True)
            logger.info("ASR connect iter %d: %.1fms", i, connect_ms)

        assert len(connect_times) == ASR_ITERATIONS

    @pytest.mark.latency
    def test_asr_turn_latency(self, latency_results, require_keys):
        audio_file = os.getenv("ASR_AUDIO_FILE")
        if not audio_file:
            pytest.skip("Set ASR_AUDIO_FILE=<path to speech wav> to measure STT turn latency")
        require_keys(["ASSEMBLYAI_API_KEY"])

        turn_ms, transcript = _measure_real_asr_turn(audio_file)
        latency_results.record(
            component="asr", model=asr_config.model,
            metric="asr_turn", ms=turn_ms,
        )
        logger.info("ASR turn latency: %.1fms transcript=%s", turn_ms, transcript)


# ---------------------------------------------------------------- E2E

class TestEndToEndLatency:
    @pytest.mark.latency
    @pytest.mark.asyncio
    async def test_e2e_pipeline_latency(self, latency_results, require_keys):
        """Speech-to-speech pipeline latency.

        If ASR_AUDIO_FILE is set, real ASR turn latency (end of speech ->
        final transcript) is measured and folded into the total. Without it,
        ASR is mocked at 0ms and the result is a best-case LLM+TTS-only
        floor -- NOT representative of real speech-to-speech latency.

        The total is a serial sum of separately-measured stages. The real
        pipeline does not actually run end to end here -- there is no mic and
        no speaker -- so treat this as an upper bound that moves when a stage
        moves, not as a measurement of this agent talking to a human.
        """
        require_keys(["GROQ_API_KEY", "ELEVENLABS_API_KEY"])

        audio_file = os.getenv("ASR_AUDIO_FILE")
        asr_turn_ms = 0.0

        if audio_file:
            require_keys(["ASSEMBLYAI_API_KEY"])
            asr_turn_ms, transcribed_text = _measure_real_asr_turn(audio_file)
            latency_results.record(
                component="e2e", model=asr_config.model,
                metric="e2e_asr_turn", ms=asr_turn_ms,
            )
            user_text_fixed = transcribed_text or PROMPT
        else:
            logger.warning(
                "ASR_AUDIO_FILE not set -- e2e_pipeline excludes real ASR "
                "turn latency and is a best-case LLM+TTS floor, not a true "
                "speech-to-speech number."
            )
            user_text_fixed = PROMPT

        class FakeASR:
            async def get_next_turn(self):
                await asyncio.sleep(0)
                return user_text_fixed

        from voice_agent.llm import LLMAgent
        from voice_agent.tts import StreamingTTS

        llm = LLMAgent()
        tts = StreamingTTS()
        asr = FakeASR()

        for i in range(LLM_ITERATIONS):
            user_text = await asr.get_next_turn()

            # Each stage is timed on its own real clock. The total is then
            # summed explicitly rather than backdated onto a single fake
            # start time, so the number is honest about being a serial
            # estimate and not a live end-to-end measurement.
            start = time.perf_counter()

            ttft = None
            async with llm.agent.run_stream(user_text) as result:
                async for chunk in result.stream_text():
                    if ttft is None:
                        ttft = _ms(start)
                        break
            llm_total = _ms(start)
            output = await result.get_output()

            tts_start = time.perf_counter()
            audio_stream = tts.client.text_to_speech.stream(
                text=output,
                voice_id=tts_config.voice_id,
                model_id=tts_config.model_id,
                output_format=tts_config.output_format,
            )
            first_audio = None
            for chunk in audio_stream:
                if first_audio is None:
                    first_audio = _ms(tts_start)
                break

            speak_latency = asr_turn_ms + llm_total + first_audio
            # ponytail: summing stages cannot see overlap between them, so this
            # over-reports once the pipeline gets concurrent. Upgrade to a fully
            # instrumented live run with a real mic before publishing a number.
            latency_results.record(
                component="e2e", model=llm_config.model,
                metric="e2e_pipeline", ms=speak_latency,
            )
            logger.info(
                "E2E iter %d: asr=%.1fms llm_total=%.1fms ttft=%.1fms tts_first=%.1fms -> sum %.1fms",
                i, asr_turn_ms, llm_total, ttft, first_audio, speak_latency,
            )

            samples = latency_results.get("e2e", "e2e_pipeline")
            assert samples, "no e2e samples recorded"


class TestPipelinedFirstAudio:
    @pytest.mark.latency
    @pytest.mark.asyncio
    async def test_pipelined_first_audio_latency(self, latency_results, require_keys):
        """Does streaming the LLM into TTS actually make the agent start sooner?

        The serial path waits for the whole reply before touching TTS, so it
        costs llm_total + tts_first. The pipelined path starts TTS on the first
        complete sentence, costing llm_first_sentence + tts_first. Both paths
        run in the same loop so the comparison is like for like.

        Caveat: only tool-free replies benefit. If the model calls a tool first,
        no text streams until the tool returns, so first_sentence waits it out.
        """
        require_keys(["GROQ_API_KEY", "ELEVENLABS_API_KEY"])

        from voice_agent.tts import StreamingTTS

        llm = LLMAgent()
        tts = StreamingTTS()

        for i in range(PIPELINE_ITERATIONS):
            # Serial reference: full reply, then TTS.
            start = time.perf_counter()
            output = await llm.generate_response(PROMPT)
            serial_llm = _ms(start)

            serial_tts_start = time.perf_counter()
            stream = tts.client.text_to_speech.stream(
                text=output,
                voice_id=tts_config.voice_id,
                model_id=tts_config.model_id,
                output_format=tts_config.output_format,
            )
            first = next(iter(stream), None)
            serial_tts = _ms(serial_tts_start)

            latency_results.record(
                component="e2e", model=llm_config.model,
                metric="e2e_pipeline", ms=serial_llm + serial_tts,
            )

            # Pipelined: TTS starts on the first finished sentence.
            pipe_start = time.perf_counter()
            first_sentence = None
            pipelined_tts = None

            async def on_first(sentence):
                nonlocal first_sentence, pipelined_tts
                if first_sentence is not None:
                    return
                first_sentence = _ms(pipe_start)
                latency_results.record(
                    component="llm", model=llm_config.model,
                    metric="llm_first_sentence", ms=first_sentence,
                )
                s_start = time.perf_counter()
                for _chunk in tts.client.text_to_speech.stream(
                    text=sentence,
                    voice_id=tts_config.voice_id,
                    model_id=tts_config.model_id,
                    output_format=tts_config.output_format,
                ):
                    pipelined_tts = _ms(s_start)
                    break

            await llm.stream_into(PROMPT, on_first)

            assert first_sentence is not None, "no sentence produced"
            latency_results.record(
                component="e2e", model=llm_config.model,
                metric="e2e_first_audio", ms=first_sentence + (pipelined_tts or 0.0),
            )

            logger.info(
                "Pipelined iter %d: serial=%.1fms first_sentence=%.1fms pipelined=%.1fms",
                i, serial_llm + serial_tts, first_sentence, first_sentence + pipelined_tts,
            )
            assert first is not None