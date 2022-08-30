import asyncio
import time
from typing import Callable, Dict, List

from bluesky.protocols import (
    Descriptor,
    Movable,
    Readable,
    Reading,
    Stageable,
    Stoppable,
)

from ophyd.v2.core import AsyncStatus, Device, Signal, SignalCollection, SignalDevice

from .comms import MotorComm


class Motor(Device, Movable, Readable, Stoppable, Stageable):
    def __init__(self, comm: MotorComm):
        self.comm: MotorComm = comm
        self._set_success = True
        # These signal collections will be cached while staged
        self._conf_signals = SignalCollection(
            velocity=self.comm.velocity,
            egu=self.comm.egu,
        )
        self._read_signals = SignalCollection(
            readback=self.comm.readback,
        )

    @Device.name.setter  # type: ignore
    def name(self, name: str):
        self._name = name
        # Create SignalDevice wrappers to all comm signals
        for name in self.comm._signals_:
            if not hasattr(self, name):
                setattr(self, name, self.signal_device(name))

    def signal_device(self, name: str) -> SignalDevice:
        signal = getattr(self.comm, name)
        assert isinstance(signal, Signal)
        return SignalDevice(signal, f"{self.name}-{name}")

    def stage(self):
        # Start caching signals
        self._read_signals.set_caching(True)
        self._conf_signals.set_caching(True)

    def unstage(self):
        # Stop caching signals
        self._read_signals.set_caching(False)
        self._conf_signals.set_caching(False)

    async def read(self) -> Dict[str, Reading]:
        return await self._read_signals.read(self.name + "-")

    async def describe(self) -> Dict[str, Descriptor]:
        return await self._read_signals.describe(self.name + "-")

    async def read_configuration(self) -> Dict[str, Reading]:
        return await self._conf_signals.read(self.name + "-")

    async def describe_configuration(self) -> Dict[str, Descriptor]:
        return await self._conf_signals.describe(self.name + "-")

    def set(self, new_position: float, timeout: float = None) -> AsyncStatus[float]:
        start = time.time()
        watchers: List[Callable] = []

        async def do_set():
            old_position, units, precision = await asyncio.gather(
                self.comm.demand.get_value(),
                self.comm.egu.get_value(),
                self.comm.precision.get_value(),
            )

            def update_watchers(current_position: float):
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

            monitor = self.comm.readback.monitor_value(update_watchers)
            try:
                await self.comm.demand.put(new_position)
            finally:
                monitor.close()
            if not self._set_success:
                raise RuntimeError("Motor was stopped")

        self._set_success = True
        status = AsyncStatus(asyncio.wait_for(do_set(), timeout=timeout), watchers)
        return status

    async def stop(self, success=False) -> None:
        self._set_success = success
        await self.comm.stop.execute()
