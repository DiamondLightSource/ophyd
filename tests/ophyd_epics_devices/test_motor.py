import asyncio
from unittest.mock import Mock, call

import pytest

from ophyd.v2.core import CommsConnector, NamedDevices
from ophyd.v2.pvsim import PvSim
from ophyd_epics_devices import motor


@pytest.fixture
async def sim_motor():
    async with CommsConnector(sim_mode=True), NamedDevices():
        sim_motor = motor.motor("BLxxI-MO-TABLE-01:X")
        # Signals connected here

    assert sim_motor.name == "sim_motor"
    egu: PvSim = sim_motor.comms.egu.read_pv
    egu.set_value("mm")
    precision: PvSim = sim_motor.comms.precision.read_pv
    precision.set_value(3)
    velocity: PvSim = sim_motor.comms.velocity.read_pv
    velocity.set_value(1)
    yield sim_motor


async def test_motor_moving_well(sim_motor: motor.devices.Motor) -> None:
    demand: PvSim = sim_motor.comms.demand.write_pv
    demand.put_proceeds.clear()
    readback: PvSim = sim_motor.comms.readback.read_pv
    s = sim_motor.set(0.55)
    m = Mock()
    s.watch(m)
    await asyncio.sleep(0)
    assert demand.value == 0.55
    assert not s.done
    readback.set_value(0.1)
    await asyncio.sleep(0.1)
    assert m.call_count == 1
    assert m.call_args == call(
        name="sim_motor",
        current=0.1,
        initial=0.0,
        target=0.55,
        unit="mm",
        precision=3,
        time_elapsed=pytest.approx(0.0, abs=0.1),
    )
    demand.put_proceeds.set()
    await asyncio.sleep(0)
    assert s.done


async def test_motor_moving_stopped(sim_motor: motor.devices.Motor):
    demand: PvSim = sim_motor.comms.demand.write_pv
    demand.put_proceeds.clear()
    s = sim_motor.set(1.5)
    await asyncio.sleep(0.2)
    await sim_motor.stop()
    demand.put_proceeds.set()
    await asyncio.sleep(0.1)
    assert s.done
    assert s.success is False


async def test_read_motor(sim_motor: motor.devices.Motor):
    sim_motor.stage()
    assert (await sim_motor.read())["sim_motor"]["value"] == 0.0
    assert (await sim_motor.describe())["sim_motor"][
        "source"
    ] == "sim://BLxxI-MO-TABLE-01:X.RBV"
    assert (await sim_motor.read_configuration())["sim_motor-velocity"]["value"] == 1
    assert (await sim_motor.describe_configuration())["sim_motor-egu"]["shape"] == []
    readback: PvSim = sim_motor.comms.readback.read_pv
    readback.set_value(0.5)
    assert (await sim_motor.read())["sim_motor"]["value"] == 0.0
    await asyncio.sleep(0)
    assert (await sim_motor.read())["sim_motor"]["value"] == 0.5
    sim_motor.unstage()
    with pytest.raises(AssertionError) as cm:
        (await sim_motor.read())["sim_motor"]["value"]
    assert str(cm.value) == "stage() not called or name not set"
