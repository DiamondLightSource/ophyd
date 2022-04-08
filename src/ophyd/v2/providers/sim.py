from __future__ import annotations

import asyncio
import collections.abc
import re
import time
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Dict,
    Optional,
    Sequence,
    Type,
    TypeVar,
)

from bluesky.protocols import Descriptor, Dtype, Reading

from ophyd.v2.core import (
    Device,
    Signal,
    SignalCollector,
    SignalDetails,
    SignalProvider,
    SignalRO,
    SignalRW,
    SignalSourcer,
    SignalWO,
    SignalX,
    T,
    check_no_args,
)

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


SetCallback = Callable[[Any], Awaitable[None]]
CallCallback = Callable[[], Awaitable[None]]

primitive_dtypes: Dict[type, Dtype] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def make_descriptor(source: Optional[str], value) -> Descriptor:
    assert source, "Not connected"
    try:
        dtype = primitive_dtypes[type(value)]
        shape = []
    except KeyError:
        assert isinstance(value, Sequence), f"Can't get dtype for {type(value)}"
        dtype = "array"
        shape = [len(value)]
    return dict(source=source, dtype=dtype, shape=shape)


class _SimStore:
    def __init__(self):
        self.on_set: Dict[int, SetCallback] = {}
        self.on_call: Dict[int, CallCallback] = {}
        self.values: Dict[int, Any] = {}
        self.events: Dict[int, asyncio.Event] = {}

    def set_value(self, signal_id: int, value):
        self.values[signal_id] = value
        self.events[signal_id].set()
        self.events[signal_id] = asyncio.Event()


class SimSignal(Signal):
    def __init__(self, store: _SimStore):
        self._store = store
        self._source: Optional[str] = None

    @property
    def source(self) -> Optional[str]:
        return self._source

    def set_source(self, source, *args, **kwargs):
        self._source = source
        check_no_args(args, kwargs)

    async def wait_for_connection(self):
        while self.source is None:
            await asyncio.sleep(0.1)


class SimSignalRO(SignalRO[T], SimSignal):
    async def get_descriptor(self) -> Descriptor:
        return make_descriptor(self.source, self._store.values[id(self)])

    async def get_reading(self) -> Reading:
        return Reading(value=self._store.values[id(self)], timestamp=time.time())

    async def observe_reading(self) -> AsyncGenerator[Reading, None]:
        id_self = id(self)
        while True:
            yield Reading(value=self._store.values[id_self], timestamp=time.time())
            await self._store.events[id_self].wait()


class SimSignalWO(SignalWO[T], SimSignal):
    """Signal that can be put to"""

    async def put(self, value: T):
        id_self = id(self)
        cb = self._store.on_set.get(id_self, None)
        if cb:
            await cb(value)
        self._store.set_value(id_self, value)


class SimSignalRW(SimSignalRO[T], SimSignalWO[T], SignalRW[T]):
    pass


class SimSignalX(SignalX, SimSignal):
    async def execute(self):
        cb = self._store.on_call.get(id(self), None)
        if cb:
            await cb()


lookup: Dict[Type[Signal], Type[SimSignal]] = {
    SignalRO: SimSignalRO,
    SignalWO: SimSignalWO,
    SignalRW: SimSignalRW,
    SignalX: SimSignalX,
}


SetCallbackT = TypeVar("SetCallbackT", bound=SetCallback)
CallCallbackT = TypeVar("CallCallbackT", bound=CallCallback)


class SimProvider(SignalProvider):
    @staticmethod
    def transport() -> str:
        return "sim"

    def __init__(self):
        self._store = _SimStore()

    def on_set(self, signal: SignalWO) -> Callable[[SetCallbackT], SetCallbackT]:
        def decorator(cb: SetCallbackT) -> SetCallbackT:
            self._store.on_set[id(signal)] = cb
            return cb

        return decorator

    def on_call(self, signal: SignalX) -> Callable[[CallCallbackT], CallCallbackT]:
        def decorator(cb: CallCallbackT) -> CallCallbackT:
            self._store.on_call[id(signal)] = cb
            return cb

        return decorator

    def get_value(self, signal: SignalRO[T]) -> T:
        return self._store.values[id(signal)]

    def set_value(self, signal: SignalRO[T], value: T) -> T:
        self._store.set_value(id(signal), value)
        return value

    def create_disconnected_signal(self, details: SignalDetails) -> Signal:
        """Create a disconnected Signal to go in all_signals"""
        signal = lookup[details.signal_cls](self._store)
        if details.value_type is not None:
            origin = getattr(details.value_type, "__origin__", None)
            if origin is None:
                # str, bool, int, float
                assert details.value_type
                value = details.value_type()
            elif origin is collections.abc.Sequence:
                # Sequence[...]
                value = ()
            elif origin is dict:
                # Dict[...]
                value = origin()
            else:
                raise ValueError(f"Can't make {details.value_type}")
            self._store.values[id(signal)] = value
            self._store.events[id(signal)] = asyncio.Event()
        return signal

    async def connect_signals(
        self, device: Device, signal_prefix: str, sourcer: SignalSourcer
    ):
        # Ignore the sourcer and make our own names
        for attr_name, signal in device.all_signals.items():
            source = self.canonical_source(signal_prefix + to_snake_case(attr_name))
            signal.set_source(source)

    @classmethod
    def instance(cls) -> Optional[SimProvider]:
        provider = SignalCollector.get_provider("sim")
        assert provider is None or isinstance(provider, SimProvider)
        return provider
