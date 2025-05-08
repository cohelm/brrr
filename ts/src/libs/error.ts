import type { MemKey } from '../models/memory';

abstract class BrrrError extends Error {
  protected constructor(message: string) {
    super();
    this.name = this.constructor.name;
    this.message = message;
  }
}

export class BrrrNotSetupError extends BrrrError {
  public constructor() {
    super('Brrr is not setup');
  }
}

export class SpawnLimitError extends BrrrError {
  public constructor(spawnLimit: number, rootId: string, memoKey: string) {
    super(`Spawn limit ${spawnLimit} reached for ${rootId} at job ${memoKey}`);
  }
}

export class InvalidTaskNameError extends BrrrError {
  public constructor(taskName: string) {
    super(
      taskName
        ? `Task name "${taskName}" is invalid`
        : 'Task name is empty - are you using an anonymous function?'
    );
  }
}

export class TaskNotFoundError extends BrrrError {
  public constructor(taskName: string) {
    super(`Task ${taskName} not found`);
  }
}

export class MemoryKeyAlreadyExistsError extends BrrrError {
  public constructor(memoKey: string) {
    super(`Key already exists for call ${memoKey}`);
  }
}

export class MemoryValueNotFoundError extends BrrrError {
  public constructor(memoKey: string) {
    super(`Value not found for call ${memoKey}`);
  }
}

export class DuplicateTaskError extends BrrrError {
  public constructor(taskName: string) {
    super(`Task ${taskName} already exists`);
  }
}

export class QueueIsClosedError extends BrrrError {
  public constructor() {
    super('Queue is closed');
  }
}

export class QueueIsEmptyError extends BrrrError {
  public constructor() {
    super('Queue is empty');
  }
}

export class QueuePopTimeoutError extends BrrrError {
  public constructor() {
    super('Queue pop timed out');
  }
}

export class WorkerAlreadyRunningError extends BrrrError {
  public constructor() {
    super('Worker already running');
  }
}

export class CompareMismatchError extends BrrrError {
  public constructor(key: MemKey) {
    super(`Key ${key.toString()} does not match expected value`);
  }
}

export class CasRetryLimitError extends BrrrError {
  public constructor(retryLimit: number) {
    super(`CAS retry limit ${retryLimit} reached`);
  }
}
