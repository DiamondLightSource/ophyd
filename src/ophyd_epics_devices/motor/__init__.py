from . import comms, devices


def motor(signal_prefix: str) -> devices.Motor:
    c = comms.MotorComm(signal_prefix)
    return devices.Motor(c)


EpicsMotor = motor
