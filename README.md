# Brrr: high performance workflow scheduling

Brrr is a POC for ultra high performance workflow scheduling.

Differences between Brrr and other workflow schedulers:

- Brrr is **queue & database agnostic**. Others lock you in to e.g. PostgreSQL, which inevitably becomes an unscalable point of failure.
- Brrr **lets the queue & database provide stability & concurrency guarantees**.  Others tend to reinvent the wheel and reimplement a half-hearted queue on top of a database.  Brrr lets your queue and DB do what they do best.
- Brrr **requires idempotency** of the call graph.  It’s ok if your tasks return a different result per call, but the sub tasks they spin up must always be exactly the same, with the same inputs.
- Brrr tasks **look sequential & blocking**.  Your Python code looks like a simple linear function.
- Brrr tasks **aren’t actually blocking** which means you don’t need to lock up RAM in your fleet equivalent to the entire call graph’s execution stack.  In other words: A Brrr fleet’s memory usage is *O(fleet)*, not *O(call graph)*.
- Brrr offers **no logging, monitoring, error handling, or tracing**.  Brrr does one thing and one thing only: workflow scheduling.  Bring your own logging.
- Brrr has **no agent**.  Every worker connects directly to the underlying queue, jobs are scheduled by directly sending them to the queue.  This allows *massive parallelism*: your only limit is your queue & DB capacity.

N.B.: That last point means that you can use Brrr with SQS & DynamoDB to scale basically as far as your wallet can stretch without any further config.

There are currently implementations for Redis and SQS as queues, and for DynamoDB as a database.

## Python Library

Brrr is a dependency-free Python uv bundle which you can import and use directly.

Look at the [`brrr_demo.py`](brrr_demo.py) file for a full demo.

Highlights:

```py
from brrr import task

@task
async def fib(n: int, salt=None):
    match n:
        case 0: return 0
        case 1: return 1
        case _: return sum(await fib.map([[n - 2, salt], [n - 1, salt]]))

@task
async def fib_and_print(n: str):
    f = await fib(int(n))
    print(f"fib({n}) = {f}", flush=True)
    return f

@task
async def hello(greetee: str):
    greeting = f"Hello, {greetee}!"
    print(greeting, flush=True)
    return greeting
```

Note: the `fib()` function looks like it blocks for two sub-calls to `fib(n-1)` and `fib(n-2)`, but in reality it is aborted and re-executed multiple times until all its inputs are available.

Benefit: your code looks intuitive.

Drawback: the call graph must be idempotent, meaning: for the same inputs, a task must always call the same sub-tasks with the same arguments.  It is allowed to return a different result each time.


## Demo

Requires [Nix](https://nixos.org), with flakes enabled.

You can start the full demo without installation:

```
$ nix run github:nobssoftware/brrr#demo
```

In the process list, select the worker process so you can see its output.   Now in another terminal:

```
$ curl 'http://localhost:8333/hello?greetee=John'
```

You should see the worker print a greeting.

You can also run a Fibonacci job:

```
$ curl 'http://localhost:8333/fib_and_print?n=11'
```


## Copyright & License

Brrr was written by Robin Lewis and Jesse Zwaan.  It is available under the AGPLv3 license (not later).

See the [LICENSE](LICENSE) file.
