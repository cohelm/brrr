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

    def put(self, message: str):
        self.messages.append(message)

    def get_message(self) -> Message:
        if self.closed:
            raise QueueIsClosed
        if not self.messages:
            raise QueueIsEmpty
        return Message(self.messages.popleft(), '')

    async def get_message_async(self):
        return self.get_message()

    def delete_message(self, receipt_handle: str):
        pass

    def get_info(self):
        return QueueInfo(
            num_messages=len(self.messages),
            num_inflight_messages=0,
        )

    def set_message_timeout(self, receipt_handle, seconds):
        pass


# Just to drive the point home
class InMemoryByteStore(Store[bytes]):
    """
    A store that stores bytes
    """
    store: dict

    def __init__(self):
        self.store = {}

    def __contains__(self, key: str) -> bool:
        return key in self.store

    def __getitem__(self, key: str) -> bytes:
        return self.store[key]

    def __setitem__(self, key: str, value: bytes):
        self.store[key] = value

    def __delitem__(self, key: str):
        try:
            del self.store[key]
        except KeyError:
            pass

    def compare_and_set(self, key: str, value: bytes, expected: bytes | None):
        if expected is None and key in self.store or self.store.get(key) != expected:
            raise CompareMismatch
        self.store[key] = value

    def compare_and_delete(self, key: str, expected: bytes | None):
        if expected is None and key in self.store or self.store.get(key) != expected:
            raise CompareMismatch
        del self.store[key]
