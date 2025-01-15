from contextlib import asynccontextmanager
from typing import AsyncIterable

from brrr.backends.in_memory import InMemoryByteStore
from brrr.store import Store

from .store_contract import MemoryContract


class TestInMemoryByteStore(MemoryContract):
    @asynccontextmanager
    async def with_store(self) -> AsyncIterable[Store]:
        yield InMemoryByteStore()
