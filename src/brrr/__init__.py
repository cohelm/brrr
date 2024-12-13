from .brrr import Brrr

# For ergonomics, we provide a singleton and a bunch of proxies as the module interface
brrr = Brrr()

setup = brrr.setup
gather = brrr.gather
wrrrk = brrr.wrrrk
task = brrr.register_task
schedule = brrr.schedule
