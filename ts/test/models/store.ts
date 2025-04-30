import { equal, ok, rejects } from 'node:assert'
import { suite, test } from 'node:test'
import { DynamoDBClient } from '@aws-sdk/client-dynamodb'
import {
  CompareMismatchError,
  DynamoStore,
  InMemoryStore,
  MemKey,
  MemoryValueNotFoundError,
  type Store
} from 'brrr'

const textDecoder = new TextDecoder()

const storeCases = [
  {
    name: InMemoryStore.name,
    createStore: async (): Promise<Store> => new InMemoryStore()
  },
  {
    name: DynamoStore.name,
    createStore: async (): Promise<Store> => {
      const client = new DynamoDBClient({
        region: process.env.AWS_DEFAULT_REGION,
        endpoint: process.env.AWS_ENDPOINT_URL,
        credentials: {
          accessKeyId: process.env.AWS_ACCESS_KEY_ID ?? '',
          secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY ?? ''
        }
      })
      const store = new DynamoStore(client, 'brrr-test')
      try {
        await store.deleteTable()
      } catch (_) {}
      try {
        await store.createTable()
      } catch (_) {}
      return store
    }
  }
]

for (const { name, createStore } of storeCases) {
  await suite(`Store implementation: ${name}`, async () => {
    await test('has behavior', async () => {
      const store = await createStore()
      const a1 = new MemKey('value', 'id-1')
      const a2 = new MemKey('value', 'id-2')
      const b1 = new MemKey('call', 'id-1')

      ok(!(await store.has(a1)))
      ok(!(await store.has(a2)))
      ok(!(await store.has(b1)))

      await store.set(a1, Buffer.from('value-1'))
      ok(await store.has(a1))
      ok(!(await store.has(a2)))
      ok(!(await store.has(b1)))

      await store.set(a2, Buffer.from('value-2'))
      ok(await store.has(a1))
      ok(await store.has(a2))
      ok(!(await store.has(b1)))

      await store.set(b1, Buffer.from('value-3'))
      ok(await store.has(a1))
      ok(await store.has(a2))
      ok(await store.has(b1))

      await store.delete(a1)
      ok(!(await store.has(a1)))
      ok(await store.has(a2))
      ok(await store.has(b1))

      await store.delete(a2)
      ok(!(await store.has(a1)))
      ok(!(await store.has(a2)))
      ok(await store.has(b1))

      await store.delete(b1)
      ok(!(await store.has(a1)))
      ok(!(await store.has(a2)))
      ok(!(await store.has(b1)))

      if (store instanceof DynamoStore) {
        await store.deleteTable()
      }
    })

    await test('get/set behavior', async () => {
      const store = await createStore()
      const a1 = new MemKey('value', 'id-1')
      const a2 = new MemKey('value', 'id-2')
      const b1 = new MemKey('call', 'id-1')

      await store.set(a1, Buffer.from('value-1'))
      await store.set(a2, Buffer.from('value-2'))
      await store.set(b1, Buffer.from('value-3'))

      equal(textDecoder.decode(await store.get(a1)), 'value-1')
      equal(textDecoder.decode(await store.get(a2)), 'value-2')
      equal(textDecoder.decode(await store.get(b1)), 'value-3')

      await store.set(a1, Buffer.from('value-4'))
      equal(textDecoder.decode(await store.get(a1)), 'value-4')

      if (store instanceof DynamoStore) {
        await store.deleteTable()
      }
    })

    await test('key error behavior', async () => {
      const store = await createStore()
      const a1 = new MemKey('value', 'id-1')

      await rejects(() => store.get(a1), MemoryValueNotFoundError)
      await store.delete(a1)
      await rejects(() => store.get(a1), MemoryValueNotFoundError)

      await store.set(a1, Buffer.from('value-1'))
      equal(textDecoder.decode(await store.get(a1)), 'value-1')

      await store.delete(a1)
      await rejects(() => store.get(a1), MemoryValueNotFoundError)

      if (store instanceof DynamoStore) {
        await store.deleteTable()
      }
    })

    await test('set new value behavior', async () => {
      const store = await createStore()
      const a1 = new MemKey('value', 'id-1')

      await store.setNewValue(a1, Buffer.from('value-1'))
      equal(textDecoder.decode(await store.get(a1)), 'value-1')

      await rejects(
        () => store.setNewValue(a1, Buffer.from('value-2')),
        CompareMismatchError
      )

      await store.set(a1, Buffer.from('value-2'))
      equal(textDecoder.decode(await store.get(a1)), 'value-2')

      if (store instanceof DynamoStore) {
        await store.deleteTable()
      }
    })

    await test('compare and set', async () => {
      const store = await createStore()
      const a1 = new MemKey('value', 'id-1')

      await store.set(a1, Buffer.from('value-1'))
      await rejects(
        () =>
          store.compareAndSet(
            a1,
            Buffer.from('value-2'),
            Buffer.from('value-3')
          ),
        CompareMismatchError
      )
      await store.compareAndSet(
        a1,
        Buffer.from('value-2'),
        Buffer.from('value-1')
      )
      equal(textDecoder.decode(await store.get(a1)), 'value-2')

      if (store instanceof DynamoStore) {
        await store.deleteTable()
      }
    })

    await test('compare and delete', async () => {
      const store = await createStore()
      const a1 = new MemKey('value', 'id-1')

      await rejects(
        () => store.compareAndDelete(a1, Buffer.from('value-2')),
        CompareMismatchError
      )
      await store.set(a1, Buffer.from('value-1'))
      await rejects(
        () => store.compareAndDelete(a1, Buffer.from('value-2')),
        CompareMismatchError
      )

      equal(textDecoder.decode(await store.get(a1)), 'value-1')
      await store.compareAndDelete(a1, Buffer.from('value-1'))
      await rejects(() => store.get(a1), MemoryValueNotFoundError)

      if (store instanceof DynamoStore) {
        await store.deleteTable()
      }
    })
  })
}
