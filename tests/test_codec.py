from collections import Counter
from unittest.mock import Mock, call

from brrr import Brrr
from brrr.backends.in_memory import InMemoryByteStore
from brrr.codec import PickleCodec

from .closable_test_queue import ClosableInMemQueue


async def test_codec_key_no_args():
    b = Brrr()
    calls = Counter()
    store = InMemoryByteStore()
    queue = ClosableInMemQueue()
    codec = PickleCodec()

    def hash_call(task_name, args, kwargs):
        return task_name

    codec.hash_call = Mock(side_effect=hash_call)

    @b.register_task
    async def same(a: int) -> int:
        calls[f"same({a})"] += 1
        return a

    @b.register_task
    async def foo(a: int) -> int:
        calls[f"foo({a})"] += 1

        val = 0
        # Call in deterministic order for the test’s sake
        for i in range(1, a + 1):
            val += await same(i)

        assert val == a
        queue.close()
        return val

    b.setup(queue, store, store, codec)
    await b.schedule("foo", (50,), {})
    await b.wrrrk()
    await queue.join()
    assert not queue.handling
    assert calls == Counter(
        {
            "same(1)": 1,
            "foo(50)": 2,
        }
    )
    codec.hash_call.assert_called()


async def test_codec_api():
    b = Brrr()
    store = InMemoryByteStore()
    queue = ClosableInMemQueue()
    codec = Mock(wraps=PickleCodec())

    @b.register_task
    async def plus(x: int, y: str) -> int:
        return x + int(y)

    @b.register_task
    async def foo() -> int:
        val = (
            await plus(1, "2")
            + await plus(x=3, y="4")
            + await plus(*(5, "6"))
            + await plus(**dict(x=7, y="8"))
        )
        assert val == sum(range(9))
        queue.close()
        return val

    b.setup(queue, store, store, codec)
    await b.schedule("foo", (), {})
    await b.wrrrk()
    await queue.join()
    assert not queue.handling
    codec.hash_call.assert_has_calls(
        [
            call("foo", (), {}),
            call("plus", (1, "2"), {}),
            call("plus", (), {"x": 3, "y": "4"}),
            call("plus", (5, "6"), {}),
            call("plus", (), {"x": 7, "y": "8"}),
        ],
        any_order=True,
    )
    codec.encode_args.assert_has_calls(
        [
            call((), {}),
            call((1, "2"), {}),
            call((), {"x": 3, "y": "4"}),
            call((5, "6"), {}),
            call((), {"x": 7, "y": "8"}),
        ],
        any_order=True,
    )
    codec.encode_return.assert_has_calls(
        [
            call(3),
            call(7),
            call(11),
            call(15),
            call(sum(range(9))),
        ],
        any_order=True,
    )
