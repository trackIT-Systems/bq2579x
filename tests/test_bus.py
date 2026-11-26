import pytest

import bq2579x
from bq2579x import SMBusDevice
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
    tps25751 = pytest.importorskip("tps25751")
    chip = FakeCharger(pn=pn)
    tps_sim = FakeTPS({0x6B: chip})
    tps = tps25751.TPS25751(FakeSMBus({0x20: tps_sim}), timeout=0.1)
    return chip, tps_sim, tps, tps25751


def test_charger_through_tps():
    chip, _, tps, tps25751 = tps_setup()
    charger = bq2579x.open(tps25751.I2CcDevice(tps, 0x6B))
    assert type(charger) is bq2579x.BQ25798
    assert charger.verify
    charger.charge_voltage = 14.4
    assert charger.charge_voltage == 14.4
    assert chip.regs[0x01:0x03] == (1440).to_bytes(2, "big")
