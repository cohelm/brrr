from .brrr import Brrr, SpawnLimitError

# Export only.  Silence linter.
assert SpawnLimitError

# For ergonomics, we provide a singleton and a bunch of proxies as the module interface.
_brrr = Brrr()

setup = _brrr.setup
gather = _brrr.gather
read = _brrr.read
wrrrk = _brrr.wrrrk
task = _brrr.register_task
tasks = _brrr.tasks
schedule = _brrr.schedule
