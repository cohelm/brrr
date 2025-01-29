import asyncio


import brrr.queue as q


_CloseSentinel = object()


class ClosableInMemQueue(q.Queue):
    """A message queue which can be closed."""

    def __init__(self):
        self.operational = True
        self.closing = False
        self.i = 0
        self.received = asyncio.Queue()
        self.handling = {}

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

        handle = str(self.i)
        self.i += 1
        self.handling[handle] = payload
        return q.Message(body=payload, receipt_handle=handle)

    async def put(self, body: str):
        assert self.operational
        await self.received.put(body)

    async def delete_message(self, receipt_handle: str):
        assert self.operational
        del self.handling[receipt_handle]
        self.received.task_done()

    async def set_message_timeout(self, receipt_handle: str, seconds: int):
        assert receipt_handle in self.handling

    async def get_info(self):
        raise NotImplementedError()
