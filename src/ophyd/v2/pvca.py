from enum import Enum
from typing import Callable, Dict, Sequence, Type

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


class CaValueConverter:
    async def validate(self, pv: str):
        ...

    def to_ca(self, value):
        ...

    def from_ca(self, value):
        ...


class NullConverter(CaValueConverter):
    def to_ca(self, value):
        return value

    def from_ca(self, value):
        return value


class EnumConverter(CaValueConverter):
    def __init__(self, enum_cls: Type[Enum]) -> None:
        self.enum_cls = enum_cls

    async def validate(self, pv: str):
        value = await caget(pv, format=FORMAT_CTRL)
        assert hasattr(value, "enums"), f"{pv} is not an enum"
        unrecognized = set(v.value for v in self.enum_cls) - set(value.enums)
        assert not unrecognized, f"Enum strings {unrecognized} not in {value.enums}"

    def to_ca(self, value: Enum):
        return value.value

    def from_ca(self, value: AugmentedValue):
        return self.enum_cls(value)


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


def make_ca_reading(value: AugmentedValue, converter: CaValueConverter) -> Reading:
    return dict(
        value=converter.from_ca(value),
        timestamp=value.timestamp,
        alarm_severity=-1 if value.severity > 2 else value.severity,
    )


class PvCa(Pv[T]):
    converter: CaValueConverter

    def __init__(self, pv: str, datatype: Type[T]):
        super().__init__(pv, datatype)
        self.converter = NullConverter()
        self.ca_datatype: type = datatype
        if issubclass(datatype, Enum):
            self.converter = EnumConverter(datatype)
            self.ca_datatype = str

    @property
    def source(self) -> str:
        return f"ca://{self.pv}"

    async def connect(self):
        await connect(self.pv, timeout=None)
        await self.converter.validate(self.pv)

    async def put(self, value: T, wait=True):
        await caput(self.pv, self.converter.to_ca(value), wait=wait, timeout=None)

    async def get_descriptor(self) -> Descriptor:
        value = await caget(self.pv, datatype=self.ca_datatype, format=FORMAT_CTRL)
        return make_ca_descriptor(self.source, value)

    async def get_reading(self) -> Reading:
        value = await caget(self.pv, datatype=self.ca_datatype, format=FORMAT_TIME)
        return make_ca_reading(value, self.converter)

    async def get_value(self) -> T:
        value = await caget(self.pv, datatype=self.ca_datatype)
        return self.converter.from_ca(value)

    def monitor_reading(self, callback: Callable[[Reading], None]) -> Subscription:
        return camonitor(
            self.pv,
            lambda v: callback(make_ca_reading(v, self.converter)),
            datatype=self.ca_datatype,
            format=FORMAT_TIME,
        )

    def monitor_value(self, callback: Callable[[T], None]) -> Subscription:
        return camonitor(
            self.pv,
            lambda v: callback(self.converter.from_ca(v)),
            datatype=self.ca_datatype,
        )
