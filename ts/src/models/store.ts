import type { MemKey } from './memory';

export interface Store {
  has(key: MemKey): Promise<boolean>;

  get(key: MemKey): Promise<Uint8Array>;

  set(key: MemKey, value: Uint8Array): Promise<void>;

  delete(key: MemKey): Promise<void>;

  setNewValue(key: MemKey, value: Uint8Array): Promise<void>;

  compareAndSet(
    key: MemKey,
    value: Uint8Array,
    expected: Uint8Array | null
  ): Promise<void>;

  compareAndDelete(key: MemKey, expected: Uint8Array): Promise<void>;
}
