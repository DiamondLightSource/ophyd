from unittest.mock import Mock

from bluesky.protocols import Descriptor, Reading

from ophyd.v2.core import Callback, Monitor, ReadingMonitor, SignalCollection, SignalR


class MockSig(SignalR):
    def __init__(self) -> None:
        self.descriptor = Mock()
        self.reading = Mock()
        self.monitored = Mock()

    def source(self) -> str:
        return "something"

    async def get_descriptor(self) -> Descriptor:
        return self.descriptor()

    async def get_reading(self) -> Reading:
        return self.reading()

    def monitor_reading(self, callback: Callback[Reading]) -> Monitor:
        callback(self.monitored())
        return ReadingMonitor(callback, [])


async def test_signal_collection_cached_read():
    sig = MockSig()
    sc = SignalCollection(sig=sig)
    # To start there is no caching
    assert sig._cache_ref is None
    # Now start caching
    sc.set_caching(True)
    assert sig._cache_ref() is not None
    # Check that calling read will call monitor
    assert sig.reading.call_count == 0
    assert sig.monitored.call_count == 1
    reading1 = await sc.read()
    assert sig.reading.call_count == 0
    assert sig.monitored.call_count == 1
    # And calling a second time uses cached result
    reading2 = await sc.read()
    assert sig.reading.call_count == 0
    assert sig.monitored.call_count == 1
    assert reading1 == reading2
    # When we make a second cache it should give the same thing
    # without doing another read
    assert (await sig.cached.get_reading()) is reading1["sig"]
    assert sig.reading.call_count == 0
    assert sig.monitored.call_count == 1
    # Adding a monitor should keep it alive
    mon = sig.cached.monitor_reading(lambda _: None)
    sc.set_caching(False)
    assert sig._cache_ref() is not None
    # But closing the monitor does gc
    mon.close()
    assert sig._cache_ref() is None
    # And read calls the right thing
    await sc.read()
    assert sig.reading.call_count == 1
    assert sig.monitored.call_count == 1
