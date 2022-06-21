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

from ophyd.v2.core import Ability, AsyncStatus, CachedSignal, ReadableSignal, SignalRO

from .devices import Motor


@dataclass
class CachedMotorSignals:
    readback: CachedSignal
    velocity: CachedSignal
    egu: CachedSignal


class MovableMotor(Ability, Movable, Readable, Stoppable, Stageable):
    def __init__(self, device: Motor):
        self.device: Motor = device
        self._trigger_task: Optional[asyncio.Task[float]] = None
        self._set_success = True
        self._cache: Optional[CachedMotorSignals] = None

    def readable_signal(self, name: str) -> Readable:
        signal = getattr(self.device, name)
        assert isinstance(signal, SignalRO)
        return ReadableSignal(signal, f"{self.name}-{name}")

    def __getitem__(self, name: str) -> Any:
        if in_bluesky_event_loop():
            raise KeyError(
                f"Can't get {self.name}['{name}'] from inside RE, "
                f"use bps.rd({self.name}.readable_signal('{name}'))"
            )
        try:
            signal = getattr(self.device, name)
        except AttributeError:
            raise KeyError(f"{self.name} has no Signal {name}")
        assert isinstance(signal, SignalRO)
        return call_in_bluesky_event_loop(signal.get_value())

    def stage(self):
        # Start monitoring signals
        self._cache = CachedMotorSignals(
            readback=CachedSignal(self.device.readback),
            velocity=CachedSignal(self.device.velocity),
            egu=CachedSignal(self.device.egu),
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
                self.device.egu.get_value(), self.device.precision.get_value()
            )
            async for current_position in self.device.readback.observe_value():
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
            old_position = await self.device.demand.get_value()
            t = asyncio.create_task(update_watchers(old_position))
            try:
                await self.device.demand.put(new_position)
            finally:
                t.cancel()
            if not self._set_success:
                raise RuntimeError("Motor was stopped")

        self._set_success = True
        status = AsyncStatus(asyncio.wait_for(do_set(), timeout=timeout), watchers)
        return status

    async def stop(self, success=False) -> None:
        self._set_success = success
        await self.device.stop()
