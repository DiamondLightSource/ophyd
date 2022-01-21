from __future__ import annotations

import asyncio
import collections.abc
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, Optional, TypeVar

from ophyd.v2.core import (
    SIGNAL_CONNECT_TIMEOUT,
    Device,
    Signal,
    SignalCollector,
    SignalDetails,
    SignalProvider,
    SignalRO,
    SignalRW,
    SignalWO,
    SignalX,
    Status,
    T,
    to_snake_case,
)

SetCallback = Callable[[Any], Awaitable[None]]
CallCallback = Callable[[], Awaitable[None]]


class _SimStore:
    def __init__(self):
        self.on_set: Dict[int, SetCallback] = {}
        self.on_call: Dict[int, CallCallback] = {}
        self.values: Dict[int, Any] = {}
        self.events: Dict[int, asyncio.Event] = {}
        self.sources: Dict[int, str] = {}

    def set_value(self, signal_id: int, value):
        self.values[signal_id] = value
        self.events[signal_id].set()
        self.events[signal_id] = asyncio.Event()


class SimSignal(Signal):
    def __init__(self, store: _SimStore):
        self._store = store

    @property
    def source(self) -> Optional[str]:
        return self._store.sources.get(id(self), None)

    async def wait_for_connection(self, timeout: float = SIGNAL_CONNECT_TIMEOUT):
        """Wait for the signal to the control system to be live"""

        async def wait_for_source():
            while self.source is None:
                await asyncio.sleep(0.1)

        await asyncio.wait_for(wait_for_source(), timeout)


class SimSignalRO(SignalRO[T], SimSignal):
    async def get(self) -> T:
        return self._store.values[id(self)]

    async def observe(self) -> AsyncGenerator[T, None]:
        id_self = id(self)
        while True:
            yield self._store.values[id_self]
            await self._store.events[id_self].wait()


class SimSignalWO(SignalWO[T], SimSignal):
    """Signal that can be put to"""

    async def _do_set(self, value):
        id_self = id(self)
        cb = self._store.on_set.get(id_self, None)
        if cb:
            await cb(value)
        self._store.set_value(id_self, value)
        return value

    def set(self, value: T) -> Status[T]:
        return Status(self._do_set(value))


class SimSignalRW(SimSignalRO[T], SimSignalWO[T], SignalRW[T]):
    pass


class SimSignalX(SignalX, SimSignal):
    async def __call__(self):
        cb = self._store.on_call.get(id(self), None)
        if cb:
            await cb()


lookup = {
    SignalRO: SimSignalRO,
    SignalWO: SimSignalWO,
    SignalRW: SimSignalRW,
    SignalX: SimSignalX,
}


SetCallbackT = TypeVar("SetCallbackT", bound=SetCallback)
CallCallbackT = TypeVar("CallCallbackT", bound=CallCallback)


class SimProvider(SignalProvider):
    @property
    def transport(self) -> str:
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

    async def _connect_signals(self):
        # In CA, this would be replaced with caget of {box_id}PVI,
        # then use the json contained in it to connect to all the
        # channels, then add to extra_channels
        return

    def create_signals(self, device: Device, signal_prefix: str) -> Awaitable[None]:
        """For each Signal subclass in the type hints of Device, make
        an instance of it, and return an awaitable that will connect them
        and fill in any extra_signals.
        """
        details = SignalDetails.for_device(device)
        # Make "disconnected" signals
        for attr_name, d in details.items():
            signal = lookup[d.signal_cls](self._store)
            if d.value_type is not None:
                origin = getattr(d.value_type, "__origin__", None)
                if origin is None:
                    # str, bool, int, float
                    assert d.value_type
                    value = d.value_type()
                elif origin is collections.abc.Sequence:
                    # Sequence[...]
                    value = ()
                elif origin is dict:
                    # Dict[...]
                    value = origin()
                else:
                    raise ValueError(f"Can't make {d.value_type}")
                self._store.values[id(signal)] = value
                self._store.events[id(signal)] = asyncio.Event()
            source = self.canonical_source(signal_prefix, to_snake_case(attr_name))
            self._store.sources[id(signal)] = source
            setattr(device, attr_name, signal)

        # Return an awaitable to "connect" them all
        return self._connect_signals()

    @classmethod
    def instance(cls) -> Optional[SimProvider]:
        provider = SignalCollector.get_provider("sim")
        assert provider is None or isinstance(provider, SimProvider)
        return provider
