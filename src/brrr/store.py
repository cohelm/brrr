from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TypeVar
from collections import namedtuple

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

class CompareMismatch(Exception): ...

T = TypeVar("T")

class Store[T](ABC):
    """
    A key-value store with a dict-like interface.
    This expresses the requirements for a store to be suitable as a Memory backend.

    All mutate operations MUST be idempotent
    All getters MUST throw a KeyError for missing keys
    """
    @abstractmethod
    def __contains__(self, key: MemKey) -> bool: ...
    @abstractmethod
    def __getitem__(self, key: MemKey) -> T: ...
    @abstractmethod
    def __setitem__(self, key: MemKey, value: T): ...
    @abstractmethod
    def __delitem__(self, key: MemKey): ...
    @abstractmethod
    def compare_and_set(self, key: MemKey, value: T, expected: T | None):
        """
        Only set the value, as a transaction, if the existing value matches the expected value
        Or, if expected value is None, if the key does not exist
        """
        ...
    @abstractmethod
    def compare_and_delete(self, key: MemKey, expected: T):
        """
        Only delete the value, as a transaction, if the existing value matches the expected value
        This is a noop if the expected value is None. While we could allow it, we've chosen not to,
        to remind the author that they're trying to delete a key that they know doesn't exist,
        which sounds like a bug.
        """
        ...

class PickleJar(Store[Any]):
    """
    A dict-like object that pickles on set and unpickles on get
    """
    pickles: Store[bytes]

    def __init__(self, store: Store):
        self.pickles = store

    def __contains__(self, key: MemKey):
        return key in self.pickles

    def __getitem__(self, key: MemKey):
        return pickle.loads(self.pickles[key])

    def __setitem__(self, key: MemKey, value):
        self.pickles[key] = pickle.dumps(value)

    def __delitem__(self, key: MemKey, value):
        del self.pickles[key]

    # BEWARE `None` has special semantics here. None means "expect key to be missing"
    # which means we never pickle the value `None`. TBD whether we want to support
    # these semantics, or instead use a "Optional" value wrapper

    # Throw CompareMismatch if the expected value does not match the actual value
    def compare_and_set(self, key: MemKey, value: Any, expected: Any | None):
        assert value is not None, "Value cannot be None"
        self.pickles.compare_and_set(key, pickle.dumps(value), None if expected is None else pickle.dumps(expected))

    # Throw CompareMismatch if the expected value does not match the actual value
    def compare_and_delete(self, key: MemKey, expected: Any):
        self.pickles.compare_and_delete(key, None if expected is None else pickle.dumps(expected))

class Memory:
    """
    A memstore that uses a PickleJar as its backend
    """
    def __init__(self, store: Store):
        self.pickles = PickleJar(store)

    def get_call(self, memo_key: str) -> Call:
        val = self.pickles[MemKey("call", memo_key)]
        assert isinstance(val, Call)
        return val

    def has_call(self, call: Call):
        return MemKey("call", call.memo_key) in self.pickles

    def set_call(self, call: Call):
        self.pickles[MemKey("call", call.memo_key)] = call

    def has_value(self, memo_key: str) -> bool:
        return MemKey("value", memo_key) in self.pickles

    def get_value(self, memo_key: str) -> Any:
        return self.pickles[MemKey("value", memo_key)]

    def set_value(self, memo_key: str, value: Any):
        # Only set if the value is not already set
        try:
            self.pickles.compare_and_set(MemKey("value", memo_key), value, None)
        except CompareMismatch:
            pass

    def get_info(self, task_name: str) -> Info:
        val = self.pickles[MemKey("info", task_name)]
        assert isinstance(val, Info)
        return val

    def set_info(self, task_name: str, value: Info):
        self.pickles[MemKey("info", task_name)] = value

    def get_pending_returns(self, memo_key: str) -> set[str]:
        val = self.pickles[MemKey("pending_returns", memo_key)]
        val = set(val.split(","))
        assert isinstance(val, set) and all(isinstance(x, str) for x in val)
        return val

    def add_pending_returns(self, memo_key: str, updated_keys: set[str]):
        # TODO is there a number of retries we should throw for?
        count = 0
        while True:
            try:
                existing_keys = self.get_pending_returns(memo_key)
            except KeyError:
                existing_keys = None
            else:
                updated_keys |= existing_keys

            try:
                keys_to_set = ",".join(sorted(updated_keys))
                existing_keys = None if existing_keys is None else ",".join(sorted(existing_keys))
                self.pickles.compare_and_set(MemKey("pending_returns", memo_key), keys_to_set, existing_keys)
            except CompareMismatch:
                count += 1
                continue
            else:
                return

    def set_pending_returns(self, memo_key: str, updated_keys: set[str], existing_keys: set[str] | None):
        updated_keys = ",".join(sorted(updated_keys))
        existing_keys = ",".join(sorted(existing_keys))
        self.pickles.compare_and_set(MemKey("pending_returns", memo_key), updated_keys, existing_keys)

    def delete_pending_returns(self, memo_key: str, existing_keys: set[str] | None):
        existing_keys = None if existing_keys is None else ",".join(sorted(existing_keys))
        self.pickles.compare_and_delete(MemKey("pending_returns", memo_key), existing_keys)

    # This has become quite puzzling; call graphs are no longer flat,
    # but a child can have many parents, and they are only stored while pending.
    def get_stack_trace(self, frame_key: str) -> list[Call]:
        frames = []
        while frame_key:
            frame = self.get_frame(frame_key)
            frames.append(frame)
            frame_key = frame.parent_key
        return frames
