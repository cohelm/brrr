import type { Brrr } from './brrr'
import {
  MemoryKeyAlreadyExistsError,
  QueueIsClosedError,
  QueueIsEmptyError,
  WorkerAlreadyRunningError
} from './libs/error'
import { Defer } from './models/defer'

export class Wrrrker implements AsyncDisposable {
  public constructor(private readonly brrr: Brrr) {
    if (this.brrr.workerSingleton) {
      throw new WorkerAlreadyRunningError()
    }
    this.brrr.workerSingleton = this
  }

  public async [Symbol.asyncDispose](): Promise<void> {
    this.brrr.workerSingleton = undefined
  }

  private parseCallId(callId: string): {
    rootId: string
    memoKey: string
  } {
    const [rootId, memoKey] = callId.split('/')
    return { rootId, memoKey }
  }

  private async handleMessage(callId: string): Promise<void> {
    this.brrr.requiresSetup()
    const { rootId, memoKey } = this.parseCallId(callId)
    const { taskName, payload } = await this.brrr.memory.getCallBytes(memoKey)
    try {
      const encodedReturn = await this.brrr.callTask(taskName, memoKey, payload)
      await this.brrr.memory?.setValue(memoKey, encodedReturn).catch(err => {
        if (!(err instanceof MemoryKeyAlreadyExistsError)) {
          throw err
        }
      })
      await this.brrr.memory.withPendingReturnsRemove(
        memoKey,
        async pendingReturns => {
          for (const pending of pendingReturns) {
            await this.scheduleReturnCall(pending)
          }
        }
      )
    } catch (error) {
      if (!(error instanceof Defer)) {
        throw error
      }
      for (const call of error.calls) {
        await this.brrr.scheduleCallNested(call, rootId, callId)
      }
    }
  }

  public async scheduleReturnCall(parentId: string): Promise<void> {
    const { rootId, memoKey } = this.parseCallId(parentId)
    return this.brrr.putJob(memoKey, rootId)
  }

  public async loop(): Promise<void> {
    this.brrr.requiresSetup()
    while (true) {
      try {
        const message = await this.brrr.queue?.getMessage()
        await this.handleMessage(message.body)
      } catch (e) {
        if (e instanceof QueueIsEmptyError) {
          continue
        }
        if (e instanceof QueueIsClosedError) {
          return
        }
        throw e
      }
    }
  }
}
