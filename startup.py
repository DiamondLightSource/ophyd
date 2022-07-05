import bluesky.plan_stubs as bps
import bluesky.plans as bp
from bluesky import RunEngine
from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.utils import ProgressBarManager

from ophyd.v2.core import NamedAbilities, ReadableSignal, SignalCollector
from ophyd.v2.hardware import motor
from ophyd.v2.providers.ca import CaProvider

# from IPython import get_ipython


RE = RunEngine({})

bec = BestEffortCallback()

# Send all metadata/data captured to the BestEffortCallback.
RE.subscribe(bec)

# Make plots update live while scans run.
# get_ipython().magic("matplotlib qt")


def spy(name, doc):
    print("spy", name, doc)


# RE.subscribe(spy)

# Make a progress bar
RE.waiting_hook = ProgressBarManager()


with SignalCollector(), NamedAbilities():
    ca = SignalCollector.add_provider(CaProvider(), set_default=True)
    x = motor.motor("pc0105-MO-SIM-01:M1")


# Run a step scan
def my_plan():
    yield from bp.scan([], x, 1, 2, 5)
    velo = yield from bps.rd(x.readable_signal("velocity"))
    print(velo)
    # or
    velo = yield from bps.rd(ReadableSignal(x.device.velocity, x.name + "-velocity"))
    print(velo)
    # TODO: Should we name Devices then?
    # But not
    print(x["velocity"])


print(x["velocity"])
RE(my_plan())
