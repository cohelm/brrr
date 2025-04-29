import { randomUUID } from 'node:crypto'
import {
  BrrrNotSetupError,
  DuplicateTaskError,
  InvalidTaskNameError,
  SpawnLimitError,
  TaskNotFoundError
} from '../libs/error'
import type { Fn } from '../libs/types'
import type { Cache } from '../models/cache'
import type { Call } from '../models/call'
import { Defer } from '../models/defer'
import type { Memory } from '../models/memory'
import type { Queue } from '../models/queue'
import { Task } from '../models/task'
import { Wrrrker } from './wrrrker'

type BrrrConfig = Readonly<{
  cache: Cache
  queue: Queue
  memory: Memory
}>

export class Brrr {
  public cache?: Cache
  public memory?: Memory
  public queue?: Queue
  public workerSingleton?: Wrrrker

  private readonly tasks = new Map<string, Task<unknown[], unknown>>()
  public readonly SPAWN_LIMIT = 500

  public setup({ cache, queue, memory }: BrrrConfig): void {
    this.cache = cache
    this.queue = queue
    this.memory = memory
  }

  public isWorkerContext(): this is Brrr & {
    workerSingleton: Wrrrker
  } {
    return this.workerSingleton !== undefined
  }

  public requiresSetup(): asserts this is Brrr & BrrrConfig {
    if (!this.cache || !this.queue || !this.memory) {
      throw new BrrrNotSetupError()
    }
  }

  public async schedule<A extends unknown[]>(
    task: Task<A, unknown>,
    args: A
  ): Promise<void>
  public async schedule(taskName: string, args: unknown[]): Promise<void>
  public async schedule<A extends unknown[]>(
    ...args: [string | Task<A, unknown>, A]
  ): Promise<void> {
    this.requiresSetup()
    const call = this.memory.makeCall(
      typeof args[0] === 'string' ? args[0] : args[0].name,
      args[1]
    )
    if (await this.memory.hasCall(call)) {
      return
    }
    return this.scheduleRootCall(call)
  }

  private async scheduleRootCall(call: Call): Promise<void> {
    this.requiresSetup()
    await this.memory.setCall(call)
    const rootId = Buffer.from(randomUUID().replaceAll('-', ''), 'hex')
      .toString('base64url')
      .replaceAll('=', '')
    await this.putJob(call.memoKey, rootId)
  }

  public async scheduleCallNested(
    child: Call,
    rootId: string,
    parentKey: string
  ): Promise<void> {
    this.requiresSetup()
    await this.memory.setCall(child)
    await this.memory.addPendingReturn(child.memoKey, parentKey, () => {
      return this.putJob(child.memoKey, rootId)
    })
  }

  public async putJob(memoKey: string, rootId: string): Promise<void> {
    this.requiresSetup()
    if ((await this.cache.incr(`brrr_count/${rootId}`)) > this.SPAWN_LIMIT) {
      throw new SpawnLimitError(this.SPAWN_LIMIT, rootId, memoKey)
    }
    this.queue.putMessage(`${rootId}/${memoKey}`)
  }

  public async callTask(
    taskName: string,
    memoKey: string,
    payload: Uint8Array
  ): Promise<Uint8Array> {
    this.requiresSetup()
    const task = this.tasks.get(taskName)
    if (!task) {
      throw new TaskNotFoundError(taskName)
    }
    return this.memory.codec.invokeTask(memoKey, task, payload)
  }

  public async read<A extends unknown[], R>(
    taskName: string,
    args: A
  ): Promise<R> {
    this.requiresSetup()
    const call = this.memory.makeCall(taskName, args)
    const encoded = await this.memory.getValue(call)
    return this.memory.codec.decodeReturn(encoded)
  }

  public task<A extends unknown[], R>(fn: Fn<A, R>): Task<A, R>
  public task<A extends unknown[], R>(name: string, fn: Fn<A, R>): Task<A, R>
  public task<A extends unknown[], R>(
    ...args: [string | Fn<A, R>, Fn<A, R>?]
  ): Task<A, R> {
    if (typeof args[0] === 'string' && args[1]) {
      const task = new Task<A, R>(this, args[0], args[1])
      if (this.tasks.has(args[0])) {
        throw new DuplicateTaskError(args[0])
      }
      this.tasks.set(args[0], task as Task<unknown[], unknown>)
      return task
    }
    const fn = args[0] as Fn<A, R>
    if (!fn.name) {
      throw new InvalidTaskNameError(fn.name)
    }
    if (this.tasks.has(fn.name)) {
      throw new DuplicateTaskError(fn.name)
    }
    const task = new Task<A, R>(this, fn.name, fn)
    this.tasks.set(task.name, task as Task<unknown[], unknown>)
    return task
  }

  public async gather<R>(...invocations: Promise<R>[]): Promise<Awaited<R>[]> {
    if (!this.isWorkerContext()) {
      return Promise.all(invocations)
    }
    const calls: Call[] = []
    const results: Awaited<R>[] = []
    for (const invocation of invocations) {
      try {
        results.push(await invocation)
      } catch (defer) {
        if (!(defer instanceof Defer)) {
          throw defer
        }
        calls.push(...defer.calls)
      }
    }
    if (calls.length) {
      throw new Defer(calls)
    }
    return results
  }

  public async wrrrk(): Promise<void> {
    await using worker = new Wrrrker(this)
    await worker.loop()
  }
}
