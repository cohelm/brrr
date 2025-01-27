from __future__ import annotations

from abc import abstractmethod, ABC
import hashlib
import pickle
from typing import Any


class Codec(ABC):
    """Codec for values that pass around the brrr datastore.

    If you want inter-language calling you'll need to ensure both languages
    can compute this.

    The serializations must be deterministic, whatever that means for you.
    E.g. if you use dictionaries, make sure to order them before serializing.

    For any serious use you want strict control over the types you accept here
    and explicit serialization routines.

    """

    @abstractmethod
    def hash_call(self, task_name: str, args: tuple, kwargs: dict) -> str:
        """Create a unique, deterministic identifier for this task invocation.

        The reference implementation is using sha256 on a the name, a naive
        serialization of the args, and on the sorted dictionary with a naive
        serialization of its values.  For correct operation of Brrr, this call
        must always return exactly the same output for the same input, so your
        best bet is to be strict here and define an explicit hash which don't
        rely on possibly non-deterministic serialization of data structures
        (e.g. str(dict) could be dependent on insertion order, or python
        version, etc).

        Pay close attention to this routine when you work cross language: while
        it makes little sense for different languages to support serving the
        same calls, they must all correctly and deterministically and
        identically hash the same invocation to the same output hash.  So if you
        want to call, say, a task served by Go, from a worker (or other code) in
        Python, they must both agree on what the input arguments to that call
        would look like for the environment, and derive the same hash from it.

        """
        raise NotImplementedError()

    @abstractmethod
    def encode_args(self, args: tuple, kwargs: dict) -> bytes:
        raise NotImplementedError()

    @abstractmethod
    def decode_args(self, payload: bytes) -> tuple[tuple, dict]:
        raise NotImplementedError()

    @abstractmethod
    def encode_return(self, val: Any) -> bytes:
        raise NotImplementedError()

    @abstractmethod
    def decode_return(self, payload: bytes) -> Any:
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

    def hash_call(self, task_name: str, args: tuple, kwargs: dict) -> str:
        h = hashlib.new("sha256")
        h.update(repr([task_name, args, list(sorted(kwargs.items()))]).encode())
        return h.hexdigest()

    def encode_args(self, args: tuple, kwargs: dict) -> bytes:
        return pickle.dumps((args, kwargs))

    def decode_args(self, payload: bytes) -> tuple[tuple, dict]:
        return pickle.loads(payload)

    def encode_return(self, val: Any) -> bytes:
        return pickle.dumps(val)

    def decode_return(self, payload: bytes) -> Any:
        return pickle.loads(payload)
