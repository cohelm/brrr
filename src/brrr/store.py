from dataclasses import dataclass
from typing import Any
from collections import namedtuple
from collections.abc import MutableMapping

import pickle

from hashlib import sha256

def input_hash(*args):
    return sha256(":".join(map(str, args)).encode()).hexdigest()


# Objects to be stored

# A memoization cache for tasks that have already been computed, based on their task name and input arguments

# Using the same memo key, we store the task and its argv here so we can retrieve them in workers
@dataclass
class Call:
    task_name: str
    argv: tuple[tuple, dict]

    @property
    def memo_key(self):
        return input_hash(self.task_name, self.argv)


# A store of task frame contexts. A frame looks something like:
#
#   memo_key: A hash of the task and its arguments
#   children: A dictionary of child tasks keys, with a bool indicating whether they have been computed (This could be a set)
#   parent: The caller's frame_key
#
# In the real world, this would be some sort of distributed store,
# optimised for specific access patterns
@dataclass
class Frame:
    """
    A frame represents a function call with a parent and a number of child frames
    """
    memo_key: str
    # The empty string means no parent
    parent_key: str
    # This one is redundant
    # children: dict

    @property
    def frame_key(self):
        return input_hash(self.parent_key, self.memo_key)



@dataclass
class Info:
    """
    Optional information about a task.
    Does not affect the computation, but may instruct orchestration
    """
    description: str | None
    timeout_seconds: int | None
    retries: int | None
    retry_delay_seconds: int | None
    log_prints: bool | None


MemKey = namedtuple("MemKey", ["type", "id"])

# All operations MUST be idempotent
# All getters MUST throw a KeyError for missing keys
Store = MutableMapping[MemKey, bytes]

class PickleJar:
    """
    A dict-like object that pickles on set and unpickles on get
    """
    pickles: MutableMapping[MemKey, bytes]

    def __init__(self, store: Store):
        self.pickles = store

    def __contains__(self, key: MemKey):
        return key in self.pickles

    def __getitem__(self, key: MemKey):
        return pickle.loads(self.pickles[key])

    def __setitem__(self, key: MemKey, value):
        self.pickles[key] = pickle.dumps(value)


class Memory:
    """
    A memstore that uses a PickleJar as its backend
    """
    def __init__(self, store: Store):
        self.pickles = PickleJar(store)

    def get_frame(self, frame_key: str) -> Frame:
        return self.pickles[MemKey("frame", frame_key)]

    def set_frame(self, frame: Frame):
        self.pickles[MemKey("frame", frame.frame_key)] = frame

    def get_call(self, memo_key: str) -> Call:
        return self.pickles[MemKey("call", memo_key)]

    def set_call(self, call: Call):
        self.pickles[MemKey("call", call.memo_key)] = call

    def has_value(self, memo_key: str) -> bool:
        return MemKey("value", memo_key) in self.pickles

    def get_value(self, memo_key: str) -> Any:
        return self.pickles[MemKey("value", memo_key)]

    def set_value(self, memo_key: str, value: Any):
        self.pickles[MemKey("value", memo_key)] = value

    def get_info(self, task_name: str) -> Info:
        return self.pickles[MemKey("info", task_name)]

    def set_info(self, task_name: str, value: Info):
        self.pickles[MemKey("info", task_name)] = value

    def get_stack_trace(self, frame_key: str) -> list[Frame]:
        frames = []
        while frame_key:
            frame = self.get_frame(frame_key)
            frames.append(frame)
            frame_key = frame.parent_key
        return frames
