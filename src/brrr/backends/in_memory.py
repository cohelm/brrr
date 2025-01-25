import collections

from brrr.store import CompareMismatch
from ..queue import Queue, Message, QueueInfo, QueueIsClosed, QueueIsEmpty
from ..store import MemKey, Store


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


def _key2str(key: MemKey) -> str:
    return f"{key.type}/{key.id}"


# Just to drive the point home
class InMemoryByteStore(Store):
    """
    A store that stores bytes
    """

    inner: dict[str, bytes]

    def __init__(self):
        self.inner = {}

    async def has(self, key: MemKey) -> bool:
        return _key2str(key) in self.inner

    async def get(self, key: MemKey) -> bytes:
        return self.inner[_key2str(key)]

    async def set(self, key: MemKey, value: bytes):
        self.inner[_key2str(key)] = value

    async def delete(self, key: MemKey):
        try:
            del self.inner[_key2str(key)]
        except KeyError:
            pass

    async def set_new_value(self, key: MemKey, value: bytes):
        k = _key2str(key)
        if k in self.inner:
            raise CompareMismatch
        self.inner[k] = value

    async def compare_and_set(self, key: MemKey, value: bytes, expected: bytes):
        k = _key2str(key)
        if (k not in self.inner) or (self.inner[k] != expected):
            raise CompareMismatch
        self.inner[k] = value

    async def compare_and_delete(self, key: MemKey, expected: bytes):
        k = _key2str(key)
        if (k not in self.inner) or (self.inner[k] != expected):
            raise CompareMismatch
        del self.inner[k]
