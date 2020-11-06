import asyncio
from dataclasses import dataclass
from datetime import datetime

import requests


@dataclass
class SearchResult:
    total: int
    page: int
    items: list[str]


@dataclass
class ParsedData:
    name: str
    username: str
    email: str


async def requests_future(
    method: str,
    *args,
    _backoff: float = 0.1,
    _max_wait: float = 32,
    _max_retries: int = 10,
    **kwargs
) -> requests.Response:
    for i in range(_max_retries):
        loop = asyncio.get_event_loop()

        async def _request():
            return getattr(requests, method.lower())(*args, **kwargs)

        try:
            resp: requests.Response = await _request()
        except requests.exceptions.ReadTimeout:
            await asyncio.sleep(_backoff)
            continue
        if resp.status_code == 429:
            await asyncio.sleep(min(2 ** i + _backoff, _max_wait))
        elif resp.status_code >= 502:
            await asyncio.sleep(_backoff)
        else:
            return resp
