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
class InMemoryByteStore(Store):
    """
    A store that stores bytes
    """

    inner: dict

    def __init__(self):
        self.inner = {}

    async def has(self, key: str) -> bool:
        return key in self.inner

    async def get(self, key: str) -> bytes:
        return self.inner[key]

    async def set(self, key: str, value: bytes):
        self.inner[key] = value

    async def delete(self, key: str):
        try:
            del self.inner[key]
        except KeyError:
            pass

    async def set_new_value(self, key: str, value: bytes):
        if key in self.inner:
            raise CompareMismatch
        self.inner[key] = value

    async def compare_and_set(self, key: str, value: bytes, expected: bytes):
        if (key not in self.inner) or (self.inner[key] != expected):
            raise CompareMismatch
        self.inner[key] = value

    async def compare_and_delete(self, key: str, expected: bytes):
        if (key not in self.inner) or (self.inner[key] != expected):
            raise CompareMismatch
        del self.inner[key]
