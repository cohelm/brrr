from typing import Any, Callable, Union

import asyncio
import threading
import os
import http.server
import socketserver
import json
from urllib.parse import parse_qsl

from .store import Call, Frame, Memory, Store, input_hash
from .queue import Queue, QueueIsEmpty

class Defer(Exception):
    """
    When a task is called and hasn't been computed yet, a Defer exception is raised
    Workers catch this exception and schedule the task to be computed
    """
    calls: list[Call]
    def __init__(self, calls: list[Call]):
        self.calls = calls

# Quick n dirty hack to achieve lazy initialization without fully rewriting this
# entire global using file.  The real solution is to use a singleton and make
# the top level functions proxies to the singleton.
class Brrr:
    """
    All state for brrr to function wrapped in a container.
    """
    # The worker loop (as of writing) is synchronous so it can safely set a
    # local global variable to indicate that it is a worker thread, which, for
    # tasks, means that their Defer raises will be caught and handled by the
    # worker
    worker_singleton: Union['Wrrrker', None]

    # For threaded workers, each worker registers itself in this dict by thread id
    worker_threads: dict[int, 'Wrrrker']

    # For async workers,
    worker_loops: dict[int, 'Wrrrker']

    # A storage backend for frames, calls and values
    memory: Memory | None
    # A queue of frame keys to be processed
    queue: Queue | None

    # Dictionary of task_name to task instance
    tasks = dict[str, 'Task']

    def __init__(self):
        self.worker_singleton = None
        self.worker_threads = {}
        self.worker_loops = {}
        self.tasks = {}
        self.queue = None
        self.memory = None

    # TODO do we like the idea of brrr as a context manager?
    def __enter__(self):
        pass
    def __exit__(self, exc_type, exc_value, traceback):
        if hasattr(self.queue, "__exit__"):
            self.queue.__exit__(exc_type, exc_value, traceback)
        if hasattr(self.memory, "__exit__"):
            self.memory.__exit__(exc_type, exc_value, traceback)

    # TODO Do we want to pass in a memstore/kv instead?
    def setup(self, queue: Queue, store: Store):
        # TODO throw if already instantiated?
        self.queue = queue
        self.memory = Memory(store)

    # TODO would we like this to be a decorator?
    def require_setup(self):
        if self.queue is None or self.memory is None:
            raise Exception("Brrr not set up")

    def are_we_inside_worker_context(self):
        if self.worker_singleton:
            return True
        elif self.worker_threads:
            # For synchronous workers, we can use a thread-local global variable
            return threading.current_thread() in self.worker_threads
        elif self.worker_loops:
            try:
                # For async workers, we can check the asyncio loop
                return asyncio.get_running_loop() in self.worker_loops
            except RuntimeError:
                return False
        else:
            return False


    def gather(self, *task_lambdas) -> list[Any]:
        """
        Takes a number of task lambdas and calls each of them.
        If they've all been computed, return their values,
        Otherwise raise jobs for those that haven't been computed
        """
        self.require_setup()

        if not self.are_we_inside_worker_context():
            return [task_lambda() for task_lambda in task_lambdas]

        defers = []
        values = []

        for task_lambda in task_lambdas:
            try:
                values.append(task_lambda())
            except Defer as d:
                defers.extend(d.calls)

        if defers:
            raise Defer(defers)

        return values

    def schedule(self, call: Call, parent_key=None) -> Frame:
        self.require_setup()

        # Value has been computed already, return straight to the parent (if there is one)
        if self.memory.has_value(call.memo_key):
            if parent_key is not None:
                self.queue.put(parent_key)
            return

        # If not, schedule the child. We don't care if it has been scheduled already for now
        # but we could check, as an optimisation. The set calls are idempotent.
        self.memory.set_call(call)
        child = Frame(call.memo_key, parent_key)
        self.memory.set_frame(child)
        self.queue.put(child.frame_key)

        return child


    def evaluate(self, frame: Frame) -> Any:
        """
        Evaluate a frame, which means calling the tasks function with its arguments
        """
        self.require_setup()

        call = self.memory.get_call(frame.memo_key)
        task = self.tasks[call.task_name]
        return task.evaluate(call.argv)

    def register_task(self, fn: Callable, name: str = None) -> 'Task':
        task = Task(self, fn, name)
        if task.name in self.tasks:
            raise Exception(f"Task {task.name} already exists")
        self.tasks[task.name] = task
        return task

    def task(self, fn: Callable, name: str = None) -> 'Task':
        return Task(self, fn, name)

    def srrrv(self, tasks: list['Task'], port: int = int(os.getenv("SRRRVER_PORT", "8333"))):
        """
        Spin up a webserver that that translates HTTP requests to tasks
        """
        # Srrrver.tasks.update({task.name: task for task in tasks})
        with socketserver.TCPServer(("", port), Srrrver.subclass_with_brrr(self)) as httpd:
            print(f"Srrrver running on port {port}")
            print("Available tasks:")
            for task in tasks:
                print("  ", task.name)
            httpd.serve_forever()

    async def wrrrk_async(self, workers: int = 1):
        """
        Start a number of async worker loops
        """
        await asyncio.gather(
            *(Wrrrker(self).loop_async() for _ in range(workers))
        )

    def wrrrk(self, threads: int = 1):
        """
        Spin up a number of worker threads
        """
        if threads == 1:
            Wrrrker(self).loop()
        else:
            for _ in range(threads):
                threading.Thread(target=Wrrrker(self).loop).start()


class Task:
    """
    A decorator to turn a function into a task.
    When it is called, within the context of a worker, it checks whether it has already been computed.
    If so, it returns the value, otherwise it raises a Call job, which causes the worker to schedule the computation.

    A task can not write to the store, only read from it
    """

    fn: Any
    name: str
    brrr: Brrr

    def __init__(self, brrr: Brrr, fn, name: str = None):
        self.brrr = brrr
        self.fn = fn
        self.name = name or fn.__name__

    # Calling a function returns the value if it has already been computed.
    # Otherwise, it raises a Call exception to schedule the computation
    def __call__(self, *args, **kwargs):
        argv = (args, kwargs)
        if not self.brrr.are_we_inside_worker_context():
            return self.evaluate(argv)
        memo_key = input_hash(self.name, argv)
        try:
            return self.brrr.memory.get_value(memo_key)
        except KeyError:
            raise Defer([Call(self.name, argv)])

    def to_lambda(self, *args, **kwargs):
        """
        Separate function to capture a closure
        """
        return lambda: self(*args, **kwargs)

    def map(self, args: list[Union[dict, list, tuple[tuple, dict]]]):
        """
        Fanning out, a map function returns the values if they have already been computed.
        Otherwise, it raises a list of Call exceptions to schedule the computation,
        for the ones that aren't already computed

        Offers a few syntaxes, TBD whether that is useful
        #TODO we _could_ support a list of elements to get passed as a single arg each
        """
        argvs = [
            (arg, {}) if isinstance(arg, list) else ((), arg) if isinstance(arg, dict) else arg
            for arg in args
        ]
        return self.brrr.gather(*(self.to_lambda(*argv[0], **argv[1]) for argv in argvs))

    def evaluate(self, argv):
        return self.fn(*argv[0], **argv[1])

    def schedule(self, *args, **kwargs):
        """
        This puts the task call on the queue, but doesn't return the result!
        """
        return self.brrr.schedule(Call(self.name, (args, kwargs)))

class Wrrrker:
    def __init__(self, brrr: Brrr):
        self.brrr = brrr

    # The context manager maintains a thread-local global variable to indicate that the thread is a worker
    # and that any invoked tasks can raise Defer exceptions
    def __enter__(self):
        if self.brrr.worker_singleton is not None:
            raise Exception("Worker already running")
        self.brrr.worker_singleton = self

    def __exit__(self, exc_type, exc_value, traceback):
        self.brrr.worker_singleton = None

    def resolve_frame(self, frame_key: str):
        """
        A queue message is a frame key and a receipt handle
        The frame key is used to look up the job to be done,
        the receipt handle is used to tell the queue that the job is done
        """

        frame = self.brrr.memory.get_frame(frame_key)
        try:
            self.brrr.memory.set_value(frame.memo_key, self.brrr.evaluate(frame))
            if frame.parent_key is not None:
                # This is a redundant step, we could just check the store whether the children have memoized values
                # frames[frame.parent_key].children[frame_key] = True
                self.brrr.queue.put(frame.parent_key)
        except Defer as defer:
            for call in defer.calls:
                self.brrr.schedule(call, frame_key)

    # TODO exit when queue empty?
    def loop(self):
        """
        Workers take jobs from the queue, one at a time, and handle them.
        They have read and write access to the store, and are responsible for
        Managing the output of tasks and scheduling new ones
        """
        with self:
            print("Worker Started")
            while True:
                try:
                    # This is presumed to be a long poll
                    message = self.brrr.queue.get_message()
                except QueueIsEmpty:
                    continue

                frame_key = message.body
                self.resolve_frame(frame_key)

                self.brrr.queue.delete_message(message.receipt_handle)

    async def loop_async(self):
        with self:
            while True:
                try:
                    message = await self.brrr.queue.get_message_async()
                except QueueIsEmpty:
                    continue

                frame_key = message.body
                self.resolve_frame(frame_key)

                self.brrr.queue.delete_message(message.receipt_handle)


class ThreadWrrrker(Wrrrker):
    # The context manager maintains a thread-local global variable to indicate that the thread is a worker
    # and that any invoked tasks can raise Defer exceptions
    def __enter__(self):
        tid = threading.current_thread()
        if tid in self.brrr.worker_threads:
            raise Exception("Worker already running in this thread")

        self.brrr.worker_threads[tid] = self
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del self.brrr.worker_threads[threading.current_thread()]


# A "Front Office" worker, that is publically exposed and takes requests
# to schedule tasks and return their results via webhooks
class Srrrver(http.server.SimpleHTTPRequestHandler):
    brrr: Brrr

    @classmethod
    def subclass_with_brrr(cls, brrr: Brrr) -> 'Srrrver':
        """
        For some reason the python server class needs to be instantiated without args
        """
        return type("SrrrverWithBrrr", (cls,), {"brrr": brrr})

    """
    A simple HTTP server that takes a JSON payload and schedules a task
    """
    def do_GET(self):
        """
        GET /task_name?argv={"..."}
        """
        task_name = self.path.split("?")[0].strip("/")
        # TODO parse the argv properly
        kwargs = dict(parse_qsl(self.path.split("?")[-1]))
        argv = ((), kwargs)

        try:
            task = self.brrr.tasks[task_name]
            call = Call(task.name, argv)
        except KeyError:
            self.send_response(404)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Task not found"}).encode())
            return

        try:
            memo_key = call.memo_key
            result = self.brrr.memory.get_value(memo_key)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "result": result}).encode())
        except KeyError:
            self.brrr.schedule(call)
            self.send_response(202)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "accepted"}).encode())
            return

    def do_POST(self):
        """
        POST /{task_name} with a JSON payload {
            "args": [],
            "kwargs": {},
        }

        """
        # Custom behavior for POST requests
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        self.wfile.write(post_data)

        # Schedule a task and submit PUT request to the webhook with the result if one is provided
        # once it's done
        try:
            data = json.loads(post_data)
            call = Call(data["task_name"], (data["args"], data["kwargs"]))
            frame = self.brrr.schedule(call)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            error_response = {"status": "OK", "frame_key": frame.frame_key}
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            error_response = {"error": "Invalid JSON"}
            self.wfile.write(json.dumps(error_response))
