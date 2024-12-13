#!/usr/bin/env python3

import os
import sys
from typing import Iterable
import time

import boto3
import redis

from brrr.backends import redis as redis_, dynamo
import brrr
from brrr import task, wrrrk, setup, brrr
from contrib.srrrver import Srrrver

def init_brrr(reset_backends):
    # Check credentials
    boto3.client('sts').get_caller_identity()

    redis_client = redis.Redis(decode_responses=True)
    queue = redis_.RedisStream(redis_client, os.environ.get("REDIS_QUEUE_KEY", "r1"))
    if reset_backends:
        queue.setup()

    dynamo_client = boto3.client("dynamodb")
    store = dynamo.DynamoDbMemStore(dynamo_client, os.environ.get("DYNAMODB_TABLE_NAME", "brrr"))
    if reset_backends:
        store.create_table()

    setup(queue, store)

@task
def fib(n: int, salt=None):
    match n:
        case 0: return 0
        case 1: return 1
        case _: return sum(fib.map([[n - 2, salt], [n - 1, salt]]))

@task
def fib_and_print(n: str, salt = None):
    f = fib(int(n), salt)
    print(f"fib({n}) = {f}", flush=True)
    return f

@task
def hello(greetee: str):
    greeting = f"Hello, {greetee}!"
    print(greeting, flush=True)
    return greeting

cmds = {}
def cmd(f):
    cmds[f.__name__] = f
    return f

@cmd
def worker():
    init_brrr(False)
    wrrrk(1)

@cmd
def server():
    init_brrr(True)
    Srrrver.srrrv(brrr)

def args2dict(args: Iterable[str]) -> dict[str, str]:
    """
    Extremely rudimentary arbitrary argparser.

    args2dict(["--foo", "bar", "--zim", "zom"])
    => {"foo": "bar", "zim": "zom"}

    """
    it = iter(args)
    return {k.lstrip('-'): v for k, v in zip(it, it)}

@cmd
def schedule(job: str, *args: str):
    """
    Put a single job onto the queue
    """
    init_brrr(False)
    brrr.schedule(job, (), args2dict(args))

@cmd
def monitor():
    init_brrr(False)
    redis_client = redis.Redis()
    queue = redis_.RedisStream(redis_client, os.environ.get("REDIS_QUEUE_KEY", "r1"))
    while True:
        print(queue.get_info())
        time.sleep(1)

@cmd
def reset():
    table_name = os.environ.get("DYNAMODB_TABLE_NAME", "brrr")
    dynamo_client = boto3.client("dynamodb")
    try:
        dynamo_client.delete_table(TableName=table_name)
    except Exception as e:
        # Table does not exist
        if "ResourceNotFoundException" not in str(e):
            raise

    redis_client = redis.Redis()
    redis_client.flushall()
    init_brrr(True)

def main():
    f = cmds.get(sys.argv[1]) if len(sys.argv) > 1 else None
    if f:
        f(*sys.argv[2:])
    else:
        print(f"Usage: brrr_demo.py <{" | ".join(cmds.keys())}>")
        sys.exit(1)

if __name__ == "__main__":
    main()
