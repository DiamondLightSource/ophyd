from ophyd.v2.core import Device, SignalRO, SignalRW, SignalX


class Motor(Device):
    demand: SignalRW[float]
    readback: SignalRO[float]
    done_move: SignalRO[bool]
    acceleration_time: SignalRW[float]
    velocity: SignalRW[float]
    max_velocity: SignalRW[float]
    # Actually read/write, but shouldn't write from scanning code
    resolution: SignalRO[float]
    offset: SignalRO[float]
    egu: SignalRO[str]
    precision: SignalRO[float]
    stop: SignalX
