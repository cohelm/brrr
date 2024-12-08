from dataclasses import dataclass


class QueueIsEmpty(Exception):
    pass

@dataclass
class Message:
    body: str
    receipt_handle: str


# Infra abstractions

class Queue:
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
