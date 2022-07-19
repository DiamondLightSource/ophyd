import asyncio
import re
from typing import Awaitable, Iterator

from ophyd.v2.epicscomms import (
    EpicsComms,
    EpicsSignalRO,
    EpicsSignalRW,
    EpicsSignalWO,
    EpicsSignalX,
)


class CamBase:
    port_name: EpicsSignalRO[str]
    acquire: EpicsSignalRW[bool]
    acquire_period: EpicsSignalRW[float]
    acquire_time: EpicsSignalRW[float]
    array_callbacks: EpicsSignalRW[bool]

    # TODO: I got bored, do we really need all the rest?
    """
    array_counter: EpicsSignalRW[int]
    array_rate: EpicsSignalRO[float]
    nd_attributes_file = EpicsSignalWO[str]

    pool_alloc_buffers: EpicsSignalRO[int]
    pool_free_buffers: EpicsSignalRO[int]
    pool_max_buffers: EpicsSignalRO[int]
    pool_max_mem: EpicsSignalRO[float]
    pool_used_buffers: EpicsSignalRO[int]
    pool_used_mem: EpicsSignalRO[float]

    array_size = DDC(ad_group(EpicsSignalRO,
                              (('array_size_z', 'ArraySizeZ_RBV'),
                               ('array_size_y', 'ArraySizeY_RBV'),
                               ('array_size_x', 'ArraySizeX_RBV'))),
                     doc='Size of the array in the XYZ dimensions')

    array_size_bytes: EpicsSignalRO[, 'ArraySize_RBV')
    bin_x: EpicsSignalRW[, 'BinX')
    bin_y: EpicsSignalRW[, 'BinY')
    color_mode: EpicsSignalRW[, 'ColorMode')
    data_type: EpicsSignalRW[, 'DataType')
    detector_state: EpicsSignalRO[, 'DetectorState_RBV')
    frame_type: EpicsSignalRW[, 'FrameType')
    gain: EpicsSignalRW[, 'Gain')

    image_mode: EpicsSignalRW[, 'ImageMode')
    manufacturer: EpicsSignalRO[, 'Manufacturer_RBV')

    max_size = DDC(ad_group(EpicsSignalRO,
                            (('max_size_x', 'MaxSizeX_RBV'),
                             ('max_size_y', 'MaxSizeY_RBV'))),
                   doc='Maximum sensor size in the XY directions')

    min_x: EpicsSignalRW[, 'MinX')
    min_y: EpicsSignalRW[, 'MinY')
    model: EpicsSignalRO[, 'Model_RBV')

    num_exposures: EpicsSignalRW[, 'NumExposures')
    num_exposures_counter: EpicsSignalRO[, 'NumExposuresCounter_RBV')
    num_images: EpicsSignalRW[, 'NumImages')
    num_images_counter: EpicsSignalRO[, 'NumImagesCounter_RBV')

    read_status = ADCpt(EpicsSignal, 'ReadStatus')
    reverse = DDC(ad_group(SignalWithRBV,
                           (('reverse_x', 'ReverseX'),
                            ('reverse_y', 'ReverseY'))
                           ))



    shutter_close_delay: EpicsSignalRW[, 'ShutterCloseDelay')
    shutter_close_epics = ADCpt(EpicsSignal, 'ShutterCloseEPICS')
    shutter_control: EpicsSignalRW[, 'ShutterControl')
    shutter_control_epics = ADCpt(EpicsSignal, 'ShutterControlEPICS')
    shutter_fanout = ADCpt(EpicsSignal, 'ShutterFanout')
    shutter_mode: EpicsSignalRW[, 'ShutterMode')
    shutter_open_delay: EpicsSignalRW[, 'ShutterOpenDelay')
    shutter_open_epics = ADCpt(EpicsSignal, 'ShutterOpenEPICS')
    shutter_status_epics: EpicsSignalRO[, 'ShutterStatusEPICS_RBV')
    shutter_status: EpicsSignalRO[, 'ShutterStatus_RBV')

    size = DDC(ad_group(SignalWithRBV,
                        (('size_x', 'SizeX'),
                         ('size_y', 'SizeY'))
                        ))

    status_message: EpicsSignalRO[, 'StatusMessage_RBV', string=True)
    string_from_server: EpicsSignalRO[, 'StringFromServer_RBV', string=True)
    string_to_server: EpicsSignalRO[, 'StringToServer_RBV', string=True)
    temperature: EpicsSignalRW[, 'Temperature')
    temperature_actual = ADCpt(EpicsSignal, 'TemperatureActual')
    time_remaining: EpicsSignalRO[, 'TimeRemaining_RBV')
    trigger_mode: EpicsSignalRW[, 'TriggerMode')
    """


class SimDetectorCam(CamBase):
    pass


# https://github.com/wyfo/apischema/blob/master/apischema/utils.py
SNAKE_CASE_REGEX = re.compile(r"_([a-z\d])")


def snake_to_camel(s: str) -> str:
    return SNAKE_CASE_REGEX.sub(lambda m: m.group(1).upper(), s)


def connect_ad_signals(comms: EpicsComms, pv_prefix: str) -> Iterator[Awaitable]:
    for name, signal in comms.__signals__.items():
        pv = f"{pv_prefix}{snake_to_camel(name)}"
        if isinstance(signal, EpicsSignalRO):
            yield signal.connect(pv + "_RBV")
        elif isinstance(signal, EpicsSignalRW):
            yield signal.connect(pv, pv + "_RBV")
        elif isinstance(signal, EpicsSignalWO):
            yield signal.connect(pv)
        elif isinstance(signal, EpicsSignalX):
            yield signal.connect(pv)
        else:
            raise LookupError(
                f"Can't work out how to connect{type(signal).__name__} with pv {pv}"
            )


async def ad_connector(comms: EpicsComms, pv_prefix: str):
    await asyncio.gather(*connect_ad_signals(comms, pv_prefix))
