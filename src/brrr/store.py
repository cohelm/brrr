from abc import abstractmethod, ABC
from dataclasses import dataclass
from collections import namedtuple
from typing import Any, TypeVar

import pickle

from hashlib import sha256


# Very much WIP: this is the most generic “everything goes” Python way of
# dealing with arguments, but we should either lock this down, or allow the user
# of the library to define this.  Leaving this generic while we figure out the
# actual usage pattern.
Argv = tuple[tuple, dict]


# Objects to be stored

# A memoization cache for tasks that have already been computed, based on their task name and input arguments


# Using the same memo key, we store the task and its argv here so we can retrieve them in workers
@dataclass(frozen=True)
class Call:
    task_name: str
    argv: Argv
    memo_key: str

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
X = TypeVar("X")
Y = TypeVar("Y")


class Store(ABC):
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
    async def get(self, key: MemKey) -> bytes:
        raise NotImplementedError()

    @abstractmethod
    async def set(self, key: MemKey, value: bytes):
        raise NotImplementedError()

    @abstractmethod
    async def delete(self, key: MemKey):
        raise NotImplementedError()

    @abstractmethod
    async def compare_and_set(self, key: MemKey, value: bytes, expected: bytes | None):
        """
        Only set the value, as a transaction, if the existing value matches the expected value
        Or, if expected value is None, if the key does not exist
        """
        raise NotImplementedError()

    @abstractmethod
    async def compare_and_delete(self, key: MemKey, expected: bytes):
        """Delete the value, iff the current value equals the given expected value.

        The expected value CANNOT be None.  If the expected value is None,
        meaning there currently is no value, then don't call this function.

        """
        raise NotImplementedError()


class Codec(ABC):
    """Codec for values that pass around the brrr datastore.

    If you want inter-language calling you'll need to ensure both languages
    can compute this.

    The serializations must be deterministic, whatever that means for you.
    E.g. if you use dictionaries, make sure to order them before serializing.

    For any serious use you want strict control over the types you accept here
    and explicit serialization routines.

    """

    # TODO: This API formalizes an agnostic codec like pickle, but we want to
    # give real codecs more information about the original call so they don’t
    # need to support arbitrary conversions.  Something like decode(type,
    # payload), for example, or multiple separate methods.  Notably, the codec
    # must support encoding some values generated internally by brrr (e.g.: an
    # ascii string for the pending returns), while also supporting “whatever a
    # task can return”.  We currently rely on the same encode/decode calls for
    # both, and pass it custom internal dataclasses (Call, …), so effectively
    # it’s locked in to pickle.  This can be untangled, starting with a better
    # API.

    @abstractmethod
    def encode(self, val: Any) -> bytes:
        raise NotImplementedError()

    @abstractmethod
    def decode(self, b: bytes) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def hash_call(self, task_name: str, argv: Argv) -> str:
        """Compute the memo_key for a Call.

        The output of this function is required for actually _creating_ a Call
        instance.  It's not the cleanest API (you could imagine e.g. a property
        getter on the Call instance) but it does make something very explicit: a
        Call instance is only relevant in the context of a Codec.  This
        dependency is crucial: codecs are the only interface between a store and
        this specific bit of code interacting with it.  Particularly with
        multiple languages it is important that all serialization and
        deserialization is done through the Codec, and computing a memkey from
        the Call description is part of that.

        """
        raise NotImplementedError()


class PickleCodec(Codec):
    """Very liberal codec, based on hopes and dreams.

    Don't use this in production because you run the risk of non-deterministic
    serialization, e.g. dicts with arbitrary order.

    """

    def encode(self, val: Any) -> bytes:
        return pickle.dumps(val)

    def decode(self, b: bytes) -> Any:
        return pickle.loads(b)

    def hash_call(self, task_name: str, argv: Argv) -> str:
        return sha256(":".join(map(str, argv)).encode()).hexdigest()


class Memory:
    """
    A memstore that uses a pickle jar as its backend
    """

    def __init__(self, store: Store, codec: Codec):
        self.store = store
        self.codec = codec

    # This method feels slightly like the plumbing sticking out through the
    # floor but it’s a step in the right direction.  At least it is explicit
    # that Calls only make sense in the context of both a store *and* a codec.
    # This is essential for cross-language functionality.
    def make_call(self, task_name: str, argv: Argv) -> Call:
        """Create a Call instance.

        Defined on the memory because it is inherently tied to the codec.

        """
        return Call(task_name, argv, self.codec.hash_call(task_name, argv))

    async def get_call(self, memo_key: str) -> Call:
        val = self.codec.decode(await self.store.get(MemKey("call", memo_key)))
        assert isinstance(val, Call)
        return val

    async def has_call(self, call: Call):
        return await self.store.has(MemKey("call", call.memo_key))

    async def set_call(self, call: Call):
        if not isinstance(call, Call):
            raise ValueError(f"set_call expected a Call, got {call}")
        await self.store.set(MemKey("call", call.memo_key), self.codec.encode(call))

    async def has_value(self, memo_key: str) -> bool:
        return await self.store.has(MemKey("value", memo_key))

    async def get_value(self, memo_key: str) -> Any:
        return self.codec.decode(await self.store.get(MemKey("value", memo_key)))

    async def set_value(self, memo_key: str, value: Any):
        if value is None:
            raise ValueError("set_value value cannot be None")

        # Only set if the value is not already set
        enc = self.codec.encode(value)
        try:
            await self.store.compare_and_set(MemKey("value", memo_key), enc, None)
        except CompareMismatch:
            # Throwing over passing here; Because of idempotency, we only ever want
            # one value to be set for a given memo_key. If we silently ignored this here,
            # we could end up executing code with the wrong value
            raise AlreadyExists(f"set_value: value already set for {memo_key}")

    async def get_info(self, task_name: str) -> Info:
        val = self.codec.decode(await self.store.get(MemKey("info", task_name)))
        assert isinstance(val, Info)
        return val

    async def set_info(self, task_name: str, value: Info):
        await self.store.set(MemKey("info", task_name), self.codec.encode(value))

    async def get_pending_returns(self, memo_key: str) -> set[str]:
        val = self.codec.decode(
            await self.store.get(MemKey("pending_returns", memo_key))
        )
        val = set(val.split(","))
        assert isinstance(val, set) and all(isinstance(x, str) for x in val)
        return val

    def _encode_returns(self, returns: set[str]) -> bytes:
        # TODO ehhh, used sets before, but they don't always hash to the same value.
        # could use lists and keep them sorted and is a safe compare across implementations.
        # This hack gets us to v1
        return self.codec.encode(",".join(sorted(returns)))

    async def add_pending_returns(self, memo_key: str, updated_keys: set[str]):
        if any(not isinstance(k, str) for k in updated_keys):
            raise ValueError("add_pending_returns: all keys must be strings")

        i = 0
        while True:
            try:
                existing_keys = await self.get_pending_returns(memo_key)
            except KeyError:
                existing_keys = None
                keys_to_match = None
            else:
                updated_keys |= existing_keys
                keys_to_match = self._encode_returns(existing_keys)

            keys_to_set = self._encode_returns(updated_keys)
            try:
                await self.store.compare_and_set(
                    MemKey("pending_returns", memo_key), keys_to_set, keys_to_match
                )
            except CompareMismatch as e:
                i += 1
                if i > 100:
                    # Very ad-hoc.  This should never be encountered, but let’s
                    # at least set _some_ kind of error message here so someone
                    # could debug this, if it ever happens.  It almost certainly
                    # indicates an issue in the underlying store’s
                    # compare_and_set implementation.
                    raise Exception(
                        f"exceeded CAS misses for pending returns on {memo_key}"
                    ) from e
                continue
            else:
                return

    async def delete_pending_returns(self, memo_key: str, existing_keys: set[str]):
        if existing_keys is None:
            # Multiplexing ‘None’ as a missing value was a mistake to begin
            # with, let’s make sure it doesn’t bleed where it isn’t supposed to.
            raise ValueError("cannot CAS delete a missing value")
        await self.store.compare_and_delete(
            MemKey("pending_returns", memo_key), self._encode_returns(existing_keys)
        )
