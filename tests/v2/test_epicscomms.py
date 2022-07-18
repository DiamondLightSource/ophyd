import asyncio

import pytest

from ophyd.v2.core import CommsConnector
from ophyd.v2.epicscomms import EpicsComms, EpicsSignalRO, epics_connector
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


class Base(EpicsComms):
    s1: EpicsSignalRO[int]
    s2: EpicsSignalRO[int]


class Derived(Base):
    s2: EpicsSignalRO[float]
    s3: EpicsSignalRO[str]


@epics_connector
async def derived_connector(comms: Derived, pv_prefix: str):
    coros = [sig.connect(pv_prefix + name) for name, sig in comms.__signals__.items()]
    await asyncio.gather(*coros)


async def test_inherited_comms():
    async with CommsConnector(sim_mode=True):
        d = Derived("prefix:")
    assert d.s3.source == "sim://prefix:s3"
    assert d.s3.read_pv.datatype == str
    assert d.s2.source == "sim://prefix:s2"
    assert d.s2.read_pv.datatype == float
    assert d.s1.source == "sim://prefix:s1"
    assert d.s1.read_pv.datatype == int
