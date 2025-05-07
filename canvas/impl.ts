import {AbstractTask} from './canvas/abstract-task'

type AbstractTaskClass = (abstract new () => AbstractTask<any, any, any>)
  & { name: string }

export type TaskMapFromList<T extends readonly AbstractTaskClass[]> = {
  [C in T[number] as InstanceType<C>['name']]: InstanceType<C>
}

export class Brrr<T extends readonly AbstractTaskClass[]> {
  public readonly tasks: TaskMapFromList<T>

  constructor(props: { tasks: T }) {
    this.tasks = {} as TaskMapFromList<T>
    for (const Task of props.tasks) {
      const instance = new Task()
      this.tasks[instance.name] = instance
    }
  }
}

// === Example Tasks ===
