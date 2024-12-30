from brrr.backends.in_memory import InMemoryByteStore
import pytest

from abc import ABC, abstractmethod
from brrr.store import AlreadyExists, Call, CompareMismatch, Memory, Store, MemKey


class ByteStoreContract(ABC):
    @abstractmethod
    def get_store(self) -> Store[bytes]:
        """
        This should return a fresh, empty store instance
        """
        ...

    def test_contains(self):
        store = self.get_store()

        a1 = MemKey("type-a", "id-1")
        a2 = MemKey("type-a", "id-2")
        b1 = MemKey("type-b", "id-1")

        assert a1 not in store
        assert a2 not in store
        assert b1 not in store

        store[a1] = b"value-1"
        assert a1 in store
        assert a2 not in store
        assert b1 not in store

        store[a2] = b"value-2"
        assert a1 in store
        assert a2 in store
        assert b1 not in store

        store[b1] = b"value-3"
        assert a1 in store
        assert a2 in store
        assert b1 in store

        del store[a1]
        assert a1 not in store
        assert a2 in store
        assert b1 in store

        del store[a2]
        assert a1 not in store
        assert a2 not in store
        assert b1 in store

        del store[b1]
        assert a1 not in store
        assert a2 not in store
        assert b1 not in store

    def test_get_set(self):
        store = self.get_store()

        a1 = MemKey("type-a", "id-1")
        a2 = MemKey("type-a", "id-2")
        b1 = MemKey("type-b", "id-1")

        store[a1] = b"value-1"
        store[a2] = b"value-2"
        store[b1] = b"value-3"

        assert store[a1] == b"value-1"
        assert store[a2] == b"value-2"
        assert store[b1] == b"value-3"

        store[a1] = b"value-4"
        assert store[a1] == b"value-4"

    def test_key_error(self):
        store = self.get_store()

        a1 = MemKey("type-a", "id-1")

        with pytest.raises(KeyError):
            store[a1]

        del store[a1]
        with pytest.raises(KeyError):
            store[a1]

        store[a1] = b"value-1"

        assert store[a1] == b"value-1"

        del store[a1]
        with pytest.raises(KeyError):
            store[a1]

    def test_compare_and_set(self):
        store = self.get_store()

        a1 = MemKey("type-a", "id-1")

        store[a1] = b"value-1"

        with pytest.raises(CompareMismatch):
            store.compare_and_set(a1, b"value-2", b"value-3")

        store.compare_and_set(a1, b"value-2", b"value-1")

        assert store[a1] == b"value-2"

    def test_compare_and_delete(self):
        store = self.get_store()

        a1 = MemKey("type-a", "id-1")

        store[a1] = b"value-1"

        with pytest.raises(CompareMismatch):
            store.compare_and_delete(a1, b"value-2")

        assert store[a1] == b"value-1"

        store.compare_and_delete(a1, b"value-1")

        with pytest.raises(KeyError):
            store[a1]


class TestMemory:
    def get_memory(self) -> Memory:
        store = InMemoryByteStore()
        return Memory(store)

    def test_call(self):
        memory = self.get_memory()

        with pytest.raises(ValueError):
            memory.set_call("foo")

        with pytest.raises(KeyError):
            memory.get_call("non-existent")

        call = Call("task", (("arg-1", "arg-2"), {"a": 1, "b": 2}))
        assert not memory.has_call(call)

        memory.set_call(call)
        assert memory.has_call(call)
        assert memory.get_call(call.memo_key) == call

    def test_value(self):
        memory = self.get_memory()

        assert not memory.has_value("key")

        memory.set_value("key", {"test": 1})
        assert memory.has_value("key")
        assert memory.get_value("key") == {"test": 1}

        with pytest.raises(AlreadyExists):
            memory.set_value("key", {"test": 2})

    def test_pending_returns(self):
        memory = self.get_memory()

        with pytest.raises(KeyError):
            assert not memory.get_pending_returns("key")

        with pytest.raises(ValueError):
            memory.add_pending_returns("key", {123})

        memory.add_pending_returns("key", {"a", "b"})

        assert memory.get_pending_returns("key") == {"a", "b"}

        memory.add_pending_returns("key", {"c", "d"})
        assert memory.get_pending_returns("key") == {"a", "b", "c", "d"}

        with pytest.raises(CompareMismatch):
            memory.delete_pending_returns("key", {"a", "b", "c", "d", "wrong"})
        assert memory.get_pending_returns("key") == {"a", "b", "c", "d"}

        memory.delete_pending_returns("key", {"a", "b", "c", "d"})
        with pytest.raises(KeyError):
            assert not memory.get_pending_returns("key")


class TestInMemoryByteStore(ByteStoreContract):
    def get_store(self) -> Store[bytes]:
        return InMemoryByteStore()
