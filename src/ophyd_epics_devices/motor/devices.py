import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from bluesky.protocols import (
    Descriptor,
    Movable,
    Readable,
    Reading,
    Stageable,
    Stoppable,
)
from bluesky.run_engine import call_in_bluesky_event_loop, in_bluesky_event_loop

from ophyd.v2.core import AsyncStatus, CachedSignal, Device, ReadableSignal, SignalR

from .comms import MotorComms


@dataclass
class CachedMotorSignals:
    readback: CachedSignal
    velocity: CachedSignal
    egu: CachedSignal


class Motor(Device, Movable, Readable, Stoppable, Stageable):
    def __init__(self, comms: MotorComms):
        self.comms: MotorComms = comms
        self._trigger_task: Optional[asyncio.Task[float]] = None
        self._set_success = True
        self._cache: Optional[CachedMotorSignals] = None

    def readable_signal(self, name: str) -> Readable:
        signal = getattr(self.comms, name)
        assert isinstance(signal, SignalR)
        return ReadableSignal(signal, f"{self.name}-{name}")

    def __getitem__(self, name: str) -> Any:
        if in_bluesky_event_loop():
            raise KeyError(
                f"Can't get {self.name}['{name}'] from inside RE, "
                f"use bps.rd({self.name}.readable_signal('{name}'))"
            )
        try:
            signal = getattr(self.comms, name)
        except AttributeError:
            raise KeyError(f"{self.name} has no Signal {name}")
        assert isinstance(signal, SignalR)
        return call_in_bluesky_event_loop(signal.get_value())

    def stage(self):
        # Start monitoring signals
        self._cache = CachedMotorSignals(
            readback=CachedSignal(self.comms.readback),
            velocity=CachedSignal(self.comms.velocity),
            egu=CachedSignal(self.comms.egu),
        )

    def unstage(self):
        self._cache = None

    async def read(self) -> Dict[str, Reading]:
        assert self.name and self._cache, "stage() not called or name not set"
        return {self.name: await self._cache.readback.get_reading()}

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
                self.comms.egu.get_value(), self.comms.precision.get_value()
            )
            async for current_position in self.comms.readback.observe_value():
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
            old_position = await self.comms.demand.get_value()
            t = asyncio.create_task(update_watchers(old_position))
            try:
                await self.comms.demand.put(new_position)
            finally:
                t.cancel()
            if not self._set_success:
                raise RuntimeError("Motor was stopped")

        self._set_success = True
        status = AsyncStatus(asyncio.wait_for(do_set(), timeout=timeout), watchers)
        return status

    async def stop(self, success=False) -> None:
        self._set_success = success
        await self.comms.stop.execute()
