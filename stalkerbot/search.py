import asyncio
from datetime import datetime, timedelta
from random import random
from typing import Union
import logging
import requests

from stalkerbot.exc import HTTPException, RateLimitExceededException
from stalkerbot.utils import requests_future, QueryResponse, create_query, State
from tqdm.asyncio import tqdm

search_uri = "https://api.github.com/graphql"

logger = logging.getLogger("search")


class Search:
    def __init__(
        self,
        token: str,
        query: str,
        page_size: int = 100,
        state: State = None,
        continue_from: datetime = None,
        silent: bool = False
    ):
        if state is not None:
            self.query = state.query
            self.continue_from = state.continue_from
            self.cursor = state.cursor
        else:
            self.query = query
            self.continue_from = continue_from
            self.cursor = None

        self.page_size = page_size
        self.token = token
        self.silent = silent
        self.continue_from = continue_from


    async def gen(self) -> dict:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        delta = timedelta(days=1)
        if self.continue_from is None:
            start_date = datetime.utcnow() - delta
            end_date = datetime.utcnow()
        else:
            start_date = self.continue_from - delta
            end_date = self.continue_from
        query = self.query + " sort:joined"

        if "created" not in self.query:
            query = self.query + f" created:{start_date.date().isoformat()}..{end_date.date().isoformat()}"
        else:
            query = self.query 

        data = {
            "query": create_query(
                cursor=self.cursor, q=query, page_size=self.page_size
            )
        }

        response = yield ({"headers": headers, "json": data}, State(end_date, self.query, self.cursor))
        average = response.userCount
        if not self.silent:
            used = tqdm(desc="used", unit="requests", total=5000, initial=response.rateLimit.used)
        prev = [average for _ in range(5)]
        while True:
            if not response.pageInfo.hasPreviousPage:
                prev = [*prev[:-1], response.userCount]
                average = sum(prev)/len(prev)
                if "created" not in self.query:
                    if response.userCount > 1000:
                        end_date -= delta / 2
                        start_date -= delta / 2
                        start_date.date().isoformat
                        query = self.query + f" created:{start_date.isoformat()}..{end_date.isoformat()} sort:joined"
                        self.cursor = None
                    elif start_date < datetime(year=2008, month=4, day=1):
                        raise StopAsyncIteration
                    else:
                        query = self.query + f" created:{start_date.isoformat()}..{end_date.isoformat()} sort:joined"
                        end_date = datetime.fromisoformat(start_date.isoformat())
                        start_date -= delta
                        self.cursor = None
                else:
                    break

                if average > 2000:
                    delta /= 2
                if average < 200:
                    delta *= 2
            else:
                self.cursor = response.pageInfo.endCursor
            if not self.silent:
                used.update(response.rateLimit.cost)

            if response.rateLimit.remaining < response.rateLimit.cost or response.rateLimit.remaining == 0:
                if not self.silent:
                    used.write(f'sleeping until {response.rateLimit.resetAt.isoformat()}')
                sleep_time = response.rateLimit.resetAt - datetime.utcnow()
                await asyncio.sleep(sleep_time.seconds)
                used.reset()

            data = {"query": create_query(self.cursor, query)}
            response = yield ({"headers": headers, "json": data}, State(end_date, self.query, self.cursor))
        raise StopAsyncIteration
