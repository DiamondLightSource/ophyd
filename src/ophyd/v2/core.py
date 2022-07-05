import asyncio
import logging
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
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
    Type,
    TypeVar,
    cast,
    get_type_hints,
)

from black import Iterator
from bluesky.protocols import Descriptor, Readable, Reading, Status
from bluesky.run_engine import call_in_bluesky_event_loop
from typing_extensions import Protocol

T = TypeVar("T")

Callback = Callable[["Status"], None]


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
        self._callbacks = cast(List[Callback], [])
        self._watchers = watchers

    def add_callback(self, callback: Callback):
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


def check_no_args(args, kwargs):
    assert not args and not kwargs, f"Unrecognised {args} {kwargs}"


class Signal(ABC):
    """Signals are like ophyd Signals, but async"""

    @property
    @abstractmethod
    def source(self) -> Optional[str]:
        """Like ca://PV_PREFIX:SIGNAL, or None if not set"""

    @abstractmethod
    def set_source(self, *args: Any, **kwargs: Any):
        """Used by the provider to provide the pv of a channel.

        Value can be anything that makes sense to the particular channel
        """

    @abstractmethod
    async def wait_for_connection(self) -> None:
        """Wait for the signal to the control system to be live"""

    __lt__ = __le__ = __eq__ = __ge__ = __gt__ = __ne__ = _fail


class SignalRO(Signal, Generic[T]):
    """Signal that can be read from and monitored"""

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


class SignalWO(Signal, Generic[T]):
    """Signal that can be put to, but not"""

    @abstractmethod
    async def put(self, value: T):
        """Put a value to the control system.

        Returns:
            The value the control system actually set it to
        """


class SignalRW(SignalWO[T], SignalRO[T]):
    """Signal that can be read from, monitored, and put to"""


class SignalX(Signal):
    """Signal that can be executed"""

    @abstractmethod
    async def execute(self):
        """Execute this"""

    async def __call__(self):
        await self.execute()


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


class CachedReading:
    """A Reading that you can wait on"""

    def __init__(self) -> None:
        self._valid = asyncio.Event()
        self._reading: Optional[Reading] = None

    async def update(self, signal: SignalRO):
        try:
            async for reading in signal.observe_reading():
                self._reading = reading
                self._valid.set()
        except asyncio.CancelledError:
            return
        except Exception:
            logging.exception(f"Caching {signal.source} raised exception")
            raise

    async def get(self) -> Reading:
        await self._valid.wait()
        assert self._reading is not None, "update() not working"
        return self._reading


class CachedSignal:
    """Subscribe to value of a signal while this object exists"""

    def __init__(self, signal: SignalRO):
        self._signal = signal
        self._descriptor: Optional[Descriptor] = None
        # Put _reading in a different class so no reference loops, so
        # __del__ will fire when we lose the ref to a CachedSignal
        self._reading = CachedReading()
        self._task = asyncio.create_task(self._reading.update(signal))

    async def get_reading(self) -> Reading:
        return await self._reading.get()

    async def get_descriptor(self) -> Descriptor:
        if self._descriptor is None:
            self._descriptor = await self._signal.get_descriptor()
        return self._descriptor

    def __del__(self):
        self._task.cancel()


class ReadableSignal(Readable):
    def __init__(self, signal: SignalRO, name: str) -> None:
        self.signal = signal
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def read(self) -> Dict[str, Reading]:
        return {self.name: await self.signal.get_reading()}

    async def describe(self) -> Dict[str, Descriptor]:
        return {self.name: await self.signal.get_descriptor()}


class Device:
    def __init__(self, signal_prefix: str):
        # signal_prefix is ca://BLxxI-MO-PMAC-01:, may not include transport
        # This will create the signals we asked for, and queue their
        # connection and any extra signals there might be
        self.all_signals: Dict[str, Signal] = {}
        SignalCollector.create_signals(self, signal_prefix)

    async def wait_for_connection(self) -> None:
        """Wait for all signals to be live"""
        fs = [signal.wait_for_connection() for signal in self.all_signals.values()]
        await asyncio.gather(*fs)


@dataclass
class SignalDetails:
    attr_name: str
    signal_cls: Type[Signal]
    value_type: Type

    @classmethod
    def for_device(cls, device: Device) -> Iterator["SignalDetails"]:
        for attr_name, hint in get_type_hints(device).items():
            # SignalX takes no typevar, so will have no origin
            origin = getattr(hint, "__origin__", hint)
            if not issubclass(origin, Signal):
                raise TypeError(f"Annotation {hint} is not a Signal")
            # This will be [ValueT], or [None] in the case of SignalX
            args = getattr(hint, "__args__", [None])
            yield cls(attr_name=attr_name, signal_cls=origin, value_type=args[0])


DeviceT = TypeVar("DeviceT", bound=Device, contravariant=True)


class SignalSourcer(Protocol, Generic[DeviceT]):
    # Possibly adds to signals, then calls set_source on them all
    async def __call__(self, device: DeviceT, signal_prefix: str):
        ...


class SignalProvider(ABC):
    @staticmethod
    @abstractmethod
    def transport() -> str:
        """Return the transport prefix, like ca or sim"""

    @classmethod
    def canonical_source(cls, source: Optional[str]) -> Optional[str]:
        """Make the canonical signal source string"""
        if source:
            return f"{cls.transport()}://{source}"
        else:
            return None

    @abstractmethod
    def create_disconnected_signal(self, details: SignalDetails) -> Signal:
        """Create a disconnected Signal to go in all_signals"""

    async def connect_signals(
        self, device: Device, signal_prefix: str, sourcer: SignalSourcer
    ):
        await sourcer(device, signal_prefix)
        await device.wait_for_connection()


InstanceT = TypeVar("InstanceT", bound="_SingletonContextManager")


class _SingletonContextManager:
    """Pattern where instance exists only during the context manager. Works with
    both async and regular context manager invocations"""

    _instance: ClassVar[Optional["_SingletonContextManager"]] = None

    @classmethod
    def _get_cls(cls):
        return cls

    def __enter__(self):
        cls = self._get_cls()
        assert not cls._instance, f"Can't nest {cls} context managers"
        cls._instance = self
        return self

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, type_, value, traceback):
        self.__exit__(type_, value, traceback)

    def __exit__(self, type_, value, traceback):
        self._get_cls()._instance = None

    @classmethod
    def get_instance(cls: Type[InstanceT]) -> InstanceT:
        assert (
            cls._instance
        ), f"Can only call classmethods of {cls} within a contextmanager"
        return cast(InstanceT, cls._instance)


SignalProviderT = TypeVar("SignalProviderT", bound=SignalProvider)


class SignalCollector(_SingletonContextManager):
    """Collector of Signals from Device instances to be used as a context manager:

    Args:
        timeout: How long to wait for signals to be connected

    [async] with SignalCollector():
        ca = SignalCollector.add_provider(CAProvider(), set_default=True)
        ca.specify_connections(MotorRecord, yaml="/path/to/motor.pvi.yaml")
        ca.specify_connections(MotorRecord, dict=dict(demand=PVConnection(".VAL")))
        ca.specify_connections(Pilatus, pvi=True)
        t1x = SettableMotor(MotorRecord("BLxxI-MO-TABLE-01:X"))
        t1y = SettableMotor(MotorRecord("BLxxI-MO-TABLE-01:Y"))
        # All Signals get connected at the end of the Context
    assert t1x.motor.velocity.connected
    """

    _sourcers: Dict[Type[Device], SignalSourcer] = {}

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self._providers: Dict[str, SignalProvider] = {}
        self._connect_coros: Dict[Device, Awaitable[None]] = {}

    async def __aexit__(self, type_, value, traceback):
        self._get_cls()._instance = None
        # Schedule coros as tasks
        task_devices = {
            asyncio.create_task(coro): device
            for device, coro in self._connect_coros.items()
        }
        # Wait for all the signals to have finished
        done, pending = await asyncio.wait(task_devices, timeout=self.timeout)
        not_connected = list(t for t in done if t.exception()) + list(pending)
        if not_connected:
            msg = f"{len(not_connected)} devices not connected:"
            for task in not_connected:
                msg += f"\n    {task_devices[task]}"
            logging.error(msg)
        for t in pending:
            t.cancel()

    def __exit__(self, type_, value, traceback):
        return call_in_bluesky_event_loop(self.__aexit__(type_, value, traceback))

    @classmethod
    def set_sourcer(
        cls, sourcer: SignalSourcer, device_cls: Type[Device] = None
    ) -> SignalSourcer:
        if device_cls is None:
            device_cls = get_type_hints(sourcer)["device"]
        cls._sourcers[device_cls] = sourcer
        return sourcer

    @classmethod
    def add_provider(
        cls, provider: SignalProviderT, set_default: bool = False
    ) -> SignalProviderT:
        self = cls.get_instance()
        if set_default:
            assert (
                "" not in self._providers
            ), "Cannot call add_provider(provider, set_default=True) twice"
            self._providers[""] = provider
        transport = provider.transport()
        assert (
            transport not in self._providers
        ), f"Provider already registered for {transport}"
        self._providers[transport] = provider
        return provider

    @classmethod
    def get_provider(cls, transport: str) -> Optional[SignalProvider]:
        self = cls.get_instance()
        return self._providers.get(transport, None)

    @classmethod
    def create_signals(cls, device: Device, signal_prefix: str):
        # Find the right provider
        self = cls.get_instance()
        split = signal_prefix.split("://", 1)
        if len(split) > 1:
            transport, signal_prefix = split
        else:
            transport, signal_prefix = "", split[0]
        provider = self._providers[transport]
        for d in SignalDetails.for_device(device):
            signal = provider.create_disconnected_signal(d)
            device.all_signals[d.attr_name] = signal
            setattr(device, d.attr_name, signal)
        sourcer = self._sourcers[type(device)]
        self._connect_coros[device] = provider.connect_signals(
            device, signal_prefix, sourcer
        )


class Ability:
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


class NamedAbilities:
    """Context manager that names Devices after their name in locals().

    [async] with NamedAbilities():
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
            if name not in self._names_on_enter and isinstance(obj, Ability):
                # We got a device, name it
                obj.name = name

    async def __aexit__(self, type, value, traceback):
        return self.__exit__(type, value, traceback)
