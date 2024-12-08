import asyncio

async def async_wrrrk(workers: int = 1):
    """
    Spin up a number of worker threads
    """
    return asyncio.gather(
        *[asyncio.create_task(asyncio_worker()) for _ in range(workers)]
    )
