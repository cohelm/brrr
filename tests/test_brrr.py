import asyncio
from collections import Counter

import pytest

from brrr import Brrr
from brrr.backends.in_memory import InMemoryByteStore
import brrr.queue as q


@pytest.fixture
def handle_nobrrr():
    b = Brrr()

    @b.register_task
    async def handle_nobrrr(a: int) -> int:
        return a if a == 0 else a + await handle_nobrrr(a - 1)

    return handle_nobrrr


async def test_no_brrr_funcall(handle_nobrrr):
    assert await handle_nobrrr(3) == 6


async def test_no_brrr_map(handle_nobrrr):
    assert await handle_nobrrr.map([[3], [4]]) == [6, 10]


class ClosableInMemQueue(q.Queue):
    """A message queue which can be closed."""

    def __init__(self):
        self.operational = True
        self.closing = False
        self.i = 0
        self.received = asyncio.Queue()
        self.handling = {}

    def close(self):
        assert not self.closing
        self.closing = True
        self.received.shutdown()

    async def join(self):
        await self.received.join()

    async def get_message(self):
        assert self.operational
        try:
            body = await self.received.get()
        except asyncio.QueueShutDown:
            assert not self.handling
            self.operational = False
            raise q.QueueIsClosed()

        handle = str(self.i)
        self.i += 1
        self.handling[handle] = body
        return q.Message(body=body, receipt_handle=handle)

    async def put(self, body: str):
        assert self.operational
        await self.received.put(body)

    async def delete_message(self, receipt_handle: str):
        assert self.operational
        del self.handling[receipt_handle]
        self.received.task_done()

    async def set_message_timeout(self, receipt_handle: str, seconds: int):
        assert receipt_handle in self.handling

    async def get_info(self):
        raise NotImplementedError()


async def test_stop_when_empty():
    # Keeping state of the calls to see how often it’s called
    b = Brrr()
    calls_pre = Counter()
    calls_post = Counter()
    queue = ClosableInMemQueue()

    @b.register_task
    async def foo(a: int) -> int:
        calls_pre[a] += 1
        if a == 0:
            return 0
        res = await foo(a - 1)
        calls_post[a] += 1
        if a == 3:
            queue.close()
        return res

    b.setup(queue, InMemoryByteStore())
    await asyncio.gather(b.wrrrk(), b.schedule("foo", (3,), {}))
    await queue.join()
    assert calls_pre == Counter({0: 1, 1: 2, 2: 2, 3: 2})
    assert calls_post == Counter({1: 1, 2: 1, 3: 1})


async def test_debounce():
    b = Brrr()
    calls = Counter()
    queue = ClosableInMemQueue()

    @b.register_task
    async def foo(a: int) -> int:
        calls[a] += 1
        if a == 0:
            return a

        ret = sum(await foo.map([[a - 1]] * 50))
        if a == 3:
            queue.close()
        return ret

    b.setup(queue, InMemoryByteStore())
    await asyncio.gather(b.wrrrk(), b.schedule("foo", (3,), {}))
    await queue.join()
    assert calls == Counter({0: 1, 1: 2, 2: 2, 3: 2})


async def test_wrrrk_recoverable():
    b = Brrr()
    queue = ClosableInMemQueue()
    store = InMemoryByteStore()
    calls = Counter()

    class MyError(Exception):
        pass

    @b.register_task
    async def foo(a: int) -> int:
        calls[f"foo({a})"] += 1
        if a == 0:
            raise MyError()
        return await foo(a - 1)

    @b.register_task
    async def bar(a: int) -> int:
        calls[f"bar({a})"] += 1
        if a == 0:
            return 0
        ret = await bar(a - 1)
        if a == 2:
            queue.close()
        return ret

    b.setup(queue, store)
    my_error_encountered = False
    await b.schedule("foo", (2,), {})
    try:
        await b.wrrrk()
    except MyError:
        my_error_encountered = True
    assert my_error_encountered

    # Trick the test queue implementation to survive this
    queue.received = asyncio.Queue()
    queue.handling = {}
    await b.schedule("bar", (2,), {})
    await b.wrrrk()

    assert calls == Counter(
        {
            "foo(0)": 1,
            "foo(1)": 1,
            "foo(2)": 1,
            "bar(0)": 1,
            "bar(1)": 2,
            "bar(2)": 2,
        }
    )
