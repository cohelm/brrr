import { QueueIsClosedError, QueueIsEmptyError } from '../../src/libs/error'
import { Message, Queue, QueueInfo } from '../../src/models/queue'

export class InMemoryQueue extends Queue {
  private readonly messages: string[] = []
  private closed = false

  public async getMessage(): Promise<Message> {
    if (this.closed) {
      throw new QueueIsClosedError()
    }
    if (!this.messages) {
      throw new QueueIsEmptyError()
    }
    return new Message(this.messages.shift() || '')
  }

  public async putMessage(body: string): Promise<void> {
    this.messages.push(body)
  }

  public getInfo(): QueueInfo {
    return new QueueInfo(this.messages.length)
  }
}
