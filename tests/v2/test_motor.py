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
    await x.trigger()
    assert x.read()["x"]["value"] == 0.55
    assert x.describe()["x"]["source"] == "sim://BLxxI-MO-TABLE-01:Xreadback"
    assert x.read_configuration() == {}
    assert x.describe_configuration() == {}
    s = x.set(1.5)
    s.add_callback(done)
    await asyncio.sleep(0.2)
    x.stop()
    await asyncio.sleep(0.2)
    assert s.done
    with pytest.raises(RuntimeError) as cm:
        await s
    assert str(cm.value) == "Motor was stopped"
