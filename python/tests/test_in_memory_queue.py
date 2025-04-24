from contextlib import asynccontextmanager
from typing import AsyncIterator

from brrr.queue import Queue
from brrr.backends.in_memory import InMemoryQueue
from tests.contract_queue import QueueContract


class TestInMemoryQueue(QueueContract):
    has_accurate_info = True

    @asynccontextmanager
    async def with_queue(self) -> AsyncIterator[Queue]:
        yield InMemoryQueue()
