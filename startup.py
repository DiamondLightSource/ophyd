import bluesky.plan_stubs as bps
import bluesky.plans as bp
from bluesky import RunEngine
from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.utils import ProgressBarManager
from IPython import get_ipython

from ophyd.v2.core import CommsConnector, NamedDevices
from ophyd.v2.magics import OphydMagics
from ophyd_epics_devices import motor

get_ipython().register_magics(OphydMagics)


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
    x = motor.motor("pc0105-MO-SIM-01:M1", name="t1-x")


# Run a step scan
def my_plan():
    # The mypy compatible way
    yield from bps.mv(x.signal_device("velocity"), 1000)
    yield from bp.scan([], x, 1, 2, 5)
    # The shortcut way
    velo = yield from bps.rd(x.velocity)
    print(velo)


RE(my_plan())

# on commandline
# mov x.velocity 1
# mov det.stat.centroid "Don't use me"
