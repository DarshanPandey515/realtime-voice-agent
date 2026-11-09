"""Does the runaway brake actually stop a runaway turn?

The live prompt that once ran 76 s stopped looping on its own, so the cap
never fired and never proved itself. This forces the loop instead: a
function-backed model that always asks for another tool call, which is the
worst case the real model produced and reproduces every time.

Each test proves its own premise first. A limit test that passes because
the loop never happened is the same failure as a cap that silently does
nothing - the one that cost 35 tool calls and 107 s.
"""

import pytest

from pydantic_ai import Agent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits


def _forever(tool_name: str, tool_args: dict):
    """A stream function that only ever asks for another tool call."""
    import json

    from pydantic_ai.models.function import DeltaToolCall

    async def stream_function(messages, info):
        # Tool call only. Yielding text alongside it ends the run at that
        # response, which silently defeats the whole harness.
        yield {0: DeltaToolCall(name=tool_name,
                                json_args=json.dumps(tool_args),
                                tool_call_id="loop-1")}
    return stream_function


def _looping_agent(executed: list[str]):
    """Agent whose model loops forever on a tool that always succeeds."""
    async def ping(n: int) -> str:
        """Returns something that invites another call."""
        executed.append(str(n))
        return f"result {n}: please fetch more"

    agent = Agent(model=FunctionModel(
        stream_function=_forever("ping", {"n": 1})))
    agent.tool_plain(ping)
    return agent


async def _run(agent, limits):
    try:
        async with agent.run_stream("go", usage_limits=limits) as result:
            async for _ in result.stream_text():
                pass
    except UsageLimitExceeded as e:
        return e
    return None


@pytest.mark.asyncio
async def test_the_harness_really_does_loop():
    """Premise check. Without this, every test below passes vacuously."""
    executed: list[str] = []
    agent = _looping_agent(executed)

    err = await _run(agent, UsageLimits(request_limit=8, tool_calls_limit=None))

    assert isinstance(err, UsageLimitExceeded)
    assert len(executed) >= 5, f"expected a real loop, only saw {len(executed)}"


@pytest.mark.asyncio
async def test_request_limit_stops_a_runaway_turn():
    """The brake the live run could not exercise."""
    executed: list[str] = []
    agent = _looping_agent(executed)

    err = await _run(agent, UsageLimits(request_limit=10, tool_calls_limit=None))

    assert isinstance(err, UsageLimitExceeded)
    assert "request_limit" in str(err)
    assert len(executed) <= 10, f"ran {len(executed)} calls under a limit of 10"


@pytest.mark.asyncio
async def test_request_limit_works_with_no_tool_cap_at_all():
    """The runaway problem is turn length, not tool count.

    tool_calls_limit alone does not bound a turn - it was measured missing
    the validation and retry paths entirely - so this pins that
    request_limit is the thing actually holding the line.
    """
    executed: list[str] = []
    agent = _looping_agent(executed)

    err = await _run(agent, UsageLimits(request_limit=6, tool_calls_limit=None))

    assert isinstance(err, UsageLimitExceeded)
    assert len(executed) <= 6
    assert len(executed) >= 1, "premise: the model did call tools"


@pytest.mark.asyncio
async def test_tool_calls_limit_bounds_executions():
    executed: list[str] = []
    agent = _looping_agent(executed)

    err = await _run(agent, UsageLimits(request_limit=10_000,
                                        tool_calls_limit=3))

    assert isinstance(err, UsageLimitExceeded)
    assert len(executed) <= 3, f"{len(executed)} executions under a cap of 3"
    assert len(executed) >= 1, "premise: tools did run"


@pytest.mark.asyncio
async def test_our_own_execution_cap_bounds_the_shipped_agent():
    """Covers the counter we ship, on the real LLMAgent wiring.

    The loop drives `bash_tool`, so this goes through the guard in the
    tool body rather than a stand-in. A request cap far above any sane
    turn isolates the execution counter from the request brake.
    """
    from voice_agent.config import llm_config
    from voice_agent.llm import LLMAgent, _tool_call_budget
    from voice_agent.tools import BashTool

    llm = LLMAgent.__new__(LLMAgent)
    llm._turns = []
    llm._tool_calls = [0]
    llm._spend_tool_call = _tool_call_budget(llm_config.tool_call_limit,
                                            llm._tool_calls)
    llm.agent = Agent(model=FunctionModel(
        stream_function=_forever("bash_tool", {"command": "pwd"})))
    llm.register_tools()

    real_exec = BashTool.execute_command
    ran = {"n": 0}

    async def fake_exec(command):
        ran["n"] += 1
        return "ok"

    BashTool.execute_command = staticmethod(fake_exec)
    try:
        err = await _run(llm.agent, UsageLimits(
            request_limit=500, tool_calls_limit=None))
    finally:
        BashTool.execute_command = real_exec

    assert err is None or isinstance(err, UsageLimitExceeded)
    assert ran["n"] >= 1, "premise: bash_tool actually ran"
    assert ran["n"] <= llm_config.tool_call_limit + 1, (
        f"{ran['n']} subprocess executions under a cap of "
        f"{llm_config.tool_call_limit}"
    )
