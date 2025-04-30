import bencode from 'bencode'

export class PendingReturns {
  constructor(
    public scheduledAt: number,
    public readonly returns: Set<string>
  ) {}

  public async encode(): Promise<Uint8Array> {
    const sortedReturns = Array.from(this.returns).sort()
    return bencode.encode([this.scheduledAt, sortedReturns])
  }

  public static async decode(enc: Uint8Array): Promise<PendingReturns> {
    const [scheduledAt, sortedReturns] = bencode.decode(Buffer.from(enc))
    const decoder = new TextDecoder()
    return new PendingReturns(
      scheduledAt,
      new Set(sortedReturns.map((it: Uint8Array) => decoder.decode(it)))
    )
  }
}
