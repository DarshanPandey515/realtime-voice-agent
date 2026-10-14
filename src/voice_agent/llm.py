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

    def register_tools(self):
        @self.agent.tool
        async def bash_tool(ctx: RunContext, command: str) -> str:
            """Run a read-only shell command (e.g. ls, cat, grep, git status) and return its output."""
            return await BashTool.execute_command(command)

        @self.agent.tool
        async def readfile_tool(ctx: RunContext, path: str) -> str:
            """Read the contents of a text file at the given path."""
            return await ReadFileTool.readfile(path)

        @self.agent.tool
        async def get_tree_tool(ctx: RunContext) -> str:
            """List the files in the current project directory."""
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