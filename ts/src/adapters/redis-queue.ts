import type {
  RedisClientType,
  RedisFunctions,
  RedisModules,
  RedisScripts
} from 'redis'
import {
  QueueIsClosedError,
  QueueIsEmptyError,
  QueuePopTimeoutError
} from '../libs/error'
import type { Cache } from '../models/cache'
import { Message, Queue, QueueInfo } from '../models/queue'

export class RedisQueue extends Queue implements Cache {
  public constructor(
    private readonly client: RedisClientType<
      RedisModules,
      RedisFunctions,
      RedisScripts
    >,
    private queue: string
  ) {
    super()
  }

  public async putMessage(body: string): Promise<void> {
    if (!this.client.isOpen) {
      throw new QueueIsClosedError()
    }
    const val = JSON.stringify([1, Math.floor(Date.now() / 1000), body])
    await this.client.rPush(this.queue, val)
  }

  public async getMessage(): Promise<Message> {
    const { length } = await this.getInfo()
    if (!length) {
      throw new QueueIsEmptyError()
    }
    const response = await this.client.blPop(this.queue, this.RECV_BLOCK_SECS)
    if (!response) {
      throw new QueuePopTimeoutError()
    }
    const chunks = JSON.parse(response.element)
    return new Message(chunks[2])
  }

  public async getInfo(): Promise<QueueInfo> {
    const total = await this.client.lLen(this.queue)
    return new QueueInfo(total)
  }

  public async close(): Promise<void> {
    await this.client.quit()
  }

  public async incr(key: string): Promise<number> {
    return this.client.incr(key)
  }
}
