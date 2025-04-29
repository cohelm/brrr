// import { deepStrictEqual, ok } from 'node:assert'
// import { suite, test } from 'node:test'
// import { mock } from 'node:test'
// import * as v8 from 'node:v8'
// import { Brrr, InMemoryStore, Memory, NaiveCodec } from '../src'
// import { ClosableInMemQueue } from './fixtures/closable-mem-queue'
//
// await suite('codec', async () => {
//   await test('key no args', async () => {
//     const brrr = new Brrr()
//     const store = new InMemoryStore()
//     const queue = new ClosableInMemQueue()
//     const codec = new NaiveCodec()
//
//     const createCallOriginal = codec.createCall.bind(codec)
//     const createCallMock = mock.fn((name, args, kwargs) => {
//       const full = createCallOriginal(name, args, kwargs)
//       const bare = createCallOriginal(name, [], {})
//       return { ...full, memoKey: bare.memoKey }
//     })
//     codec.createCall = createCallMock
//
//     const calls: Record<string, number> = {}
//
//     const same = brrr.task('same', async (a: number) => {
//       const key = `same(${a})`
//       calls[key] = (calls[key] ?? 0) + 1
//       return a
//     })
//
//     const foo = brrr.task('foo', async (a: number) => {
//       calls[`foo(${a})`] = (calls[`foo(${a})`] ?? 0) + 1
//       let val = 0
//       for (let i = 1; i <= a; i++) {
//         val += await same.invoke(i)
//       }
//       deepStrictEqual(val, a)
//       await queue.close()
//       return val
//     })
//
//     brrr.setup({ cache: store, queue, memory: new Memory(store, codec) })
//     await brrr.schedule(foo, [50])
//     await brrr.wrrrk()
//     await queue.join()
//
//     deepStrictEqual(calls, {
//       'same(1)': 1,
//       'foo(50)': 2
//     })
//     ok(createCallMock.mock.calls.length > 0)
//   })
//
//   await test('deterministic memo key', async () => {
//     const codec = new NaiveCodec()
//     const call1 = codec.createCall('foo', [1, 2], { b: 4, a: 3 })
//     const call2 = codec.createCall('foo', [1, 2], { a: 3, b: 4 })
//     deepStrictEqual(call1.memoKey, call2.memoKey)
//   })
//
//   await test('API usage', async () => {
//     const brrr = new Brrr()
//     const store = new InMemoryStore()
//     const queue = new ClosableInMemQueue()
//     const codec = mock.proxy(new NaiveCodec())
//
//     const plus = brrr.task('plus', async (x: number, y: string) => {
//       return x + Number.parseInt(y, 10)
//     })
//
//     const foo = brrr.task('foo', async () => {
//       const sum =
//         (await plus.invoke(1, '2')) +
//         (await plus.invokeNamed({ x: 3, y: '4' })) +
//         (await plus.invoke(5, '6')) +
//         (await plus.invokeNamed({ x: 7, y: '8' }))
//       deepStrictEqual(sum, 36)
//       await queue.close()
//       return sum
//     })
//
//     brrr.setup({ cache: store, queue, memory: new Memory(store, codec) })
//     await brrr.schedule(foo, [])
//     await brrr.wrrrk()
//     await queue.join()
//
//     const expectedCalls = [
//       ['foo', [], {}],
//       ['plus', [1, '2'], {}],
//       ['plus', [], { x: 3, y: '4' }],
//       ['plus', [5, '6'], {}],
//       ['plus', [], { x: 7, y: '8' }]
//     ]
//     for (const args of expectedCalls) {
//       ok(
//         codec.createCall.mock.calls.some(
//           c => JSON.stringify(c.args) === JSON.stringify(args)
//         )
//       )
//     }
//
//     const nameCounts = codec.invokeTask.mock.calls.reduce(
//       (acc, c) => {
//         const name = c.args[1]
//         acc[name] = (acc[name] ?? 0) + 1
//         return acc
//       },
//       {} as Record<string, number>
//     )
//
//     deepStrictEqual(nameCounts, { foo: 5, plus: 4 })
//
//     for (const c of codec.decodeReturn.mock.calls) {
//       const result = v8.deserialize(c.args[0])
//       ok([3, 7, 11, 15, 36].includes(result))
//     }
//   })
// })
