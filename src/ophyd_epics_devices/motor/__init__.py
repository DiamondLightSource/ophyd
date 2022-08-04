from . import comms, devices


def motor(signal_prefix: str, name=None) -> devices.Motor:
    c = comms.MotorComm(signal_prefix)
    d = devices.Motor(c)
    if name:
        d.name = name
    return d


EpicsMotor = motor
