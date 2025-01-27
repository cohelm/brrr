from collections import Counter


from brrr import Brrr
from brrr.backends.in_memory import InMemoryByteStore
from brrr.codec import PickleCodec

from .closable_test_queue import ClosableInMemQueue


class NoArgsCodec(PickleCodec):
    def hash_call(self, task_name: str, args: tuple, kwargs: dict) -> str:
        # Ignore args & kwargs
        return task_name


async def test_cache_key_no_args():
    b = Brrr()
    calls = Counter()
    store = InMemoryByteStore()
    queue = ClosableInMemQueue()

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

    b.setup(queue, store, store, NoArgsCodec())
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
