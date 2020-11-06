import asyncio
import datetime
from asyncio.queues import Queue
from http.cookiejar import CookieJar

from requests.auth import HTTPBasicAuth
from tqdm.asyncio import tqdm

from stalkerbot.exc import RateLimitExceededException
from stalkerbot.search import Search
from stalkerbot.workers import CSVWriter, StalkerWorker


class Stalker:
    def __init__(
        self,
        cookiejar: CookieJar,
        query: str,
        username: str,
        token: str,
        workers: int = 1,
        page_size: int = 100,
        continue_from: int = 1,
        output_path: str = "github_users.csv",
        tqcb: tqdm = None,
    ):
        if workers < 1:
            raise ValueError("Must have atleast one worker")
        self.data_queue = Queue(page_size * workers)
        self.search_queue = Queue(page_size * workers)
        self.tqcb = tqcb
        self.cookiejar = cookiejar
        self.workers = self._init_workers(workers)
        self.writer = CSVWriter(
            self.data_queue, filename=output_path, max_chunk=page_size
        )
        self.query = query
        self.page_size = page_size
        self.page = continue_from
        self.total = 0
        self.processed = 0
        self.start_time = datetime.datetime.utcnow()

        self.search = Search(
            HTTPBasicAuth(username, token),
            self.query,
            "followers",
            self.page_size,
            continue_from,
        )
        tqcb.refresh()

    def start(self):
        loop = asyncio.get_event_loop()
        tasks = [worker.start(self.search_queue) for worker in self.workers]
        gather = asyncio.gather(
            *tasks, self.writer.write_queue(), self._search(), loop=loop
        )

        loop.run_until_complete(gather)

    def stop(self):
        loop = asyncio.get_running_loop()
        loop.stop()

    def _init_workers(self, num_workers) -> list[StalkerWorker]:
        return [
            StalkerWorker(
                self.cookiejar,
                self.data_queue,
                tqcb=tqdm(position=i + 1, desc=f"worker #{i}", leave=False),
            )
            for i in range(num_workers)
        ]

    async def _search(self):
        async for result in self.search:
            self.total = result.total
            for item in result.items:
                await self.search_queue.put(item)
            if self.tqcb is not None:
                self.tqcb.total = int(self.total / self.page_size) + min(
                    1, self.total % self.page_size
                )
                self.tqcb.update(1)