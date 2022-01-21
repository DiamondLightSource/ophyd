from typing import Any, Sequence, Set

from typing_extensions import TypedDict

from ophyd.v2.core import Device, SignalRO, SignalWO, SignalX
from ophyd.v2.hardware import motor

# 9 axes in a PMAC co-ordinate system
CS_AXES = "abcuvwxyz"


class Demands(TypedDict, total=False):
    demand_a: float
    demand_b: float
    demand_c: float
    demand_u: float
    demand_v: float
    demand_w: float
    demand_x: float
    demand_y: float
    demand_z: float


class PMACCoord(Device):
    port: SignalRO[str]
    demands: SignalWO[Demands]
    move_time: SignalWO[float]
    defer_moves: SignalWO[bool]
    thing: SignalWO[Set[Any]]


class Positions(TypedDict, total=False):
    position_a: Sequence[float]
    position_b: Sequence[float]
    position_c: Sequence[float]
    position_u: Sequence[float]
    position_v: Sequence[float]
    position_w: Sequence[float]
    position_x: Sequence[float]
    position_y: Sequence[float]
    position_z: Sequence[float]


class Use(TypedDict, total=False):
    use_a: bool
    use_b: bool
    use_c: bool
    use_u: bool
    use_v: bool
    use_w: bool
    use_x: bool
    use_y: bool
    use_z: bool


class PMACTrajectory(Device):
    times: SignalWO[Sequence[float]]
    velocity_modes: SignalWO[Sequence[float]]
    user_programs: SignalWO[Sequence[int]]
    positions: SignalWO[Positions]
    use: SignalWO[Use]
    cs: SignalWO[str]
    build: SignalX
    build_message: SignalRO[str]
    build_status: SignalRO[str]
    points_to_build: SignalWO[int]
    append: SignalX
    append_message: SignalRO[str]
    append_status: SignalRO[str]
    execute: SignalX
    execute_message: SignalRO[str]
    execute_status: SignalRO[str]
    points_scanned: SignalRO[int]
    abort: SignalX
    program_version: SignalRO[float]


class PMAC:
    def __init__(self, pv_prefix: str):
        self.pv_prefix = pv_prefix
        self.cs_list = [PMACCoord(f"{pv_prefix}CS{i+1}") for i in range(16)]
        self.traj = PMACTrajectory(f"{pv_prefix}TRAJ")


class PMACCompoundMotor(motor.devices.Motor):
    input_link: SignalRO[str]


class PMACRawMotor(motor.devices.Motor):
    cs_axis: SignalRO[str]
    cs_port: SignalRO[str]
