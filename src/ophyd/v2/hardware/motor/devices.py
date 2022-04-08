from ophyd.v2.core import Device, SignalCollector, SignalRO, SignalRW, SignalX


class Motor(Device):
    demand: SignalRW[float]
    readback: SignalRO[float]
    done_move: SignalRO[bool]
    acceleration_time: SignalRW[float]
    velocity: SignalRW[float]
    max_velocity: SignalRW[float]
    resolution: SignalRO[float]
    offset: SignalRO[float]
    egu: SignalRO[str]
    precision: SignalRO[float]
    stop: SignalX


@SignalCollector.set_sourcer
async def motor_set_sources(device: Motor, signal_prefix: str):
    device.demand.set_source(f"{signal_prefix}.VAL")
    device.readback.set_source(f"{signal_prefix}.RBV")
    device.done_move.set_source(f"{signal_prefix}.DMOV")
    device.acceleration_time.set_source(f"{signal_prefix}.ACCL")
    device.velocity.set_source(f"{signal_prefix}.VELO")
    device.max_velocity.set_source(f"{signal_prefix}.VMAX")
    device.resolution.set_source(f"{signal_prefix}.MRES")
    device.offset.set_source(f"{signal_prefix}.OFF")
    device.egu.set_source(f"{signal_prefix}.EGU")
    device.precision.set_source(f"{signal_prefix}.PREC")
    device.stop.set_source(f"{signal_prefix}.STOP", 1, wait=False)
