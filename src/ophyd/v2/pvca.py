from typing import Callable, Dict, Sequence

from aioca import (
    FORMAT_CTRL,
    FORMAT_TIME,
    Subscription,
    caget,
    camonitor,
    caput,
    connect,
)
from aioca.types import AugmentedValue, Dbr
from bluesky.protocols import Descriptor, Dtype, Reading
from epicscorelibs.ca import dbr

from .core import T
from .pv import Pv

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


def make_ca_descriptor(source: str, value: AugmentedValue) -> Descriptor:
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


class PvCa(Pv[T]):
    @property
    def source(self) -> str:
        return f"ca://{self.pv}"

    async def connect(self):
        await connect(self.pv, timeout=None)

    async def put(self, value: T, wait=True):
        await caput(self.pv, value, wait=wait, timeout=None)

    async def get_descriptor(self) -> Descriptor:
        value = await caget(self.pv, datatype=self.datatype, format=FORMAT_CTRL)
        return make_ca_descriptor(self.source, value)

    async def get_reading(self) -> Reading:
        value = await caget(self.pv, datatype=self.datatype, format=FORMAT_TIME)
        return make_ca_reading(value)

    async def get_value(self) -> T:
        value = await caget(self.pv, datatype=self.datatype)
        return value

    def monitor_reading(self, cb: Callable[[Reading], None]) -> Subscription:
        return camonitor(
            self.pv,
            lambda v: cb(make_ca_reading(v)),
            datatype=self.datatype,
            format=FORMAT_TIME,
        )

    def monitor_value(self, cb: Callable[[T], None]) -> Subscription:
        return camonitor(self.pv, cb, datatype=self.datatype)
