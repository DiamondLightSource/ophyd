from abc import ABC, abstractmethod
from typing import Generic, Type

from bluesky.protocols import Descriptor, Reading

from .core import Callback, Monitor, T


class Pv(ABC, Generic[T]):
    def __init__(self, pv: str, datatype: Type[T]):
        self.pv = pv
        self.datatype = datatype

    @property
    @abstractmethod
    def source(self) -> str:
        """Like ca://PV_PREFIX:SIGNAL, or None if not set"""

    @abstractmethod
    async def connect(self):
        """Connect to PV"""

    @abstractmethod
    async def put(self, value: T, wait=True):
        """Put a value to the PV, if wait then wait for completion"""

    @abstractmethod
    async def get_descriptor(self) -> Descriptor:
        """Metadata like source, dtype, shape, precision, units"""

    @abstractmethod
    async def get_reading(self) -> Reading:
        """The current value, timestamp and severity"""

    @abstractmethod
    async def get_value(self) -> T:
        """The current value"""

    @abstractmethod
    def monitor_reading(self, callback: Callback[Reading]) -> Monitor:
        """Observe changes to the current value, timestamp and severity."""

    @abstractmethod
    def monitor_value(self, callback: Callback[T]) -> Monitor:
        """Observe changes to the current value."""


DISCONNECTED_ERROR = NotImplementedError(
    "No PV has been set as EpicsSignal.connect has not been called"
)


class DisconnectedPv(Pv):
    @property
    def source(self) -> str:
        raise DISCONNECTED_ERROR

    async def connect(self):
        raise DISCONNECTED_ERROR

    async def put(self, value: T, wait=True):
        raise DISCONNECTED_ERROR

    async def get_descriptor(self) -> Descriptor:
        raise DISCONNECTED_ERROR

    async def get_reading(self) -> Reading:
        raise DISCONNECTED_ERROR

    async def get_value(self) -> T:
        raise DISCONNECTED_ERROR

    def monitor_reading(self, callback: Callback[Reading]) -> Monitor:
        raise DISCONNECTED_ERROR

    def monitor_value(self, callback: Callback[T]) -> Monitor:
        raise DISCONNECTED_ERROR


DISCONNECTED_PV = DisconnectedPv("", object)


def uninstantiatable_pv(transport: str):
    class UninstantiatablePv:
        def __init__(self, *args, **kwargs):
            raise LookupError(
                f"Can't make a {transport} pv "
                "as the correct libraries are not installed"
            )

    return UninstantiatablePv
