import asyncio
import logging
import os
from asyncio.queues import Queue, QueueEmpty, QueueFull
from http.cookiejar import CookieJar
from random import random

import requests
from bs4 import BeautifulSoup

from stalkerbot.exc import (
    HTTPException,
    MaxRetriesExceededException,
    ParsingError,
    RateLimitExceededException,
)
from stalkerbot.utils import ParsedData, SearchResult, requests_future
from functools import partial
from tqdm.asyncio import tqdm
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
        self.stop_flag = False

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

    async def process_entry(self, url: str):
        logger.debug("processing %s", url)
        done = False
        while not done:
            done = True
            try:
                soup = await self.get_userpage(url)
                logger.debug("souped")
                parsed = self.parse_html(soup)
                logger.debug("parsed")
                put_done = False

                while not put_done:
                    try:
                        self.out.put_nowait(parsed)
                        put_done = True
                        logger.debug("inserted")
                    except QueueFull:
                        raise QueueFull
                        await asyncio.sleep(0.1)
            except (HTTPException, RateLimitExceededException) as exc:
                logger.critical("Error fetching %s - %s", url, exc)
                done = False
                await asyncio.sleep(self.max_timeout * random())
                continue
            except ParsingError:
                logger.debug("parsing error")
            finally:
                if done:
                    self.processed += 1

    async def process_batch(self, entries: list[str]):
        logger.debug("processing %i entries", len(entries))
        self.total = len(entries)
        self.processed = 0
        if self.tqcb is not None:
            self.tqcb.total = self.total
            self.tqcb.reset()
            self.tqcb.refresh()

        tasks = [self._process_entry(url) for url in entries]
        gather = asyncio.gather(*tasks, loop=asyncio.get_event_loop())
        await gather

    async def astart(self, input_queue: Queue, batch_size=10):
        batch = []
        while not self.stop_flag or (self.stop_flag and input_queue.qsize() > 0):
            try:
                entry = input_queue.get_nowait()
                batch.append(asyncio.get_event_loop().create_task(self.process_entry(entry)))
            except QueueEmpty:
                await asyncio.sleep(10*random())
            
            if self.stop_flag or (len(batch) > batch_size and not self.stop_flag):
                await asyncio.gather(*batch)


    def start(self, input_queue: Queue) -> asyncio.Future:
        loop = asyncio.get_event_loop()
        return asyncio.ensure_future(self.astart(input_queue, batch_size), loop=loop)

    def stop(self, *args, **kwargs):
        self.stop_flag = True


class CSVWriter:
    def __init__(
        self,
        queue: Queue,
        filename: str,
        max_interval: int = 60,
        max_chunk: int = 100,
        include_headers: bool = False,
    ):
        self.filename = filename
        if not os.path.exists(filename):
            head, tail = os.path.split(self.filename)
            if len(head) > 0:
                os.makedirs(head)
        self._write_headers()

        self.max_interval = max_interval
        self.max_chunk = max_chunk
        self.data_queue = queue
        self._task: asyncio.Future = None
        self._chunk: list[ParsedData] = []
        self.stop_flag = False

    async def write_queue(self):
        loop = asyncio.get_event_loop()
        chunk = []

        timeout = loop.call_at(loop.time() + self.max_interval, callback=partial(self._write, chunk))
        logger.debug("set write interval %i", self.max_interval)

        while not self.stop_flag:
            if timeout.cancelled:
                timeout = loop.call_at(loop.time() + self.max_interval, callback=partial(self._write, chunk))
            try:
                data = self.data_queue.get_nowait()
                chunk.append(f"{data.name},{data.username},{data.email}\n")
                logger.debug("batching total: %i", len(chunk))
                if len(chunk) >= self.max_chunk:
                    logger.debug("sending write call")
                    timeout.cancel()
                    loop.call_at(loop.time() + 0.01, callback=partial(self._write, chunk))
            except QueueEmpty:
                await asyncio.sleep(0.05)
                    
        #Stop flag triggered

        while self.data_queue.qsize() > 0:
            try:
                data = self.data_queue.get_nowait()
                chunk.append(f"{data.name},{data.username},{data.email}")
            except QueueEmpty:
                pass
        
        self._write(chunk)

    def _write(self, chunk):
        logger.debug("writing %i", len(chunk))
        with open(self.filename, "a+") as fp:
            fp.writelines(chunk)
        chunk.clear()

    def _write_headers(self):
        with open(self.filename, "w") as fp:
            fp.write("name,username,email\n")

    def stop(self, *args, **kwargs):
        self.stop_flag = True
