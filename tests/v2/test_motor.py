import asyncio
from unittest.mock import Mock, call

import pytest

from ophyd.v2.core import NamedAbilities, SignalCollector
from ophyd.v2.hardware import motor
from ophyd.v2.providers.sim import SimProvider


async def test_motor_moving():
    async with SignalCollector(), NamedAbilities():
        SignalCollector.add_provider(SimProvider(), set_default=True)
        x = motor.motor("BLxxI-MO-TABLE-01:X")
        # Signals connected here

    assert x.name == "x"
    s = x.set(0.55)
    m = Mock()
    done = Mock()
    s.add_callback(done)
    s.watch(m)
    assert not s.done
    done.assert_not_called()
    await asyncio.sleep(0.3)
    assert not s.done
    assert m.call_count == 3
    await asyncio.sleep(0.3)
    assert s.done
    assert s.success
    assert m.call_count == 6
    assert m.call_args_list[1] == call(
        name="x",
        current=0.1,
        initial=0.0,
        target=0.55,
        unit="mm",
        precision=3,
        time_elapsed=pytest.approx(0.1, abs=0.05),
    )
    done.assert_called_once()
    x.stage()
    assert (await x.read())["x"]["value"] == 0.55
    assert (await x.describe())["x"]["source"] == "sim://BLxxI-MO-TABLE-01:Xreadback"
    assert (await x.read_configuration())["x-velocity"]["value"] == 1
    assert (await x.describe_configuration())["x-egu"]["shape"] == []
    x.unstage()
    s = x.set(1.5)
    await asyncio.sleep(0.2)
    await x.stop()
    await asyncio.sleep(0.2)
    assert s.done
    assert s.success is False
