import bencode from 'bencode'
import {
  CasRetryLimitError,
  CompareMismatchError,
  MemoryKeyAlreadyExistsError,
  MemoryValueNotFoundError
} from '../libs/error'
import type { Fn } from '../types'
import type { Call } from './call'
import type { Codec } from './codec'
import { PendingReturns } from './pending-returns'
import type { Store } from './store'

interface Payload {
  taskName: Uint8Array
  callBytes: Uint8Array
}

export class MemKey {
  constructor(
    public readonly type: 'call' | 'value' | 'pending_returns',
    public readonly id: string
  ) {}

  public toString(): string {
    return `${this.type}/${this.id}`
  }
}

export class Memory {
  private readonly CAS_RETRY_LIMIT = 100

  constructor(
    public readonly store: Store,
    public readonly codec: Codec
  ) {}

  public makeCall<A extends unknown[]>(task_name: string, args: A): Call {
    return this.codec.createCall(task_name, args)
  }

  public async hasCall(call: Call): Promise<boolean> {
    return await this.store.has(new MemKey('call', call.memoKey))
  }

  async setCall(call: Call): Promise<void> {
    const payload: Payload = {
      taskName: new TextEncoder().encode(call.taskName),
      callBytes: this.codec.encodeCall(call)
    }
    return this.store.set(
      new MemKey('call', call.memoKey),
      bencode.encode(payload)
    )
  }

  public async hasValue(call: Call): Promise<boolean> {
    const memKey = new MemKey('value', call.memoKey)
    return this.store.has(memKey)
  }

  public async getValue(call: Call): Promise<Uint8Array> {
    const memKey = new MemKey('value', call.memoKey)
    const value = await this.store.get(memKey)
    if (!value) {
      throw new MemoryValueNotFoundError(call.memoKey)
    }
    return value
  }

  public async setValue(memoKey: string, payload: Uint8Array): Promise<void> {
    try {
      await this.store.setNewValue(new MemKey('value', memoKey), payload)
    } catch (e) {
      if (e instanceof CompareMismatchError) {
        throw new MemoryKeyAlreadyExistsError(memoKey)
      }
      throw e
    }
  }

  public async addPendingReturn(
    memoKey: string,
    newReturn: string,
    scheduleJob: () => Promise<void>
  ): Promise<void> {
    await this.withCas(async () => {
      const memKey = new MemKey('pending_returns', memoKey)
      let shouldStoreAgain = false
      let existingEncoded: Uint8Array
      let existing: PendingReturns
      try {
        existingEncoded = await this.store.get(memKey)
        existing = await PendingReturns.decode(existingEncoded)
        if (!existing.returns.has(newReturn)) {
          existing.returns.add(newReturn)
          shouldStoreAgain = true
        }
      } catch (err) {
        if (!(err instanceof MemoryValueNotFoundError)) {
          throw err
        }
        existing = new PendingReturns(undefined, new Set([newReturn]))
        existingEncoded = await existing.encode()
        await this.store.setNewValue(memKey, existingEncoded)
      }
      if (!existing.scheduledAt) {
        await scheduleJob()
        existing.scheduledAt = Math.floor(Date.now() / 1000).toString()
        shouldStoreAgain = true
      }
      if (shouldStoreAgain) {
        const newEnc = await existing.encode()
        await this.store.compareAndSet(memKey, newEnc, existingEncoded)
      }
    })
  }

  async getCallBytes(memoKey: string): Promise<{
    taskName: string
    payload: Uint8Array
  }> {
    const payload = await this.store.get(new MemKey('call', memoKey))
    const { taskName, callBytes } = bencode.decode(
      Buffer.from(payload)
    ) as Payload
    return {
      taskName: Buffer.from(taskName).toString('utf-8'),
      payload: callBytes
    }
  }

  public async withCas(fn: Fn<[], Promise<void>>): Promise<void> {
    for (let attempt = 0; attempt <= this.CAS_RETRY_LIMIT; attempt++) {
      try {
        await fn()
        return
      } catch (err) {
        if (!(err instanceof CompareMismatchError)) {
          throw err
        }
        if (attempt === this.CAS_RETRY_LIMIT) {
          throw new CasRetryLimitError(this.CAS_RETRY_LIMIT)
        }
      }
    }
  }

  public async withPendingReturnsRemove(
    memoKey: string,
    fn: Fn<[Set<string>], Promise<void>>
  ): Promise<void> {
    const memKey = new MemKey('pending_returns', memoKey)
    const handled = new Set<string>()
    await this.withCas(async () => {
      try {
        const encodedPending = await this.store.get(memKey)
        const pending = await PendingReturns.decode(encodedPending)
        const handles = pending.returns.difference(handled)
        await fn(handles)
        for (const handle of handles) {
          handled.add(handle)
        }
        await this.store.compareAndDelete(memKey, encodedPending)
      } catch (e) {
        if (!(e instanceof MemoryValueNotFoundError)) {
          throw e
        }
        await fn(new Set())
      }
    })
  }
}
