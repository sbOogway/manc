"""`claude -p` as a LiteLLM provider: argv, stdin, structured output, failures."""

import json
import subprocess
from typing import Any

import pytest
from pydantic import BaseModel

from manc import llm
from manc.config import LlmConfig
from manc.llm import claude_code

CONFIG = LlmConfig(model="claude_code/opus", fallback=None, temperature=0, batch_size=5)
MESSAGES = [
    {"role": "system", "content": "You tag headlines."},
    {"role": "user", "content": "[0] US CPI runs hot"},
]


class Answer(BaseModel):
    value: int


class FakeRun:
    """Stands in for subprocess.run: records the call, returns canned claude -p output."""

    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


def _result(**fields: Any) -> str:
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, **fields})


def test_provider_is_registered_with_litellm() -> None:
    providers = {entry["provider"] for entry in llm.litellm.custom_provider_map}
    assert "claude_code" in providers


def test_complete_runs_claude_headless_with_the_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun(stdout=_result(structured_output={"value": 42}))
    monkeypatch.setattr(claude_code.subprocess, "run", run)

    answer, model = llm.complete(CONFIG, MESSAGES, Answer)

    assert (answer, model) == (Answer(value=42), "claude_code/opus")
    [call] = run.calls
    argv = call["argv"]
    assert argv[:2] == ["claude", "-p"]
    assert argv[argv.index("--model") + 1] == "opus"
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--system-prompt") + 1] == "You tag headlines."
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert schema["properties"]["value"]["type"] == "integer"
    assert call["input"] == "[0] US CPI runs hot"
    assert call["cwd"] != "." and call["capture_output"] and call["text"]


def test_several_user_messages_join_into_the_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun(stdout=_result(structured_output={"value": 1}))
    monkeypatch.setattr(claude_code.subprocess, "run", run)
    messages = [{"role": "user", "content": "first"}, {"role": "user", "content": "second"}]
    llm.complete(CONFIG, messages, Answer)
    [call] = run.calls
    assert call["input"] == "first\n\nsecond"
    assert "--system-prompt" not in call["argv"]


@pytest.mark.parametrize(
    ("run", "message"),
    [
        (FakeRun(returncode=1, stderr="not logged in"), "not logged in"),
        (
            FakeRun(
                stdout=json.dumps({"type": "result", "is_error": True, "result": "usage limit"})
            ),
            "usage limit",
        ),
        (FakeRun(stdout=_result(result="plain text, no structured output")), "structured_output"),
        (FakeRun(stdout="not json"), "not json"),
    ],
)
def test_failures_become_an_llm_error(
    monkeypatch: pytest.MonkeyPatch, run: FakeRun, message: str
) -> None:
    monkeypatch.setattr(claude_code.subprocess, "run", run)
    with pytest.raises(llm.LlmError, match=message):
        llm.complete(CONFIG, MESSAGES, Answer)


def test_missing_binary_becomes_an_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_binary(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("claude")

    monkeypatch.setattr(claude_code.subprocess, "run", no_binary)
    with pytest.raises(llm.LlmError, match="claude"):
        llm.complete(CONFIG, MESSAGES, Answer)
