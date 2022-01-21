from . import abilities, devices, sims


def motor(
    signal_prefix: str,
    sim_params: sims.MotorSimParams = sims.MotorSimParams(),
) -> abilities.MovableMotor:
    device = devices.Motor(signal_prefix)
    sims.add_motor_sim(device, sim_params)
    return abilities.MovableMotor(device)
