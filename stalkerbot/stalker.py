import asyncio
import datetime
from asyncio.queues import Queue, QueueFull
from http.cookiejar import CookieJar

from requests.auth import HTTPBasicAuth
from tqdm.asyncio import tqdm

from stalkerbot.exc import RateLimitExceededException
from stalkerbot.search import Search
from stalkerbot.workers import CSVWriter, StalkerWorker
from logging import getLogger

logger = getLogger('stalker')

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
        early_stop: int = 0,
        output_path: str = "github_users.csv",
        sort: str = "followers",
        order: str = "desc",
        tqcb: tqdm = None,
    ):
        if workers < 1:
            raise ValueError("Must have atleast one worker")
        self.data_queue = Queue(page_size)
        self.search_queue = Queue(page_size)
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
        self.early_stop = early_stop
        self.search = Search(
            auth=HTTPBasicAuth(username, token),
            query=self.query,
            sort=sort,
            order=order,
            per_page=self.page_size,
            continue_from=continue_from,
            early_stop=early_stop
        )
        if self.tqcb is not None:
            tqcb.refresh()


    def start(self):
        logger.debug('starting...')

        loop = asyncio.get_event_loop()
        tasks = [worker.astart(self.search_queue) for worker in self.workers]

        workers = asyncio.gather(*tasks, loop=loop)

        writer = loop.create_task(self.writer.write_queue())

        search_task = loop.create_task(self._search())

        for w in self.workers:
            search_task.add_done_callback(w.stop)

        workers.add_done_callback(self.writer.stop)

        logger.debug('Tasks started')
        all_tasks = asyncio.gather(workers, writer, search_task, loop=loop)
        loop.run_until_complete(all_tasks)
        logger.debug('Tasks complete')


    def stop(self, cb=None):
        try:
            loop = asyncio.get_running_loop()
            loop.stop()
        except RuntimeError:
            # Already stopped
            pass

    def _init_workers(self, num_workers) -> list[StalkerWorker]:
        return [
            StalkerWorker(
                self.cookiejar,
                self.data_queue,
            )
            for i in range(num_workers)
        ]

    async def _search(self):
        logger.debug('Search started')
        if self.tqcb is not None:
            progress = tqdm(desc='progress', position=1)
        async for result in self.search:
            self.total = result.total
            progress.total = result.total
            logger.debug('Total results %i', self.total)
            for item in result.items:
                put_done = False
                while not put_done:
                    try:
                        self.search_queue.put_nowait(item)
                        put_done = True
                        if self.tqcb is not None:
                            progress.update(1)
                            self.tqcb.refresh()
                            progress.refresh
                        logger.debug('Put item %s', str(item))
                    except QueueFull:
                        logger.debug('Search Queue full, sleeping')
                        await self.search_queue.put(item)
                        put_done = True
                        logger.debug('Put item %s', str(item))
                        if self.tqcb is not None:
                            progress.update(1)
                            self.tqcb.refresh()
                            progress.refresh
            if self.tqcb is not None:
                if self.early_stop > 0:
                    self.tqcb.total = self.early_stop
                else:
                    self.tqcb.total = int(self.total / self.page_size) + min(
                        1, self.total % self.page_size
                    )
                self.tqcb.update(1)
