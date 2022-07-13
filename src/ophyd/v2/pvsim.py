from __future__ import annotations

import asyncio
import time
from typing import Callable, Dict, Generic, List, Sequence, Type, TypeVar

from bluesky.protocols import Descriptor, Dtype, Reading
from typing_extensions import Protocol

from .core import T
from .pv import Pv

primitive_dtypes: Dict[type, Dtype] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def make_sim_descriptor(source: str, value) -> Descriptor:
    try:
        dtype = primitive_dtypes[type(value)]
        shape = []
    except KeyError:
        assert isinstance(value, Sequence), f"Can't get dtype for {type(value)}"
        dtype = "array"
        shape = [len(value)]
    return dict(source=source, dtype=dtype, shape=shape)


def make_sim_reading(value) -> Reading:
    return dict(value=value, timestamp=time.time())


class SimMonitor:
    def __init__(self, listeners: List[SimMonitor], callback: Callable, value):
        self.listeners = listeners
        self.callback = callback
        self.listeners.append(self)
        callback(value)

    def close(self):
        self.listeners.remove(self)


ValueT = TypeVar("ValueT", contravariant=True)


class PutHandler(Protocol, Generic[ValueT]):
    async def __call__(self, value: ValueT) -> None:
        pass


class PvSim(Pv[T]):
    def __init__(self, pv: str, datatype: Type[T]):
        super().__init__(pv, datatype)
        self.value = datatype()
        self.put_proceeds = asyncio.Event()
        self.put_proceeds.set()
        self.listeners: List[SimMonitor] = []

    @property
    def source(self) -> str:
        return f"sim://{self.pv}"

    async def connect(self):
        pass

    async def put(self, value: T, wait=True):
        self.set_value(value)
        if wait:
            await self.put_proceeds.wait()

    async def get_descriptor(self) -> Descriptor:
        return make_sim_descriptor(self.source, self.value)

    async def get_reading(self) -> Reading:
        return make_sim_reading(self.value)

    async def get_value(self) -> T:
        return self.value

    def monitor_reading(self, cb: Callable[[Reading], None]) -> SimMonitor:
        return SimMonitor(self.listeners, lambda v: cb(make_sim_reading(v)), self.value)

    def monitor_value(self, cb: Callable[[T], None]) -> SimMonitor:
        return SimMonitor(self.listeners, cb, self.value)

    def set_value(self, value: T) -> None:
        self.value = value
        for listener in self.listeners:
            listener.callback(value)
