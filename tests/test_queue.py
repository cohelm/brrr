import pytest

from abc import ABC, abstractmethod
from brrr.queue import Queue, QueueIsEmpty, QueueIsClosed
from brrr.backends.in_memory import InMemoryQueue

class QueueContract(ABC):
    throws_closes: bool
    has_accurate_info: bool
    deletes_messages: bool

    @abstractmethod
    def get_queue(self) -> Queue:
        """
        This should return a fresh, empty queue instance
        """
        ...

    # TODO Move this to a mixin? This is pretty ugly.
    #      One problem is that we have no control over clients, which usually do the closing
    @abstractmethod
    def close_queue(self):
        ...

    def test_queue_raises_empty(self):
        queue = self.get_queue()
        with pytest.raises(QueueIsEmpty):
            queue.get_message()

    def test_queue_enqueues(self):
        queue = self.get_queue()
        messages = set(["message-1", "message-2", "message-3"])

        if self.has_accurate_info:
            assert queue.get_info().num_messages == 0

        queue.put("message-1")
        if self.has_accurate_info:
            assert queue.get_info().num_messages == 1

        queue.put("message-2")
        if self.has_accurate_info:
            assert queue.get_info().num_messages == 2

        queue.put("message-3")
        if self.has_accurate_info:
            assert queue.get_info().num_messages == 3

        message = queue.get_message()
        assert message.body in messages
        messages.remove(message.body)
        if self.has_accurate_info:
            assert queue.get_info().num_messages == 2

        message = queue.get_message()
        assert message.body in messages
        messages.remove(message.body)
        if self.has_accurate_info:
            assert queue.get_info().num_messages == 1

        message = queue.get_message()
        assert message.body in messages
        messages.remove(message.body)
        if self.has_accurate_info:
            assert queue.get_info().num_messages == 0

        with pytest.raises(QueueIsEmpty):
            queue.get_message()

    def test_closing(self):
        if not self.throws_closes:
            pytest.skip("Queue does not throw QueueIsClosed exceptions")
        queue = self.get_queue()
        queue.put("message-1")
        self.close_queue(queue)
        with pytest.raises(QueueIsClosed):
            queue.get_message()


class TestInMemoryQueue(QueueContract):
    throws_closes = True
    has_accurate_info = True
    deletes_messages = True

    def get_queue(self) -> Queue:
        return InMemoryQueue()

    def close_queue(self, queue):
        queue.closed = True
