export interface Cache {
  incr(key: string): Promise<number>;
}
