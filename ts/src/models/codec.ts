import type { Fn } from '../libs/types';
import type { Call } from './call';

export interface Codec {
  createCall<A extends unknown[]>(taskName: string, args: A): Call;

  encodeCall(call: Call): Uint8Array;

  invokeTask<A extends unknown[], R>(
    memoKey: string,
    taskName: string,
    taskFn: Fn<A, R>,
    payload: Uint8Array
  ): Promise<Uint8Array>;

  decodeReturn<R>(payload: Uint8Array): R;
}
