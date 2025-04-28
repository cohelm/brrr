import type { Brrr } from '../brrr'
import { MemoryValueNotFoundError } from '../libs/error'
import type { Fn } from '../types'
import { Defer } from './defer'

export class Task<const in A extends unknown[], out R> {
  public constructor(
    public readonly brrr: Brrr,
    public readonly name: string,
    public readonly fn: Fn<A, R>
  ) {}

  public async invoke(...args: A): Promise<R> {
    if (!this.brrr.isWorkerContext()) {
      return this.fn(...args)
    }
    this.brrr.requiresSetup()
    const call = this.brrr.memory?.makeCall(this.name, args)
    try {
      const encoded = await this.brrr.memory?.getValue(call)
      return this.brrr.memory?.codec.decodeReturn(encoded)
    } catch (e) {
      if (!(e instanceof MemoryValueNotFoundError)) {
        throw e
      }
      throw new Defer([call])
    }
  }

  public async map(...argsList: A[]): Promise<Awaited<R>[]> {
    return this.brrr.gather(...argsList.map(args => this.invoke(...args)))
  }
}
