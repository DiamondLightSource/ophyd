import asyncio
from typing import Dict, cast
from unittest.mock import Mock, call

import pytest
from bluesky.protocols import Reading

from ophyd.v2.core import CommsConnector, NamedDevices, SignalDevice
from ophyd.v2.pvsim import PvSim
from ophyd_epics_devices import motor

# Long enough for multiple asyncio event loop cycles to run so
# all the tasks have a chance to run
A_BIT = 0.001


@pytest.fixture
async def sim_motor():
    async with CommsConnector(sim_mode=True), NamedDevices():
        sim_motor = motor.motor("BLxxI-MO-TABLE-01:X")
        # Signals connected here

    assert sim_motor.name == "sim_motor"
    egu = cast(PvSim, sim_motor.comm.egu.read_pv)
    egu.set_value("mm")
    precision = cast(PvSim, sim_motor.comm.precision.read_pv)
    precision.set_value(3)
    velocity = cast(PvSim, sim_motor.comm.velocity.read_pv)
    velocity.set_value(1)
    yield sim_motor


async def test_motor_moving_well(sim_motor: motor.devices.Motor) -> None:
    demand = cast(PvSim, sim_motor.comm.demand.write_pv)
    demand.put_proceeds.clear()
    readback = cast(PvSim, sim_motor.comm.readback.read_pv)
    s = sim_motor.set(0.55)
    watcher = Mock()
    s.watch(watcher)
    await asyncio.sleep(A_BIT)
    assert watcher.call_count == 1
    assert watcher.call_args == call(
        name="sim_motor",
        current=0.0,
        initial=0.0,
        target=0.55,
        unit="mm",
        precision=3,
        time_elapsed=pytest.approx(0.0, abs=0.05),
    )
    watcher.reset_mock()
    assert demand.value == 0.55
    assert not s.done
    await asyncio.sleep(0.1)
    readback.set_value(0.1)
    assert watcher.call_count == 1
    assert watcher.call_args == call(
        name="sim_motor",
        current=0.1,
        initial=0.0,
        target=0.55,
        unit="mm",
        precision=3,
        time_elapsed=pytest.approx(0.1, abs=0.05),
    )
    demand.put_proceeds.set()
    await asyncio.sleep(0)
    assert s.done


async def test_motor_moving_stopped(sim_motor: motor.devices.Motor):
    demand = cast(PvSim, sim_motor.comm.demand.write_pv)
    demand.put_proceeds.clear()
    s = sim_motor.set(1.5)
    await asyncio.sleep(0.2)
    await sim_motor.stop()
    demand.put_proceeds.set()
    await asyncio.sleep(0)
    assert s.done
    assert s.success is False


async def test_read_motor(sim_motor: motor.devices.Motor):
    sim_motor.stage()
    assert (await sim_motor.read())["sim_motor-readback"]["value"] == 0.0
    assert (await sim_motor.describe())["sim_motor-readback"][
        "source"
    ] == "sim://BLxxI-MO-TABLE-01:X.RBV"
    assert (await sim_motor.read_configuration())["sim_motor-velocity"]["value"] == 1
    assert (await sim_motor.describe_configuration())["sim_motor-egu"]["shape"] == []
    readback = cast(PvSim, sim_motor.comm.readback.read_pv)
    readback.set_value(0.5)
    assert (await sim_motor.read())["sim_motor-readback"]["value"] == 0.5
    sim_motor.unstage()
    # Check we can still read and describe when not staged
    readback.set_value(0.1)
    assert (await sim_motor.read())["sim_motor-readback"]["value"] == 0.1
    assert await sim_motor.describe()


async def test_set_velocity(sim_motor: motor.devices.Motor):
    v: SignalDevice = sim_motor.velocity
    assert (await v.describe())["sim_motor-velocity"][
        "source"
    ] == "sim://BLxxI-MO-TABLE-01:X.VELO"
    q: asyncio.Queue[Dict[str, Reading]] = asyncio.Queue()
    v.subscribe(q.put_nowait)
    assert (await q.get())["sim_motor-velocity"]["value"] == 1.0
    await v.set(2.0)
    assert (await q.get())["sim_motor-velocity"]["value"] == 2.0
    v.clear_sub(q.put_nowait)
    await v.set(3.0)
    assert (await v.read())["sim_motor-velocity"]["value"] == 3.0
    assert q.empty()
