import asyncio
from typing import Any, AsyncGenerator, Dict, Optional, Sequence, Type

from aioca import FORMAT_CTRL, FORMAT_TIME, caget, camonitor, caput, connect
from aioca.types import AugmentedValue, Dbr
from bluesky.protocols import Descriptor, Dtype, Reading
from epicscorelibs.ca import dbr

from ophyd.v2.core import (
    Signal,
    SignalDetails,
    SignalProvider,
    SignalRO,
    SignalRW,
    SignalWO,
    SignalX,
    T,
    check_no_args,
)


class CaSignal(Signal):
    def __init__(self, datatype: Optional[Type] = None):
        self._datatype = datatype


dbr_to_dtype: Dict[Dbr, Dtype] = {
    dbr.DBR_STRING: "string",
    dbr.DBR_SHORT: "integer",
    dbr.DBR_FLOAT: "number",
    dbr.DBR_ENUM: "integer",
    dbr.DBR_CHAR: "string",
    dbr.DBR_LONG: "integer",
    dbr.DBR_DOUBLE: "number",
    dbr.DBR_ENUM_STR: "string",
    dbr.DBR_CHAR_BYTES: "string",
    dbr.DBR_CHAR_UNICODE: "string",
    dbr.DBR_CHAR_STR: "string",
}


def make_ca_descriptor(source: Optional[str], value: AugmentedValue) -> Descriptor:
    assert source, "Not connected"
    try:
        dtype = dbr_to_dtype[value.datatype]
        shape = []
    except KeyError:
        assert isinstance(
            value, Sequence
        ), f"Can't get dtype for {value} with datatype {value.datatype}"
        dtype = "array"
        shape = [len(value)]
    return dict(source=source, dtype=dtype, shape=shape)


def make_ca_reading(value: AugmentedValue) -> Reading:
    return dict(
        value=value,
        timestamp=value.timestamp,
        alarm_severity=-1 if value.severity > 2 else value.severity,
    )


class CaSignalRO(SignalRO[T], CaSignal):
    _read_pv: str = ""

    @property
    def source(self) -> Optional[str]:
        return CaProvider.canonical_source(self._read_pv)

    def set_source(self, read_pv, *args, **kwargs):
        self._read_pv = read_pv
        check_no_args(args, kwargs)

    async def wait_for_connection(self) -> None:
        await connect(self._read_pv, timeout=None)

    async def get_descriptor(self) -> Descriptor:
        value = await caget(self._read_pv, datatype=self._datatype, format=FORMAT_CTRL)
        return make_ca_descriptor(self.source, value)

    async def get_reading(self) -> Reading:
        value = await caget(self._read_pv, datatype=self._datatype, format=FORMAT_TIME)
        return make_ca_reading(value)

    async def get_value(self) -> T:
        value = await caget(self._read_pv, datatype=self._datatype)
        return value

    async def observe_reading(self) -> AsyncGenerator[Reading, None]:
        q: asyncio.Queue[AugmentedValue] = asyncio.Queue()
        m = camonitor(
            self._read_pv, q.put_nowait, datatype=self._datatype, format=FORMAT_TIME
        )
        try:
            while True:
                value = await q.get()
                reading = make_ca_reading(value)
                yield reading
        finally:
            m.close()

    async def observe_value(self) -> AsyncGenerator[T, None]:
        q: asyncio.Queue[AugmentedValue] = asyncio.Queue()
        m = camonitor(self._read_pv, q.put_nowait, datatype=self._datatype)
        try:
            while True:
                value = await q.get()
                yield value
        finally:
            m.close()


class CaSignalWO(SignalWO[T], CaSignal):
    """Signal that can be put to, but not got"""

    _write_pv: str = ""
    _wait: bool = True

    @property
    def source(self) -> Optional[str]:
        return CaProvider.canonical_source(self._write_pv)

    def set_source(self, write_pv, wait=True, *args, **kwargs):
        self._write_pv = write_pv
        self._wait = wait
        check_no_args(args, kwargs)

    async def wait_for_connection(self) -> None:
        await connect(self._write_pv, timeout=None)

    async def put(self, value: T):
        await caput(self._write_pv, value, wait=self._wait, timeout=None)


class CaSignalRW(CaSignalRO[T], CaSignalWO[T], SignalRW[T]):
    def set_source(self, write_pv, read_pv=None, wait=True, *args, **kwargs):
        self._write_pv = write_pv
        self._read_pv = read_pv or write_pv
        self._wait = wait
        check_no_args(args, kwargs)

    async def wait_for_connection(self) -> None:
        await asyncio.gather(
            connect(self._write_pv, timeout=None), connect(self._read_pv, timeout=None)
        )


class CaSignalX(SignalX, CaSignal):
    _write_pv: str = ""
    _write_value: Any = 0
    _wait: bool = True

    @property
    def source(self) -> Optional[str]:
        return CaProvider.canonical_source(self._write_pv)

    def set_source(self, write_pv, write_value=0, wait=True, *args, **kwargs):
        self._write_pv = write_pv
        self._write_value = write_value
        self._wait = wait
        check_no_args(args, kwargs)

    async def wait_for_connection(self) -> None:
        await connect(self._write_pv, timeout=None)

    async def execute(self):
        await caput(self._write_pv, self._write_value, wait=self._wait, timeout=None)


lookup: Dict[Type[Signal], Type[CaSignal]] = {
    SignalRO: CaSignalRO,
    SignalWO: CaSignalWO,
    SignalRW: CaSignalRW,
    SignalX: CaSignalX,
}


class CaProvider(SignalProvider):
    @staticmethod
    def transport() -> str:
        return "ca"

    def create_disconnected_signal(self, details: SignalDetails) -> Signal:
        """Create a disconnected Signal to go in all_signals"""
        signal_cls = lookup[details.signal_cls]
        return signal_cls(details.value_type)
