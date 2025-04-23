import asyncio
from collections import Counter

import pytest

from brrr import Brrr
from brrr.backends.in_memory import InMemoryByteStore
from brrr.naive_codec import PickleCodec

from .closable_test_queue import ClosableInMemQueue


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


async def test_nop_closed_queue():
    b = Brrr()
    store = InMemoryByteStore()
    queue = ClosableInMemQueue()
    await queue.close()
    b.setup(queue, store, store, PickleCodec())
    await b.wrrrk()
    await b.wrrrk()
    await b.wrrrk()


async def test_stop_when_empty():
    # Keeping state of the calls to see how often it’s called
    b = Brrr()
    calls_pre = Counter()
    calls_post = Counter()
    store = InMemoryByteStore()
    queue = ClosableInMemQueue()

    @b.register_task
    async def foo(a: int) -> int:
        calls_pre[a] += 1
        if a == 0:
            return 0
        res = await foo(a - 1)
        calls_post[a] += 1
        if a == 3:
            await queue.close()
        return res

    b.setup(queue, store, store, PickleCodec())
    await b.schedule("foo", (3,), {})
    await b.wrrrk()
    await queue.join()
    assert calls_pre == Counter({0: 1, 1: 2, 2: 2, 3: 2})
    assert calls_post == Counter({1: 1, 2: 1, 3: 1})


async def test_debounce_child():
    b = Brrr()
    calls = Counter()
    store = InMemoryByteStore()
    queue = ClosableInMemQueue()

    @b.register_task
    async def foo(a: int) -> int:
        calls[a] += 1
        if a == 0:
            return a

        ret = sum(await foo.map([[a - 1]] * 50))
        if a == 3:
            await queue.close()
        return ret

    b.setup(queue, store, store, PickleCodec())
    await b.schedule("foo", (3,), {})
    await b.wrrrk()
    await queue.join()
    assert calls == Counter({0: 1, 1: 2, 2: 2, 3: 2})


# This formalizes an anti-feature: we actually do want to debounce calls to the
# same parent.  Let’s at least be explicit about this for now.
async def test_no_debounce_parent():
    b = Brrr()
    calls = Counter()
    store = InMemoryByteStore()
    queue = ClosableInMemQueue()

    @b.register_task
    async def one(_: int) -> int:
        calls["one"] += 1
        return 1

    @b.register_task
    async def foo(a: int) -> int:
        calls["foo"] += 1
        # Different argument to avoid debouncing children
        ret = sum(await one.map([[i] for i in range(a)]))
        # Obviously we only actually ever want to reach this point once
        if calls["foo"] == 1 + a:
            await queue.close()
        return ret

    b.setup(queue, store, store, PickleCodec())
    await b.schedule("foo", (50,), {})
    await b.wrrrk()
    await queue.join()
    # We want foo=2 here
    assert calls == Counter(one=50, foo=51)


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
            await queue.close()
        return ret

    b.setup(queue, store, store, PickleCodec())
    my_error_encountered = False
    await b.schedule("foo", (2,), {})
    try:
        await b.wrrrk()
    except MyError:
        my_error_encountered = True
    assert my_error_encountered

    # Trick the test queue implementation to survive this
    queue.received = asyncio.Queue()
    await b.schedule("bar", (2,), {})
    await b.wrrrk()
    await queue.join()

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
