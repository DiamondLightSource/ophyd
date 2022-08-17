import asyncio

import pytest

from ophyd.v2.core import CommsConnector
from ophyd.v2.epics import EpicsComm, EpicsSignalRO, EpicsSignalRW, epics_connector
from ophyd.v2.pv import Pv, uninstantiatable_pv


def test_uninstantiatable_pv():
    pv = uninstantiatable_pv("ca")
    with pytest.raises(LookupError) as cm:
        pv("pv_prefix")
    assert (
        str(cm.value) == "Can't make a ca pv as the correct libraries are not installed"
    )


async def test_disconnected_signal():
    signal = EpicsSignalRO(Pv, object)
    with pytest.raises(NotImplementedError) as cm:
        await signal.get_reading()
    assert (
        str(cm.value) == "No PV has been set as EpicsSignal.connect has not been called"
    )


class Base(EpicsComm):
    s1: EpicsSignalRO[int]
    s2: EpicsSignalRO[float]


class Derived(Base):
    s2: EpicsSignalRW[float]  # type: ignore
    s3: EpicsSignalRO[str]


@epics_connector
async def derived_connector(comm: Derived, pv_prefix: str):
    coros = [sig.connect(pv_prefix + name) for name, sig in comm._signals_.items()]
    await asyncio.gather(*coros)


async def test_inherited_comms():
    async with CommsConnector(sim_mode=True):
        d = Derived("prefix:")
    assert isinstance(d.s3, EpicsSignalRO)
    assert d.s3.source == "sim://prefix:s3"
    assert d.s3.read_pv.datatype == str
    assert isinstance(d.s2, EpicsSignalRW)
    assert d.s2.source == "sim://prefix:s2"
    assert d.s2.read_pv.datatype == float
    assert isinstance(d.s1, EpicsSignalRO)
    assert d.s1.source == "sim://prefix:s1"
    assert d.s1.read_pv.datatype == int
