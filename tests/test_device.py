import pytest

import bq2579x
from bq2579x import (
    BQ25790,
    BQ25792,
    BQ25798,
    ChargeStatus,
    Event,
    Fault,
    Status,
    VacOvp25790,
    VbusStatus,
    WatchdogTimeout,
)
from fakes import DeviceAdapter, FakeCharger


def make(pn=3, queued=False):
    chip = FakeCharger(pn=pn)
    return chip, bq2579x.open(DeviceAdapter(chip, queued_writes=queued))


@pytest.mark.parametrize("pn, cls", [(0, BQ25790), (1, BQ25792), (3, BQ25798)])
def test_open_detects_part(pn, cls):
    _, charger = make(pn)
    assert type(charger) is cls
    assert charger.part_number == cls.part


def test_open_unknown_part():
    with pytest.raises(bq2579x.UnknownPartError):
        make(pn=2)


def test_open_forced_part():
    chip = FakeCharger(pn=7)
    assert type(bq2579x.open(DeviceAdapter(chip), part="bq25792")) is BQ25792


def test_device_revision():
    _, charger = make()
    assert charger.device_revision == 1


def test_charge_voltage_encoding():
    chip, charger = make()
    assert charger.charge_voltage == 16.8
    charger.charge_voltage = 14.4
    assert chip.regs[0x01:0x03] == (1440).to_bytes(2, "big")
    assert charger.charge_voltage == 14.4


def test_reserved_bits_kept():
    chip, charger = make()
    chip.regs[0x00] = 0xC0  # reserved bits 7:6
    charger.min_system_voltage = 12.0
    assert chip.regs[0x00] == 0xC0 | 0x26  # (12 - 2.5) / 0.25 = 38


def test_offset_and_rounding():
    chip, charger = make()
    charger.otg_voltage = 5.0
    assert int.from_bytes(chip.regs[0x0B:0x0D], "big") == 220  # 0xDC, the POR default
    charger.charge_current = 1.234
    assert charger.charge_current == 1.23


@pytest.mark.parametrize("value", [2.9, 18.9])
def test_range_check(value):
    _, charger = make()
    with pytest.raises(ValueError):
        charger.charge_voltage = value


def test_type_check():
    _, charger = make()
    with pytest.raises(TypeError):
        charger.charge_voltage = "14.4"


def test_readonly():
    _, charger = make()
    with pytest.raises(AttributeError):
        charger.battery_voltage = 12.0


def test_otg_current_range_per_part():
    _, c98 = make(3)
    _, c92 = make(1)
    c92.otg_current = 0.12
    with pytest.raises(ValueError):
        c98.otg_current = 0.12
    c98.otg_current = 3.36


def test_bq25798_only_properties():
    chip, c98 = make(3)
    c98.mppt_enabled = True
    assert chip.regs[0x15] & 1
    _, c92 = make(1)
    assert not hasattr(c92, "mppt_enabled")
    assert "mppt_enabled" in BQ25798.fields()
    assert "mppt_enabled" not in BQ25792.fields()


def test_bq25790_vac_ovp():
    chip, c90 = make(0)
    chip.regs[0x10] = 0x10
    assert c90.vac_ovp is VacOvp25790.V_22


def test_choice_by_name_and_member():
    chip, charger = make()
    charger.watchdog_timeout = "off"
    assert charger.watchdog_timeout is WatchdogTimeout.OFF
    charger.watchdog_timeout = WatchdogTimeout.S_160
    assert chip.regs[0x10] & 0x07 == 7
    with pytest.raises(ValueError):
        charger.watchdog_timeout = "forever"
    with pytest.raises(TypeError):
        charger.watchdog_timeout = ChargeStatus.DONE


def test_bit_from_string():
    chip, charger = make()
    charger.charge_enabled = "on"
    assert chip.regs[0x0F] & 0x20
    charger.charge_enabled = False
    assert not chip.regs[0x0F] & 0x20


def test_signed_adc_values():
    chip, charger = make()
    chip.regs[0x33:0x35] = (-1500 & 0xFFFF).to_bytes(2, "big")
    chip.regs[0x41:0x43] = (-20 & 0xFFFF).to_bytes(2, "big")
    assert charger.battery_current == -1.5
    assert charger.die_temperature == -10.0


def test_read_status():
    chip, charger = make()
    chip.regs[0x1B] = 0x09  # PG, VBUS present
    chip.regs[0x1C] = (3 << 5) | (0xB << 1)
    chip.regs[0x21] = 0x04
    st = charger.read_status()
    assert st.charge_status is ChargeStatus.FAST_CC
    assert st.vbus_status is VbusStatus.DIRECT_VBUS
    assert st.status == Status.POWER_GOOD | Status.VBUS_PRESENT
    assert st.faults == Fault.THERMAL_SHUTDOWN


def test_reserved_charge_status_code():
    chip, charger = make()
    chip.regs[0x1C] = 5 << 5
    assert charger.charge_status == 5


def test_events_read_once_and_clear():
    chip, charger = make()
    chip.regs[0x22] = 0x20  # WD
    chip.regs[0x27] = 0x80  # VSYS short
    assert charger.read_events() == Event.WATCHDOG | Event.VSYS_SHORT
    assert charger.read_events() == Event(0)


def test_interrupt_mask():
    chip, charger = make()
    charger.interrupt_mask = Event.ADC_DONE | Event.TS_HOT
    assert chip.regs[0x2A] == 0x20
    assert chip.regs[0x2B] == 0x01
    assert charger.interrupt_mask == Event.ADC_DONE | Event.TS_HOT
    charger.interrupt_mask = "adc_done, vbus_ovp"
    assert charger.interrupt_mask == Event.ADC_DONE | Event.VBUS_OVP


def test_measure_one_shot():
    chip, charger = make()
    chip.regs[0x3B:0x3D] = (13200).to_bytes(2, "big")
    chip.regs[0x3F:0x41] = (512).to_bytes(2, "big")
    m = charger.measure()
    assert m.battery_voltage == 13.2
    assert m.ts_percent == pytest.approx(50.0, abs=0.01)
    assert chip.regs[0x2E] & 0x40  # one-shot rate set
    assert not chip.regs[0x2E] & 0x80  # finished


def test_measure_timeout():
    chip, charger = make()
    original = chip.write

    def sticky(reg, data):  # ADC_EN never clears
        original(reg, data)
        if reg == 0x2E:
            chip.regs[0x2E] |= 0x80

    chip.write = sticky
    with pytest.raises(TimeoutError):
        charger.measure(timeout=0.05)


def test_measure_continuous_reads_directly():
    chip, charger = make()
    chip.regs[0x2E] = 0x80  # enabled, continuous
    charger.measure()
    assert chip.writes == []


def test_dump_contains_all_fields_and_events():
    chip, charger = make()
    chip.regs[0x22] = 0x08
    d = charger.dump()
    assert set(BQ25798.fields()) <= set(d)
    assert d["events"] == Event.POWER_GOOD
    assert d["charge_voltage"] == 16.8


def test_kick_and_reset():
    chip, charger = make()
    charger.kick_watchdog()
    assert chip.writes[-1] == (0x10, bytes([0x0D]))
    charger.reset()
    assert chip.writes[-1] == (0x09, bytes([0x40]))


def test_verify_on_queued_writes():
    chip, charger = make(queued=True)
    assert charger.verify
    charger.charge_voltage = 14.0
    chip.on_write = lambda reg, data: None  # the write never arrives
    with pytest.raises(bq2579x.WriteVerifyError):
        charger.charge_voltage = 14.2


def test_volatile_fields_not_verified():
    chip, charger = make(queued=True)
    charger.kick_watchdog()  # WD_RST clears itself, must not fail verification


def test_field_infos():
    infos = {i.name: i for i in BQ25798.field_infos()}
    assert infos["charge_voltage"].datasheet == "VREG"
    assert infos["charge_current"].reset_by == ("WATCHDOG", "REG_RST")
    assert "WATCHDOG" not in infos["charge_voltage"].reset_by
    assert not infos["battery_voltage"].writable
    assert infos["charge_voltage"].range == "3-18.8 V in steps of 0.01"


def test_field_docstring():
    assert "VREG" in BQ25798.charge_voltage.__doc__
