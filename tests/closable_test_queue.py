import asyncio


import brrr.queue as q


_CloseSentinel = object()


class ClosableInMemQueue(q.Queue):
    """A message queue which can be closed."""

    def __init__(self):
        self.operational = True
        self.closing = False
        self.received = asyncio.Queue()

    async def close(self):
        assert not self.closing
        self.closing = True
        await self.received.put(_CloseSentinel)

    async def join(self):
        await self.received.join()

    async def get_message(self):
        if not self.operational:
            raise q.QueueIsClosed()

        payload = await self.received.get()
        if payload is _CloseSentinel:
            self.operational = False
            self.received.task_done()
            raise q.QueueIsClosed()

        self.received.task_done()
        return q.Message(body=payload)

    async def put_message(self, body: str):
        assert self.operational
        await self.received.put(body)

    async def get_info(self):
        raise NotImplementedError()
