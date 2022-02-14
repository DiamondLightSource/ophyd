import asyncio
import logging
import re
import sys
import threading
from abc import ABC, abstractmethod, abstractproperty
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
    Mapping,
    Optional,
    Set,
    Type,
    TypeVar,
    cast,
    get_type_hints,
)

from bluesky.protocols import Descriptor, Readable, Reading, Status
from bluesky.run_engine import get_bluesky_event_loop

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
            self.task = asyncio.create_task(awaitable)
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


SIGNAL_CONNECT_TIMEOUT = 10.0


class Signal(ABC):
    """Signals are like ophyd Signals, but async"""

    @property
    def source(self) -> Optional[str]:
        """like ca://PV_PREFIX:SIGNAL, or None if not connected"""

    @abstractmethod
    async def wait_for_connection(
        self, timeout: float = SIGNAL_CONNECT_TIMEOUT
    ) -> None:
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


class CachedSignal(Generic[T], Readable):
    """Subscribe to value of a signal while this object exists"""

    def __init__(self, signal: SignalRO[T]):
        self._signal = signal
        self._descriptor: Optional[Descriptor] = None
        self._reading: Optional[Reading] = None
        self._task = asyncio.create_task(self._update_reading())
        self._first_update = asyncio.Event()

    async def _update_reading(self) -> None:
        async for reading in self._signal.observe_reading():
            self._reading = reading
            self._first_update.set()

    async def get_reading(self) -> Reading:
        await self._first_update.wait()
        assert self._reading is not None, "_update_reading not working"
        return self._reading

    async def get_descriptor(self) -> Descriptor:
        if self._descriptor is None:
            self._descriptor = await self._signal.get_descriptor()
        return self._descriptor

    def __del__(self):
        self._task.cancel()


class SignalWO(Signal, Generic[T]):
    """Signal that can be put to, but not"""

    @abstractmethod
    async def put(self, value: T) -> T:
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


class Device:
    def __init__(self, signal_prefix: str):
        # signal_prefix is ca://BLxxI-MO-PMAC-01:, may not include transport
        # This will create the signals we asked for, and queue their
        # connection and any extra signals there might be
        self.all_signals: Mapping[str, Signal] = {}
        SignalCollector.create_signals(self, signal_prefix)

    async def wait_for_connection(
        self, timeout: float = SIGNAL_CONNECT_TIMEOUT
    ) -> None:
        """Wait for all signals to be live"""
        await asyncio.gather(
            signal.wait_for_connection(timeout) for signal in self.all_signals.values()
        )


@dataclass
class SignalDetails:
    attr_name: str
    signal_cls: Type[Signal]
    value_type: Type

    @classmethod
    def for_device(cls, device: Device) -> Dict[str, "SignalDetails"]:
        details = {}
        for attr_name, hint in get_type_hints(device).items():
            # SignalX takes no typevar, so will have no origin
            origin = getattr(hint, "__origin__", hint)
            if not issubclass(origin, Signal):
                raise TypeError(f"Annotation {hint} is not a Signal")
            # This will be [ValueT], or [None] in the case of SignalX
            args = getattr(hint, "__args__", [None])
            details[attr_name] = cls(
                attr_name=attr_name, signal_cls=origin, value_type=args[0]
            )
        return details


SignalT = TypeVar("SignalT", bound=Signal)


class SignalProvider(ABC):
    @abstractproperty
    def transport(self) -> str:
        """Return the transport prefix, like ca or sim"""

    def canonical_source(self, prefix: str, suffix: str) -> str:
        """Make the canonical signal source string"""
        return f"{self.transport}://{prefix}{suffix}"

    @abstractmethod
    def create_signals(self, device: Device, signal_prefix: str) -> Awaitable[None]:
        """For each Signal subclass in the type hints of Device, make
        an instance of it, and return an awaitable that will connect them
        and fill in any extra_signals.
        """


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

    def __init__(self):
        self._providers: Dict[str, SignalProvider] = {}
        self._signal_awaitables: Dict[Device, Awaitable[None]] = {}

    async def __aexit__(self, type_, value, traceback):
        self._get_cls()._instance = None
        # Wait for all the signals to have finished
        await asyncio.gather(*self._signal_awaitables.values())

    def __exit__(self, type_, value, traceback):
        fut = asyncio.run_coroutine_threadsafe(
            self.__aexit__(type_, value, traceback),
            loop=get_bluesky_event_loop(),
        )
        event = threading.Event()
        fut.add_done_callback(lambda _: event.set())
        event.wait()

    @classmethod
    def add_provider(
        cls, provider: SignalProviderT, set_default: bool = False
    ) -> SignalProviderT:
        self = cls.get_instance()
        if set_default:
            assert (
                "" not in self._providers
            ), "Cannot call add_provider(provider, set_default=False) twice"
            self._providers[""] = provider
        assert provider.transport not in self._providers, "Provider already registered"
        self._providers[provider.transport] = provider
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
        self._signal_awaitables[device] = provider.create_signals(device, signal_prefix)


# TODO: use the one in pvi
PASCAL_CASE_REGEX = re.compile(r"(?<![A-Z])[A-Z]|[A-Z][a-z/d]|(?<=[a-z])\d")


def to_snake_case(pascal_s: str) -> str:
    """Takes a PascalCaseFieldName and returns an Title Case Field Name
    Args:
        pascal_s: E.g. PascalCaseFieldName
    Returns:
        snake_case converted name. E.g. pascal_case_field_name
    """
    return PASCAL_CASE_REGEX.sub(lambda m: "_" + m.group().lower(), pascal_s).strip("_")


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
        assert not self._name, f"Name already set to {self._name}"
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
