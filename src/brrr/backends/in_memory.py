import collections
from ..queue import Queue, Message, QueueIsEmpty

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
InMemoryMemStore = dict
