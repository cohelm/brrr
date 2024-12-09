from dataclasses import dataclass


class QueueIsEmpty(Exception):
    pass

@dataclass
class Message:
    body: str
    receipt_handle: str


# Infra abstractions

class Queue:
    # Inspired by SQS: maximum time for a get_message call to block while
    # waiting for new messages, if there are currently no messages on the queue.
    # Just as with SQS, if there is a message, return immediately.  This value
    # is best effort, just a way to keep this DRY if nothing else.  If the
    # underlying queue doesn’t support this primitive it’s OK, but don’t sleep
    # for this time indiscriminately because the point of this value is to block
    # only while there are no messages available.
    recv_block_secs: int = 20

    async def get_message_async(self) -> Message:
        return self.get_message()
    def get_message(self) -> Message:
        raise NotImplementedError
    def delete_message(self, receipt_handle: str):
        raise NotImplementedError
    def set_message_timeout(self, receipt_handle: str, seconds: int):
        raise NotImplementedError


class RichQueue(Queue):
    # Max number of jobs that can be processed concurrently
    max_concurrency: int

    # Every job requires a token from the pool to be dequeued
    rate_limit_pool_capacity: int

    # The number of tokens restored to the pool per second
    replenish_rate_per_second: float
