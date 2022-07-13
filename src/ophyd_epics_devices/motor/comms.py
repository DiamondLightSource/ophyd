import asyncio
from typing import Awaitable, Iterator

from ophyd.v2.epicscomms import (
    EpicsComms,
    EpicsSignalRO,
    EpicsSignalRW,
    EpicsSignalWO,
    EpicsSignalX,
    epics_connector,
)


class MotorComms(EpicsComms):
    demand: EpicsSignalRW[float]
    readback: EpicsSignalRO[float]
    done_move: EpicsSignalRO[bool]
    acceleration_time: EpicsSignalRW[float]
    velocity: EpicsSignalRW[float]
    max_velocity: EpicsSignalRW[float]
    resolution: EpicsSignalRO[float]
    offset: EpicsSignalRO[float]
    egu: EpicsSignalRO[str]
    precision: EpicsSignalRO[float]
    stop: EpicsSignalX


# This can live anywhere
@epics_connector
async def motor_v33_connector(comms: MotorComms, pv_prefix: str):
    await asyncio.gather(
        comms.demand.connect(f"{pv_prefix}.VAL"),
        comms.readback.connect(f"{pv_prefix}.RBV"),
        comms.done_move.connect(f"{pv_prefix}.DMOV"),
        comms.acceleration_time.connect(f"{pv_prefix}.ACCL"),
        comms.velocity.connect(f"{pv_prefix}.VELO"),
        comms.max_velocity.connect(f"{pv_prefix}.VMAX"),
        comms.resolution.connect(f"{pv_prefix}.MRES"),
        comms.offset.connect(f"{pv_prefix}.OFF"),
        comms.egu.connect(f"{pv_prefix}.EGU"),
        comms.precision.connect(f"{pv_prefix}.PREC"),
        comms.stop.connect(f"{pv_prefix}.STOP", 1, wait=False),
    )


def connect_ad_signals(comms: EpicsComms, pv_prefix: str) -> Iterator[Awaitable]:
    for name, signal in comms.__signals__.items():
        pv = f"{pv_prefix}{snake_to_camel(name)}"
        if isinstance(signal, EpicsSignalRO):
            yield signal.connect(pv + "_RBV")
        elif isinstance(signal, EpicsSignalRW):
            yield signal.connect(pv, pv + "_RBV")
        elif isinstance(signal, EpicsSignalWO):
            yield signal.connect(pv)
        elif isinstance(signal, EpicsSignalX):
            yield signal.connect(pv)
        else:
            raise LookupError(
                f"Can't work out how to connect{type(signal).__name__} with pv {pv}"
            )


async def ad_connector(comms: EpicsComms, pv_prefix: str):
    await asyncio.gather(*connect_ad_signals(comms, pv_prefix))


# MotorComms()
# epics_connector(motor_v34_connector)
# MotorComms()
# epics_connector(pvi_connector, MotorComms)
