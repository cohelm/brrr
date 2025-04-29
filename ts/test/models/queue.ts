import { equal, ok, rejects } from 'node:assert'
import { suite, test } from 'node:test'
import { InMemoryQueue } from '../../src/adapters/in-memory-queue'
import { QueueIsEmptyError } from '../../src/libs/error'
import type { Queue } from '../../src/models/queue'

const cases: {
  readonly name: string
  readonly createQueue: () => Queue
}[] = [
  {
    name: InMemoryQueue.name,
    createQueue: (): InMemoryQueue => new InMemoryQueue()
  }
]

for (const { name, createQueue } of cases) {
  await suite(`Queue implementation: ${name}`, async () => {
    await test('raises QueueIsEmpty when empty', async () => {
      const queue = createQueue()

      await rejects(async () => {
        await queue.getMessage()
      }, QueueIsEmptyError)
    })

    await test('enqueues and dequeues messages correctly', async () => {
      const queue = createQueue()

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
    })
  })
}
