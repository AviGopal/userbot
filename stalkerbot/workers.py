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
from stalkerbot.utils import ParsedData, SearchResult, requests_future, State
from functools import partial
from tqdm.asyncio import tqdm
import pickle

logger = logging.getLogger("worker")


class StalkerWorker:
    def __init__(
        self,
        output_queue: Queue,
        max_retries=10,
        max_timeout=32,
        max_concurrent=25,
        tqcb: "tqdm_asyncio" = None,
    ):
        self.output_queue = output_queue
        self.max_retries = max_retries
        self.max_timeout = max_timeout
        self.stop_flag = False

    async def astart(self, input_queue: Queue):
        while not self.stop_flag or (self.stop_flag and input_queue.qsize() > 0):
            kwargs = await input_queue.get()
            resp = await requests_future(
                "post", "https://api.github.com/graphql", **kwargs
            )
            if resp.status_code == 200:
                await self.output_queue.put(resp.content)

    def stop(self, *args, **kwargs):
        self.stop_flag = True


class CSVWriter:
    def __init__(
        self,
        queue: Queue,
        filename: str,
        max_interval: int = 2,
        max_chunk: int = 100,
        include_headers: bool = False,
        silent: bool = False,
        early_stop: int = None,
    ):
        self.filename = filename
        if not os.path.exists(filename):
            head, tail = os.path.split(self.filename)
            if len(head) > 0:
                os.makedirs(head, exist_ok=True)
        self._write_headers()

        self.max_interval = max_interval
        self.max_chunk = max_chunk
        self.data_queue = queue
        self.stop_flag = False
        self.early_stop = early_stop
        self.total = 0
        if not silent:
            self.progress = tqdm(desc="written", unit="emails")
        else:
            self.progress = None
        self.state = None

    async def astart(self):
        loop = asyncio.get_event_loop()
        chunk = []

        timeout = loop.call_at(
            loop.time() + self.max_interval, callback=partial(self._write, chunk)
        )
        logger.debug("set write interval %i", self.max_interval)

        while not self.stop_flag:
            if timeout.cancelled:
                timeout = loop.call_at(
                    loop.time() + self.max_interval,
                    callback=partial(self._write, chunk),
                )
            try:
                data = self.data_queue.get_nowait()
                if isinstance(data, State):
                    self.state = data
                    self._save(data)
                    continue
                chunk.append(f"{data.name},{data.login},{data.email}\n")
                if len(chunk) >= self.max_chunk:
                    timeout.cancel()
                    self._write(chunk)
                    # await loop.run_in_executor(None, partial(self._write, chunk))
                    self._write(chunk)
                    timeout = loop.call_at(
                        loop.time() + self.max_interval,
                        callback=partial(self._write, chunk),
                    )
                    chunk = []
            except QueueEmpty:
                if timeout.cancelled:
                    timeout = loop.call_at(
                        loop.time() + self.max_interval,
                        callback=partial(self._write, chunk),
                    )
                await asyncio.sleep(self.max_interval)

        # Stop flag triggered

        while self.data_queue.qsize() > 0:
            try:
                data = self.data_queue.get_nowait()
                if isinstance(data, State):
                    self._save(data)
                    continue
                chunk.append(f"{data.name},{data.login},{data.email}\n")
            except QueueEmpty:
                pass

        self._write(chunk)

    def _save(self, state):
        with open(".state", "wb") as fp:
            pickle.dump(state, fp)

    def _write(self, chunk):
        with open(self.filename, "a+") as fp:
            fp.writelines(chunk)
            if self.progress is not None:
                self.progress.update(len(chunk))
        self.total += len(chunk)
        if (
            self.early_stop is not None
            and self.early_stop > 0
            and self.total > self.early_stop
        ):
            self.stop_flag = True
        chunk.clear()
        self._save(self.state)

    def _write_headers(self):
        with open(self.filename, "w") as fp:
            fp.write("name,username,email\n")

    def stop(self, *args, **kwargs):
        self.stop_flag = True
