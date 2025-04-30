import type { Call } from './call'

export class Defer {
  constructor(public readonly calls: Call[]) {}
}
