import { deepStrictEqual, ok, strictEqual } from 'node:assert'
import { suite, test } from 'node:test'
import {
  Brrr,
  InMemoryStore,
  Memory,
  type NaiveCall,
  NaiveCodec
} from '../../src'
import { ClosableInMemQueue } from '../fixtures/closable-mem-queue'

await suite(import.meta.filename, async () => {
  await test('codec key with no args normalizes memo_key', async t => {
    const brrr = new Brrr()
    const calls: Record<string, number> = {}
    const store = new InMemoryStore()
    const queue = new ClosableInMemQueue()
    const codec = new NaiveCodec()
    let invocation = 0

    codec.createCall = (taskName: string, args: unknown[]): NaiveCall => {
      invocation++
      const call = new NaiveCodec().createCall(taskName, args)
      Object.defineProperty(call, 'memoKey', {
        value: new NaiveCodec().createCall(taskName, []).memoKey
      })
      return call
    }

    const same = brrr.task('same', async (a: number) => {
      calls[`same(${a})`] = (calls[`same(${a})`] || 0) + 1
      return a
    })

    brrr.task('foo', async (a: number) => {
      calls[`foo(${a})`] = (calls[`foo(${a})`] || 0) + 1
      let val = 0
      for (let i = 1; i <= a; i++) {
        val += await same.invoke(i)
      }
      strictEqual(val, a)
      return val
    })

    await queue.close()

    brrr.setup({
      cache: store,
      queue,
      memory: new Memory(store, codec)
    })
    await brrr.schedule('foo', [50])
    await brrr.wrrrk()

    deepStrictEqual(calls, {
      'same(1)': 1,
      'foo(50)': 2
    })
    ok(invocation)
  })

  await test('codec produces deterministic memo keys', () => {
    const codec = new NaiveCodec()
    deepStrictEqual(
      codec.createCall('foo', [1, 2]),
      codec.createCall('foo', [1, 2])
    )
  })
})
