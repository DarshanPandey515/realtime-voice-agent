# llm_agent.py
import os
import re

from pydantic_ai.agent import Agent
from pydantic_ai import RunContext
from pydantic_ai.usage import UsageLimits
from voice_agent.tools import BashTool, ReadFileTool, GetTreeTool
from voice_agent.config import llm_config
from dotenv import load_dotenv


from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider
from pydantic_ai.models.groq import GroqModelSettings



load_dotenv()

MAX_TURNS = 6
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

# The model often narrates an action instead of taking it: "Let me check that
# for you." followed by no tool call and no answer. Said out loud that is a
# promise the agent does not keep, which is worse than silence - the user waits
# for an answer that never comes. Measured on both models with the tool cap
# engaged: turns ended on "Let me check..." or cut off mid-sentence.
_ACTIONS = ("check", "look", "search", "run", "read", "find", "see", "open",
            "inspect", "grab", "list", "grep")
_SUBJECTS = ("let me", "i'll", "i will", "i'd", "i would", "i'm going to",
             "i am going to", "i need to", "i should", "i can", "i could")
# Matched on subject *plus* action verb, so "let me think about that" survives
# - thinking aloud is not a promise to go read something.
_INTENT_LEAD = tuple(f"{s} {a}" for s in _SUBJECTS for a in _ACTIONS) + (
    "to check", "to find", "to look", "to search", "to read",
)
# Phrases that can sit mid-clause, so they cannot be startswith matches.
_INTENT_IDIOM = ("take a look", "go take a look", "i would normally",
                 "i would typically")


def is_intent_narration(sentence: str) -> bool:
    """True if the sentence promises an action rather than reporting a result.

    ponytail: a leading-clause keyword match. It will occasionally drop a
    legitimate sentence that opens "Let me think..." - acceptable, since such a
    sentence is dead air in a voice agent anyway. A model-level fix would be to
    stop prompting for narration, but the prompt is shared with the tool path.
    """
    head = sentence.strip().lower().lstrip('"\'“‘ ')
    # Only the opening clause: the answer, if any, follows it.
    head = re.split(r"[.,;:]", head)[0]
    if any(head.startswith(marker) for marker in _INTENT_LEAD):
        return True
    return any(idiom in head for idiom in _INTENT_IDIOM)


class ToolCallLimitReached(RuntimeError):
    """Raised when one turn makes more tool calls than we allow.

    pydantic-ai's own `tool_calls_limit` is not sufficient here. It increments
    `usage.tool_calls` only *after* a tool executes successfully
    (tool_manager.py:1031); the argument-validation, ModelRetry and ToolFailed
    paths all return or raise before that line. Each of those still advances
    the model conversation, so a model stuck emitting invalid tool arguments
    loops with the counter frozen and the limit never trips. Observed: 9 and 15
    calls against a limit of 6, with no exception raised.
    """


def _tool_call_budget(limit: int, counter: list[int]):
    """Return a callable that reports when this turn's tool budget is spent.

    Deliberately returns a refusal string rather than raising. An exception
    from a tool body is handed back to the model as a retry, which invites
    exactly the loop this exists to stop - measured at 24 calls against a limit
    of 6 while raising, plus a rate-limit failure from the retries. Telling the
    model the budget is spent gets the same result without feeding it a reason
    to try again.
    """
    def spend() -> str | None:
        counter[0] += 1
        if counter[0] > limit:
            return (
                f"Tool budget for this turn is spent ({limit} calls). Do not "
                "call another tool. Answer now using what you already found, "
                "or say that you could not find it."
            )
        return None
    return spend


def split_sentences(buf: str) -> tuple[list[str], str]:
    """Pull complete sentences off the front of buf. Returns (sentences, tail)."""
    sentences = []
    while (cut := _SENTENCE_BOUNDARY.search(buf)) is not None:
        sentence, buf = buf[: cut.start()].strip(), buf[cut.end():]
        if sentence:
            sentences.append(sentence)
    return sentences, buf

SYSTEM_PROMPT = """
You are a helpful, natural-sounding voice assistant. Keep responses:
- Concise and conversational (1-3 sentences)
- No long sentences
- to heavy words, only simple easy words to talk
- Spoken-style: no markdown, lists, or labels
- Direct and clear

When a tool returns file paths, code, or command output, summarize it in
plain spoken language instead of reading it verbatim — don't recite file
paths, symbols, or raw command output character-by-character.

Available tools: bash (read-only commands only), read a file, list the
project tree.
"""


class LLMAgent:

    def __init__(self):

        self.groq_agent = GroqModel(
            "qwen/qwen3.8-27b",
            provider=GroqProvider(api_key=os.environ["GROQ_API_KEY"])
        )


        self.agent = Agent(
            model=self.groq_agent,
            model_settings=GroqModelSettings(groq_reasoning_effort="none"),
            system_prompt=SYSTEM_PROMPT,
        )
        self.register_tools()
        # Whole turns, not raw messages: one run appends a user message plus a
        # response plus any tool calls, and slicing a flat list cuts a
        # ToolCallPart away from its ToolReturnPart.
        self._turns = []
        self._tool_calls = [0]
        self._spend_tool_call = _tool_call_budget(
            llm_config.tool_call_limit, self._tool_calls)

    def register_tools(self):
        @self.agent.tool
        async def bash_tool(ctx: RunContext, command: str) -> str:
            """Run a read-only shell command (e.g. ls, cat, grep, git status) and return its output."""
            if (refusal := self._spend_tool_call()) is not None:
                return refusal
            return await BashTool.execute_command(command)

        @self.agent.tool
        async def readfile_tool(ctx: RunContext, path: str) -> str:
            """Read the contents of a text file at the given path."""
            if (refusal := self._spend_tool_call()) is not None:
                return refusal
            return await ReadFileTool.readfile(path)

        @self.agent.tool
        async def get_tree_tool(ctx: RunContext) -> str:
            """List the files in the current project directory."""
            if (refusal := self._spend_tool_call()) is not None:
                return refusal
            return await GetTreeTool.get_tree()

    @property
    def history(self):
        return [m for turn in self._turns for m in turn]

    def _record_turn(self, result) -> None:
        self._turns.append(list(result.all_messages()))
        self._turns = self._turns[-MAX_TURNS:]

    async def generate_response(self, user_text: str) -> str:
        parts: list[str] = []

        async def collect(sentence: str) -> None:
            parts.append(sentence)

        await self.stream_into(user_text, collect)
        return " ".join(parts)

    async def stream_into(self, user_text: str, on_sentence) -> None:
        """Hand each sentence to `on_sentence` as it completes.

        So TTS can start before the reply is finished. Takes a callback instead
        of being an async generator on purpose: pydantic-ai's streaming context
        cannot be unwound by async-generator finalisation, so a generator
        abandoned on barge-in raises out of its own `async with`.
        """
        buf = ""
        self._tool_calls[0] = 0          # the cap is per turn, not per session
        async with self.agent.run_stream(
            user_text,
            message_history=self.history,
            usage_limits=UsageLimits(
                request_limit=llm_config.request_limit,
                tool_calls_limit=llm_config.tool_call_limit,
            ),
        ) as result:
            try:
                async for delta in result.stream_text(delta=True, debounce_by=0.05):
                    buf += delta
                    sentences, buf = split_sentences(buf)
                    for sentence in sentences:
                        await on_sentence(sentence)
                tail = buf.strip()
                if tail:
                    await on_sentence(tail)
            finally:
                self._record_turn(result)