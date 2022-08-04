import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from bluesky.protocols import (
    Descriptor,
    Movable,
    Readable,
    Reading,
    Stageable,
    Stoppable,
)

from ophyd.v2.core import AsyncStatus, CachedSignal, Device, Signal, SignalDevice

from .comms import MotorComm


@dataclass
class CachedMotorSignals:
    readback: CachedSignal
    velocity: CachedSignal
    egu: CachedSignal


class Motor(Device, Movable, Readable, Stoppable, Stageable):
    def __init__(self, comm: MotorComm):
        self.comm: MotorComm = comm
        self._trigger_task: Optional[asyncio.Task[float]] = None
        self._set_success = True
        self._cache: Optional[CachedMotorSignals] = None
        for name in self.comm.__signals__:
            if not hasattr(self, name):
                setattr(self, name, self.signal_device(name))

    def signal_device(self, name: str) -> SignalDevice:
        signal = getattr(self.comm, name)
        assert isinstance(signal, Signal)
        return SignalDevice(signal, f"{self.name}-{name}")

    def stage(self):
        # Start monitoring signals
        self._cache = CachedMotorSignals(
            readback=CachedSignal(self.comm.readback),
            velocity=CachedSignal(self.comm.velocity),
            egu=CachedSignal(self.comm.egu),
        )

    def unstage(self):
        self._cache = None

    async def read(self) -> Dict[str, Reading]:
        if self.name and self._cache:
            return {self.name: await self._cache.readback.get_reading()}
        else:
            return {self.name: await self.comm.readback.get_reading()}

    async def describe(self) -> Dict[str, Descriptor]:
        assert self.name and self._cache, "stage() not called or name not set"
        return {self.name: await self._cache.readback.get_descriptor()}

    async def read_configuration(self) -> Dict[str, Reading]:
        assert self.name and self._cache, "stage() not called or name not set"
        return {
            f"{self.name}-velocity": await self._cache.velocity.get_reading(),
            f"{self.name}-egu": await self._cache.egu.get_reading(),
        }

    async def describe_configuration(self) -> Dict[str, Descriptor]:
        assert self.name and self._cache, "stage() not called or name not set"
        return {
            f"{self.name}-velocity": await self._cache.velocity.get_descriptor(),
            f"{self.name}-egu": await self._cache.egu.get_descriptor(),
        }

    def set(self, new_position: float, timeout: float = None) -> AsyncStatus[float]:
        start = time.time()
        watchers: List[Callable] = []

        async def update_watchers(old_position):
            units, precision = await asyncio.gather(
                self.comm.egu.get_value(), self.comm.precision.get_value()
            )
            async for current_position in self.comm.readback.observe_value():
                for watcher in watchers:
                    watcher(
                        name=self.name,
                        current=current_position,
                        initial=old_position,
                        target=new_position,
                        unit=units,
                        precision=precision,
                        time_elapsed=time.time() - start,
                    )

        async def do_set():
            old_position = await self.comm.demand.get_value()
            t = asyncio.create_task(update_watchers(old_position))
            try:
                await self.comm.demand.put(new_position)
            finally:
                t.cancel()
            if not self._set_success:
                raise RuntimeError("Motor was stopped")

        self._set_success = True
        status = AsyncStatus(asyncio.wait_for(do_set(), timeout=timeout), watchers)
        return status

    async def stop(self, success=False) -> None:
        self._set_success = success
        await self.comm.stop.execute()
