#!/usr/bin/env python3

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import json
import os
from pprint import pprint
import sys
from typing import Iterable

import aioboto3
from aiohttp import web
from redis.asyncio import Redis
from types_aiobotocore_dynamodb import DynamoDBClient

from brrr.backends.redis import RedisStream
from brrr.backends.dynamo import DynamoDbMemStore
import brrr
from brrr import task

routes = web.RouteTableDef()

def table_name() -> str:
    """
    Get table name from environment
    """
    return os.environ.get("DYNAMODB_TABLE_NAME", "brrr")


def response(status: int, content: dict):
    return web.Response(status=status, text=json.dumps(content))


@routes.get("/{task_name}")
async def get_task_result(request: web.BaseRequest):
    # aiohttp uses a multidict but we don’t need that for this demo.
    kwargs = dict(request.query)

    task_name = request.match_info["task_name"]
    if task_name not in brrr.tasks:
        return response(404, {"error": "No such task"})

    try:
        result = await brrr.read(task_name, (), kwargs)
    except KeyError:
        return response(404, dict(error="No result for this task"))
    return response(200, dict(status="ok", result=result))


@routes.post("/{task_name}")
async def schedule_task(request: web.BaseRequest):
    kwargs = dict(request.query)

    task_name = request.match_info["task_name"]
    if task_name not in brrr.tasks:
        return response(404, {"error": "No such task"})

    await brrr.schedule(task_name, (), kwargs)
    return response(202, {"status": "accepted"})


# ... where is the python contextmanager monad?


@asynccontextmanager
async def with_resources() -> AsyncIterator[tuple[Redis, DynamoDBClient]]:
    session = aioboto3.Session()
    async with session.client("dynamodb") as dync:
        dync: DynamoDBClient
        rc = Redis(decode_responses=True)
        try:
            yield (rc, dync)
        finally:
            await rc.aclose()


@asynccontextmanager
async def with_brrr_wrap() -> AsyncIterator[tuple[RedisStream, DynamoDbMemStore]]:
    async with with_resources() as (rc, dync):
        store = DynamoDbMemStore(dync, table_name())
        queue = RedisStream(rc, os.environ.get("REDIS_QUEUE_KEY", "r1"))
        yield (queue, store)


@asynccontextmanager
async def with_brrr(reset_backends):
    async with with_brrr_wrap() as (queue, store):
        if reset_backends:
            await queue.setup()
            await store.create_table()
        brrr.setup(queue, store)
        yield


@task
async def fib(n: int, salt=None):
    match n:
        case 0 | 1:
            return n
        case _:
            return sum(await fib.map([[n - 2, salt], [n - 1, salt]]))


@task
async def fib_and_print(n: str, salt=None):
    f = await fib(int(n), salt)
    print(f"fib({n}) = {f}", flush=True)
    return f


@task
async def hello(greetee: str):
    greeting = f"Hello, {greetee}!"
    print(greeting, flush=True)
    return greeting


cmds = {}


def cmd(f):
    cmds[f.__name__] = f
    return f


@cmd
async def worker():
    async with with_brrr(False):
        await brrr.wrrrk()


@cmd
async def server():
    async with with_brrr(True):
        app = web.Application()
        app.add_routes(routes)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", 8080)
        await site.start()
        print("Listening on http://localhost:8080")
        await asyncio.Event().wait()

def args2dict(args: Iterable[str]) -> dict[str, str]:
    """
    Extremely rudimentary arbitrary argparser.

    args2dict(["--foo", "bar", "--zim", "zom"])
    => {"foo": "bar", "zim": "zom"}

    """
    it = iter(args)
    return {k.lstrip("-"): v for k, v in zip(it, it)}


@cmd
async def schedule(job: str, *args: str):
    """
    Put a single job onto the queue
    """
    async with with_brrr(False):
        await brrr.schedule(job, (), args2dict(args))


@cmd
async def monitor():
    async with with_brrr_wrap() as (queue, _):
        while True:
            pprint(await queue.get_info())
            await asyncio.sleep(1)


@cmd
async def reset():
    async with with_resources() as (rc, dync):
        try:
            await dync.delete_table(TableName=table_name())
        except Exception as e:
            # Table does not exist
            if "ResourceNotFoundException" not in str(e):
                raise

        await rc.flushall()


async def amain():
    f = cmds.get(sys.argv[1]) if len(sys.argv) > 1 else None
    if f:
        await f(*sys.argv[2:])
    else:
        print(f"Usage: brrr_demo.py <{" | ".join(cmds.keys())}>")
        sys.exit(1)


def main():
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
