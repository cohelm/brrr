import { deepStrictEqual, ok, rejects } from 'node:assert'
import { suite, test } from 'node:test'
import { Brrr } from '../src'
import { InMemoryStore } from '../src/adapters/in-memory-store'
import { SpawnLimitError } from '../src/libs/error'
import { Memory } from '../src/models/memory'
import { ClosableInMemQueue } from './fixtures/closable-mem-queue'
import { NaiveCodec } from './fixtures/naive-codec'

await suite(import.meta.filename, async () => {
  await test('depth limit', async () => {
    const brrr = new Brrr()

    const queue = new ClosableInMemQueue()
    const store = new InMemoryStore()
    let n = 0

    const foo = brrr.task('foo', async (a: number): Promise<number> => {
      n++
      if (a === 0) {
        await queue.close()
        return 0
      }
      return foo.invoke(a - 1)
    })

    brrr.setup({
      cache: store,
      queue,
      memory: new Memory(store, new NaiveCodec())
    })

    await brrr.schedule(foo, [brrr.SPAWN_LIMIT + 3])

    await rejects(async () => {
      await brrr.wrrrk()
    }, SpawnLimitError)

    deepStrictEqual(n, brrr.SPAWN_LIMIT)
  })

  await test('breadth mapped limit', async () => {
    const brrr = new Brrr()

    const queue = new ClosableInMemQueue()
    const store = new InMemoryStore()
    const calls = { one: 0, foo: 0 }

    const one = brrr.task('one', async (_: number): Promise<number> => {
      calls.one++
      return 1
    })

    const foo = brrr.task('foo', async (a: number): Promise<number> => {
      calls.foo++
      const inputs = [...new Array(a)].map((_, i) => [i] as [number])
      const results = await one.map(...inputs)
      const sum = results.reduce((acc, v) => acc + v, 0)
      if (calls.foo === a + 1) {
        await queue.close()
      }
      return sum
    })

    brrr.setup({
      cache: store,
      queue,
      memory: new Memory(store, new NaiveCodec())
    })

    await brrr.schedule(foo, [brrr.SPAWN_LIMIT + 4])

    await rejects(async () => {
      await brrr.wrrrk()
    }, SpawnLimitError)

    deepStrictEqual(calls.foo, 1)
  })

  await test('recoverable', async () => {
    const brrr = new Brrr()

    const queue = new ClosableInMemQueue()
    const store = new InMemoryStore()
    const cache = new InMemoryStore()

    const calls = { one: 0, foo: 0 }

    const one = brrr.task('one', async (_: number): Promise<number> => {
      calls.one++
      return 1
    })

    const foo = brrr.task('foo', async (a: number): Promise<number> => {
      calls.foo++
      const inputs = [...new Array(a)].map((_, i) => [i] as [number])
      const results = await one.map(...inputs)
      const sum = results.reduce((acc, v) => acc + v, 0)
      if (calls.foo === a + 1) {
        await queue.close()
      }
      return sum
    })

    brrr.setup({
      cache,
      queue,
      memory: new Memory(store, new NaiveCodec())
    })

    let spawnLimitEncountered = false
    const n = brrr.SPAWN_LIMIT + 1
    await brrr.schedule(foo, [n])

    while (true) {
      cache.innerByteStore.clear()
      cache.spawnCountStore.clear()
      try {
        await brrr.wrrrk()
        break
      } catch (err) {
        if (!(err instanceof SpawnLimitError)) {
          throw err
        }
        spawnLimitEncountered = true
      }
    }

    ok(spawnLimitEncountered)
    deepStrictEqual(calls, { one: n, foo: n + 1 })
  })

  await test('breadth manual limit', async () => {
    const brrr = new Brrr()

    const queue = new ClosableInMemQueue()
    const store = new InMemoryStore()
    const calls = { one: 0, foo: 0 }

    const one = brrr.task('one', async (i: number): Promise<number> => {
      calls.one++
      return 1
    })

    const foo = brrr.task('foo', async (a: number): Promise<number> => {
      calls.foo++
      let total = 0
      for (let i = 0; i < a; i++) {
        total += await one.invoke(i)
      }
      await queue.close()
      return total
    })

    brrr.setup({
      cache: store,
      queue,
      memory: new Memory(store, new NaiveCodec())
    })

    await brrr.schedule(foo, [brrr.SPAWN_LIMIT + 3])

    await rejects(async () => {
      await brrr.wrrrk()
    }, SpawnLimitError)

    deepStrictEqual(calls, {
      one: brrr.SPAWN_LIMIT / 2,
      foo: brrr.SPAWN_LIMIT / 2
    })
  })

  await test('cached single spawn', async () => {
    const brrr = new Brrr()

    const queue = new ClosableInMemQueue()
    const store = new InMemoryStore()
    let n = 0
    let final: number | undefined

    const same = brrr.task('same', async (a: number): Promise<number> => {
      n++
      return a
    })

    const foo = brrr.task('foo', async (a: number): Promise<number> => {
      const inputs = Array(a).fill([1] as [number])
      const results = await same.map(...inputs)
      await queue.close()
      final = results.reduce((sum, v) => sum + v, 0)
      return final
    })

    brrr.setup({
      cache: store,
      queue,
      memory: new Memory(store, new NaiveCodec())
    })

    await brrr.schedule(foo, [brrr.SPAWN_LIMIT + 5])
    await brrr.wrrrk()

    deepStrictEqual(n, 1)
    deepStrictEqual(final, brrr.SPAWN_LIMIT + 5)
  })
})
