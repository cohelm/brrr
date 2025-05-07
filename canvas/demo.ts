import {AbstractTask} from "./abstract-task";
import {Brrr} from "./impl";


/**
 * Most basic way to define a task.
 *
 * Why take the task name as a generic?
 * Because it allows us to enforce `name` to be `readonly`
 *
 * Generics: <taskname, args, result>
 */
export class FibTask extends AbstractTask<'fib', [number], number> {
  public readonly name = 'fib'

  async def(n: number): Promise<number> {
    return n
  }
}

/**
 * Python task? Define it as an abstract class.
 */
export abstract class AddTask extends AbstractTask<'add', [number, number], number> {
  public readonly name = 'add'
}

// === Example Usage ===

const brrr = new Brrr({
  tasks: [FibTask, AddTask]
})

// name of the task, args, and results are all typesafe :)
brrr.tasks.fib.invoke(5)
brrr.tasks.add.invoke(1, 2)
