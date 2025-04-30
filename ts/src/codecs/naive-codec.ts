import type { Fn } from '../libs/types'
import { Call } from '../models/call'
import type { Codec } from '../models/codec'

export class NaiveCall extends Call {
  public readonly taskName: string
  public readonly args: unknown[]
  public readonly memoKey: string

  constructor(taskName: string, args: unknown[]) {
    super()
    this.taskName = taskName
    this.args = args
    this.memoKey = JSON.stringify([taskName, args])
  }
}

export class NaiveCodec implements Codec {
  public createCall<A extends unknown[]>(taskName: string, args: A): NaiveCall {
    return new NaiveCall(taskName, args)
  }

  public encodeCall(call: NaiveCall): Uint8Array {
    const json = JSON.stringify(call.args)
    return new TextEncoder().encode(json)
  }

  public async invokeTask<A extends unknown[], R>(
    memoKey: string,
    taskName: string,
    taskFn: Fn<A, R>,
    payload: Uint8Array
  ): Promise<Uint8Array> {
    const json = new TextDecoder().decode(payload)
    const args = JSON.parse(json) as A
    const result = await taskFn(...args)
    const resultJson = JSON.stringify(result)
    return new TextEncoder().encode(resultJson)
  }

  public decodeReturn<R>(payload: Uint8Array): R {
    const json = new TextDecoder().decode(payload)
    return JSON.parse(json) as R
  }
}
