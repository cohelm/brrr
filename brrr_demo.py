#!/usr/bin/env python3

import os
import sys

import redis
import boto3

from brrr.backends import redis as redis_, dynamo
from brrr import task, wrrrk, srrrv, setup

def init_brrr(reset_backends):
    # Check credentials
    boto3.client('sts').get_caller_identity()

    redis_client = redis.Redis(decode_responses=True)
    queue = redis_.RedisQueue(redis_client, os.environ.get("REDIS_QUEUE_KEY", "r1"))

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
    srrrv([hello, fib, fib_and_print])

def main():
    f = cmds.get(sys.argv[1]) if len(sys.argv) > 1 else None
    if f:
        f()
    else:
        print(f"Usage: brrr_demo.py <{" | ".join(cmds.keys())}>")
        sys.exit(1)

if __name__ == "__main__":
    main()
