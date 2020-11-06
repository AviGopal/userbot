import asyncio
from datetime import datetime, timedelta
from random import random
from typing import Union
import logging
import requests

from stalkerbot.exc import HTTPException, RateLimitExceededException
from stalkerbot.utils import SearchResult, requests_future

search_uri = "https://api.github.com/search/users"


class Search:
    def __init__(
        self,
        auth: requests.auth.HTTPBasicAuth,
        query: str,
        per_page: int,
        continue_from: int = 1,
        early_stop: int = 0,
        max_retries: int = 10,
        max_timeout: int = 32,
        sort: str = "followers",
        order: str = "desc",
    ):
        self.query = query
        self.sort = sort
        self.order = order
        self.per_page = per_page
        self.page = continue_from
        self.early_stop = early_stop
        self.auth = auth
        self.max_retries = max_retries
        self.max_timeout = max_timeout

    def __aiter__(self):
        return self

    async def __anext__(self) -> SearchResult:
        headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        backoff = random()
        items = None

        for i in range(self.max_retries):
            resp: requests.Response = await requests_future(
                "get",
                search_uri,
                params={
                    "q": self.query,
                    "sort": self.sort,
                    "order": self.order,
                    "per_page": self.per_page,
                    "page": self.page,
                },
                headers=headers,
                auth=self.auth,
                _max_retries=self.max_retries,
                _max_wait=self.max_timeout,
                _backoff=backoff
            )
            if resp.status_code == 200:
                data = resp.json()
                total = data["total_count"]
                items = data["items"]
                break
            elif resp.status_code == 429:
                backoff = min(2 ** i + random(), self.max_timeout)
                await asyncio.sleep(backoff)
            elif resp.status_code == 403:
                rate_data = await requests_future(
                    "get",
                    "https://api.github.com/rate_limit",
                    headers=headers,
                    auth=self.auth,
                )
                dt = datetime.fromtimestamp(
                    int(rate_data.json()["resources"]["search"]["reset"])
                )
                await asyncio.sleep(dt.timestamp() - datetime.utcnow().timestamp())
            else:
                pass
        if (
            not items
            or len(items) == 0
            or (self.early_stop > 0 and self.page >= self.early_stop)
        ):
            raise StopAsyncIteration

        self.page += 1
        return SearchResult(total, self.page, [i["html_url"] for i in items])
