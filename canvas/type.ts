export interface Class<T, A extends unknown[]> {
  prototype: Pick<T, keyof T>

  new (...args: A): T
}

export type AbstractConstructor<
  T,
  Arguments extends unknown[] = any[]
> = abstract new (...arguments_: Arguments) => T

export interface AbstractClass<T, Arguments extends unknown[] = any[]>
  extends AbstractConstructor<T, Arguments> {
  prototype: Pick<T, keyof T>
}
