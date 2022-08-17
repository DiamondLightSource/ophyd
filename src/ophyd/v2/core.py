from __future__ import annotations

import asyncio
import logging
import sys
from abc import ABC, abstractmethod
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    ClassVar,
    Dict,
    Generic,
    List,
    Optional,
    Set,
    TypeVar,
    cast,
)
from weakref import ReferenceType, ref

from bluesky.protocols import Descriptor, Movable, Readable, Reading, Status
from bluesky.run_engine import call_in_bluesky_event_loop
from typing_extensions import Protocol

T = TypeVar("T")

Callback = Callable[[T], None]


class AsyncStatus(Status, Generic[T]):
    "Convert asyncio Task to bluesky Status interface"

    def __init__(
        self,
        awaitable: Awaitable[T],
        watchers: Optional[List[Callable]] = None,
    ):
        if isinstance(awaitable, asyncio.Task):
            self.task = awaitable
        else:
            self.task = asyncio.create_task(awaitable)  # type: ignore
        self.task.add_done_callback(self._run_callbacks)
        self._callbacks = cast(List[Callback[Status]], [])
        self._watchers = watchers

    def add_callback(self, callback: Callback[Status]):
        if self.done:
            callback(self)
        else:
            self._callbacks.append(callback)

    @property
    def done(self) -> bool:
        return self.task.done()

    @property
    def success(self) -> bool:
        assert self.done, "Status has not completed yet"
        try:
            self.task.result()
        except (Exception, asyncio.CancelledError):
            logging.exception("Failed status")
            return False
        else:
            return True

    def _run_callbacks(self, task: asyncio.Task):
        if not task.cancelled():
            for callback in self._callbacks:
                callback(self)

    # TODO: should this be in the protocol?
    def watch(self, watcher: Callable):
        if self._watchers is not None:
            self._watchers.append(watcher)


def _fail(self, other, *args, **kwargs):
    if isinstance(other, Signal):
        raise ValueError(
            "Can't compare two Signals, did you mean await signal.get_value() instead?"
        )
    else:
        return NotImplemented


class Signal(ABC):
    """Signals are like ophyd Signals, but async"""

    @property
    @abstractmethod
    def source(self) -> str:
        """Like ca://PV_PREFIX:SIGNAL, or "" if not set"""

    __lt__ = __le__ = __eq__ = __ge__ = __gt__ = __ne__ = _fail


class SignalR(Signal, Generic[T]):
    """Signal that can be read from and monitored"""

    _cache_ref: ReferenceType[CachedSignalR[T]] = lambda _: None

    @abstractmethod
    async def get_descriptor(self) -> Descriptor:
        """Metadata like source, dtype, shape, precision, units"""

    @abstractmethod
    async def get_reading(self) -> Reading:
        """The current value, timestamp and severity"""

    async def get_value(self) -> T:
        """The current value"""
        reading = await self.get_reading()
        return reading["value"]

    @abstractmethod
    async def observe_reading(self) -> AsyncGenerator[Reading, None]:
        """Observe changes to the current value, timestamp and severity.

        First update is the current value"""
        return
        yield

    async def observe_value(self) -> AsyncGenerator[T, None]:
        """Observe changes to the current value.

        First update is the current value"""
        async for reading in self.observe_reading():
            yield reading["value"]

    @property
    def cached(self) -> CachedSignalR[T]:
        cached_signal = self._cache_ref()
        if cached_signal is None:
            cached_signal = CachedSignalR(self)
            self._cache_ref = ref(cached_signal)
        cached_signal.clear_descriptor()
        return cached_signal


class SignalW(Signal, Generic[T]):
    """Signal that can be put to, but not read"""

    @abstractmethod
    async def put(self, value: T, wait=True):
        """Put a value to the control system."""


def monitor_observable(
    observable: AsyncGenerator[T, None], callback: Callable[[T], None]
) -> asyncio.Task:
    """Monitors a signal, calling callback on new value

    Returns:
        Task with a cancel() method
    """

    async def do_observe():
        async for value in observable:
            callback(value)

    return asyncio.create_task(do_observe())


class Monitor(Protocol):
    def close(self):
        ...


async def observe_monitor(
    monitor: Callable[[Callback[T]], Monitor]
) -> AsyncGenerator[T, None]:
    q: asyncio.Queue[T] = asyncio.Queue()
    m = monitor(q.put_nowait)
    try:
        while True:
            yield await q.get()
    finally:
        m.close()


class ReadingMonitor:
    def __init__(
        self, callback: Callback[Reading], listeners: List[ReadingMonitor]
    ) -> None:
        self.callback = callback
        self._listeners = listeners
        self._listeners.append(self)

    def close(self):
        self._listeners.remove(self)


class _CachedReading:
    """A Reading that you can wait on"""

    def __init__(self) -> None:
        self._listeners: List[ReadingMonitor] = []
        self._valid = asyncio.Event()
        self._reading: Optional[Reading] = None

    async def update(self, signal: SignalR):
        try:
            async for reading in signal.observe_reading():
                self._reading = reading
                self._valid.set()
                for listener in self._listeners:
                    listener.callback(reading)
        except asyncio.CancelledError:
            return
        except Exception:
            logging.exception(f"Caching {signal.source} raised exception")
            raise

    def monitor_reading(self, callback: Callback[Reading]) -> Monitor:
        if self._reading:
            callback(self._reading)
        return ReadingMonitor(callback, self._listeners)

    async def get(self) -> Reading:
        await self._valid.wait()
        assert self._reading is not None, "update() not working"
        return self._reading


class CachedSignalR(SignalR[T]):
    """Subscribe to value of a signal while this object exists"""

    def __init__(self, signal: SignalR[T]):
        assert signal.source, "Can't create a cached signal until it's disconnected"
        self._signal = signal
        self._descriptor: Optional[Descriptor] = None
        # Put _reading in a different class so no reference loops, so
        # __del__ will fire when we lose the ref to a CachedSignal
        self._reading = _CachedReading()
        self._task = asyncio.create_task(self._reading.update(signal))

    @property
    def source(self) -> str:
        return self._signal.source

    async def get_descriptor(self) -> Descriptor:
        if self._descriptor is None:
            self._descriptor = await self._signal.get_descriptor()
        return self._descriptor

    def clear_descriptor(self):
        self._descriptor = None

    async def get_reading(self) -> Reading:
        reading = await self._reading.get()
        print(reading, self)
        return reading

    async def observe_reading(self) -> AsyncGenerator[Reading, None]:
        return observe_monitor(self._reading.monitor_reading())

    @property
    def cached(self) -> CachedSignalR[T]:
        return self

    def __del__(self):
        self._task.cancel()


K = TypeVar("K")
V = TypeVar("V")


async def gather_dict(d: Dict[K, Awaitable[V]]) -> Dict[K, V]:
    results = await asyncio.gather(*d.values())
    return dict(zip(d, results))


class SignalCollection:
    """Create a group of signals to be read together"""

    def __init__(self, **signals: SignalR):
        self._signals = signals
        self._cached_signals: Dict[str, SignalR] = {}

    def set_caching(self, caching: bool):
        if caching:
            self._cached_signals = {k: v.cached for k, v in self._signals.items()}
        else:
            self._cached_signals = {}

    @property
    def signals(self) -> Dict[str, SignalR]:
        return self._cached_signals or self._signals

    async def describe(self, name_prefix: str) -> Dict[str, Descriptor]:
        d = {name_prefix + k: sig.get_descriptor() for k, sig in self.signals.items()}
        return await gather_dict(d)

    async def read(self, name_prefix: str) -> Dict[str, Reading]:
        d = {name_prefix + k: sig.get_reading() for k, sig in self.signals.items()}
        return await gather_dict(d)


class Comm(Protocol):
    async def __connect__(self):
        ...


class CommsConnector:
    """Collector of Signals from Device instances to be used as a context manager:

    Args:
        timeout: How long to wait for signals to be connected

    [async] with CommsConnector():
        t1x = motor.motor("BLxxI-MO-TABLE-01:X")
        t1y = motor.motor("pva://BLxxI-MO-TABLE-01:Y")
        # Call Comm.__connect__() for all created Comms at end of with block
    assert t1x.comm.velocity.source
    """

    _instance: ClassVar[Optional[CommsConnector]] = None

    def __init__(self, sim_mode=False, timeout: float = 10.0):
        self._sim_mode = sim_mode
        self._timeout = timeout
        self._to_connect: List[Comm] = []

    def __enter__(self):
        assert not CommsConnector._instance, "Can't nest SignalConnectors"
        CommsConnector._instance = self
        return self

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, type_, value, traceback):
        CommsConnector._instance = None
        # Schedule coros as tasks
        task_comms = {
            asyncio.create_task(comm.__connect__()): comm for comm in self._to_connect
        }
        # Wait for all the signals to have finished
        done, pending = await asyncio.wait(task_comms, timeout=self._timeout)
        not_connected = list(t for t in done if t.exception()) + list(pending)
        if not_connected:
            msg = f"{len(not_connected)} comm not connected:"
            for task in not_connected:
                msg += f"\n    {task_comms[task]}:{task.exception()}"
            logging.error(msg)
        for t in pending:
            t.cancel()

    def __exit__(self, type_, value, traceback):
        return call_in_bluesky_event_loop(self.__aexit__(type_, value, traceback))

    @classmethod
    def get_instance(cls) -> CommsConnector:
        assert (
            CommsConnector._instance
        ), "Can only call classmethods of SignalConnector within a contextmanager"
        return CommsConnector._instance

    @classmethod
    def schedule_connect(cls, comm: Comm):
        self = cls.get_instance()
        self._to_connect.append(comm)

    @classmethod
    def in_sim_mode(cls) -> bool:
        self = cls.get_instance()
        return self._sim_mode


class Device:
    # TODO: what do we actually want here?
    @property
    def parent(self) -> Optional[Any]:
        return None

    _name: str = ""

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, name: str):
        self._name = name


class SignalDevice(Readable, Movable, Device):
    def __init__(self, signal: Signal, name: str) -> None:
        self.signal = signal
        self._name = name

    async def read(self) -> Dict[str, Reading]:
        assert isinstance(self.signal, SignalR), f"Signal {self.name} not readable"
        return {self.name: await self.signal.get_reading()}

    async def describe(self) -> Dict[str, Descriptor]:
        assert isinstance(self.signal, SignalR), f"Signal {self.name} not readable"
        return {self.name: await self.signal.get_descriptor()}

    def set(self, value) -> AsyncStatus:
        assert isinstance(self.signal, SignalW), f"Signal {self.name} not writeable"
        status = AsyncStatus(self.signal.put(value))
        return status


class NamedDevices:
    """Context manager that names Devices after their name in locals().

    [async] with NamedDevices():
        t1x = SettableMotor(MotorRecord("BLxxI-MO-TABLE-01:X"))
    assert t1x.name == "t1x"
    """

    def __init__(self):
        self._names_on_enter: Set[str] = set()

    def _caller_locals(self):
        """Walk up until we find a stack frame that doesn't have us as self"""
        try:
            raise ValueError
        except ValueError:
            _, _, tb = sys.exc_info()
            assert tb, "Can't get traceback, this shouldn't happen"
            caller_frame = tb.tb_frame
            while caller_frame.f_locals.get("self", None) is self:
                caller_frame = caller_frame.f_back
            return caller_frame.f_locals

    def __enter__(self):
        # Stash the names that were defined before we were called
        self._names_on_enter = set(self._caller_locals())
        return self

    async def __aenter__(self):
        return self.__enter__()

    def __exit__(self, type, value, traceback):
        for name, obj in self._caller_locals().items():
            if name not in self._names_on_enter and isinstance(obj, Device):
                # We got a device, name it if it isn't named already
                if not obj.name:
                    obj.name = name

    async def __aexit__(self, type, value, traceback):
        return self.__exit__(type, value, traceback)
