import type { RedisClientType } from 'redis'
import { QueueIsEmptyError } from '../../src/libs/error'
import type { Cache } from '../../src/models/cache'
import { Message, Queue, QueueInfo } from '../../src/models/queue'

export class RedisQueue extends Queue implements Cache {
  public constructor(
    private readonly client: RedisClientType,
    private queue: string
  ) {
    super()
  }

  public async putMessage(body: string): Promise<void> {
    const val = JSON.stringify([1, Math.floor(Date.now() / 1000), body])
    await this.client.rPush(this.queue, val)
  }

  public async getMessage(): Promise<Message> {
    const response = await this.client.blPop(this.queue, this.RECV_BLOCK_SECS)
    if (!response) {
      throw new QueueIsEmptyError()
    }
    const chunks = JSON.parse(response.element)
    return new Message(chunks[2])
  }

  public async getInfo(): Promise<QueueInfo> {
    const total = await this.client.lLen(this.queue)
    return new QueueInfo(total)
  }

  public async incr(key: string): Promise<number> {
    return this.client.incr(key)
  }
}
