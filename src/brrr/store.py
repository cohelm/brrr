from __future__ import annotations

from abc import abstractmethod, ABC
from collections.abc import AsyncIterator, Awaitable, Callable
from collections import namedtuple
from contextlib import asynccontextmanager
from dataclasses import dataclass
import hashlib
import json
import logging
import pickle
import time
from typing import Any, TypeVar


logger = logging.getLogger(__name__)

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

    def __str__(self):
        args = [repr(x) for x in self.argv[0]]
        kwargs = ["=".join(x) for x in self.argv[1].items()]
        return f"Call({self.task_name}({', '.join(args + kwargs)}))"


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


@dataclass
class PendingReturns:
    """Set of parents waiting for a child call to complete.

    When the child call is scheduled, a timestamp is added to this record to
    indicate it doesn't need to be rescheduled.  If the record exists but with a
    null scheduled timestamp, you cannot be sure this child has ever actually
    been scheduled, so it should be rescheduled.

    This record is used in highly race sensitive context and is the point of a
    lot of CASing.

    """

    # Unix time, in seconds.  Purposefully coarse to drive home that this value
    # is not meant for synchronization, only for measuring age.  Don’t use this
    # to determine which pending return record was written later than another or
    # any such event serialization where order matters.  This is for expiring
    # entries in a stale cache, that’s all.
    scheduled_at: int | None
    returns: set[str]

    # For some reason I’m annoyed that this uses JSON internally but it really
    # is the most pragmatic choice here.  I so wished we could have used some
    # cool prefix-length-encoded format but the reality is we need nesting,
    # lists, ints, optional null values, etc—aka json.  🙁 As long as it’s not a
    # dictionary I can live with it.

    def encode(self) -> bytes:
        return json.dumps([self.scheduled_at, list(sorted(self.returns))]).encode(
            "utf-8"
        )

    @classmethod
    def decode(cls, enc: bytes) -> PendingReturns:
        time, returns = json.loads(enc.decode("utf-8"))
        return PendingReturns(time, set(returns))


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
    async def set_new_value(self, key: MemKey, value: bytes):
        """Set a fresh value, throwing if any value already exists."""
        raise NotImplementedError()

    @abstractmethod
    async def compare_and_set(self, key: MemKey, value: bytes, expected: bytes):
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


class Cache(ABC):
    """A best-effort store for light-weight, non-critical data.

    Values in this cache are allowed, even encouraged to expire within a few
    minutes time.  They don't need to be consistent across nodes, there is no
    requirement for read-after-write nor even write-after-write consistency.
    It's all best effort and the worst case consequence of returning invalid
    data to brrr is just that more duplicated work might happen.  No correctness
    guarantees would be violated by brrr if this cache returns incorrect /
    incomplete / out-of-date data.

    Basically a formalization of the subset of Redis which we use.

    This is technically a "store" and it could be implemented by the exact same
    class which implements the Store interface.  It has only been separated out
    because it could be nice to implement this separately.  Concretely, it makes
    sense to use Dynamo for the store, and Redis for the cache, but do what you
    want.

    Note the required guarantees on this interface are very lax, both in
    persistence and immediately, i.e. it's ok to return speculative responses.

    It's undefined what happens if the keys for these elements are shared
    between cache, memory and/or queue.  It's probably worth being explicit
    about it at some point.

    """

    @abstractmethod
    async def incr(self, k: str) -> int:
        """Increase by 1 and return the new value.

        In reality this is used for spawn limit tracking but 🤫 that's an
        implementation detail.

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
        h = hashlib.new("sha256")
        h.update(repr([task_name, argv[0], list(sorted(argv[1].items()))]).encode())
        return h.hexdigest()


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
            await self.store.set_new_value(MemKey("value", memo_key), enc)
        except CompareMismatch:
            # Throwing over passing here; Because of idempotency, we only ever want
            # one value to be set for a given memo_key. If we silently ignored this here,
            # we could end up executing code with the wrong value
            raise AlreadyExists(f"set_value: value already set for {memo_key}")

    @asynccontextmanager
    async def _with_cas(self) -> AsyncIterator:
        """Wrap a CAS exception generating body.

        This abstracts the retry nature of a CAS gated operation.  The with
        block will be retried as long as it keeps throwing CompareMismatch
        exceptions.  Once it completes without throwing that, this with block
        will exit.  The retries are capped at a hard-coded 100, after which a
        generic error is returned (don't reach that, I guess).

        """
        i = 0
        while True:
            try:
                yield
            except CompareMismatch as e:
                i += 1
                # Do this within the catch so we can attach the last
                # CompareMismatch exception to the new exception.
                if i > 100:
                    # Very ad-hoc.  This should never be encountered, but let’s
                    # at least set _some_ kind of error message here so someone
                    # could debug this, if it ever happens.  It almost certainly
                    # indicates an issue in the underlying store’s
                    # compare_and_set implementation.
                    raise Exception("exceeded CAS retry limit") from e
                continue
            else:
                return

    async def add_pending_return(
        self,
        memo_key: str,
        new_return: str,
        schedule_job: Callable[[], Awaitable[None]],
    ):
        """Register a pending return address for a call.

        Note this is inherently racy: as soon as this call completes, another
        worker could swoop in and immediately read the pending returns for this
        call and clear them.  You can't trust that the new return is ever
        visible to the thread that writes it--you can only trust that it is
        visible to _some_ worker.

        Return value indicates whether or not a call (any call) was already
        pending, even if it was this very same call, or any other call.  This
        can be used as an indication that an operation is currently `in flight.'

        """
        # Beware race conditions here!  Be aware of concurrency corner cases on
        # every single line.
        async with self._with_cas():
            memkey = MemKey("pending_returns", memo_key)
            should_store_again = False
            try:
                existing_enc = await self.store.get(memkey)
            except KeyError:
                existing = PendingReturns(None, {new_return})
                existing_enc = existing.encode()
                logger.debug(f"    ... none found. Creating new: {existing_enc}")
                # Note the double CAS!
                await self.store.set_new_value(memkey, existing_enc)
                adj = "First"
                verb = "added to"
            else:
                logger.debug(f"    ... found! {existing_enc}")
                existing = PendingReturns.decode(existing_enc)
                if new_return not in existing.returns:
                    existing.returns |= {new_return}
                    should_store_again = True
                    adj = "Another"
                    verb = "added to"
                else:
                    # 🙄
                    adj = "Existing"
                    verb = "ignored by"

            if existing.scheduled_at is None:
                await schedule_job()
                existing.scheduled_at = int(time.time())
                should_store_again = True
                verb += " and scheduled"

            # Something changed, store the update.  Think through the potential
            # race conditions here, in particular.  CAS failures, restarts, etc.
            if should_store_again:
                await self.store.compare_and_set(
                    memkey, existing.encode(), existing_enc
                )

            logger.debug(f"{adj} pending return {new_return} {verb} {memo_key}")

    @asynccontextmanager
    async def with_pending_returns_remove(
        self, memo_key: str
    ) -> AsyncIterator[set[str]]:
        """ """
        memkey = MemKey("pending_returns", memo_key)
        handled = set()
        async with self._with_cas():
            try:
                pending_enc = await self.store.get(memkey)
            except KeyError:
                # No pending returns means we were raced by a concurrent
                # execution of the same call with the same parent.
                # Unfortunately because of how Python context managers work, we
                # must yield _something_.  Yuck.
                #
                # https://stackoverflow.com/a/34519857
                yield set()
                return
            to_handle = PendingReturns.decode(pending_enc).returns - handled
            logger.debug(f"Handling returns for {memo_key}: {to_handle}...")
            yield to_handle
            handled |= to_handle
            await self.store.compare_and_delete(memkey, pending_enc)
