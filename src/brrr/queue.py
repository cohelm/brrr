from abc import ABC, abstractmethod
from dataclasses import dataclass


class QueueIsEmpty(Exception):
    pass


class QueueIsClosed(Exception):
    """
    Queue implementations may raise this exception for workers to shut down gracefully
    """


@dataclass
class Message:
    body: str
    receipt_handle: str


@dataclass
class QueueInfo:
    """
    Approximate info about the queue
    """

    num_messages: int
    num_inflight_messages: int


# Infra abstractions


class Queue(ABC):
    # Inspired by SQS: maximum time for a get_message call to block while
    # waiting for new messages, if there are currently no messages on the queue.
    # Just as with SQS, if there is a message, return immediately.  This value
    # is best effort, just a way to keep this DRY if nothing else.  If the
    # underlying queue doesn’t support this primitive it’s OK, but don’t sleep
    # for this time indiscriminately because the point of this value is to block
    # only while there are no messages available.
    recv_block_secs: int = 20

    throws_queue_is_closed: bool
    has_accurate_info: bool
    deletes_messages: bool

    @abstractmethod
    async def put(self, body: str): ...
    @abstractmethod
    async def get_message(self) -> Message: ...
    @abstractmethod
    async def delete_message(self, receipt_handle: str): ...
    @abstractmethod
    async def set_message_timeout(self, receipt_handle: str, seconds: int): ...
    @abstractmethod
    async def get_info(self) -> QueueInfo: ...


class RichQueue(Queue):
    # Max number of jobs that can be processed concurrently
    max_concurrency: int

    # Every job requires a token from the pool to be dequeued
    rate_limit_pool_capacity: int

    # The number of tokens restored to the pool per second
    replenish_rate_per_second: float
