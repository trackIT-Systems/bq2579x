"""Driver for the TI BQ2579x battery chargers (BQ25790, BQ25792, BQ25798), over I2C or a TPS25751."""

from .bus import BusError, I2CDevice, SMBusDevice
from .device import (
    ADDRESS,
    BQ25790,
    BQ25792,
    BQ25798,
    BQ2579x,
    ChargerStatus,
    Measurements,
    UnknownPartError,
    WriteVerifyError,
    open,
)
from .enums import *  # noqa: F403
from .flags import Event, Fault, Status

__version__ = "0.1.0"

__all__ = [
    "ADDRESS",
    "BQ25790",
    "BQ25792",
    "BQ25798",
    "BQ2579x",
    "BusError",
    "ChargerStatus",
    "Event",
    "Fault",
    "I2CDevice",
    "Measurements",
    "SMBusDevice",
    "Status",
    "UnknownPartError",
    "WriteVerifyError",
    "open",
]
