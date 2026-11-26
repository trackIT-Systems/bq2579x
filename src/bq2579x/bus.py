"""Register access to an I2C target: the interface the driver needs, and the smbus2 implementation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class BusError(OSError):
    """A transfer to the target failed."""


@runtime_checkable
class I2CDevice(Protocol):
    """One I2C target with 8-bit register addresses and auto-incrementing multi-byte access.

    ``queued_writes`` is true when a successful :meth:`write` only means the write was accepted
    for later execution (as with the TPS25751 ``I2Cw`` task); the driver then reads the value back.
    """

    queued_writes: bool

    def read(self, reg: int, length: int) -> bytes:
        """Read ``length`` bytes starting at register ``reg``."""
        ...

    def write(self, reg: int, data: bytes) -> None:
        """Write ``data`` starting at register ``reg``."""
        ...


class SMBusDevice:
    """A target on a Linux I2C bus (``/dev/i2c-N``), accessed with smbus2.

    ``bus`` is the bus number, a device path, or an open ``smbus2.SMBus``.
    """

    queued_writes = False

    def __init__(self, bus: int | str | object, address: int):
        from smbus2 import SMBus

        self._owned = not hasattr(bus, "i2c_rdwr")
        self._bus = SMBus(bus) if self._owned else bus
        self.address = address

    def __repr__(self) -> str:
        return f"SMBusDevice(bus={getattr(self._bus, 'fd', '?')}, address=0x{self.address:02X})"

    def read(self, reg: int, length: int) -> bytes:
        from smbus2 import i2c_msg

        wr = i2c_msg.write(self.address, [reg])
        rd = i2c_msg.read(self.address, length)
        try:
            self._bus.i2c_rdwr(wr, rd)
        except OSError as e:
            raise BusError(e.errno, f"read 0x{reg:02X}+{length} from 0x{self.address:02X}: {e.strerror}") from e
        return bytes(rd)

    def write(self, reg: int, data: bytes) -> None:
        from smbus2 import i2c_msg

        msg = i2c_msg.write(self.address, [reg, *data])
        try:
            self._bus.i2c_rdwr(msg)
        except OSError as e:
            raise BusError(e.errno, f"write 0x{reg:02X} to 0x{self.address:02X}: {e.strerror}") from e

    def close(self) -> None:
        if self._owned:
            self._bus.close()

    def __enter__(self) -> SMBusDevice:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
