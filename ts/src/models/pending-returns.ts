export class PendingReturns {
  constructor(
    public scheduledAt: string | undefined,
    public readonly returns: Set<string>
  ) {}

  public async encode(): Promise<Uint8Array> {
    const sortedReturns = Array.from(this.returns).sort()
    const jsonString = JSON.stringify([this.scheduledAt, sortedReturns])
    return new TextEncoder().encode(jsonString)
  }

  public static async decode(enc: Uint8Array): Promise<PendingReturns> {
    const jsonString = new TextDecoder().decode(enc)
    const [scheduledAt, returns] = JSON.parse(jsonString)
    return new PendingReturns(scheduledAt, new Set(returns))
  }
}
