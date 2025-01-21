from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from collections import namedtuple
from typing import Any, TypeVar

import pickle

from hashlib import sha256


def input_hash(*args):
    return sha256(":".join(map(str, args)).encode()).hexdigest()


# Objects to be stored

# A memoization cache for tasks that have already been computed, based on their task name and input arguments


# Using the same memo key, we store the task and its argv here so we can retrieve them in workers
@dataclass(frozen=True)
class Call:
    task_name: str
    argv: tuple[tuple, dict]
    memo_key: str = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "memo_key", input_hash(self.task_name, self.argv))

    def __eq__(self, other):
        return isinstance(other, Call) and self.memo_key == other.memo_key


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


class AlreadyExists(Exception): ...


T = TypeVar("T")


# TODO: Use custom error rather than KeyError as part of contract.
class Store[T](ABC):
    """
    A key-value store with a dict-like interface.
    This expresses the requirements for a store to be suitable as a Memory backend.

    All mutate operations MUST be idempotent
    All getters MUST throw a KeyError for missing keys
    """

    @abstractmethod
    async def has(self, key: MemKey) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def get(self, key: MemKey) -> T:
        raise NotImplementedError()

    @abstractmethod
    async def set(self, key: MemKey, value: T):
        raise NotImplementedError()

    @abstractmethod
    async def delete(self, key: MemKey):
        raise NotImplementedError()

    @abstractmethod
    async def compare_and_set(self, key: MemKey, value: T, expected: T | None):
        """
        Only set the value, as a transaction, if the existing value matches the expected value
        Or, if expected value is None, if the key does not exist
        """
        raise NotImplementedError()

    @abstractmethod
    async def compare_and_delete(self, key: MemKey, expected: T):
        """
        Only delete the value, as a transaction, if the existing value matches the expected value
        This is a noop if the expected value is None. While we could allow it, we've chosen not to,
        to remind the author that they're trying to delete a key that they know doesn't exist,
        which sounds like a bug.
        """
        raise NotImplementedError()


class PickleJar(Store[Any]):
    """
    A dict-like object that pickles on set and unpickles on get
    """

    pickles: Store[bytes]

    def __init__(self, store: Store):
        self.pickles = store

    async def has(self, key: MemKey):
        return await self.pickles.has(key)

    async def get(self, key: MemKey):
        return pickle.loads(await self.pickles.get(key))

    async def set(self, key: MemKey, value):
        await self.pickles.set(key, pickle.dumps(value))

    async def delete(self, key: MemKey):
        await self.pickles.delete(key)

    # BEWARE `None` has special semantics here. None means "expect key to be missing"
    # which means we never pickle the value `None`. TBD whether we want to support
    # these semantics, or instead use a "Optional" value wrapper

    # Throw CompareMismatch if the expected value does not match the actual value
    async def compare_and_set(self, key: MemKey, value: Any, expected: Any | None):
        assert value is not None, "Value cannot be None"
        await self.pickles.compare_and_set(
            key,
            pickle.dumps(value),
            None if expected is None else pickle.dumps(expected),
        )

    # Throw CompareMismatch if the expected value does not match the actual value
    async def compare_and_delete(self, key: MemKey, expected: Any):
        await self.pickles.compare_and_delete(
            key, None if expected is None else pickle.dumps(expected)
        )


class Memory:
    """
    A memstore that uses a PickleJar as its backend
    """

    def __init__(self, store: Store):
        self.pickles = PickleJar(store)

    async def get_call(self, memo_key: str) -> Call:
        val = await self.pickles.get(MemKey("call", memo_key))
        assert isinstance(val, Call)
        return val

    async def has_call(self, call: Call):
        return await self.pickles.has(MemKey("call", call.memo_key))

    async def set_call(self, call: Call):
        if not isinstance(call, Call):
            raise ValueError(f"set_call expected a Call, got {call}")
        await self.pickles.set(MemKey("call", call.memo_key), call)

    async def has_value(self, memo_key: str) -> bool:
        return await self.pickles.has(MemKey("value", memo_key))

    async def get_value(self, memo_key: str) -> Any:
        return await self.pickles.get(MemKey("value", memo_key))

    async def set_value(self, memo_key: str, value: Any):
        if value is None:
            raise ValueError("set_value value cannot be None")

        # Only set if the value is not already set
        try:
            await self.pickles.compare_and_set(MemKey("value", memo_key), value, None)
        except CompareMismatch:
            # Throwing over passing here; Because of idempotency, we only ever want
            # one value to be set for a given memo_key. If we silently ignored this here,
            # we could end up executing code with the wrong value
            raise AlreadyExists(f"set_value: value already set for {memo_key}")

    async def get_info(self, task_name: str) -> Info:
        val = await self.pickles.get(MemKey("info", task_name))
        assert isinstance(val, Info)
        return val

    async def set_info(self, task_name: str, value: Info):
        await self.pickles.set(MemKey("info", task_name), value)

    async def get_pending_returns(self, memo_key: str) -> set[str]:
        val = await self.pickles.get(MemKey("pending_returns", memo_key))
        val = set(val.split(","))
        assert isinstance(val, set) and all(isinstance(x, str) for x in val)
        return val

    async def add_pending_returns(self, memo_key: str, updated_keys: set[str]):
        if any(not isinstance(k, str) for k in updated_keys):
            raise ValueError("add_pending_returns: all keys must be strings")

        # TODO is there a number of retries we should throw for?
        while True:
            try:
                existing_keys = await self.get_pending_returns(memo_key)
            except KeyError:
                existing_keys = None
            else:
                updated_keys |= existing_keys

            try:
                # TODO ehhh, used sets before, but they don't always hash to the same value.
                # could use lists and keep them sorted and is a safe compare across implementations.
                # This hack gets us to v1
                keys_to_set = ",".join(sorted(updated_keys))
                keys_to_match = (
                    None if existing_keys is None else ",".join(sorted(existing_keys))
                )
                await self.pickles.compare_and_set(
                    MemKey("pending_returns", memo_key), keys_to_set, keys_to_match
                )
            except CompareMismatch:
                continue
            else:
                return

    async def delete_pending_returns(
        self, memo_key: str, existing_keys: set[str] | None
    ):
        existing_keys = (
            None if existing_keys is None else ",".join(sorted(existing_keys))
        )
        await self.pickles.compare_and_delete(
            MemKey("pending_returns", memo_key), existing_keys
        )
