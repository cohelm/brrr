from __future__ import annotations

from abc import abstractmethod, ABC
from typing import Any

from brrr.call import Call


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
    def create_call(self, task_name: str, args: tuple, kwargs: dict) -> Call:
        raise NotImplementedError()

    @abstractmethod
    def encode_call(self, call: Call) -> bytes:
        raise NotImplementedError()

    @abstractmethod
    async def invoke_task(
        self, memo_key: str, name: str, handler, payload: bytes
    ) -> bytes:
        raise NotImplementedError()

    @abstractmethod
    def decode_return(self, payload: bytes) -> Any:
        raise NotImplementedError()
