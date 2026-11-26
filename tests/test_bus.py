import pytest

import bq2579x
from bq2579x import SMBusDevice, TaskError, TPS25751, TPS25751I2CcDevice
from bq2579x.bus import BusError
from fakes import FakeCharger, FakeSMBus, FakeTPS


def test_smbus_device_read_write():
    chip = FakeCharger()
    dev = SMBusDevice(FakeSMBus({0x6B: chip}), 0x6B)
    assert dev.read(0x48, 1) == bytes([0x19])
    dev.write(0x01, bytes([0x05, 0xA0]))
    assert chip.regs[0x01:0x03] == bytes([0x05, 0xA0])
    assert not dev.queued_writes


def test_smbus_device_nack():
    dev = SMBusDevice(FakeSMBus({}), 0x6B)
    with pytest.raises(BusError):
        dev.read(0x00, 1)
    with pytest.raises(BusError):
        dev.write(0x00, b"\0")


def test_smbus_device_owned_bus(monkeypatch):
    import smbus2

    opened = []

    class Owned(FakeSMBus):
        def __init__(self, bus):
            super().__init__({})
            opened.append(bus)

    monkeypatch.setattr(smbus2, "SMBus", Owned)
    with SMBusDevice(3, 0x6B) as dev:
        assert opened == [3]
    assert dev._bus.closed


def tps_setup(pn=3):
    chip = FakeCharger(pn=pn)
    tps_sim = FakeTPS({0x6B: chip})
    tps = TPS25751(FakeSMBus({0x20: tps_sim}), timeout=0.1)
    return chip, tps_sim, tps


def test_tps_mode():
    _, _, tps = tps_setup()
    assert tps.mode() == "APP "


def test_tps_i2c_read_write():
    chip, sim, tps = tps_setup()
    assert tps.i2c_read(0x6B, 0x48, 1) == bytes([0x19])
    tps.i2c_write(0x6B, 0x0F, bytes([0x00]))
    assert chip.regs[0x0F] == 0
    assert sim.log == ["I2Cr", "I2Cw"]


def test_tps_polls_until_done():
    _, sim, tps = tps_setup()
    sim.pending_polls = 3
    assert tps.i2c_read(0x6B, 0x48, 1) == bytes([0x19])


def test_tps_timeout():
    _, sim, tps = tps_setup()
    sim.pending_polls = 10**6
    with pytest.raises(TaskError, match="not completed"):
        tps.i2c_read(0x6B, 0x48, 1)


def test_tps_unknown_task():
    _, _, tps = tps_setup()
    with pytest.raises(TaskError, match="not recognised"):
        tps.run_4cc("XXXX")
    with pytest.raises(ValueError):
        tps.run_4cc("TOOLONG")


def test_tps_task_rejected():
    _, sim, tps = tps_setup()
    sim.result = 3
    with pytest.raises(TaskError, match="rejected") as e:
        tps.i2c_read(0x6B, 0x48, 1)
    assert e.value.result == 3


def test_tps_length_limits():
    _, _, tps = tps_setup()
    with pytest.raises(ValueError):
        tps.i2c_read(0x6B, 0, 65)
    with pytest.raises(ValueError):
        tps.i2c_write(0x6B, 0, bytes(12))


def test_i2cc_device_chunks():
    chip, sim, tps = tps_setup()
    dev = TPS25751I2CcDevice(tps, 0x6B)
    assert dev.queued_writes
    regs = dev.read(0x00, 0x49)
    assert regs[0x48] == 0x19 and len(regs) == 0x49
    assert sim.log == ["I2Cr", "I2Cr"]  # 64 + 9 bytes
    dev.write(0x28, bytes(range(1, 15)))  # 14 bytes: 11 + 3
    assert chip.writes[-2:] == [(0x28, bytes(range(1, 12))), (0x33, bytes([12, 13, 14]))]


def test_charger_through_tps():
    chip, _, tps = tps_setup()
    charger = bq2579x.open(TPS25751I2CcDevice(tps, 0x6B))
    assert type(charger) is bq2579x.BQ25798
    assert charger.verify
    charger.charge_voltage = 14.4
    assert charger.charge_voltage == 14.4
    assert chip.regs[0x01:0x03] == (1440).to_bytes(2, "big")


def test_tps_bus_error():
    tps = TPS25751(FakeSMBus({}))
    with pytest.raises(BusError):
        tps.mode()
    with pytest.raises(BusError):
        tps.block_write(0x09, b"x")
