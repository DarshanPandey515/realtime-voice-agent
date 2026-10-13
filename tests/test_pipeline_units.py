"""Unit checks for pipeline logic that needs no API keys and no audio device.

Covers the pieces that are easy to break silently: the bash allowlist, turn
pairing in conversation history, and sentence splitting.
"""

import asyncio

import pytest

from voice_agent.tools import BashTool, MAX_CONTENT, _rejection_reason


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

    def run_stream(self, prompt, message_history=None):
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


def _bare_agent():
    """VoiceAgent without __init__, which would open real clients."""
    from voice_agent.main import VoiceAgent
    agent = VoiceAgent.__new__(VoiceAgent)
    agent.tts = _FakeTTS()
    agent.is_running = True
    agent._turns = asyncio.Queue(maxsize=1)
    agent._barge_in = asyncio.Event()
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