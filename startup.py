import bluesky.plan_stubs as bps
import bluesky.plans as bp
from bluesky import RunEngine
from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.utils import ProgressBarManager

from ophyd.v2.core import CommsConnector, NamedDevices, ReadableSignal
from ophyd_epics_devices import motor

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


with CommsConnector(), NamedDevices():
    x = motor.motor("pc0105-MO-SIM-01:M1")


# Run a step scan
def my_plan():
    yield from bp.scan([], x, 1, 2, 5)
    velo = yield from bps.rd(x.readable_signal("velocity"))
    print("inside 1", velo)
    # or
    velo = yield from bps.rd(ReadableSignal(x.comms.velocity, x.name + "-velocity"))
    print("inside 2", velo)
    # TODO: Should we name Devices then?
    # But not
    print("but not", x["velocity"])


print("outside", x["velocity"])
RE(my_plan())
