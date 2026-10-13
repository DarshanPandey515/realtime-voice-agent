# tools.py
import asyncio
import shlex
from pathlib import Path

MAX_CONTENT = 1500
TREE_MAX_ENTRIES = 200
DEFAULT_TIMEOUT = 5


ALLOWED_COMMANDS = {
    "ls", "pwd", "cat", "head", "tail", "grep", "find",
    "git", "wc", "echo", "date", "whoami", "df", "du",
}

# `git <anything>` is not read-only: `git push`, `git config --global` and
# `git log --output=file` all write. Pin it to subcommands that only read.
READONLY_GIT_SUBCOMMANDS = {
    "status", "log", "diff", "show", "blame", "describe", "shortlog",
    "ls-files", "rev-parse", "cat-file", "annotate", "branch",
}

# `find` takes a command to run or a list of things to erase. These flags are
# the whole attack surface.
UNSAFE_FIND_FLAGS = (
    "-delete", "-exec", "-execdir", "-ok", "-okdir",
    "-fprint", "-fprintf", "-fls", "-fopen",
)

COMMAND_TIMEOUTS = {"find": 15, "grep": 10, "git": 10}


def truncate(text: str, limit: int = MAX_CONTENT) -> str:
    if len(text) > limit:
        return text[:limit] + f"... [truncated {len(text) - limit} more characters]"
    return text


def _rejection_reason(base_cmd: str, args: list[str]) -> str | None:
    """Why this command is refused, or None if it is allowed.

    Only args[0] used to be checked, which let `git push` and `find -delete`
    through an allowlist that read as read-only.
    """
    if base_cmd not in ALLOWED_COMMANDS:
        return (
            f"'{base_cmd}' isn't allowed. I can only run read-only commands "
            f"like: {', '.join(sorted(ALLOWED_COMMANDS))}."
        )

    rest = args[1:]

    if base_cmd == "git":
        sub = rest[0] if rest else ""
        if sub not in READONLY_GIT_SUBCOMMANDS:
            return (
                f"'git {sub}' isn't read-only. I can only run git "
                f"{', '.join(sorted(READONLY_GIT_SUBCOMMANDS))}."
            )
        if any(a == "--output" or a.startswith("--output=") for a in rest):
            return "'git --output' writes to a file, so I won't run it."

    if base_cmd == "find":
        for arg in rest:
            if arg.startswith(UNSAFE_FIND_FLAGS):
                return (
                    f"'find {arg}' can run commands or delete files, "
                    "so I won't run it."
                )

    return None


async def _read_capped(stream: asyncio.StreamReader, limit: int) -> tuple[bytes, bool]:
    """Read at most `limit` bytes. Returns (data, hit_limit).

    Stops reading instead of buffering a runaway command's whole output.
    """
    buf = bytearray()
    while len(buf) < limit:
        chunk = await stream.read(min(8192, limit - len(buf)))
        if not chunk:
            return bytes(buf), False
        buf += chunk
    return bytes(buf), True


class BashTool:
    """Runs a small allowlist of read-only shell commands, safely and asynchronously."""

    @staticmethod
    async def execute_command(command: str) -> str:
        if not command or not command.strip():
            return "No command given."

        try:
            args = shlex.split(command)
        except ValueError as e:
            return f"Couldn't parse that command: {e}"

        if not args:
            return "No command given."

        base_cmd = args[0]
        reason = _rejection_reason(base_cmd, args)
        if reason:
            return reason

        timeout = COMMAND_TIMEOUTS.get(base_cmd, DEFAULT_TIMEOUT)

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, capped = await asyncio.wait_for(
                    _read_capped(proc.stdout, MAX_CONTENT), timeout=timeout
                )
                if capped:
                    proc.kill()
                stderr, _ = await asyncio.wait_for(
                    _read_capped(proc.stderr, MAX_CONTENT), timeout=1.0
                )
                await proc.wait()
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return f"'{base_cmd}' timed out after {timeout}s."

            # A command we stopped for overrunning the cap exits on SIGKILL, so
            # `capped` has to win over the return code or truncated-but-usable
            # output gets reported as a failure.
            if capped or proc.returncode == 0:
                out = stdout.decode(errors="replace").strip() or "(no output)"
                if capped:
                    out += f"... [truncated at {MAX_CONTENT} bytes]"
                return out
            err = stderr.decode(errors="replace").strip()
            return f"Command failed: {err[:MAX_CONTENT]}" if err else \
                "Command failed and printed nothing (no matches, or a bad flag)."

        except FileNotFoundError:
            return f"Command not found: {base_cmd}"
        except Exception as e:
            return f"Error executing command: {e}"


class ReadFileTool:
    """Reads a text file from disk and returns a short, voice-friendly excerpt."""

    @staticmethod
    async def readfile(path: str) -> str:
        if not path:
            return "No file path provided."

        p = Path(path)
        if not p.exists():
            return f"File not found: {path}"
        if not p.is_file():
            return f"{path} is not a file."

        try:
            content = await asyncio.to_thread(p.read_text, errors="replace")
        except Exception as e:
            return f"Error reading file: {e}"

        return truncate(content)


class GetTreeTool:
    """Lists project files (capped in size) so the model can describe the structure briefly."""

    IGNORE = {".git", "__pycache__", "env", "venv", ".venv", "node_modules"}

    @staticmethod
    async def get_tree(root: str = ".") -> str:
        def _walk():
            lines = []
            for path in Path(root).rglob("*"):
                if any(part in GetTreeTool.IGNORE for part in path.parts):
                    continue
                lines.append(str(path))
                if len(lines) >= TREE_MAX_ENTRIES:
                    lines.append(f"... [truncated, more than {TREE_MAX_ENTRIES} entries]")
                    break
            return "\n".join(lines) if lines else "(empty directory)"

        return await asyncio.to_thread(_walk)