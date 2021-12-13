import asyncio
from dataclasses import dataclass, field
import datetime
import json
import requests
from logging import getLogger

logger = getLogger("utils")


@dataclass(frozen=True)
class State:
    continue_from: datetime.datetime
    query: str
    cursor: str


@dataclass
class SearchResult:
    total: int
    page: int
    items: list[str]


@dataclass
class ParsedData:
    name: str
    login: str
    email: str
    createdAt: datetime.datetime

    def __post_init__(self):
        if isinstance(self.createdAt, str):
            self.createdAt = datetime.datetime.fromisoformat(self.createdAt[:-1])


async def requests_future(
    method: str,
    *args,
    _backoff: float = 0.1,
    _max_wait: float = 32,
    _max_retries: int = 10,
    **kwargs,
) -> requests.Response:
    for i in range(_max_retries):

        async def _request():
            return getattr(requests, method.lower())(*args, **kwargs)

        try:
            resp: requests.Response = await _request()
            return resp
        except requests.exceptions.ReadTimeout:
            logger.info("read timeout")
            await asyncio.sleep(_backoff)
            continue
        if resp.status_code == 429:
            logger.info("sleeping backoff")
            await asyncio.sleep(min(2 ** i + _backoff, _max_wait))
        elif resp.status_code >= 502:
            logger.info("sleeping")
            await asyncio.sleep(_backoff)
        else:
            raise Exception(resp.status_code, resp.content)


@dataclass
class RateLimit:
    cost: int
    used: int
    remaining: int
    resetAt: datetime

    def __post_init__(self):
        if isinstance(self.resetAt, str):
            offset = datetime.timedelta(hours=+4)
            self.resetAt = datetime.datetime.fromisoformat(self.resetAt[:-1]) + offset


@dataclass
class PageInfo:
    hasNextPage: bool
    hasPreviousPage: bool
    endCursor: str


@dataclass
class QueryResponse:
    _raw: str
    rateLimit: RateLimit = field(init=False)
    pageInfo: PageInfo = field(init=False)
    users: list[ParsedData] = field(init=False)
    userCount: int = field(init=False)

    def __post_init__(self):
        data = json.loads(self._raw)["data"]
        self.rateLimit = RateLimit(**data["rateLimit"])
        self.pageInfo = PageInfo(**data["search"]["pageInfo"])
        self.users = [ParsedData(**d) for d in data["search"]["nodes"] if d]
        self.userCount = data["search"]["userCount"]


def create_query(
    cursor: str = None,
    q: str = "language:python3",
    page_size: int = 100,
    user_type: str = "User",
) -> str:
    cursor_arg = f'before: "{cursor}",' if cursor is not None else ""
    search_args = f'query: "{q}", {cursor_arg} last: {page_size}, type: USER'
    q = f"{{rateLimit{{cost used remaining resetAt}} search({search_args}) {{pageInfo {{hasNextPage hasPreviousPage endCursor}} userCount nodes {{... on {user_type} {{name login email createdAt}}}}}}}}\n"
    return q
