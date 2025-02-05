from __future__ import annotations

import asyncio
import logging
import typing

from ..queue import Message, QueueInfo, RichQueue, QueueIsEmpty
from ..store import Cache

COMPARE_AND_SET_SCRIPT = """
local key = KEYS[1]
local value = ARGV[1]
local expected = ARGV[2]
local current = redis.call('GET', key)
if current == expected then
    redis.call('SET', key, value)
    return 1
else
    return 0
end
"""

COMPARE_AND_DELETE_SCRIPT = """
local key = KEYS[1]
local expected = ARGV[2]
local current = redis.call('GET', key)
if current == nil then
    return 1
elseif current == expected then
    redis.call('DEL', key)
    return 1
else
    return {current, expected}
    -- return 0
end
"""

if typing.TYPE_CHECKING:
    from redis.asyncio import Redis

# This script takes care of all of the queue semantics beyond at least once delivery
# - Rate limiting
# - Max concurrency
# - Job timeout
# - Requeueing stuck jobs
#
# Features to consider:
# - Dead letter queue
# - Cleaning up from failed scripts.
DEQUEUE_FUNCTION = """
-- This script is used to dequeue a message from a Redis stream
-- It respects max_concurrency as well as rate limits using a simple token bucket implementation
-- Usage: DEQUEUE_SCRIPT 1 <stream> <group> <consumer> <rate_limit_pool_capacity> <replenish_rate_per_second> <max_concurrency> <job_timeout_ms>
-- TODO make rate_limiting and max_concurrency optional

local stream = KEYS[1]
local rate_limiters = stream .. ":rate_limiters"
local group = ARGV[1]
local consumer = ARGV[2]
local rate_limit_pool_capacity = tonumber(ARGV[3])
local replenish_rate_per_second = tonumber(ARGV[4])
local max_concurrency = tonumber(ARGV[5])
local job_timeout_ms = tonumber(ARGV[6])

-- Grab one message from the stream
local message = redis.call('XREADGROUP', 'GROUP', group, consumer, 'COUNT', 1, 'STREAMS', stream, '>')

if message and #message > 0 then
    local stream_messages = message[1][2]
    if #stream_messages > 0 then
        local msg_id = stream_messages[1][1]
        -- If we have more key, value pairs, we'd need to find the body key here
        local msg_body = stream_messages[1][2][2]

        -- Before returning the message, add expiry to the key, then add it to the rate limiters (in this order to avoid immortal rate limiters)
        --local max_rate_limit_lookback_seconds = rate_limit_pool_capacity / replenish_rate_per_second
        --redis.call("EXPIRE", msg_id, max_rate_limit_lookback_seconds)
        --redis.call("SADD", rate_limiters, msg_id)

        return {msg_body, msg_id}
    end
end

return nil
""".strip()

ACK_FUNCTION = """
-- This script is used to delete a message from a Redis stream
-- Usage: DEQUEUE_SCRIPT 1 <stream> <group> <consumer> <rate_limit_pool_capacity> <replenish_rate_per_second> <max_concurrency> <job_timeout_ms>
-- TODO make rate_limiting and max_concurrency optional

local stream = KEYS[1]
local group = ARGV[1]
local msg_id = ARGV[2]

redis.call('XACK', stream, group, msg_id)
redis.call('XDEL', stream, msg_id)
"""

logger = logging.getLogger(__name__)


class RedisStream(RichQueue, Cache):
    client: Redis

    queue: str
    group = "workers"

    rate_limit_pool_capacity = 100
    replenish_rate_per_second = 10
    max_concurrency = 2
    job_timeout_ms = 1000

    consumer = "TODO_WORKER_ID"
    lib_name = "brrr"
    func_name = "dequeue"

    def __init__(self, client: Redis, queue: str):
        self.client = client
        self.queue = queue

    async def clear(self):
        await self.client.delete(self.queue)
        await self.client.delete(self.queue + ":rate_limiters")

    async def setup(self):
        try:
            await self.client.xgroup_create(
                self.queue, self.group, id="0", mkstream=True
            )
        # Ideally we would want to catch ‘redis.exceptions.ResponseError’ here
        # instead, but currently the entire production part of the code is
        # dependency-free.  That works because the actual redis client is
        # dependency-injected into the constructor.  The “real” solution is to
        # set up the build system to offer redis as a peer dependency, in an
        # “extras” group, but we’re not at that stage yet and this is an
        # acceptable hack for now.
        except Exception as e:
            if "BUSYGROUP Consumer Group name already exists" not in str(e):
                raise
            logger.debug(f"Creating fresh queue {self.queue}: queue already existed")
            return

        logger.debug(f"Created fresh queue {self.queue}")

    async def put(self, body: str):
        logger.debug(f"Putting new message on {self.queue}")
        # Messages can not be added to specific groups, so we just create a stream per topic
        await self.client.xadd(self.queue, {"body": body})

    async def get_message(self) -> Message:
        keys = (self.queue,)
        argv = map(
            str,
            (
                self.group,
                self.consumer,
                self.rate_limit_pool_capacity,
                self.replenish_rate_per_second,
                self.max_concurrency,
                self.job_timeout_ms,
            ),
        )
        response = await self.client.eval(DEQUEUE_FUNCTION, len(keys), *keys, *argv)
        if not response:
            # TODO: Do not wait indiscriminately but simulate blpop.  How do you
            # do that with a script?
            await asyncio.sleep(1)
            raise QueueIsEmpty
        body, receipt_handle = response[:2]
        return Message(body, receipt_handle)

    # TODO: This has a bug; xack does not remove the message from the stream
    async def delete_message(self, receipt_handle: str):
        # The receipt handle here must match the message ID
        # self.client.xack(self.queue, self.group, receipt_handle)
        keys = (self.queue,)
        argv = (
            self.group,
            receipt_handle,
        )
        await self.client.eval(ACK_FUNCTION, len(keys), *keys, *argv)

    async def get_info(self):
        total = await self.client.xlen(self.queue)
        pending = await self.client.xpending(self.queue, self.group)
        return QueueInfo(
            num_messages=total,
            num_inflight_messages=pending["pending"],
        )

    async def incr(self, key: str) -> int:
        return await self.client.incr(key)
