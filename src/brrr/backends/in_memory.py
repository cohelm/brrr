import collections

from brrr.store import CompareMismatch
from ..queue import Queue, Message, QueueInfo, QueueIsClosed, QueueIsEmpty
from ..store import Store


class InMemoryQueue(Queue):
    """
    This queue does not do receipts
    """

    messages = collections.deque()
    closed = False

    async def put(self, body: str):
        self.messages.append(body)

    async def get_message(self) -> Message:
        if self.closed:
            raise QueueIsClosed
        if not self.messages:
            raise QueueIsEmpty
        return Message(self.messages.popleft(), "")

    async def delete_message(self, receipt_handle: str):
        pass

    async def get_info(self):
        return QueueInfo(
            num_messages=len(self.messages),
            num_inflight_messages=0,
        )

    async def set_message_timeout(self, receipt_handle, seconds):
        pass


# Just to drive the point home
class InMemoryByteStore(Store[bytes]):
    """
    A store that stores bytes
    """

    store: dict

    def __init__(self):
        self.store = {}

    async def has(self, key: str) -> bool:
        return key in self.store

    async def get(self, key: str) -> bytes:
        return self.store[key]

    async def set(self, key: str, value: bytes):
        self.store[key] = value

    async def delete(self, key: str):
        try:
            del self.store[key]
        except KeyError:
            pass

    async def compare_and_set(self, key: str, value: bytes, expected: bytes | None):
        if expected is None and key in self.store or self.store.get(key) != expected:
            raise CompareMismatch
        self.store[key] = value

    async def compare_and_delete(self, key: str, expected: bytes | None):
        if expected is None and key in self.store or self.store.get(key) != expected:
            raise CompareMismatch
        del self.store[key]
