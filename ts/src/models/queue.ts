export class QueueInfo {
  constructor(public readonly length: number) {}
}

export class Message {
  constructor(public readonly body: string) {}
}

export abstract class Queue {
  protected readonly RECV_BLOCK_SECS = 20

  abstract putMessage(body: string): Promise<void>

  abstract getMessage(): Promise<Message>

  abstract getInfo(): Promise<QueueInfo>

  abstract close(): Promise<void>
}
