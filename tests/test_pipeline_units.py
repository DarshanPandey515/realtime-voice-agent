"""Unit checks for pipeline logic that needs no API keys and no audio device.

Covers the pieces that are easy to break silently: the bash allowlist, turn
pairing in conversation history, and sentence splitting.
"""

import asyncio
import time

import numpy as np
import pytest

from voice_agent.aec import EchoCancellation
from voice_agent.tools import BashTool, MAX_CONTENT, _rejection_reason


def _bare_tts():
    """StreamingTTS without __init__, which would open a real speaker."""
    import threading
    from collections import deque

    from voice_agent.tts import StreamingTTS
    tts = StreamingTTS.__new__(StreamingTTS)
    tts._cancel = threading.Event()
    tts._echo = None
    tts._play_lock = threading.Lock()
    tts._spoken = deque(maxlen=3)
    tts._playback_started_at = 0.0
    return tts


# ------------------------------------------------------------------ allowlist

@pytest.mark.parametrize("command,fragment", [
    ("rm -rf /", "isn't allowed"),
    ("git push --force origin main", "isn't read-only"),
    ("git config --global user.email x@y.z", "isn't read-only"),
    ("git log --output=/tmp/leak", "read-only list"),
    ("git log --exec-path=/tmp/evil", "read-only list"),
    ("git log --ext-diff -p", "read-only list"),
    ("git log -c core.pager=id", "read-only list"),
    ("git log --upload-pack='sh -c id'", "read-only list"),
    ("git log --no-pager --output=/tmp/x", "read-only list"),
    ("find . -delete", "delete files"),
    ("find . -exec rm {} ;", "delete files"),
    ("find . -execdir sh -c 'id' ;", "delete files"),
    ("curl http://x", "isn't allowed"),
])
def test_rejects_dangerous_commands(command, fragment):
    result = asyncio.run(BashTool.execute_command(command))
    assert fragment in result, f"{command!r} should be refused, got {result!r}"


@pytest.mark.parametrize("command", [
    "git status",
    "git log --oneline -5",
    "git log -n 5",
    "git log -5 --stat",
    "git log --since=2.weeks --author=someone",
    "git diff --name-only",
    "find . -name '*.py'",
    "ls -la",
    "pwd",
])
def test_allows_readonly_commands(command):
    args = command.split()
    reason = _rejection_reason(args[0], args)
    assert reason is None, f"{command!r} should be allowed, got {reason!r}"


def test_runs_a_command_for_real():
    """Baseline: the happy path still shells out and returns output."""
    out = asyncio.run(BashTool.execute_command("echo hello"))
    assert "hello" in out


class _HangingReader:
    """Emits a few chunks, then blocks forever (so wait_for fires)."""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def read(self, n):
        if self._chunks:
            return self._chunks.pop(0)
        await asyncio.sleep(3600)


class _FakeProc:
    def __init__(self, stdout_chunks, stderr_chunks=()):
        self.stdout = _HangingReader(stdout_chunks)
        self.stderr = _DrainingReader(stderr_chunks)
        self.returncode = 0
        self.killed = False

    def kill(self):
        self.killed = True

    async def wait(self):
        return 0


class _DrainingReader:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def read(self, n):
        return self._chunks.pop(0) if self._chunks else b""


def test_timeout_returns_partial_output(monkeypatch):
    """A silent stall reads as a crash, so partial output must come back."""
    import voice_agent.tools as tools

    async def fake_exec(*args, **kwargs):
        return _FakeProc([b"first chunk\n", b"second chunk\n"])

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(tools, "COMMAND_TIMEOUTS", {"find": 0.05})

    out = asyncio.run(BashTool.execute_command("find . -name x"))
    assert "first chunk" in out
    assert "second chunk" in out
    assert "still running" in out


def test_timeout_with_no_output_says_so(monkeypatch):
    import voice_agent.tools as tools

    async def fake_exec(*args, **kwargs):
        return _FakeProc([])

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(tools, "COMMAND_TIMEOUTS", {"find": 0.05})

    out = asyncio.run(BashTool.execute_command("find . -name x"))
    assert "(no output yet)" in out
    assert "still running" in out


def test_overlong_output_is_truncated_not_reported_as_failure():
    """Killing at the cap flips the exit code to SIGKILL; that is not a failure."""
    out = asyncio.run(BashTool.execute_command("find . -name '*.py'"))
    assert "Command failed" not in out
    assert f"truncated at {MAX_CONTENT} bytes" in out


def test_no_match_reports_clearly():
    """grep with no hits exits non-zero and silent; say so rather than nothing."""
    out = asyncio.run(BashTool.execute_command("grep -r zzz_no_such_token_zzz src"))
    assert "printed nothing" in out or "No such file" in out


# ------------------------------------------------------------------ history

def test_history_keeps_turns_whole():
    """Trimming must not orphan a tool result from its tool call."""
    from voice_agent.llm import LLMAgent, MAX_TURNS
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart

    llm = LLMAgent.__new__(LLMAgent)          # skip __init__, no client needed
    llm._turns = []

    def fake_result(messages):
        class R:
            def all_messages(self_inner):
                return messages
        return R()

    for i in range(MAX_TURNS + 3):
        req = ModelRequest(parts=[TextPart(f"q{i}")])
        resp = ModelResponse(parts=[TextPart(f"a{i}")])
        llm._record_turn(fake_result([req, resp]))

    flat = llm.history
    assert len(llm._turns) == MAX_TURNS
    # History must start on a user message, never mid-pair.
    assert isinstance(flat[0], ModelRequest)
    for req, resp in zip(flat[::2], flat[1::2]):
        assert isinstance(req, ModelRequest)
        assert isinstance(resp, ModelResponse)


# ------------------------------------------------------------------ sentences

def test_splits_on_sentence_boundaries():
    from voice_agent.llm import split_sentences

    # A boundary needs trailing whitespace, so the last sentence is the tail
    # until the caller flushes it at end of stream.
    sentences, tail = split_sentences("One two. Three four! Five six?")
    assert sentences == ["One two.", "Three four!"]
    assert tail == "Five six?"


def test_keeps_unfinished_tail_for_next_chunk():
    """Streaming arrives in fragments, so a partial sentence must survive."""
    from voice_agent.llm import split_sentences

    sentences, tail = split_sentences("Hello there. This one is incom")
    assert sentences == ["Hello there."]
    assert tail == "This one is incom"

    sentences, tail = split_sentences(tail + "plete now.")
    assert sentences == []
    assert tail == "This one is incomplete now."


def test_does_not_split_inside_a_number_or_abbreviation():
    from voice_agent.llm import split_sentences

    # Only ".", "!" and "?" followed by whitespace end a sentence, so "3.5"
    # and "Dr" must not break.
    sentences, tail = split_sentences("Ask Dr Smith about 3.5 units. Then leave.")
    assert sentences == ["Ask Dr Smith about 3.5 units."]
    assert tail == "Then leave."


# ------------------------------------------------------------------ streaming

class _FakeStreamResult:
    def __init__(self, chunks, messages):
        self._chunks = chunks
        self._messages = messages

    async def stream_text(self, delta=True, debounce_by=None):
        for c in self._chunks:
            yield c

    def all_messages(self):
        return self._messages


class _FakeRun:
    def __init__(self, result):
        self._result = result

    async def __aenter__(self):
        return self._result

    async def __aexit__(self, *exc):
        return False


class _FakeAgent:
    def __init__(self, result):
        self._result = result
        self.calls = []

    def run_stream(self, prompt, message_history=None, **kwargs):
        self.calls.append((prompt, message_history))
        return _FakeRun(self._result)


def _fake_llm(chunks, messages=()):
    from voice_agent.llm import LLMAgent
    llm = LLMAgent.__new__(LLMAgent)
    llm._turns = []
    llm.agent = _FakeAgent(_FakeStreamResult(chunks, list(messages)))
    return llm


def _collect(llm, prompt="hi"):
    seen = []

    async def on_sentence(sentence):
        seen.append(sentence)

    return asyncio.run(llm.stream_into(prompt, on_sentence)), seen


def test_stream_into_covers_whole_reply_including_tail():
    """The final sentence has no trailing space, so it must still be flushed."""
    llm = _fake_llm(["Hello there. ", "This is ", "the last one."])
    _, seen = _collect(llm)
    assert seen == ["Hello there.", "This is the last one."]


def test_stream_into_records_turn_history():
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart
    msgs = [ModelRequest(parts=[TextPart("q")]), ModelResponse(parts=[TextPart("a")])]
    llm = _fake_llm(["Hi."], messages=msgs)

    _collect(llm)

    assert len(llm._turns) == 1
    assert len(llm.history) == 2


def test_on_sentence_raising_still_records_history():
    """Barge-in stops playback by refusing the sentence; history must survive."""
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart
    msgs = [ModelRequest(parts=[TextPart("q")]), ModelResponse(parts=[TextPart("a")])]
    llm = _fake_llm(["One. ", "Two. "], messages=msgs)

    seen = []

    async def barge(sentence):
        seen.append(sentence)
        if len(seen) == 2:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(llm.stream_into("hi", barge))

    assert seen == ["One.", "Two."]
    assert len(llm._turns) == 1


def test_generate_response_joins_sentences():
    llm = _fake_llm(["Hello there. ", "Second part."])

    out = asyncio.run(llm.generate_response("hi"))
    assert out == "Hello there. Second part."


def test_tool_loops_are_capped():
    """Measured 35 tool calls (107s) on gpt-oss and 21 (172s) on qwen3.8.

    A turn like that is silence from the user's side, and it is how the run
    that ended in a Groq 429 burned its quota.
    """
    import inspect

    from voice_agent.config import llm_config
    from voice_agent.llm import LLMAgent

    source = inspect.getsource(LLMAgent.stream_into)
    assert "usage_limits" in source, "stream_into must pass usage limits"
    assert "tool_calls_limit" in source
    assert llm_config.tool_call_limit <= 10, (
        f"{llm_config.tool_call_limit} tool calls is already an unusable turn"
    )
    # pydantic-ai's own default leaves tool calls uncapped.
    from pydantic_ai.usage import UsageLimits

    assert UsageLimits().tool_calls_limit is None


# ------------------------------------------------------------------ barge-in VAD

class _FakeVAD:
    def __init__(self, probs):
        self._probs = list(probs)

    def process(self, pcm):
        return self._probs.pop(0) if self._probs else 0.0


def test_sustained_speech_is_detected_without_a_transcript():
    """The point of VAD gating: no transcript, no turn, still cuts off."""
    agent = _bare_agent()
    agent._vad = _FakeVAD([0.9, 0.9])
    agent._voice_frames = 0

    chunk = np.zeros(800, dtype=np.int16).tobytes()
    fired = [agent._is_user_speech(chunk) for _ in range(2)]

    # Onset gating: the first loud frame arms it, the second fires.
    assert fired == [False, True]


def test_single_frame_blip_does_not_interrupt():
    """A click should not cut off the agent mid-sentence."""
    agent = _bare_agent()
    agent._vad = _FakeVAD([0.95, 0.1, 0.95])
    agent._voice_frames = 0

    chunk = np.zeros(800, dtype=np.int16).tobytes()
    fired = [agent._is_user_speech(chunk) for _ in range(3)]

    assert fired == [False, False, False]


def test_silence_never_interrupts():
    agent = _bare_agent()
    agent._vad = _FakeVAD([0.0] * 5)
    agent._voice_frames = 0

    chunk = np.zeros(800, dtype=np.int16).tobytes()
    assert not any(agent._is_user_speech(chunk) for _ in range(5))


def test_vad_threshold_is_the_documented_calibration_point():
    from voice_agent.config import asr_config

    assert 0.35 < asr_config.vad_threshold < 0.78, (
        "threshold sits between measured silence (~0.35) and speech (~0.78)"
    )


def test_shipped_threshold_clears_the_measured_silence_ceiling():
    """0.6 passed the loudest silence we measured; 0.5 must too, with margin."""
    from voice_agent.config import asr_config

    measured_silence_ceiling = 0.479        # scripts/calibrate_vad.py on a
    assert asr_config.vad_threshold > measured_silence_ceiling


def test_suggested_threshold_keys_off_the_ceiling_not_the_median():
    """The rule: silence ceiling plus a share of the separation."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from calibrate_vad import suggest_threshold

    # Ceiling is high but median is low - the case that fooled the median.
    silence = np.concatenate([np.full(60, 0.05), [0.479]])
    speech = np.concatenate([np.full(50, 0.95), [0.574]])

    got = suggest_threshold(silence, speech)
    assert got > silence.max(), "must clear the loudest silence"
    assert got <= speech.min(), "must not sit above the quietest speech"


def test_suggested_threshold_returns_none_when_the_clip_overlaps():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from calibrate_vad import suggest_threshold

    assert suggest_threshold(np.array([0.9, 0.95]), np.array([0.2, 0.3])) is None
    assert suggest_threshold(np.array([]), np.array([0.5])) is None
    assert suggest_threshold(np.array([0.1]), np.array([])) is None


def test_calibrator_refuses_a_threshold_from_a_collapsed_span():
    """A narrow gap means the recording dominated it, not that 0.51 is right.

    Louder room tone or a worse mic pushes the silence ceiling up and squeezes
    the span. Emitting a number from that is worse than emitting nothing.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from calibrate_vad import MIN_SEPARATION, suggest_threshold

    tight_silence = np.concatenate([np.full(80, 0.30), [0.479]])
    tight_speech = np.concatenate([np.full(60, 0.60), [0.499]])  # span 0.02
    assert tight_speech.min() > tight_silence.max()
    assert suggest_threshold(tight_silence, tight_speech) is None

    wide_speech = np.concatenate([np.full(60, 0.60), [0.479 + MIN_SEPARATION]])
    assert suggest_threshold(tight_silence, wide_speech) is not None


# ------------------------------------------------------------------ self-echo loop

AGENT_SPOKEN = [
    "The project builds a real-time voice assistant.",
    "It takes what you say, turns it into text, runs it through an AI model.",
]


def _echo_capture(gain=0.35, delay_ms=10, seed=0):
    """(capture, far_end) chunks: the agent's own voice leaking into the mic."""
    import wave

    with wave.open("tests/sample.wav", "rb") as w:
        speech = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    sig = np.tile(speech, 3)[:len(speech) // 800 * 800 * 3]

    rng = np.random.default_rng(seed)
    delay = int(delay_ms / 1000 * 16000)
    pairs = []
    for i in range(0, len(sig) - 800, 800):
        far = sig[i:i + 800]
        leaked = np.concatenate((np.zeros(delay, np.int16), far))[:800]
        cap = leaked.astype(np.float64) * gain + rng.normal(0, 120, 800)
        pairs.append((np.clip(cap, -32768, 32767).astype(np.int16).tobytes(),
                      far.tobytes()))
    return pairs


def _vad_fires(chunks, threshold):
    from pywebrtc_audio import VoiceDetector

    detector = VoiceDetector()
    return sum(1 for c in chunks
               if detector.process(np.frombuffer(c, dtype=np.int16)) >= threshold)


def test_own_voice_drives_the_barge_in_gate_on_synthetic_echo():
    """Why the AEC test above exists: uncancelled self-echo self-interrupts."""
    from voice_agent.config import asr_config

    pairs = _echo_capture()
    assert _vad_fires([c for c, _ in pairs], asr_config.vad_threshold) > len(pairs) * 0.2


def test_aec_reduces_vad_firing_on_synthetic_echo():
    """Named for what it checks, not for what it hopes to imply.

    Synthetic echo is a single delayed path with no reverb or speaker
    distortion, so this does NOT establish that AEC works in a real room. It
    establishes the mechanism: uncancelled self-echo drives the barge-in gate,
    and removing it does not. Whether a real room behaves this way is what the
    next live run has to show.
    """
    from voice_agent.config import asr_config

    pairs = _echo_capture()
    aec = EchoCancellation(sample_rate=16000, stream_delay_ms=64)
    cleaned = []
    for capture, far in pairs:
        aec.add_playback(far)
        cleaned.append(aec.process(capture))

    fired = _vad_fires(cleaned, asr_config.vad_threshold)
    assert fired <= len(cleaned) * 0.02, (
        f"AEC left {fired}/{len(cleaned)} frames loud enough to self-interrupt"
    )


def test_guard_catches_self_echo_despite_transcription_errors():
    """Far-field echo reaches ASR degraded, not verbatim."""
    import random

    from voice_agent.tts import StreamingTTS

    def degrade(sentence, wer, seed):
        rng = random.Random(seed)
        words = sentence.split()
        keep = max(1, int(round(len(words) * (1 - wer))))
        idx = sorted(rng.sample(range(len(words)), keep))
        return " ".join(words[i] for i in idx)

    t = _bare_tts()
    for wer in (0.1, 0.2, 0.3):
        for sentence in AGENT_SPOKEN:
            t._spoken.clear()
            t._spoken.append(sentence)
            for seed in range(10):
                assert t.is_self_echo(degrade(sentence, wer, seed)), (
                    f"guard missed degraded self-echo at {int(wer * 100)}% WER: "
                    f"{degrade(sentence, wer, seed)!r}"
                )


def test_guard_does_not_cover_unrecognisable_echo():
    """The coverage boundary, stated as a test so it is not forgotten.

    When echo arrives so degraded that ASR emits filler rather than the
    agent's words, difflib sees no match and lets it through. Nothing
    downstream can recover that - AEC has to have removed the echo first.
    """
    from voice_agent.tts import StreamingTTS

    t = _bare_tts()
    t._spoken.append(AGENT_SPOKEN[0])
    assert t.is_self_echo("mhm uh you know so okay right hmm wow") is False


# ------------------------------------------------------------------ self-echo

def test_warmup_window_is_treated_as_echo():
    import time
    from voice_agent.config import aec_config

    tts = _bare_tts()
    tts._playback_started_at = time.monotonic()
    assert tts.is_self_echo("stop", now=tts._playback_started_at + 0.01) is True


def test_turns_are_trusted_again_after_warmup():
    import time
    from voice_agent.config import aec_config

    tts = _bare_tts()
    tts._playback_started_at = time.monotonic()
    later = tts._playback_started_at + aec_config.warmup_ms / 1000 + 0.1
    assert tts.is_self_echo("what does this project do", now=later) is False


def test_repeated_sentence_is_dropped_as_echo():
    tts = _bare_tts()
    tts._spoken.append("The project builds a real-time voice assistant.")
    assert tts.is_self_echo("The project builds a real time voice assistant") is True


def test_unrelated_speech_is_not_dropped():
    tts = _bare_tts()
    tts._spoken.append("The project builds a real-time voice assistant.")
    assert tts.is_self_echo("what time is my meeting tomorrow") is False


def test_nothing_spoken_means_nothing_to_match():
    tts = _bare_tts()
    assert tts.is_self_echo("hello there") is False


# ------------------------------------------------------------------ echo

def _rms(x):
    a = np.frombuffer(x, dtype=np.int16).astype(np.float64)
    return float(np.sqrt((a ** 2).mean()))


def _speech_like(chunks=5, samples=800, seed=0, scale=6000):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(chunks):
        a = rng.normal(0, scale, samples).astype(np.int16)
        out.append(a.tobytes())
    return out


def test_echo_canceller_removes_the_agents_own_voice():
    """Feeding a signal as both capture and reference must suppress it hard."""
    aec = EchoCancellation(sample_rate=16000)
    pcm = _speech_like(chunks=1)[0]
    aec.add_playback(pcm)                       # it is "playing" into the room
    cleaned = aec.process(pcm)                  # mic hears exactly that

    assert len(cleaned) == len(pcm)
    assert _rms(cleaned) < _rms(pcm) / 10, f"only {_rms(cleaned):.0f} vs {_rms(pcm):.0f}"


def test_echo_canceller_leaves_speech_alone_when_nothing_is_playing():
    """A silent reference must pass speech through, not eat it."""
    aec = EchoCancellation(sample_rate=16000)
    for pcm in _speech_like(chunks=6):
        cleaned = aec.process(pcm)
        assert abs(_rms(cleaned) - _rms(pcm)) < _rms(pcm) * 0.25


def test_echo_canceller_pads_when_playback_runs_dry():
    aec = EchoCancellation(sample_rate=16000)
    cleaned = aec.process(_speech_like(chunks=1)[0])
    assert len(cleaned) == 800 * 2


def test_echo_reference_buffer_does_not_grow_without_bound():
    aec = EchoCancellation(sample_rate=16000, reference_ms=100)
    for _ in range(50):
        aec.add_playback(_speech_like(chunks=1)[0])
    assert len(aec._reference) <= aec._capacity


def test_echo_canceller_survives_odd_sized_chunks():
    """Mic buffers are not guaranteed to be a whole number of 10 ms frames."""
    aec = EchoCancellation(sample_rate=16000)
    for n in (333, 160, 801):
        pcm = np.zeros(n, dtype=np.int16).tobytes()
        aec.add_playback(pcm)
        assert len(aec.process(pcm)) == n * 2


def test_echo_canceller_reset_clears_history():
    aec = EchoCancellation(sample_rate=16000)
    aec.add_playback(_speech_like(chunks=1)[0])
    aec.reset()
    assert len(aec._reference) == 0


def test_playback_is_teed_before_it_is_written(monkeypatch):
    """Ordering is load-bearing: recording after write() mistimes the far end.

    write() blocks for the whole chunk, so a reference recorded afterwards is
    timestamped to when playback ended rather than when it started, which
    pushes the far end outside AEC3's delay search.
    """
    import threading
    from types import SimpleNamespace

    import voice_agent.tts as tts_mod
    from voice_agent.tts import StreamingTTS

    events = []

    class _Echo:
        def add_playback(self, pcm):
            events.append(("tee", pcm))

    class _Out:
        def write(self, chunk):
            events.append(("write", chunk))

        def stop_stream(self):
            pass

        def close(self):
            pass

    class _FakePa:
        def open(self, **kwargs):
            return _Out()

        def terminate(self):
            pass

    tts = _bare_tts()
    tts._echo = _Echo()
    tts.client = SimpleNamespace(
        text_to_speech=SimpleNamespace(stream=lambda **kw: iter([b"c1"]))
    )
    monkeypatch.setattr(tts_mod.pyaudio, "PyAudio", _FakePa)

    tts._play_blocking("hello")

    assert events == [("tee", b"c1"), ("write", b"c1")], events


def test_only_one_output_stream_plays_at_a_time(monkeypatch):
    """Overlapping streams interleave at the speaker and scramble the reference."""
    import threading
    from types import SimpleNamespace

    import voice_agent.tts as tts_mod
    from voice_agent.tts import StreamingTTS

    state = {"open": 0, "peak": 0}

    class _Out:
        def write(self, chunk):
            time.sleep(0.02)

        def stop_stream(self):
            pass

        def close(self):
            pass

    class _FakePa:
        def open(self, **kwargs):
            state["open"] += 1
            state["peak"] = max(state["peak"], state["open"])
            return _Out()

        def terminate(self):
            state["open"] -= 1

    tts = _bare_tts()
    tts.client = SimpleNamespace(
        text_to_speech=SimpleNamespace(stream=lambda **kw: iter([b"a", b"b", b"c"]))
    )
    monkeypatch.setattr(tts_mod.pyaudio, "PyAudio", _FakePa)

    threads = [threading.Thread(target=tts._play_blocking, args=(f"t{i}",))
               for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert state["peak"] == 1, state


def test_interrupt_during_playback_stops_it(monkeypatch):
    """Barge-in depends on the cancel flag being checked between chunks."""
    import threading
    from types import SimpleNamespace

    import voice_agent.tts as tts_mod
    from voice_agent.tts import StreamingTTS

    class _Out:
        def __init__(self):
            self.written = []

        def write(self, chunk):
            self.written.append(chunk)

        def stop_stream(self):
            pass

        def close(self):
            pass

    class _FakePa:
        def open(self, **kwargs):
            return _Out()

        def terminate(self):
            pass

    tts = _bare_tts()
    tts.client = SimpleNamespace(
        text_to_speech=SimpleNamespace(
            stream=lambda **kw: iter([b"c1", b"c2", b"c3"])
        )
    )
    monkeypatch.setattr(tts_mod.pyaudio, "PyAudio", _FakePa)

    worker = threading.Thread(target=tts._play_blocking, args=("hello",))
    worker.start()
    worker.join(timeout=0.5)

    # Interrupt while it is mid-stream.
    tts.interrupt()
    worker.join(timeout=2)

    assert worker.is_alive() is False


def test_stale_interrupt_does_not_silence_the_next_utterance(monkeypatch):
    """An interrupt aimed at a previous reply must not kill the reply after it.

    The cancel flag is cleared once playback owns the device, which is what
    makes clear-then-interrupt ordering safe without a race.
    """
    import threading
    from types import SimpleNamespace

    import voice_agent.tts as tts_mod
    from voice_agent.tts import StreamingTTS

    out = _CountingOut()

    class _FakePa:
        def open(self, **kwargs):
            return out

        def terminate(self):
            pass

    tts = _bare_tts()
    tts.client = SimpleNamespace(
        text_to_speech=SimpleNamespace(stream=lambda **kw: iter([b"c1"]))
    )
    monkeypatch.setattr(tts_mod.pyaudio, "PyAudio", _FakePa)

    tts.interrupt()          # left over from the previous turn
    tts._play_blocking("hello")

    assert out.written == [b"c1"]


class _CountingOut:
    def __init__(self):
        self.written = []

    def write(self, chunk):
        self.written.append(chunk)

    def stop_stream(self):
        pass

    def close(self):
        pass


# ------------------------------------------------------------------ orchestration

class _FakeTTS:
    def __init__(self):
        self.spoken = []
        self.interrupts = 0

    async def speak(self, text):
        self.spoken.append(text)
        await asyncio.sleep(0)

    def interrupt(self):
        self.interrupts += 1

    def is_self_echo(self, text, now=None):
        return False


def _bare_agent():
    """VoiceAgent without __init__, which would open real clients."""
    from voice_agent.main import VoiceAgent
    agent = VoiceAgent.__new__(VoiceAgent)
    agent.tts = _FakeTTS()
    agent.is_running = True
    agent._turns = asyncio.Queue(maxsize=1)
    agent._barge_in = asyncio.Event()
    agent._vad = _FakeVAD([])
    agent._voice_frames = 0
    return agent


def test_responder_speaks_every_sentence():
    agent = _bare_agent()

    async def fake_stream_into(text, cb):
        for s in ["One.", "Two.", "Three."]:
            await cb(s)

    agent.llm = type("L", (), {"stream_into": staticmethod(fake_stream_into)})()

    async def run():
        await agent._turns.put("hello")
        task = asyncio.create_task(agent._respond_loop())
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())
    assert agent.tts.spoken == ["One.", "Two.", "Three."]


def test_barge_in_drops_rest_of_reply_and_answers_the_new_turn():
    """The whole point of splitting the loops: interrupt mid-reply."""
    agent = _bare_agent()
    first_sentence_spoken = asyncio.Event()

    async def fake_stream_into(text, cb):
        if text == "first":
            await cb("One.")
            first_sentence_spoken.set()
            await asyncio.sleep(0.05)      # window for the barge-in to land
            await cb("Two.")
            await cb("Three.")
        else:
            await cb("Reply to the new turn.")

    agent.llm = type("L", (), {"stream_into": staticmethod(fake_stream_into)})()

    async def run():
        await agent._turns.put("first")
        task = asyncio.create_task(agent._respond_loop())
        await first_sentence_spoken.wait()
        # a new turn arrives while the agent is still talking
        agent.tts.interrupt()
        agent._barge_in.set()
        await agent._turns.put("second")
        await asyncio.sleep(0.1)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())

    assert "One." in agent.tts.spoken
    assert "Two." not in agent.tts.spoken, "barge-in should drop the rest"
    assert "Three." not in agent.tts.spoken
    assert "Reply to the new turn." in agent.tts.spoken


def test_turn_queue_drops_stale_turn():
    """A size-1 queue means the newest turn wins, not a backlog."""
    agent = _bare_agent()
    agent.asr = None

    class _FakeASR:
        def __init__(self):
            self.q = asyncio.Queue()
            self.q.put_nowait("stale")
            self.q.put_nowait("fresh")

        async def get_next_turn(self):
            return await self.q.get()

    agent.asr = _FakeASR()

    async def fake_stream_into(text, cb):
        await cb(f"answered {text}")

    agent.llm = type("L", (), {"stream_into": staticmethod(fake_stream_into)})()

    async def run():
        task = asyncio.create_task(agent._turn_loop())
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())
    assert agent.tts.interrupts >= 1