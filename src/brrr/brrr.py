from typing import Any, Callable, Union

import logging

from .store import AlreadyExists, Call, CompareMismatch, Memory, Store, input_hash
from .queue import Queue, QueueIsClosed, QueueIsEmpty

logger = logging.getLogger(__name__)


class Defer(Exception):
    """
    When a task is called and hasn't been computed yet, a Defer exception is raised
    Workers catch this exception and schedule the task to be computed
    """

    calls: list[Call]

    def __init__(self, calls: list[Call]):
        self.calls = calls


class Brrr:
    """
    All state for brrr to function wrapped in a container.
    """

    def requires_setup(method):
        def wrapper(self, *args, **kwargs):
            if self.queue is None or self.memory is None:
                raise Exception("Brrr not set up")
            return method(self, *args, **kwargs)

        return wrapper

    # The worker loop (as of writing) is synchronous so it can safely set a
    # local global variable to indicate that it is a worker thread, which, for
    # tasks, means that their Defer raises will be caught and handled by the
    # worker
    worker_singleton: Union["Wrrrker", None]

    # A storage backend for calls, values and pending returns
    memory: Memory | None
    # A queue of call keys to be processed
    queue: Queue | None

    # Dictionary of task_name to task instance
    tasks = dict[str, "Task"]

    def __init__(self):
        self.tasks = {}
        self.queue = None
        self.memory = None
        self.worker_singleton = None

    # TODO Do we want to pass in a memstore/kv instead?
    def setup(self, queue: Queue, store: Store):
        # TODO throw if already instantiated?
        self.queue = queue
        self.memory = Memory(store)

    def are_we_inside_worker_context(self) -> bool:
        return self.worker_singleton

    @requires_setup
    def gather(self, *task_lambdas) -> list[Any]:
        """
        Takes a number of task lambdas and calls each of them.
        If they've all been computed, return their values,
        Otherwise raise jobs for those that haven't been computed
        """
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

    def schedule(self, task_name: str, args: tuple, kwargs: dict):
        """Public-facing one-shot schedule method.

        The exact API for the type of args and kwargs is still WIP.  We're doing
        (args, kwargs) for now but it's WIP.

        Don't use this internally.

        """
        return self._schedule_call(Call(task_name, (args, kwargs)))

    @requires_setup
    def _schedule_call(self, call: Call, parent_key=None):
        """Schedule this call on the brrr workforce.

        This is the real internal entrypoint which should be used by all brrr
        internal-facing code, to avoid confusion about what's internal API and
        what's external.

        """
        # Value has been computed already, return straight to the parent (if there is one)
        if self.memory.has_value(call.memo_key):
            if parent_key is not None:
                self.queue.put(parent_key)
            return

        # If this call has previously been scheduled, don't reschedule it
        if not self.memory.has_call(call):
            self.memory.set_call(call)
            self.queue.put(call.memo_key)

        if parent_key is not None:
            self.memory.add_pending_returns(call.memo_key, set([parent_key]))

    @requires_setup
    def read(self, task_name: str, args: tuple, kwargs: dict):
        """
        Returns the value of a task, or raises a KeyError if it's not present in the store
        """
        memo_key = Call(task_name, (args, kwargs)).memo_key
        return self.memory.get_value(memo_key)

    @requires_setup
    def evaluate(self, call: Call) -> Any:
        """
        Evaluate a frame, which means calling the tasks function with its arguments
        """
        task = self.tasks[call.task_name]
        return task.evaluate(call.argv)

    def register_task(self, fn: Callable, name: str = None) -> "Task":
        task = Task(self, fn, name)
        if task.name in self.tasks:
            raise Exception(f"Task {task.name} already exists")
        self.tasks[task.name] = task
        return task

    def task(self, fn: Callable, name: str = None) -> "Task":
        return Task(self, fn, name)

    async def wrrrk_async(self, workers: int = 1):
        """
        Start a number of async worker loops
        """
        await Wrrrker(self).loop_async()

    def wrrrk(self):
        """
        Spin up a single brrr worker.
        """
        Wrrrker(self).loop()


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
            (arg, {})
            if isinstance(arg, list)
            else ((), arg)
            if isinstance(arg, dict)
            else arg
            for arg in args
        ]
        return self.brrr.gather(
            *(self.to_lambda(*argv[0], **argv[1]) for argv in argvs)
        )

    def evaluate(self, argv):
        return self.fn(*argv[0], **argv[1])

    def schedule(self, *args, **kwargs):
        """
        This puts the task call on the queue, but doesn't return the result!
        """
        call = Call(self.name, (args, kwargs))
        return self.brrr._schedule_call(call)


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

    def resolve_call(self, memo_key: str):
        """
        A queue message is a frame key and a receipt handle
        The frame key is used to look up the job to be done,
        the receipt handle is used to tell the queue that the job is done
        """

        call = self.brrr.memory.get_call(memo_key)

        logger.info("Resolving %s %s %s", memo_key, call.task_name, call.argv)

        try:
            value = self.brrr.evaluate(call)
        except Defer as defer:
            for call in defer.calls:
                self.brrr._schedule_call(call, memo_key)
            return

        # We can end up in a race against another worker to write the value.
        # We only accept the first entry and the rest will be bounced
        try:
            self.brrr.memory.set_value(call.memo_key, value)
        except AlreadyExists:
            # It is possible that we can formally prove that this situation means we don't need to
            # requeue here. Until then, let's just feel safer and run through any pending parents below.
            pass

        # Now we need to make sure that we enqueue all the parents.
        # We keep some local state here while we try to compare-and-delete our way out
        # Due to idempotency, the failure mode is fine here, since we only ever delete
        # the pending return list after all of themn have been enqueued
        # For a particularly hot job, it is possible that this gets "stuck" enqueuing
        # new parents over and over. That is mostly a problem because it could cause
        # the pending return list to grow out of bounds.

        # TODO This try except jungle needs work. Not sure who wants to throw and who wants to return None

        handled_returns = set()
        try:
            all_returns = self.brrr.memory.get_pending_returns(call.memo_key)
        except KeyError:
            return

        for memo_key in all_returns - handled_returns:
            self.brrr.queue.put(memo_key)

        try:
            self.brrr.memory.delete_pending_returns(call.memo_key, all_returns)
        except CompareMismatch:
            # TODO tried to loop here but the dynamo CAS wasn't working. Perhaps revisit at some point
            # Not required though as the root level task will eventually clean this up
            pass

    # TODO exit when queue empty?
    def loop(self):
        """
        Workers take jobs from the queue, one at a time, and handle them.
        They have read and write access to the store, and are responsible for
        Managing the output of tasks and scheduling new ones
        """
        with self:
            logger.info("Worker Started")
            while True:
                try:
                    # This is presumed to be a long poll
                    message = self.brrr.queue.get_message()
                except QueueIsEmpty:
                    logger.info("Queue is empty")
                    continue
                except QueueIsClosed:
                    logger.info("Queue is closed")
                    return

                memo_key = message.body
                self.resolve_call(memo_key)

                self.brrr.queue.delete_message(message.receipt_handle)

    async def loop_async(self):
        async with self:
            logger.info("Worker Started")
            while True:
                try:
                    message = await self.brrr.queue.get_message_async()
                except QueueIsEmpty:
                    logger.info("Queue is empty")
                    continue
                except QueueIsClosed:
                    logger.info("Queue is closed")
                    return

                memo_key = message.body
                self.resolve_call(memo_key)

                self.brrr.queue.delete_message(message.receipt_handle)
