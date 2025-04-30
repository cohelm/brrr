export abstract class Call {
  public abstract readonly taskName: string
  public abstract readonly memoKey: string

  public equals(other: Call): boolean {
    return this.memoKey === other.memoKey
  }

  public toString(): string {
    return `Call(${this.taskName})`
  }
}
