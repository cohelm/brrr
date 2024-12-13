import collections

from brrr.store import CompareMismatch
from ..queue import Queue, Message, QueueIsEmpty, Store

class InMemoryQueue(Queue):
    """
    This queue does not do receipts
    """
    messages = collections.deque()

    def put(self, message: str):
        self.messages.append(message)

    def get_message(self) -> Message:
        if not self.messages:
            raise QueueIsEmpty
        return Message(self.messages.popleft(), '')

    async def get_message_async(self):
        return self.get_message()

    def delete_message(self, receipt_handle: str):
        pass


# Just to drive the point home
class InMemoryByteStore(Store[bytes]):
    """
    A store that stores bytes
    """
    store = {}

    def __contains__(self, key: str) -> bool:
        return key in self.store

    def __getitem__(self, key: str) -> bytes:
        return self.store[key]

    def __setitem__(self, key: str, value: bytes):
        self.store[key] = value

    def __delitem__(self, key: str):
        del self.store[key]

    def compare_and_set(self, key: str, value: bytes, expected: bytes | None):
        if expected is None and key in self.store or self.store.get(key) != expected:
            raise CompareMismatch
        self.store[key] = value

    def compare_and_delete(self, key: str, expected: bytes | None):
        if expected is None and key in self.store or self.store.get(key) != expected:
            raise CompareMismatch
        del self.store[key]
