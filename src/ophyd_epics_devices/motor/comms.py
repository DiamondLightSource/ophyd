import asyncio

from ophyd.v2.epics import (
    EpicsComm,
    EpicsSignalRO,
    EpicsSignalRW,
    EpicsSignalX,
    epics_connector,
)


class MotorComm(EpicsComm):
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
async def motor_v33_connector(comm: MotorComm, pv_prefix: str):
    await asyncio.gather(
        comm.demand.connect(f"{pv_prefix}.VAL"),
        comm.readback.connect(f"{pv_prefix}.RBV"),
        comm.done_move.connect(f"{pv_prefix}.DMOV"),
        comm.acceleration_time.connect(f"{pv_prefix}.ACCL"),
        comm.velocity.connect(f"{pv_prefix}.VELO"),
        comm.max_velocity.connect(f"{pv_prefix}.VMAX"),
        comm.resolution.connect(f"{pv_prefix}.MRES"),
        comm.offset.connect(f"{pv_prefix}.OFF"),
        comm.egu.connect(f"{pv_prefix}.EGU"),
        comm.precision.connect(f"{pv_prefix}.PREC"),
        comm.stop.connect(f"{pv_prefix}.STOP", 1, wait=False),
    )


# MotorComm()
# epics_connector(motor_v34_connector)
# MotorComm()
# epics_connector(pvi_connector, MotorComm)
