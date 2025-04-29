import { Deque } from '@datastructures-js/deque'
import { QueueIsClosedError, QueueIsEmptyError } from '../libs/error'
import { Message, Queue, QueueInfo } from '../models/queue'

export class InMemoryQueue extends Queue {
  private readonly messages = new Deque<string>()
  private closed = false

  public async getMessage(): Promise<Message> {
    if (this.closed) {
      throw new QueueIsClosedError()
    }
    if (this.messages.isEmpty()) {
      throw new QueueIsEmptyError()
    }
    const message = this.messages.popFront()
    return new Message(message)
  }

  public async putMessage(body: string): Promise<void> {
    this.messages.pushBack(body)
  }

  public async getInfo(): Promise<QueueInfo> {
    const size = this.messages.size()
    return new QueueInfo(size)
  }
}
