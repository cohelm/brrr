import { equal, ok, rejects } from 'node:assert'
import { suite, test } from 'node:test'
import { createClient } from 'redis'
import {
  InMemoryQueue,
  type Queue,
  QueueIsEmptyError,
  RedisQueue
} from '../../src'

const cases: {
  readonly name: string
  readonly createQueue: () => Promise<Queue>
  readonly cleanup?: (queue: Queue) => Promise<void>
}[] = [
  {
    name: InMemoryQueue.name,
    createQueue: async (): Promise<InMemoryQueue> => {
      return new InMemoryQueue()
    }
  },
  {
    name: RedisQueue.name,
    createQueue: async (): Promise<RedisQueue> => {
      const client = createClient()
      await client.connect()
      return new RedisQueue(client, 'brrr-test')
    }
  }
]

for (const { name, createQueue } of cases) {
  await suite(`Queue implementation: ${name}`, async () => {
    await test('raises QueueIsEmpty when empty', async () => {
      const queue = await createQueue()
      await rejects(async () => {
        await queue.getMessage()
      }, QueueIsEmptyError)
      await queue.close()
    })

    await test('enqueues and dequeues messages correctly', async () => {
      const queue = await createQueue()

      const messages = new Set(['message-1', 'message-2', 'message-3'])

      equal((await queue.getInfo()).length, 0)

      await queue.putMessage('message-1')
      equal((await queue.getInfo()).length, 1)

      await queue.putMessage('message-2')
      equal((await queue.getInfo()).length, 2)

      await queue.putMessage('message-3')
      equal((await queue.getInfo()).length, 3)

      let message = await queue.getMessage()
      ok(messages.has(message.body))
      messages.delete(message.body)
      equal((await queue.getInfo()).length, 2)

      message = await queue.getMessage()
      ok(messages.has(message.body))
      messages.delete(message.body)
      equal((await queue.getInfo()).length, 1)

      message = await queue.getMessage()
      ok(messages.has(message.body))
      messages.delete(message.body)
      equal((await queue.getInfo()).length, 0)

      await rejects(async () => {
        await queue.getMessage()
      }, QueueIsEmptyError)

      await queue.close()
    })
  })
}
