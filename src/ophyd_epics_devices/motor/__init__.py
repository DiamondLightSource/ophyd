from . import comms, devices


def motor(signal_prefix: str) -> devices.Motor:
    c = comms.MotorComms(signal_prefix)
    return devices.Motor(c)


EpicsMotor = motor
