import asyncio

from ophyd.v2.epicscomms import (
    EpicsComms,
    EpicsSignalRO,
    EpicsSignalRW,
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


# MotorComms()
# epics_connector(motor_v34_connector)
# MotorComms()
# epics_connector(pvi_connector, MotorComms)
