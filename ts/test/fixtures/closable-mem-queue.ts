import AsyncQueue from '@ai-zen/async-queue'
import { QueueIsClosedError } from '../../src/libs/error'
import { Message, Queue } from '../../src/models/queue'

export class ClosableInMemQueue extends Queue {
  private operational = true
  private closing = false
  private received = new AsyncQueue<string>()
  private iterator: AsyncIterator<string>

  constructor() {
    super()
    this.iterator = this.received[Symbol.asyncIterator]()
  }

  public reset(): void {
    this.operational = true
    this.closing = false
    this.received = new AsyncQueue<string>()
    this.iterator = this.received[Symbol.asyncIterator]()
  }

  public async close(): Promise<void> {
    if (this.closing) {
      throw new QueueIsClosedError()
    }
    this.closing = true
    this.received.done()
  }

  public async getMessage(): Promise<Message> {
    if (!this.operational) {
      throw new QueueIsClosedError()
    }
    const { value, done } = await this.iterator.next()
    if (done) {
      this.operational = false
      throw new QueueIsClosedError()
    }
    return new Message(value)
  }

  public async putMessage(body: string): Promise<void> {
    if (!this.operational) {
      throw new QueueIsClosedError()
    }
    this.received.push(body)
  }
}
