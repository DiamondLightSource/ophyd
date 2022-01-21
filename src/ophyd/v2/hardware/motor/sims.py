import asyncio
from dataclasses import dataclass

from ophyd.v2.providers.sim import SimProvider

from .devices import Motor


@dataclass
class MotorSimParams:
    velocity: float = 1
    precision: int = 3
    units: str = "mm"


def add_motor_sim(motor: Motor, params: MotorSimParams):
    p = SimProvider.instance()
    if p is None:
        return
    task = None
    p.set_value(motor.velocity, params.velocity)
    p.set_value(motor.max_velocity, params.velocity)
    p.set_value(motor.precision, params.precision)
    p.set_value(motor.egu, params.units)

    @p.on_set(motor.demand)
    async def do_move(new_position):
        async def actually_do_move():
            p.set_value(motor.done_move, 0)
            old_position = p.get_value(motor.readback)
            velocity = p.get_value(motor.velocity)
            # Don't try to be clever, just move at a constant velocity
            move_time = (new_position - old_position) / velocity
            for i in range(int(move_time / 0.1)):
                p.set_value(motor.readback, old_position + i * 0.1 * velocity)
                await asyncio.sleep(0.1)
            p.set_value(motor.readback, new_position)
            p.set_value(motor.done_move, 1)

        nonlocal task
        task = asyncio.create_task(actually_do_move())
        try:
            await task
        except asyncio.CancelledError:
            pass

    @p.on_call(motor.stop)
    async def do_stop():
        if task:
            task.cancel()
