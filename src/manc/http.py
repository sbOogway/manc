"""One HTTP client for every provider: a browser User-Agent, one timeout, redirects on.

`gather` runs independent requests on a few threads; `httpx.Client` is thread-safe.
"""

from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

USER_AGENT = (  # a browser agent: some sources (Nasdaq) stall or refuse anything else
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 15.0
WORKERS = 8  # concurrent requests in `gather`


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


def gather[InputT, ResultT](
    function: Callable[[InputT], ResultT], inputs: Iterable[InputT], workers: int = WORKERS
) -> list[ResultT]:
    """`function` over `inputs` on a thread pool; results in input order, errors re-raised."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(function, inputs))
