import bluesky.plan_stubs as bps
import bluesky.plans as bp
from bluesky import RunEngine
from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.utils import ProgressBarManager

from ophyd.v2.core import CommsConnector, NamedDevices, SignalDevice
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
    velo = yield from bps.rd(x.signal_device("velocity"))
    print("inside 1", velo)
    # or
    velo = yield from bps.rd(SignalDevice(x.comm.velocity, x.name + "-velocity"))
    print("inside 2", velo)
    # But not
    # print("but not", x["velocity"])


x["velocity"] = 1
print("outside1", x["velocity"])
x["velocity"] = 2
print("outside2", x["velocity"])
RE(my_plan())
