from typing import Callable

from .brrr import Task

class CompatTask(Task):
    def to_deployment(self):
        return self

def serve(*tasks):
    pass

def deploy(*tasks):
    pass

def task(
    fn=None,
    *,
    name: str = None,
    description: str = None,
    timeout_seconds: int = None,
    cache_key_fn: Callable[[tuple[tuple, dict]], str] = None,
    cache_expiration: int = None,
    retries: int = None,
    retry_delay_seconds: int = None,
    log_prints: bool,
    **kwargs
):
    def decorator(_fn):
        return CompatTask(
            _fn,
            name=name or _fn.__name__,
        )
    return decorator if fn is None else decorator(fn)


def flow(
    fn=None,
    *,
    name: str = None,
    description: str = None,
    timeout_seconds: int = None,
    retries: int = None,
    retry_delay_seconds: int = None,
    flow_run_name: str = None,
    validate_parameters: bool = None,
    version: str = None,
):
    return task(fn, name=name, description=description, timeout_seconds=timeout_seconds, retries=retries, retry_delay_seconds=retry_delay_seconds)
