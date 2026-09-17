"""The one LiteLLM call site: model from config, structured response, fallback on error."""

import os
from typing import Any

import pytest
from pydantic import BaseModel

from manc import llm
from manc.config import LlmConfig, load_config

CONFIG = LlmConfig(model="primary/model", fallback="backup/model", temperature=0, batch_size=40)
MESSAGES = [{"role": "user", "content": "hi"}]


class Answer(BaseModel):
    value: int


class _Response:
    def __init__(self, content: str, model: str) -> None:
        self.model = model
        self.choices = [
            type("Choice", (), {"message": type("Message", (), {"content": content})()})()
        ]


def test_complete_passes_config_and_parses_the_response(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_completion(**kwargs: Any) -> _Response:
        calls.append(kwargs)
        return _Response('{"value": 7}', model="primary/model-2026")

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    answer, model = llm.complete(CONFIG, MESSAGES, Answer)
    assert answer == Answer(value=7)
    assert model == "primary/model-2026"
    [call] = calls
    assert call["model"] == "primary/model"
    assert call["messages"] == MESSAGES
    assert call["temperature"] == 0
    assert call["response_format"] is Answer


def test_complete_falls_back_when_the_first_model_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    models: list[str] = []

    def fake_completion(**kwargs: Any) -> _Response:
        models.append(kwargs["model"])
        if kwargs["model"] == "primary/model":
            raise RuntimeError("rate limited")
        return _Response('{"value": 1}', model="backup/model")

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    answer, model = llm.complete(CONFIG, MESSAGES, Answer)
    assert (answer, model) == (Answer(value=1), "backup/model")
    assert models == ["primary/model", "backup/model"]


def test_complete_raises_when_every_model_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_completion(**kwargs: Any) -> _Response:
        raise RuntimeError("down")

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    with pytest.raises(llm.LlmError, match="backup/model"):
        llm.complete(CONFIG, MESSAGES, Answer)


def test_complete_treats_invalid_content_as_a_model_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_completion(**kwargs: Any) -> _Response:
        return _Response("not json", model=kwargs["model"])

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    with pytest.raises(llm.LlmError):
        llm.complete(CONFIG, MESSAGES, Answer)


def test_complete_without_fallback_tries_once(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[str] = []

    def fake_completion(**kwargs: Any) -> _Response:
        attempts.append(kwargs["model"])
        raise RuntimeError("down")

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    with pytest.raises(llm.LlmError):
        llm.complete(LlmConfig("only/model", None, 0, 40), MESSAGES, Answer)
    assert attempts == ["only/model"]


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY not set")
def test_live_configured_model_answers_with_structured_output() -> None:
    config = load_config().llm
    answer, model = llm.complete(
        config, [{"role": "user", "content": 'Reply with the JSON object {"value": 42}.'}], Answer
    )
    assert answer.value == 42
    assert model
