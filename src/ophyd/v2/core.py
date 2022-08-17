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

from bluesky.protocols import (
    Descriptor,
    Movable,
    Readable,
    Reading,
    Status,
    Subscribable,
)
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


class Signal(ABC):
    """Signals are like ophyd Signals, but async"""

    @property
    @abstractmethod
    def source(self) -> str:
        """Like ca://PV_PREFIX:SIGNAL, or "" if not set"""

    __lt__ = __le__ = __eq__ = __ge__ = __gt__ = __ne__ = _fail


class SignalR(Signal, Generic[T]):
    """Signal that can be read from and monitored"""

    _cache_ref: Optional[ReferenceType[CachedSignalR[T]]] = None

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
    def monitor_reading(self, callback: Callback[Reading]) -> Monitor:
        """Observe changes to the current value, timestamp and severity.

        First update is the current value"""

    def monitor_value(self, callback: Callback[T]) -> Monitor:
        """Observe changes to the current value.

        First update is the current value"""
        return self.monitor_reading(lambda r: callback(r["value"]))

    @property
    def cached(self) -> CachedSignalR[T]:
        cached_signal = None
        if self._cache_ref:
            # We did make a CachedSignal, but is it still alive?
            cached_signal = self._cache_ref()
        if cached_signal is None:
            # No live CachedSignal, so make it and keep a weakref to it
            cached_signal = CachedSignalR(self)
            self._cache_ref = ref(cached_signal)
        # If we are asked for a new cached signal, then someone new is asking
        # for it, so clear the descriptor to ensure it will be correct if they
        # ask for it
        cached_signal.clear_descriptor()
        return cached_signal


class SignalW(Signal, Generic[T]):
    """Signal that can be put to, but not read"""

    @abstractmethod
    async def put(self, value: T, wait=True):
        """Put a value to the control system."""


class ReadingMonitor:
    def __init__(
        self, callback: Callback[Reading], listeners: List[ReadingMonitor]
    ) -> None:
        self.callback = callback
        self._listeners = listeners
        self._listeners.append(self)

    def close(self):
        self._listeners.remove(self)
        # Remove the callback so we lose a ref to caller
        del self.callback


class _LatestReading:
    """A Reading that you can wait on"""

    def __init__(self) -> None:
        self.listeners: List[ReadingMonitor] = []
        self.valid = asyncio.Event()
        self.reading: Optional[Reading] = None

    def update(self, reading: Reading):
        self.reading = reading
        self.valid.set()
        for listener in self.listeners:
            listener.callback(reading)

    async def get(self) -> Reading:
        await self.valid.wait()
        assert self.reading is not None, "CachedReading.update not working"
        return self.reading

    def add_monitor(self, callback: Callback[Reading]) -> ReadingMonitor:
        if self.reading:
            callback(self.reading)
        return ReadingMonitor(callback, self.listeners)


class CachedSignalR(SignalR[T]):
    """Subscribe to value of a signal while this object exists"""

    def __init__(self, signal: SignalR[T]):
        assert signal.source, "Can't create a cached signal until it's disconnected"
        self._signal = signal
        self._descriptor: Optional[Descriptor] = None
        # Put _reading in a different class so no reference loops, so
        # __del__ will fire when we lose the ref to a CachedSignal
        self._latest = _LatestReading()
        self._monitor = signal.monitor_reading(self._latest.update)

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
        return await self._latest.get()

    def monitor_reading(self, callback: Callback[Reading]) -> Monitor:
        # Add a ref to ourself in the callback, so while the monitor is
        # alive we will stay cached
        def bound_callback(reading: Reading, self=self):
            callback(reading)

        return self._latest.add_monitor(bound_callback)

    @property
    def cached(self) -> CachedSignalR[T]:
        return self

    def __del__(self):
        self._monitor.close()


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
        signals = self._cached_signals or self._signals
        return signals

    async def describe(self, name_prefix: str = "") -> Dict[str, Descriptor]:
        return await gather_dict(
            {name_prefix + k: sig.get_descriptor() for k, sig in self.signals.items()}
        )

    async def read(self, name_prefix: str = "") -> Dict[str, Reading]:
        return await gather_dict(
            {name_prefix + k: sig.get_reading() for k, sig in self.signals.items()}
        )


class Comm(Protocol):
    async def _connect_(self):
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
            asyncio.create_task(comm._connect_()): comm for comm in self._to_connect
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


class SignalDevice(Readable, Movable, Subscribable, Device):
    def __init__(self, signal: Signal, name: str) -> None:
        self.signal = signal
        self._name = name
        self._callback_monitors: Dict[Callback[Dict[str, Reading]], Monitor] = {}

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

    def subscribe(self, function: Callback[Dict[str, Reading]]):
        assert isinstance(self.signal, SignalR), f"Signal {self.name} not readable"

        def callback(reading: Reading):
            function({self.name: reading})

        self._callback_monitors[function] = self.signal.monitor_reading(callback)

    def clear_sub(self, function: Callback[Dict[str, Reading]]) -> None:
        self._callback_monitors[function].close()


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
