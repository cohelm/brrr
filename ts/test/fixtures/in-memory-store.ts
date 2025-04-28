import {
  CompareMismatchError,
  MemoryValueNotFoundError
} from '../../src/libs/error'
import type { Cache } from '../../src/models/cache'
import type { MemKey } from '../../src/models/memory'
import type { Store } from '../../src/models/store'

export class InMemoryStore implements Store, Cache {
  public innerByteStore = new Map<string, Uint8Array>()
  public spawnCountStore = new Map<string, number>()

  public async has(key: MemKey): Promise<boolean> {
    return this.innerByteStore.has(key.toString())
  }

  public async get(key: MemKey): Promise<Uint8Array> {
    const value = this.innerByteStore.get(key.toString())
    if (!value) {
      throw new MemoryValueNotFoundError(key.toString())
    }
    return value
  }

  public async set(key: MemKey, value: Uint8Array): Promise<void> {
    this.innerByteStore.set(key.toString(), value)
  }

  public async delete(key: MemKey): Promise<void> {
    this.innerByteStore.delete(key.toString())
  }

  public async setNewValue(key: MemKey, value: Uint8Array): Promise<void> {
    const keyStr = key.toString()
    if (this.innerByteStore.has(keyStr)) {
      throw new CompareMismatchError(key)
    }
    this.innerByteStore.set(keyStr, value)
  }

  public async compareAndSet(
    key: MemKey,
    value: Uint8Array,
    expected: Uint8Array
  ): Promise<void> {
    const keyStr = key.toString()
    const current = this.innerByteStore.get(keyStr)

    if (current === undefined || !uint8ArrayEquals(current, expected)) {
      throw new CompareMismatchError(key)
    }

    this.innerByteStore.set(keyStr, value)
  }

  public async compareAndDelete(
    key: MemKey,
    expected: Uint8Array
  ): Promise<void> {
    const keyStr = key.toString()
    const current = this.innerByteStore.get(keyStr)

    if (current === undefined || !uint8ArrayEquals(current, expected)) {
      throw new CompareMismatchError(key)
    }

    this.innerByteStore.delete(keyStr)
  }

  public async incr(key: string): Promise<number> {
    const value = (this.spawnCountStore.get(key) ?? 0) + 1
    this.spawnCountStore.set(key, value)
    return value
  }
}

function uint8ArrayEquals(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false
  }
  return true
}
