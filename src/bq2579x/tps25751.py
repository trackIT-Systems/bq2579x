"""TI TPS25751 USB PD controller: the host interface, and its I2C controller port (I2Cc) as an I2C target.

The TPS25751 owns its own I2C controller bus (I2Cc), typically shared with a battery charger. A host
on the target port (I2Ct) can run single transactions on I2Cc with the 4CC tasks ``I2Cr`` and
``I2Cw`` (TPS25751 Technical Reference Manual, SLVUCR8B, sections 3.2.3, 3.2.4, 4.6.3 and 4.6.4).
:class:`TPS25751I2CcDevice` wraps that as an :class:`~bq2579x.bus.I2CDevice`.

This module does not depend on the rest of the package except :mod:`bq2579x.bus`, so it can move
into a library of its own.
"""

from __future__ import annotations

import time

from .bus import BusError

REG_MODE = 0x03
REG_CMD1 = 0x08
REG_DATA1 = 0x09
REG_INT_EVENT1 = 0x14

DATA1_SIZE = 64
I2CR_MAX = DATA1_SIZE  # data bytes per I2Cr (output bytes 2-65)
I2CW_MAX = 11  # payload bytes per I2Cw (input bytes 4-14)

TASK_RESULTS = {
    0x0: "success",
    0x1: "timed out or aborted",
    0x3: "rejected",
    0x4: "rejected, Rx buffer locked",
}


class TaskError(BusError):
    """A 4CC task failed: unknown to the controller, timed out, or returned a non-zero result."""

    def __init__(self, task: str, message: str, result: int | None = None):
        super().__init__(f"4CC task '{task}': {message}")
        self.task = task
        self.result = result


class TPS25751:
    """The host interface of a TPS25751 on a Linux I2C bus (default target address 0x20).

    Registers use TI's block protocol: register number, a byte count, then the data, for writes
    and reads alike.
    """

    def __init__(self, bus: int | str | object, address: int = 0x20, timeout: float = 1.0):
        from smbus2 import SMBus

        self._owned = not hasattr(bus, "i2c_rdwr")
        self._bus = SMBus(bus) if self._owned else bus
        self.address = address
        self.timeout = timeout

    def __repr__(self) -> str:
        return f"TPS25751(address=0x{self.address:02X})"

    def block_read(self, reg: int, length: int) -> bytes:
        from smbus2 import i2c_msg

        wr = i2c_msg.write(self.address, [reg])
        rd = i2c_msg.read(self.address, length + 1)
        try:
            self._bus.i2c_rdwr(wr, rd)
        except OSError as e:
            raise BusError(e.errno, f"TPS25751 read 0x{reg:02X}: {e.strerror}") from e
        return bytes(rd)[1 : length + 1]  # the first byte is the register's byte count

    def block_write(self, reg: int, data: bytes) -> None:
        from smbus2 import i2c_msg

        msg = i2c_msg.write(self.address, [reg, len(data), *data])
        try:
            self._bus.i2c_rdwr(msg)
        except OSError as e:
            raise BusError(e.errno, f"TPS25751 write 0x{reg:02X}: {e.strerror}") from e

    def mode(self) -> str:
        """The operating mode, e.g. ``APP `` (configured and running), ``BOOT`` or ``PTCH``."""
        return self.block_read(REG_MODE, 4).decode("ascii", errors="replace")

    def run_4cc(self, task: str, data: bytes = b"", out_len: int = 1) -> bytes:
        """Run a 4CC task and return the first ``out_len`` bytes of DATA1 (byte 0 is the return code)."""
        if len(task) != 4:
            raise ValueError(f"a 4CC task has 4 characters, not {task!r}")
        if data:
            self.block_write(REG_DATA1, data)
        self.block_write(REG_CMD1, task.encode("ascii"))
        deadline = time.monotonic() + self.timeout
        while True:
            cmd = self.block_read(REG_CMD1, 4)
            if cmd == b"\0\0\0\0":
                break
            if cmd == b"!CMD":
                raise TaskError(task, "not recognised by the controller")
            if time.monotonic() > deadline:
                raise TaskError(task, f"not completed within {self.timeout} s")
            time.sleep(0.002)
        return self.block_read(REG_DATA1, out_len)

    def _checked(self, task: str, data: bytes, out_len: int) -> bytes:
        out = self.run_4cc(task, data, out_len)
        result = out[0] & 0x0F
        if result:
            raise TaskError(task, TASK_RESULTS.get(result, f"result 0x{result:X}"), result)
        return out[1:]

    def i2c_read(self, target: int, reg: int, length: int) -> bytes:
        """Read up to 64 bytes from ``target`` on I2Cc (``I2Cr``)."""
        if not 1 <= length <= I2CR_MAX:
            raise ValueError(f"I2Cr reads 1-{I2CR_MAX} bytes, not {length}")
        return self._checked("I2Cr", bytes([target & 0x7F, reg, length]), 1 + length)

    def i2c_write(self, target: int, reg: int, payload: bytes) -> None:
        """Queue a write of up to 11 bytes to ``target`` on I2Cc (``I2Cw``).

        Success means only that the transaction was queued; read the value back to be sure.
        """
        if not 1 <= len(payload) <= I2CW_MAX:
            raise ValueError(f"I2Cw writes 1-{I2CW_MAX} bytes, not {len(payload)}")
        self._checked("I2Cw", bytes([target & 0x7F, len(payload), reg, *payload]), 1)

    def close(self) -> None:
        if self._owned:
            self._bus.close()

    def __enter__(self) -> TPS25751:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class TPS25751I2CcDevice:
    """A target on the TPS25751's I2Cc bus, reached through ``I2Cr`` / ``I2Cw``.

    Longer transfers are split into chunks of 64 (read) and 11 (write) bytes. Writes are only
    queued by the controller (``queued_writes``).
    """

    queued_writes = True

    def __init__(self, tps: TPS25751, address: int):
        self.tps = tps
        self.address = address

    def __repr__(self) -> str:
        return f"TPS25751I2CcDevice({self.tps!r}, address=0x{self.address:02X})"

    def read(self, reg: int, length: int) -> bytes:
        out = bytearray()
        while len(out) < length:
            n = min(I2CR_MAX, length - len(out))
            out += self.tps.i2c_read(self.address, reg + len(out), n)
        return bytes(out)

    def write(self, reg: int, data: bytes) -> None:
        for i in range(0, len(data), I2CW_MAX):
            self.tps.i2c_write(self.address, reg + i, data[i : i + I2CW_MAX])

    def close(self) -> None:
        self.tps.close()
