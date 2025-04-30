export type Fn<A extends unknown[], R, T = unknown> = (this: T, ...args: A) => R
