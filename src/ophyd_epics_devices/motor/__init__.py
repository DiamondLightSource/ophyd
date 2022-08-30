from ophyd.v2.core import named

from . import comms, devices


def motor(signal_prefix: str, name="") -> devices.Motor:
    c = comms.MotorComm(signal_prefix)
    return named(devices.Motor(c), name)


EpicsMotor = motor
