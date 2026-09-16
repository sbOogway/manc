"""One HTTP client for every provider: a browser User-Agent, one timeout, redirects on."""

from collections.abc import Mapping
from typing import Any

import httpx

USER_AGENT = (  # a browser agent: some sources (Nasdaq) stall or refuse anything else
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36"
)
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
