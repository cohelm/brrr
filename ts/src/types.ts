export type Fn<A extends unknown[], R, T = unknown> = (this: T, ...args: A) => R

export type Maybe<T> = T | undefined
