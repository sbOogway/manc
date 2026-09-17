"""The one place that calls an LLM (blueprint §4): LiteLLM, model string from config."""

import logging
from collections.abc import Sequence
from typing import Any

import litellm
from pydantic import BaseModel

from manc.config import LlmConfig

log = logging.getLogger(__name__)


class LlmError(RuntimeError):
    """Every configured model failed; the message names the last one."""


def complete[ResponseT: BaseModel](
    config: LlmConfig, messages: Sequence[dict[str, str]], response_model: type[ResponseT]
) -> tuple[ResponseT, str]:
    """Structured completion. Returns the parsed response and the model LiteLLM reports."""
    errors: list[str] = []
    for model in (config.model, config.fallback):
        if not model:
            continue
        try:
            response = litellm.completion(
                model=model,
                messages=list(messages),
                temperature=config.temperature,
                response_format=response_model,
                num_retries=2,
            )
            content = response.choices[0].message.content or ""
            return response_model.model_validate_json(content), _reported_model(response, model)
        except Exception as error:  # LiteLLM raises many provider types; ValidationError too
            log.warning("llm: %s failed: %s", model, error)
            errors.append(f"{model}: {error}")
    raise LlmError("; ".join(errors))


def _reported_model(response: Any, requested: str) -> str:
    return str(getattr(response, "model", None) or requested)
