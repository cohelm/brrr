import pytest

from brrr import Brrr
from brrr.backends.in_memory import InMemoryByteStore


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
