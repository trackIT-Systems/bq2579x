"""Simulated hardware: a BQ2579x register file and an smbus2-like bus with a TPS25751 on it."""

from __future__ import annotations

import ctypes

FLAG_REGS = range(0x22, 0x28)


class FakeCharger:
    """A BQ2579x register file; flag registers clear on read, one-shot ADC finishes at once."""

    def __init__(self, pn: int = 3, rev: int = 1):
        self.regs = bytearray(0x49)
        self.regs[0x48] = (pn << 3) | rev
        self.regs[0x01:0x03] = (1680).to_bytes(2, "big")  # VREG 16.8 V
        self.regs[0x10] = 0x05  # WATCHDOG 40 s
        self.writes: list[tuple[int, bytes]] = []
        self.on_write = None  # hook(reg, data) -> data actually stored, or None to drop

    def read(self, reg: int, length: int) -> bytes:
        if reg + length > len(self.regs):
            raise OSError(121, "Remote I/O error")
        out = bytes(self.regs[reg : reg + length])
        for r in range(reg, reg + length):
            if r in FLAG_REGS:
                self.regs[r] = 0
        return out

    def write(self, reg: int, data: bytes) -> None:
        self.writes.append((reg, bytes(data)))
        if self.on_write is not None:
            data = self.on_write(reg, bytes(data))
            if data is None:
                return
        for i, b in enumerate(data):
            r = reg + i
            if r == 0x2E and b & 0x80 and b & 0x40:  # one-shot ADC: done immediately
                b &= ~0x80
                self.regs[0x1E] |= 0x20
            if r == 0x10:
                b &= ~0x08  # WD_RST clears itself
            self.regs[r] = b


class DeviceAdapter:
    """FakeCharger as an I2CDevice (direct access)."""

    def __init__(self, charger: FakeCharger, queued_writes: bool = False):
        self.charger = charger
        self.queued_writes = queued_writes

    def read(self, reg, length):
        return self.charger.read(reg, length)

    def write(self, reg, data):
        self.charger.write(reg, data)


class FakeTPS:
    """The TPS25751 host interface with CMD1/DATA1 and the I2Cr/I2Cw tasks."""

    def __init__(self, i2cc: dict[int, FakeCharger], mode: bytes = b"APP "):
        self.i2cc = i2cc
        self.regs = {0x03: mode, 0x08: b"\0\0\0\0", 0x09: bytes(64)}
        self.result = 0  # task result to return
        self.pending_polls = 0  # CMD1 reads that still show the task as running
        self.log: list[str] = []

    def write(self, data: bytes) -> None:
        reg, count, payload = data[0], data[1], data[2:]
        assert count == len(payload), "byte count must match the payload"
        if reg == 0x08:
            self._run(payload.decode("ascii"))
        else:
            self.regs[reg] = payload + bytes(64 - len(payload)) if reg == 0x09 else payload

    def read(self, reg: int, length: int) -> bytes:
        value = self.regs.get(reg, b"")
        if reg == 0x08 and self.pending_polls:
            self.pending_polls -= 1
            value = b"I2Cr"
        body = (bytes([len(value)]) + value).ljust(length, b"\0")
        return body[:length]

    def _run(self, task: str) -> None:
        self.log.append(task)
        data = self.regs[0x09]
        if task == "I2Cr":
            target, reg, n = data[0], data[1], data[2]
            out = bytes([self.result]) + (self.i2cc[target].read(reg, n) if not self.result else b"")
        elif task == "I2Cw":
            target, n, reg = data[0], data[1], data[2]
            if not self.result:
                self.i2cc[target].write(reg, data[3 : 3 + n])
            out = bytes([self.result])
        else:
            self.regs[0x08] = b"!CMD"
            return
        self.regs[0x09] = out.ljust(64, b"\0")
        self.regs[0x08] = b"\0\0\0\0"


class FakeSMBus:
    """Enough of smbus2.SMBus for i2c_rdwr; targets are FakeCharger (register pointer) or FakeTPS."""

    def __init__(self, targets: dict[int, object]):
        self.targets = targets
        self.closed = False

    def i2c_rdwr(self, *msgs) -> None:
        pointer = None
        for msg in msgs:
            target = self.targets.get(msg.addr)
            if target is None:
                raise OSError(121, "Remote I/O error")
            if msg.flags & 1:  # read
                if isinstance(target, FakeTPS):
                    data = target.read(pointer, msg.len)
                else:
                    data = target.read(pointer, msg.len)
                ctypes.memmove(msg.buf, data, msg.len)
            else:
                buf = bytes(msg)
                if isinstance(target, FakeTPS):
                    if len(buf) == 1:
                        pointer = buf[0]
                    else:
                        target.write(buf)
                else:
                    pointer = buf[0]
                    if len(buf) > 1:
                        target.write(buf[0], buf[1:])

    def close(self) -> None:
        self.closed = True
