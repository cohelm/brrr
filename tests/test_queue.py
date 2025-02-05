from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncIterator

import pytest

from brrr.queue import Queue, QueueIsEmpty
from brrr.backends.in_memory import InMemoryQueue


class QueueContract(ABC):
    throws_closes: bool
    has_accurate_info: bool
    deletes_messages: bool

    @abstractmethod
    @asynccontextmanager
    async def with_queue(self) -> AsyncIterator[Queue]:
        """
        A context manager which calls test function f with a queue
        """
        ...

    async def test_queue_raises_empty(self):
        async with self.with_queue() as queue:
            with pytest.raises(QueueIsEmpty):
                await queue.get_message()

    async def test_queue_enqueues(self):
        async with self.with_queue() as queue:
            messages = set(["message-1", "message-2", "message-3"])

            if self.has_accurate_info:
                assert (await queue.get_info()).num_messages == 0

            await queue.put_message("message-1")
            if self.has_accurate_info:
                assert (await queue.get_info()).num_messages == 1

            await queue.put_message("message-2")
            if self.has_accurate_info:
                assert (await queue.get_info()).num_messages == 2

            await queue.put_message("message-3")
            if self.has_accurate_info:
                assert (await queue.get_info()).num_messages == 3

            message = await queue.get_message()
            assert message.body in messages
            messages.remove(message.body)
            if self.has_accurate_info:
                assert (await queue.get_info()).num_messages == 2

            message = await queue.get_message()
            assert message.body in messages
            messages.remove(message.body)
            if self.has_accurate_info:
                assert (await queue.get_info()).num_messages == 1

            message = await queue.get_message()
            assert message.body in messages
            messages.remove(message.body)
            if self.has_accurate_info:
                assert (await queue.get_info()).num_messages == 0

            with pytest.raises(QueueIsEmpty):
                await queue.get_message()


class TestInMemoryQueue(QueueContract):
    throws_closes = True
    has_accurate_info = True
    deletes_messages = True

    @asynccontextmanager
    async def with_queue(self) -> AsyncIterator[Queue]:
        yield InMemoryQueue()
