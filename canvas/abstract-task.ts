export abstract class AbstractTask<Name extends string, A extends readonly unknown[], R> {
  /**
   * Unique, literal task name (inferred from initializer)
   */
  abstract readonly name: Name;

  /**
   * Task implementation. Must be defined as an arrow-property to enable strict argument checking.
   */
  abstract def(...args: A) : Promise<R>;

  /**
   * Invoke the task with appropriately-typed arguments
   */
  public async invoke(...args: A): Promise<R> {
    return this.def(...args);
  }

  /**
   * Default: JSON-based codec implementation
   */
  public encode(...args: A): Uint8Array {
    return new TextEncoder().encode(JSON.stringify(args));
  }

  public decode(payload: Uint8Array): A {
    const json = new TextDecoder().decode(payload);
    return JSON.parse(json) as A;
  }
}