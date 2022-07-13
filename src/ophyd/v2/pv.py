from dataclasses import dataclass
from typing import Generic, Type

from bluesky.protocols import Descriptor, Reading
from typing_extensions import Protocol

from .core import Callback, T


class Monitor(Protocol):
    def close(self):
        ...


@dataclass
class Pv(Generic[T]):
    pv: str
    datatype: Type[T]

    @property
    def source(self) -> str:
        """Like ca://PV_PREFIX:SIGNAL, or None if not set"""

    async def connect(self):
        """Connect to PV"""

    async def put(self, value: T, wait=True):
        """Put a value to the PV, if wait then wait for completion"""

    async def get_descriptor(self) -> Descriptor:
        """Metadata like source, dtype, shape, precision, units"""

    async def get_reading(self) -> Reading:
        """The current value, timestamp and severity"""

    async def get_value(self) -> T:
        """The current value"""

    def monitor_reading(self, cb: Callback[Reading]) -> Monitor:
        """Observe changes to the current value, timestamp and severity."""

    def monitor_value(self, cb: Callback[T]) -> Monitor:
        """Observe changes to the current value."""


def uninstantiatable_pv(transport: str) -> Type[Pv]:
    class UninstantiatablePv(Pv):
        def __init__(self, *args, **kwargs):
            raise LookupError(
                f"Can't make a {transport} pv "
                "as the correct libraries are not installed"
            )

    return UninstantiatablePv
