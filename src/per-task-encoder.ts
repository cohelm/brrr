import { Brrr } from './brrr'

abstract class AbstractTask<A extends unknown[], R> {
  abstract readonly name: string

  abstract def(...args: A): Promise<R>

  public async invoke(...args: A): Promise<R> {
    // DO NOT OVERRIDE
    // maybe make it private, then forcibly access within SDK?
    // or, we can do this: `brrr.invoke(this, ...args)`, dual API approach?
  }

  // default impl - naive codec, or use whatever was set up using `brrr::setup`
  public encode(...args: A): Uint8Array {
    return new TextEncoder().encode(JSON.stringify(args))
  }

  // same here
  public decode(payload: Uint8Array): A {
    const json = new TextDecoder().decode(payload)
    return JSON.parse(json) as A
  }
}

/**
 * Sample task definition. Simple Fib task, with custom per-task encoder
 */
class FibTask extends AbstractTask<[number], number> {
  public readonly name = 'sample_fib'

  async def(n: number): Promise<number> {
    return n <= 1
      ? n
      : await brrr.gather(this.invoke(n - 1), this.invoke(n - 2))
  }

  // optional, typesafe encoder
  public override encode(...args: [number]): Uint8Array {
    // BYO-Encoder
  }
}

const brrr = new Brrr({
  cache: new Cache(),
  queue: new Queue(),
  tasks: [new FibTask()]
})

brrr.task('sample_fib').invoke(10)