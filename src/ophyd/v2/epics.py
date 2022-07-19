import asyncio
from enum import Enum
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    Generic,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    get_type_hints,
)

from bluesky.protocols import Descriptor, Reading
from typing_extensions import Protocol, get_args, get_origin

from .core import Callback, CommsConnector, SignalR, SignalW, T
from .pv import DISCONNECTED_PV, Monitor, Pv, uninstantiatable_pv
from .pvsim import PvSim

try:
    from .pvca import PvCa
except ImportError:
    PvCa = uninstantiatable_pv("ca")  # type: ignore


class _WithPvCls:
    def __init__(self, pv_cls: Type[Pv]):
        self._pv_cls = pv_cls


class _WithDatatype(Generic[T], _WithPvCls):
    def __init__(self, pv_cls: Type[Pv], datatype: Type[T]):
        super().__init__(pv_cls)
        self._datatype = datatype


V = TypeVar("V")


async def observe_monitor(
    monitor: Callable[[Callback[V]], Monitor]
) -> AsyncGenerator[V, None]:
    q: asyncio.Queue[V] = asyncio.Queue()
    m = monitor(q.put_nowait)
    try:
        while True:
            yield await q.get()
    finally:
        m.close()


class _EpicsSignalR(SignalR[T], _WithDatatype):
    read_pv: Pv[T] = DISCONNECTED_PV

    @property
    def source(self) -> Optional[str]:
        return self.read_pv.source

    async def get_descriptor(self) -> Descriptor:
        return await self.read_pv.get_descriptor()

    async def get_reading(self) -> Reading:
        return await self.read_pv.get_reading()

    async def get_value(self) -> T:
        return await self.read_pv.get_value()

    def observe_reading(self) -> AsyncGenerator[Reading, None]:
        return observe_monitor(self.read_pv.monitor_reading)

    def observe_value(self) -> AsyncGenerator[T, None]:
        return observe_monitor(self.read_pv.monitor_value)


class _EpicsSignalW(SignalW[T], _WithDatatype):
    write_pv: Pv[T] = DISCONNECTED_PV

    @property
    def source(self) -> Optional[str]:
        return self.write_pv.source

    async def put(self, value: T, wait=True):
        await self.write_pv.put(value, wait=wait)


def assert_pv_matches(pv_inst: Pv, pv_str: str):
    if pv_inst is not DISCONNECTED_PV:
        assert (
            pv_inst.pv == pv_str
        ), f"Reconnect asked to change from {pv_inst.pv} to {pv_str}"


class EpicsSignalRO(_EpicsSignalR[T]):
    async def connect(self, read_pv: str):
        assert_pv_matches(self.read_pv, read_pv)
        self.read_pv = self._pv_cls(read_pv, self._datatype)
        await self.read_pv.connect()


class EpicsSignalWO(_EpicsSignalW[T]):
    async def connect(self, write_pv: str):
        assert_pv_matches(self.write_pv, write_pv)
        self.write_pv = self._pv_cls(write_pv, self._datatype)
        await self.write_pv.connect()


class EpicsSignalRW(_EpicsSignalR[T], _EpicsSignalW[T]):
    async def connect(self, write_pv: str, read_pv: str = None):
        assert_pv_matches(self.write_pv, write_pv)
        assert_pv_matches(self.read_pv, read_pv or write_pv)
        self.write_pv = self._pv_cls(write_pv, self._datatype)
        if read_pv:
            self.read_pv = self._pv_cls(read_pv, self._datatype)
        else:
            self.read_pv = self.write_pv
        await asyncio.gather(self.write_pv.connect(), self.read_pv.connect())


class EpicsSignalX(_WithPvCls):
    write_pv: Pv = DISCONNECTED_PV
    write_value: Any = 0
    wait: bool = True

    @property
    def source(self) -> Optional[str]:
        return self.write_pv.source

    async def connect(self, write_pv: str, write_value=0, wait=True):
        assert_pv_matches(self.write_pv, write_pv)
        self.write_pv = self._pv_cls(write_pv, type(self.write_value))
        self.write_value = write_value
        self.wait = wait
        await self.write_pv.connect()

    async def execute(self) -> None:
        await self.write_pv.put(self.write_value, wait=self.wait)


class PvMode(Enum):
    ca = PvCa
    pva = PvCa


_default_pv_mode = PvMode.ca


def set_default_pv_mode(pv_mode: PvMode):
    global _default_pv_mode
    _default_pv_mode = pv_mode


class EpicsComm:
    def __init__(self, pv_prefix: str):
        self.__signals__, self._pv_prefix = make_epics_signals(self, pv_prefix)
        self._connector = get_epics_connector(self)
        CommsConnector.schedule_connect(self)

    async def __connect__(self):
        await self._connector(self, self._pv_prefix)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(pv_prefix={self._pv_prefix!r})"


EpicsSignal = Union[EpicsSignalRO, EpicsSignalRW, EpicsSignalWO, EpicsSignalX]
Signals = Dict[str, EpicsSignal]


def make_epics_signals(comm: EpicsComm, pv_prefix: str) -> Tuple[Signals, str]:
    signals: Signals = {}
    split = pv_prefix.split("://", 1)
    if len(split) > 1:
        # We got something like pva://mydevice, so use specified comms mode
        transport, pv_prefix = split
        pv_mode = PvMode[transport]
    else:
        # No comms mode specified, use the default
        pv_mode = _default_pv_mode
    if CommsConnector.in_sim_mode():
        pv_cls = PvSim
    else:
        pv_cls = pv_mode.value
    # This is duplicated work for every class instance, but could be in a
    # subclass hook if it gets slow
    for cls in reversed(comm.__class__.__mro__):
        for attr_name, hint in get_type_hints(cls).items():
            origin = get_origin(hint)
            if origin is None:
                # SignalX takes no typevar, so will have no origin
                origin = hint
            # SignalRO, WO, RW take a datatype as arg, so pass that
            signal = origin(pv_cls, *get_args(hint))
            # Attach to the comms
            signals[attr_name] = signal
            setattr(comm, attr_name, signal)
    return signals, pv_prefix


EpicsCommT = TypeVar("EpicsCommT", bound=EpicsComm, contravariant=True)


class EpicsConnector(Protocol, Generic[EpicsCommT]):
    # Possibly adds to signals, then calls set_source on them all
    async def __call__(self, comm: EpicsCommT, pv_prefix: str):
        ...


_epics_connectors: Dict[Type[EpicsComm], EpicsConnector] = {}


def epics_connector(connector: EpicsConnector, comm_cls: Type[EpicsComm] = None):
    if comm_cls is None:
        comm_cls = get_type_hints(connector)["comm"]
    _epics_connectors[comm_cls] = connector


def get_epics_connector(comm: EpicsComm) -> EpicsConnector:
    return _epics_connectors[type(comm)]
