import asyncio
import time
from typing import Callable, List, Optional

from bluesky.protocols import Configuration, Movable, Stoppable

from ophyd.v2.core import Ability, Status

from .devices import Motor


class MovableMotor(Ability, Movable, Stoppable):
    def __init__(self, device: Motor):
        self.device = device
        self._trigger_task: Optional[asyncio.Task[float]] = None
        self._set_success = True

    def trigger(self) -> Status[float]:
        self._trigger_task = asyncio.create_task(self.device.readback.get())
        return Status(self._trigger_task)

    def read(self) -> Configuration:
        assert self._trigger_task, "trigger() not called"
        assert self.name
        return {
            self.name: dict(value=self._trigger_task.result(), timestamp=time.time())
        }

    def describe(self) -> Configuration:
        assert self.name
        return {
            self.name: dict(
                source=self.device.readback.source, dtype="number", shape=[]
            )
        }

    def read_configuration(self) -> Configuration:
        # TODO: no trigger, so can't do this at the moment
        return {}

    def describe_configuration(self) -> Configuration:
        return {}

    def set(self, new_position: float, timeout: float = None) -> Status[float]:
        start = time.time()
        watchers: List[Callable] = []

        async def update_watchers(old_position):
            units, precision = await asyncio.gather(
                self.device.egu.get(), self.device.precision.get()
            )
            async for current_position in self.device.readback.observe():
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
            old_position = await self.device.demand.get()
            t = asyncio.create_task(update_watchers(old_position))
            await self.device.demand.set(new_position)
            t.cancel()
            if not self._set_success:
                raise RuntimeError("Motor was stopped")

        self._set_success = True
        status = Status(asyncio.wait_for(do_set(), timeout=timeout), watchers)
        return status

    def stop(self, *, success=False):
        self._set_success = success
        asyncio.create_task(self.device.stop())
