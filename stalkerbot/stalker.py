import asyncio
import datetime
from asyncio.queues import Queue, QueueFull
from http.cookiejar import CookieJar

from requests.auth import HTTPBasicAuth
from tqdm.asyncio import tqdm

from stalkerbot.exc import RateLimitExceededException
from stalkerbot.search import Search
from stalkerbot.workers import CSVWriter, StalkerWorker
from stalkerbot.utils import QueryResponse, State
from logging import getLogger
from concurrent.futures import ProcessPoolExecutor
from random import random

logger = getLogger("stalker")


class Stalker:
    def __init__(
        self,
        query: str,
        token: str,
        continue_from: State = None,
        early_stop: int = None,
        output_path: str = "data/github_users.csv",
        silent: bool = False,
        state: State = None,
    ):
        self.data_queue = Queue()
        self.search_queue = Queue()
        self.output_queue = Queue()
        if not silent:
            self.progress = tqdm(desc="progress", position=0, unit="pages")
        else:
            self.progress = None

        self.worker = StalkerWorker(self.data_queue)
        self.writer = CSVWriter(self.output_queue, filename=output_path, early_stop=early_stop, silent=silent)
        self.query = query
        self.state = continue_from
        self.start_time = datetime.datetime.utcnow()
        self.early_stop = early_stop
        self.search = Search(
            query=query,
            token=token,
            continue_from=continue_from,
            state=state,
            silent=silent
        )

    def start(self):
        logger.debug("starting...")

        loop = asyncio.get_event_loop()

        worker_task = loop.create_task(self.worker.astart(self.search_queue))
        writer_task = loop.create_task(self.writer.astart())
        search_task = loop.create_task(self._search())

        worker_task.add_done_callback(self.writer.stop)
        if self.early_stop:
            writer_task.add_done_callback(self.worker.stop)

        logger.debug("Tasks started")
        all_tasks = asyncio.gather(writer_task, worker_task, loop=loop)
        loop.run_until_complete(all_tasks)
        logger.debug("Tasks complete")

    def stop(self, cb=None):
        try:
            loop = asyncio.get_running_loop()
            loop.stop()
        except RuntimeError:
            # Already stopped
            pass

    async def _search(self):
        logger.debug("Search started")
        try:
            resp = None
            gen = self.search.gen()
            kwargs, state = await gen.asend(None)
            while True:
                logger.debug("fetching")
                await self.search_queue.put(kwargs)
                raw = await self.data_queue.get()
                logger.debug("parsing")
                resp = QueryResponse(raw)
                if self.progress is not None:
                    self.progress.update()
                logger.debug("putting")
                for user in resp.users:
                    if user.email is not None and len(user.email) > 0:
                        await self.output_queue.put(user)
                self.state = state
                logger.debug("sending")
                await self.writer.data_queue.put(state)                    
                kwargs, state = await gen.asend(resp)
                await asyncio.sleep(max(0.01, random()))
        except RuntimeError:
            pass
