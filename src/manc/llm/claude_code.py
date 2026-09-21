"""Claude Code's headless mode as a LiteLLM provider: `claude_code/<opus|sonnet|haiku|id>`.

`claude -p --output-format json --json-schema ...` answers with a `structured_output` that
matches the schema, on the owner's Claude login, so the tagger runs on a subscription with
no API key. LiteLLM hands the Pydantic `response_format` over as a JSON schema; the system
messages become `--system-prompt`, the rest go to stdin. Headlines are untrusted input, so the
model gets no built-in tools and none of the owner's MCP servers, and no transcript is kept.
"""

import json
import subprocess
import tempfile
from typing import Any

from litellm import CustomLLM
from litellm.types.utils import Choices, Message, ModelResponse

PROVIDER = "claude_code"


class ClaudeCodeError(RuntimeError):
    """`claude -p` failed or answered without the structured output."""


class ClaudeCode(CustomLLM):
    def completion(
        self,
        model: str,
        messages: list,
        model_response: ModelResponse,
        optional_params: dict,
        **_: Any,
    ) -> ModelResponse:
        schema = (optional_params.get("response_format") or {}).get("json_schema", {}).get("schema")
        system = "\n\n".join(msg["content"] for msg in messages if msg["role"] == "system")
        prompt = "\n\n".join(msg["content"] for msg in messages if msg["role"] != "system")
        argv = [
            "claude",
            "-p",
            "--model",
            model,
            "--tools",
            "",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--output-format",
            "json",
        ]
        if system:
            argv += ["--system-prompt", system]
        if schema:
            argv += ["--json-schema", json.dumps(schema)]
        try:  # outside the repo, so claude does not load CLAUDE.md into the prompt
            run = subprocess.run(
                argv, input=prompt, capture_output=True, text=True, cwd=tempfile.gettempdir()
            )
        except FileNotFoundError as error:
            raise ClaudeCodeError(f"claude is not installed: {error}") from error
        if run.returncode != 0:
            raise ClaudeCodeError(run.stderr.strip() or f"claude -p exited {run.returncode}")
        try:
            result = json.loads(run.stdout)
        except json.JSONDecodeError as error:
            raise ClaudeCodeError(f"claude -p wrote {run.stdout[:200]!r}") from error
        if result.get("is_error"):
            raise ClaudeCodeError(str(result.get("result") or "claude -p reported an error"))
        if schema and "structured_output" not in result:
            raise ClaudeCodeError("claude -p answered without structured_output")
        content = json.dumps(result["structured_output"]) if schema else result.get("result", "")
        return ModelResponse(
            model=f"{PROVIDER}/{model}",
            choices=[Choices(message=Message(content=content, role="assistant"))],
        )
