import asyncio
from typing import Callable
from unittest.mock import Mock

import pytest
from bluesky.protocols import Descriptor, Reading

from ophyd.v2.core import CommsConnector, Monitor, SignalCollection, T
from ophyd.v2.epics import EpicsComm, EpicsSignalRO, EpicsSignalRW, epics_connector
from ophyd.v2.pv import Pv, uninstantiatable_pv
from ophyd.v2.pvsim import SimMonitor


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


class MockPv(Pv[T]):
    descriptor: Mock = Mock()
    reading: Mock = Mock()
    monitored: Mock = Mock()

    @property
    def source(self) -> str:
        return "something"

    async def connect(self):
        pass

    async def put(self, value: T, wait=True):
        pass

    async def get_descriptor(self) -> Descriptor:
        return self.descriptor()

    async def get_reading(self) -> Reading:
        return self.reading()

    async def get_value(self) -> T:
        return self.reading()["value"]

    def monitor_reading_value(self, callback: Callable[[Reading, T], None]) -> Monitor:
        m = self.monitored()
        callback(m, m.value)
        return SimMonitor(callback, [])


async def test_signal_collection_cached_read() -> None:
    sig = EpicsSignalRO(pv_cls=MockPv, datatype=float)
    await sig.connect("blah")
    pv: MockPv = sig.read_pv
    sc = SignalCollection(sig=sig)
    # To start there is no monitoring
    assert None is sig._cache
    # Now start caching
    sc.set_caching(True)
    assert sig._cache and sig._cache.monitor
    # Check that calling read will call monitor
    assert pv.reading.call_count == 0
    assert pv.monitored.call_count == 1
    reading1 = await sc.read()
    assert pv.reading.call_count == 0
    assert pv.monitored.call_count == 1
    # And calling a second time uses cached result
    reading2 = await sc.read()
    assert pv.reading.call_count == 0
    assert pv.monitored.call_count == 1
    assert reading1 == reading2
    # When we make a second cache it should give the same thing
    # without doing another read
    assert (await sig.get_reading()) is reading1["sig"]
    assert pv.reading.call_count == 0
    assert pv.monitored.call_count == 1
    # Same with value
    assert (await sig.get_value()) is reading1["sig"].value
    assert pv.reading.call_count == 0
    assert pv.monitored.call_count == 1
    # Adding a monitor should keep it alive
    mon = sig.monitor_reading(lambda _: None)
    sc.set_caching(False)
    assert sig._cache.monitor
    # But closing the monitor does gc
    mon.close()
    assert sig._cache.monitor is None
    # And read calls the right thing
    await sc.read()
    assert pv.reading.call_count == 1
    assert pv.monitored.call_count == 1
