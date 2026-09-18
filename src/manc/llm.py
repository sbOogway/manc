"""The one place that calls an LLM (blueprint §4): LiteLLM, model string from config."""

import logging
import re
import time
from collections.abc import Sequence
from typing import Any

import litellm
from pydantic import BaseModel

from manc.claude_code import PROVIDER, ClaudeCode
from manc.config import LlmConfig

log = logging.getLogger(__name__)
litellm.custom_provider_map = [{"provider": PROVIDER, "custom_handler": ClaudeCode()}]

# A 429 is waited out this many times before the fallback model is tried, for the seconds the
# provider asks (Groq's free tier meters tokens per minute and asks for a few seconds).
RATE_LIMIT_WAITS = 3
RATE_LIMIT_MARGIN = 1.0  # added to the provider's figure
RATE_LIMIT_DEFAULT_WAIT = 20.0  # when the provider gives no figure
RATE_LIMIT_MAX_WAIT = 120.0  # longer than this, fall through to the next model at once
_RETRY_AFTER = re.compile(r"try again in (?:(\d+)m)?([\d.]+)s", re.IGNORECASE)


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
            response = _completion(config, model, messages, response_model)
            content = response.choices[0].message.content or ""
            return response_model.model_validate_json(content), _reported_model(response, model)
        except Exception as error:  # LiteLLM raises many provider types; ValidationError too
            log.warning("llm: %s failed: %s", model, error)
            errors.append(f"{model}: {error}")
    raise LlmError("; ".join(errors))


def _completion(
    config: LlmConfig, model: str, messages: Sequence[dict[str, str]], response_model: type
) -> Any:
    for waited in range(RATE_LIMIT_WAITS + 1):
        try:
            return litellm.completion(
                model=model,
                messages=list(messages),
                temperature=config.temperature,
                response_format=response_model,
                num_retries=2,
            )
        except litellm.RateLimitError as error:
            wait = _retry_after(error)
            if waited == RATE_LIMIT_WAITS or wait > RATE_LIMIT_MAX_WAIT:
                raise
            log.info("llm: %s rate limited, waiting %.0fs", model, wait)
            time.sleep(wait)
    raise AssertionError("unreachable")  # pragma: no cover


def _retry_after(error: litellm.RateLimitError) -> float:
    """Seconds the provider asks for: the header, else the "try again in 1m2.5s" message."""
    header = (getattr(error, "headers", None) or {}).get("retry-after")
    if header:
        return float(header) + RATE_LIMIT_MARGIN
    found = _RETRY_AFTER.search(str(error))
    if found:
        minutes, seconds = found.groups()
        return int(minutes or 0) * 60 + float(seconds) + RATE_LIMIT_MARGIN
    return RATE_LIMIT_DEFAULT_WAIT


def _reported_model(response: Any, requested: str) -> str:
    return str(getattr(response, "model", None) or requested)
