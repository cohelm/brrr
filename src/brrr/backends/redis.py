from __future__ import annotations

import time
import typing
from typing import Any

from ..queue import Message, Queue, QueueInfo, RichQueue, QueueIsEmpty
from ..store import CompareMismatch, MemKey, Store

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
    import redis

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

-- Before dequeueing, restore all stuck jobs to the stream
-- TODO do we want to set timeout per job?
-- Count of 100 is the default, presumably we want this to be 'inf'
--local stuck_jobs = redis.call('XAUTOCLAIM', stream, group, 'watchdog', job_timeout_ms, '0-0', 'COUNT', 100)
--for _, job in ipairs(stuck_jobs[2] or {}) do
    ---- Add before removing to avoid race conditions
    --redis.call('XADD', stream, '*', 'body', job[2][2])
    --redis.call('SREM', rate_limiters, job[1])
--end

-- The PEL holds all currently active jobs, grabbed by a consumer that haven't been acked
-- If the PEL is full, we can't take any more jobs, we do need to make sure that
-- jobs don't get stuck in the PEL forever
--if (tonumber(redis.call('XPENDING', stream, group)[1]) or 0) >= max_concurrency then
    --return nil
--end

-- Rate limits are implemented by adding each grabbed task to a set of rate limiters, with a TTL
-- Calculated by the rate limit pool capacity and the replenish rate
-- If the rate limiter set is full, we can't take any more jobs
--if (tonumber(redis.call('SCARD', rate_limiters)) or 0) >= rate_limit_pool_capacity then
    --return nil
--end

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
--end)
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


class RedisQueue(Queue):
    """
    Single-topic queue on Redis using LPOP and RPUSH
    """

    client: redis.Redis
    key: str

    def __init__(self, client: redis.Redis, key: str):
        """
        Bring your own sync Redis client.

        The redis client must be initialized with `decode=True`.
        """
        self.client = client
        self.key = key

    def put(self, message: str):
        self.client.rpush(self.key, message)

    def get_message(self) -> Message:
        # This is not an async client
        ret = typing.cast(
            list[Any], self.client.blpop([self.key], self.recv_block_secs)
        )
        if not ret:
            raise QueueIsEmpty

        if not len(ret) >= 2:
            raise Exception(f"Unexpected length of return value from BLPOP: {len(ret)}")
        return Message(ret[1], "")

    def get_message_async(self):
        # TODO: This is a blocking operation right now
        return self.get_message()

    def delete_message(self, receipt_handle: str):
        pass

    def set_message_timeout(self, receipt_handle: str):
        pass

    def get_info(self):
        # TODO untested
        return QueueInfo(
            num_messages=self.client.llen(self.key),
            num_inflight_messages=0,
        )


class RedisStream(RichQueue):
    client: redis.Redis

    queue: str
    group = "workers"

    rate_limit_pool_capacity = 100
    replenish_rate_per_second = 10
    max_concurrency = 2
    job_timeout_ms = 1000

    consumer = "TODO_WORKER_ID"
    lib_name = "brrr"
    func_name = "dequeue"

    def __init__(self, client: redis.Redis, queue: str):
        self.client = client
        self.queue = queue

    def clear(self):
        self.client.delete(self.queue)
        self.client.delete(self.queue + ":rate_limiters")

    def setup(self):
        try:
            self.client.xgroup_create(self.queue, self.group, id="0", mkstream=True)
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

    def put(self, body: str):
        # Messages can not be added to specific groups, so we just create a stream per topic
        self.client.xadd(self.queue, {"body": body})

    def get_message(self) -> Message:
        keys = (self.queue,)
        argv = (
            self.group,
            self.consumer,
            self.rate_limit_pool_capacity,
            self.replenish_rate_per_second,
            self.max_concurrency,
            self.job_timeout_ms,
        )
        response = self.client.eval(DEQUEUE_FUNCTION, len(keys), *keys, *argv)
        if not response:
            # TODO: Do not wait indiscriminately but simulate blpop.  How do you
            # do that with a script?
            time.sleep(1)
            raise QueueIsEmpty
        body, receipt_handle = response[:2]
        return Message(body, receipt_handle)

    def get_message_async(self):
        # TODO: This is a blocking operation right now
        return self.get_message()

    # TODO: This has a bug; xack does not remove the message from the stream
    def delete_message(self, receipt_handle: str):
        # The receipt handle here must match the message ID
        # self.client.xack(self.queue, self.group, receipt_handle)
        keys = (self.queue,)
        argv = (
            self.group,
            receipt_handle,
        )
        self.client.eval(ACK_FUNCTION, len(keys), *keys, *argv)

    def set_message_timeout(self, receipt_handle: str, seconds: int):
        # The seconds don't do anything for now; I wasn't sure how to translate a fixed timeout to the Redis model
        # At least this resets the idle time @jkz
        self.client.xclaim(
            self.queue,
            self.group,
            self.consumer,
            min_idle_time=0,
            message_ids=[receipt_handle],
        )

    def get_info(self):
        return QueueInfo(
            num_messages=self.client.xlen(self.queue),
            num_inflight_messages=self.client.xpending(self.queue, self.group)[
                "pending"
            ],
        )


class RedisMemStore(Store):
    client: redis.Redis

    def __init__(self, client: redis.Redis):
        self.client = client

    def key(self, key: MemKey) -> str:
        return f"{key.type}:{key.id}"

    def __getitem__(self, key: MemKey) -> bytes:
        value = self.client.get(self.key(key))
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: bytes):
        self.client.set(self.key(key), value)

    def __delitem__(self, key: str):
        self.client.delete(self.key(key))

    def __contains__(self, key: str) -> bool:
        return self.client.exists(self.key(key)) == 1

    def compare_and_set(self, key: str, value: bytes, expected: bytes):
        keys = (self.key(key),)
        argv = (
            value,
            expected,
        )
        if not self.client.eval(COMPARE_AND_SET_SCRIPT, len(keys), *keys, *argv):
            raise CompareMismatch

    def compare_and_delete(self, key: str, expected: bytes):
        keys = (self.key(key),)
        argv = (expected,)
        if not self.client.eval(COMPARE_AND_DELETE_SCRIPT, len(keys), *keys, *argv):
            raise CompareMismatch
