from typing import Any
import pickle
import sys
import json
from dataclasses import dataclass
from hashlib import sha256
import asyncio
from queue import Queue

import boto3

# Takes a number of task lambdas and calls each of them.
# If they've all been computed, return their values,
# Otherwise raise jobs for those that haven't been computed
def gather(*task_lambdas):
    defer = Call.Defer([])
    values = []
    for task in task_lambdas:
        try:
            values.append(task())
        except Call.Defer as d:
            print("DEFER", d)
            defer.calls.extend(d.calls)
    if defer.calls:
        raise defer
    return values


def input_hash(*args):
    # return ":".join(map(repr, args))
    return sha256(":".join(map(str, args)).encode()).hexdigest()

class PickleJar:
    def __init__(self):
        self.pickles = {}

    def __contains__(self, key):
        return key in self.pickles

    def __getitem__(self, key):
        return pickle.loads(self.pickles[key])

    def __setitem__(self, key, value):
        self.pickles[key] = pickle.dumps(value)

# A queue of frame keys to be processed
queue = Queue()

# A store of task frame contexts. A frame looks something like:
#
#   memo_key: A hash of the task and its arguments
#   children: A dictionary of child tasks keys, with a bool indicating whether they have been computed (This could be a set)
#   parent: The caller's frame_key
#
# In the real world, this would be some sort of distributed store,
# optimised for specific access patterns
frames = {}

# A memoization cache for tasks that have already been computed, based on their task name and input arguments
memos = PickleJar()

# Using the same memo key, we store the task and its argv here so we can retrieve them in workers
calls = PickleJar()


class Task:
    """
    A decorator to turn a function into a task.
    When it is called, it checks whether it has already been computed.
    If so, it returns the value, otherwise it raises a Call job

    A task can not write to the store, only read from it
    """
    _tasks: dict[str, 'Task'] = {}

    fn: Any
    def __init__(self, fn):
        self.fn = fn
        self._tasks[fn.__name__] = self

    def __str__(self):
        return f"{self.fn.__name__}()"

    def __repr__(self):
        return f"Task({self.fn.__name__})"

    @classmethod
    def from_name(cls, name):
        return cls._tasks[name]

    def to_name(self):
        return self.fn.__name__

    # @property
    # def context(self):
    #     return context[threading.get_ident()]

    # Calling a function returns the value if it has already been computed.
    # Otherwise, it raises a Call exception to schedule the computation
    def __call__(self, *args, **kwargs):
        print("Calling", self.fn.__name__, kwargs)
        key = self.memo_key((args, kwargs))
        if key not in memos:
            raise Call.Defer([Call(self, (args, kwargs))])
        return memos[key]

    def to_lambda(self, *args, **kwargs):
        """
        Is a separate function to capture a closure
        """
        return lambda: self(*args, **kwargs)

    # Fanning out, a map function returns the values if they have already been computed.
    # Otherwise, it raises a list of Call exceptions to schedule the computation,
    # for the ones that aren't already computed
    def map(self, args):
        print("MAP", args)
        return gather(*(self.to_lambda(**arg) for arg in args))

    def resolve(self, argv):
        return self.fn(*argv[0], **argv[1])

    # Some deterministic hash of a task and its arguments
    def memo_key(self, argv):
        """A deterministic hash of a task and its arguments"""
        return input_hash(self.to_name(), argv)

task = Task

class Frame:
    """
    A frame represents a function call with a parent and a number of child frames
    """
    memo_key: str
    children: dict
    parent_key: str

    def __repr__(self):
        return f"Frame({self.memo_key}, {self.children}, {self.parent_key})"

    def __init__(self, memo_key, parent_key):
        self.memo_key = memo_key
        self.children = {}
        self.parent_key = parent_key

    # A key is a unique identifier for a task and its arguments
    def resolve(self):
        print("RESOLVE", self)
        name, argv = calls[self.memo_key]
        return Task.from_name(name).resolve(argv)

    @property
    def is_waiting(frame_key):
        return not all(frames[frame_key].children.values())


class Call:
    class Defer(Exception):
        calls: list['Call']
        def __init__(self, calls: list['Call']):
            print("Deferring", calls)
            self.calls = calls

    task: Task
    argv: tuple

    def __repr__(self):
        return f"Call({self.task.fn.__name__}, {json.dumps(self.argv)})"

    def __init__(self, task: Task, argv: tuple[tuple, dict]):
        self.task = task
        self.argv = argv

    @property
    def memo_key(self):
        return self.task.memo_key(self.argv)

    def frame_key(self, parent_key):
        return input_hash(parent_key, self.memo_key)

    def schedule(self, parent_key=None):
        memo_key = self.memo_key
        if memo_key not in calls:
            calls[memo_key] = (self.task.to_name(), self.argv)

        child_key = self.frame_key(parent_key)
        if child_key not in frames:
            frames[child_key] = Frame(memo_key, parent_key)

        if memo_key in memos:
            if parent_key is not None:
                frames[parent_key].children[child_key] = True
                print("💝", child_key)
                queue.put(parent_key)
        else:
            print("🚀", child_key)
            if child_key is not None:
                queue.put(child_key)


def handle_frame(frame_key):
    print("Handle frame", frame_key)
    frame = frames[frame_key]
    try:
        memos[frame.memo_key] = frame.resolve()
        # This is a redundant step, we could just check the store whether the children have memoized values
        if frame.parent_key is not None:
            frames[frame.parent_key].children[frame_key] = True
            queue.put(frame.parent_key)
    except Call.Defer as defer:
        for call in defer.calls:
            call.schedule(frame_key)


class Worker:
    def __init__(self, queue: boto3, kv):
        self.sqs = sqs 
        self.kv = kv

async def worker():
    """
    Workers take jobs from the queue, one at a time, and handles them.
    They have read and write access to the store, and are responsible for
    Managing the output of tasks and scheduling new ones
    """
    print("WORK WORK")
    while not queue.empty():
        # print()
        print()
        print("QUEUE", len(queue.queue))
        # for item in queue.queue:
        #     print("  ", item)
        # print()
        # print()
        print("MEMOS", len(memos.pickles))
        # for key, val in memos.items():
        #     print("  ", key, ":", val, ":", calls[key])
        # print()
        print()


        handle_frame(queue.get())
        await asyncio.sleep(.1)

@task
def fib(n):
    match n:
        case 0: return 0
        case 1: return 1
        case _: return sum(fib.map([{"n": n - 2}, {"n": n - 1}]))

@task
def output(n):
    n = fib(n=n)
    print("output", n)

async def main():
    sqs = boto3.client("sqs")
    kv = boto3.client("dynamo")
    call = Call(output, {"n": 9})
    call.schedule(None)

    await asyncio.gather(
        *(worker() for _ in range(int(sys.argv[1]) if len(sys.argv) > 1 else 3))
    )


if __name__ == "__main__":
    asyncio.run(main())
