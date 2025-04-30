import { deepStrictEqual, rejects } from 'node:assert'
import { suite, test } from 'node:test'
import { Brrr, InMemoryStore, Memory, NaiveCodec } from 'brrr'
import { ClosableInMemQueue } from './fixtures/closable-mem-queue'

await suite(import.meta.filename, async () => {
  await suite('No Brrr', async () => {
    const brrr = new Brrr()
    const triangularSum = brrr.task(
      'triangular_sum',
      async (a: number): Promise<number> => {
        return a === 0 ? a : a + (await triangularSum.invoke(a - 1))
      }
    )

    await test('invoke', async () => {
      deepStrictEqual(await triangularSum.invoke(3), 6)
    })

    await test('map', async () => {
      deepStrictEqual(await triangularSum.map([3], [4]), [6, 10])
    })
  })

  await test('Nop closed queue', async () => {
    const brrr = new Brrr()
    const store = new InMemoryStore()
    const queue = new ClosableInMemQueue()
    await queue.close()
    brrr.setup({
      cache: store,
      queue,
      memory: new Memory(store, new NaiveCodec())
    })
    await brrr.wrrrk()
    await brrr.wrrrk()
    await brrr.wrrrk()
  })

  await test('Stop when empty', async () => {
    const brrr = new Brrr()
    const store = new InMemoryStore()
    const queue = new ClosableInMemQueue()

    const pre = [0, 0, 0, 0]
    const post = [0, 0, 0, 0]

    const foo = brrr.task('foo', async (a: number): Promise<number> => {
      pre[a]++
      if (a === 0) {
        return 0
      }
      const res = await foo.invoke(a - 1)
      post[a]++
      if (a === 3) {
        await queue.close()
      }
      return res
    })

    brrr.setup({
      cache: store,
      queue,
      memory: new Memory(store, new NaiveCodec())
    })

    await brrr.schedule(foo, [3])
    await brrr.wrrrk()
    deepStrictEqual(pre, [1, 2, 2, 2])
    deepStrictEqual(post, [0, 1, 1, 1])
  })

  await test('Debounce child', async () => {
    const brrr = new Brrr()
    const calls: number[] = [0, 0, 0, 0]
    const store = new InMemoryStore()
    const queue = new ClosableInMemQueue()

    const foo = brrr.task('foo', async (a: number): Promise<number> => {
      calls[a] = (calls[a] || 0) + 1
      if (a === 0) {
        return a
      }
      const results = await foo.map(...Array(50).fill([a - 1]))
      const ret = results.reduce((sum, x) => sum + x, 0)
      if (a === 3) {
        await queue.close()
      }
      return ret
    })

    brrr.setup({
      cache: store,
      queue,
      memory: new Memory(store, new NaiveCodec())
    })

    await brrr.schedule(foo, [3])
    await brrr.wrrrk()

    deepStrictEqual(calls, [1, 2, 2, 2])
  })

  await test('No debounce parent', async () => {
    const brrr = new Brrr()
    const calls = {
      one: 0,
      foo: 0
    }
    const store = new InMemoryStore()
    const queue = new ClosableInMemQueue()

    const one = brrr.task('one', async (_: number): Promise<number> => {
      calls.one++
      return 1
    })

    const foo = brrr.task('foo', async (a: number): Promise<number> => {
      calls.foo++
      const inputs = [...new Array(a)].map((_, i) => [i] as [number])
      const ret = (await one.map(...inputs)).reduce((sum, val) => sum + val, 0)
      if (calls.foo === 1 + a) {
        await queue.close()
      }
      return ret
    })

    brrr.setup({
      cache: store,
      queue,
      memory: new Memory(store, new NaiveCodec())
    })

    await brrr.schedule(foo, [50])
    await brrr.wrrrk()

    deepStrictEqual(calls, { one: 50, foo: 51 })
  })

  await test('Wrrrk recoverable', async () => {
    const brrr = new Brrr()
    const store = new InMemoryStore()
    const queue = new ClosableInMemQueue()
    const calls: Record<string, number> = {}

    class MyError extends Error {}

    const foo = brrr.task('foo', async (a: number): Promise<number> => {
      const key = `foo(${a})`
      calls[key] = (calls[key] ?? 0) + 1
      if (a === 0) {
        throw new MyError()
      }
      return await foo.invoke(a - 1)
    })

    const bar = brrr.task('bar', async (a: number): Promise<number> => {
      const key = `bar(${a})`
      calls[key] = (calls[key] ?? 0) + 1
      if (a === 0) {
        return 0
      }
      const ret = await bar.invoke(a - 1)
      if (a === 2) {
        await queue.close()
      }
      return ret
    })

    brrr.setup({
      cache: store,
      queue,
      memory: new Memory(store, new NaiveCodec())
    })

    await brrr.schedule(foo, [2])

    await rejects(async () => {
      await brrr.wrrrk()
    }, MyError)

    queue.reset()

    await brrr.schedule(bar, [2])
    await brrr.wrrrk()

    deepStrictEqual(calls, {
      'foo(0)': 1,
      'foo(1)': 1,
      'foo(2)': 1,
      'bar(0)': 1,
      'bar(1)': 2,
      'bar(2)': 2
    })
  })
})
