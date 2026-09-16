"""One HTTP client for every provider: an identified User-Agent, one timeout, redirects on."""

from collections.abc import Mapping
from importlib.metadata import version
from typing import Any

import httpx

USER_AGENT = f"manc/{version('manc')} (+https://github.com/sbOogway/manc)"
DEFAULT_TIMEOUT = 15.0


class Client(httpx.Client):
    """httpx.Client with the project defaults; `headers` are merged over the User-Agent."""

    def __init__(
        self,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, **(headers or {})},
            **kwargs,
        )
