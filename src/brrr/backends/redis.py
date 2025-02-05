from __future__ import annotations

import json
import logging
import time
import typing

from ..queue import Message, Queue, QueueInfo, QueueIsEmpty
from ..store import Cache

if typing.TYPE_CHECKING:
    from redis.asyncio import Redis


logger = logging.getLogger(__name__)


class RedisQueue(Queue, Cache):
    client: Redis
    queue: str

    def __init__(self, client: Redis, queue: str):
        self.client = client
        self.queue = queue

    async def setup(self):
        pass

    async def put_message(self, body: str):
        logger.debug(f"Putting new message on {self.queue}")
        val = json.dumps((1, int(time.time()), body), separators=(",", ":"))
        await self.client.rpush(self.queue, val)

    async def get_message(self) -> Message:
        response = await self.client.blpop(self.queue, self.recv_block_secs)
        if not response:
            raise QueueIsEmpty()
        try:
            chunks = json.loads(response[1])
        except json.JSONDecodeError:
            logger.error(f"Invalid message json in {self.queue}: {repr(response)}")
            raise
        if chunks[0] != 1:
            # The message has disappeared from the queue and won’t be retried
            # anyway.
            logger.error(f"Invalid message structure in {self.queue}: {repr(chunks)}")
            raise ValueError("Invalid message in queue")
        # Ignore timestamp for now
        return Message(chunks[2])

    async def get_info(self):
        total = await self.client.llen(self.queue)
        return QueueInfo(num_messages=total)

    async def incr(self, key: str) -> int:
        return await self.client.incr(key)
