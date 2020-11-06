import asyncio
import logging
from asyncio.queues import Queue
from http.cookiejar import CookieJar
from random import random
import os
import requests
from bs4 import BeautifulSoup

from stalkerbot.exc import (HTTPException, MaxRetriesExceededException,
                            ParsingError, RateLimitExceededException)
from stalkerbot.utils import ParsedData, SearchResult, requests_future

logger = logging.getLogger("worker")


class StalkerWorker:
    def __init__(
        self,
        cookiejar: CookieJar,
        output_queue: Queue,
        max_retries=10,
        max_timeout=32,
        max_concurrent=25,
        tqcb: "tqdm_asyncio" = None,
    ):
        self.cookies = cookiejar
        self.out = output_queue
        self.processed = 0
        self.total = 0
        self.max_retries = max_retries
        self.max_timeout = max_timeout
        self.tqcb = tqcb
        self.max_concurrent = max_concurrent

    async def get_userpage(self, url: str) -> BeautifulSoup:
        headers = {
            "Accept": "text/html",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.111 Safari/537.36",
            "cache-control": "public",
        }

        resp: requests.Response = await requests_future(
            "get",
            url,
            headers=headers,
            cookies=self.cookies,
            timeout=10,
            _backoff=random(),
            _max_retries=self.max_retries,
            _max_wait=self.max_timeout,
        )
        if resp.status_code == 200:
            return BeautifulSoup(resp.content, "html.parser")
        else:
            raise HTTPException(resp.status_code, resp.content)

    def parse_html(self, html: BeautifulSoup) -> ParsedData:
        try:
            return ParsedData(
                name=html.find("span", class_="vcard-fullname").string,
                username=html.find("span", class_="vcard-username").string,
                email=html.find("li", itemprop="email").a.string,
            )
        except AttributeError:
            raise ParsingError

    async def process(self, entries: list[str]):
        self.total = len(entries)
        self.processed = 0
        if self.tqcb is not None:
            self.tqcb.total = self.total
            self.tqcb.reset()
            self.tqcb.refresh()

        async def _process_entry(url: str):
            done = False
            while not done:
                done = True
                try:
                    soup = await self.get_userpage(url)
                    parsed = self.parse_html(soup)
                    await self.out.put(parsed)
                except (HTTPException, RateLimitExceededException) as exc:
                    logger.critical(f"Error fetching {url} - {exc}")
                    done = False
                    await asyncio.sleep(self.max_timeout * random())
                    continue
                except ParsingError:
                    pass
                finally:
                    if done:
                        self.processed += 1
                        if self.tqcb is not None:
                            self.tqcb.update(1)

        tasks = [_process_entry(url) for url in entries]
        gather = asyncio.gather(*tasks, loop=asyncio.get_event_loop())
        await gather


    async def astart(self, input_queue: Queue, batch_size: int = 25):
        loop = asyncio.get_event_loop()

        while loop.is_running:
            batch = []
            while len(batch) < batch_size:
                batch.append(await input_queue.get())
                input_queue.task_done()
            await self.process(batch)

    def start(self, input_queue: Queue, batch_size: int = 25) -> asyncio.Future:
        loop = asyncio.get_event_loop()
        return asyncio.ensure_future(self.astart(input_queue, batch_size), loop=loop)


class CSVWriter:
    def __init__(
        self,
        queue: Queue,
        filename: str,
        max_interval: int = 10,
        max_chunk: int = 100,
        include_headers: bool = False,
    ):
        self.filename = filename
        if not os.path.exists(filename):
            head, tail = os.path.split(self.filename)
            if len(head) > 0:
                os.makedirs(head)
        self.max_interval = max_interval
        self.max_chunk = max_chunk
        self.data_queue = queue
        self.include_headers = include_headers
        self._task: asyncio.Future = None
        self._chunk: list[ParsedData] = []

    async def write_queue(self):
        loop = asyncio.get_event_loop()
        while loop.is_running:
            self._chunk = []
            timeout_write = loop.call_later(self.max_interval, self._write)

            while len(self._chunk) < self.max_chunk:
                self._chunk.append(await self.data_queue.get())
                self.data_queue.task_done()

            timeout_write.cancel()
            self._write()

    def _write(self):
        chunk = "\n".join(
            [f"{row.name},{row.username},{row.email}" for row in self._chunk]
        )
        with open(self.filename, "a+") as fp:
            if self.include_headers:
                fp.write("name,username,email")
            fp.write(chunk + "\n")

    def start(self):
        self._task = asyncio.ensure_future(
            self.write_queue, loop=asyncio.get_event_loop()
        )

    def stop(self):
        self._task.cancel()
