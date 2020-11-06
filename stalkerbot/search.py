import asyncio
from datetime import datetime, timedelta
from random import random
from typing import Union

import requests

from stalkerbot.exc import HTTPException, RateLimitExceededException
from stalkerbot.utils import SearchResult, requests_future

search_uri = "https://api.github.com/search/users"


class Search:
    def __init__(
        self,
        auth: requests.auth.HTTPBasicAuth,
        query: str,
        sort: str,
        per_page: int,
        continue_from: int = 1,
        max_retries: int = 10,
        max_timeout: int = 32,
    ):
        self.query = query
        self.sort = sort
        self.per_page = per_page
        self.page = continue_from
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
                    "order": "desc",
                    "per_page": self.per_page,
                    "page": self.page,
                },
                headers=headers,
                auth=self.auth,
            )
            if resp.status_code == 200:
                data = resp.json()
                total = data["total_count"]
                items = data["items"]
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
                raise HTTPException(resp.status_code, resp.content)

        if not items or len(items) == 0:
            raise StopIteration

        self.page += 1
        return SearchResult(total, self.page, [i["html_url"] for i in items])


if __name__ == "__main__":
    pass
