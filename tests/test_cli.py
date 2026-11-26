import importlib.util
import json

import pytest

from bq2579x import cli
from fakes import FakeCharger, FakeSMBus, FakeTPS


@pytest.fixture
def hw(monkeypatch):
    """Bus 2: the charger directly; bus 1: a TPS25751 with the charger on I2Cc."""
    chip = FakeCharger()
    tps = FakeTPS({0x6B: chip})
    buses = {2: FakeSMBus({0x6B: chip}), 1: FakeSMBus({0x20: tps}), 3: FakeSMBus({})}
    import smbus2

    monkeypatch.setattr(smbus2, "SMBus", lambda n: buses[n])
    return chip, tps


needs_tps = pytest.mark.skipif(importlib.util.find_spec("tps25751") is None, reason="tps25751 not installed")


def run(capsys, *argv):
    code = cli.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


@pytest.mark.parametrize("text, unit, value", [
    ("14.4", "V", 14.4), ("14.4V", "V", 14.4), ("14400mV", "V", 14.4), ("2A", "A", 2.0),
    ("500 mA", "A", 0.5), ("-5°C", "°C", -5.0), ("40C", "°C", 40.0), ("50%", "%", 50.0),
])
def test_parse_quantity(text, unit, value):
    assert cli.parse_quantity(text, unit) == pytest.approx(value)


@pytest.mark.parametrize("text, unit", [("2A", "V"), ("abc", "V"), ("14m", "V")])
def test_parse_quantity_errors(text, unit):
    with pytest.raises(ValueError):
        cli.parse_quantity(text, unit)


def test_parse_tps():
    assert cli.parse_tps("1") == ("1", 0x20)
    assert cli.parse_tps("1:0x21") == ("1", 0x21)


def test_info_direct(hw, capsys):
    code, out, _ = run(capsys, "--bus", "2", "info")
    assert code == 0
    assert "BQ25798" in out and "I2C bus 2" in out


@needs_tps
def test_info_tps_json(hw, capsys):
    code, out, _ = run(capsys, "--tps", "1", "--json", "info")
    data = json.loads(out)
    assert data["part"] == "BQ25798"
    assert data["tps_mode"] == "APP "
    assert data["watchdog_timeout"] == "S_40"


@needs_tps
def test_auto_fallback(hw, capsys):
    code, out, err = run(capsys, "--bus", "3", "--tps", "1", "info")
    assert code == 0
    assert "TPS25751" in out
    assert "direct access failed" in err


def test_no_transport(hw, capsys):
    with pytest.raises(SystemExit):
        cli.main(["info"])


def test_direct_failure_without_tps(hw, capsys):
    code, _, err = run(capsys, "--bus", "3", "info")
    assert code == 1 and "Remote I/O" in err


def test_status(hw, capsys):
    chip, _ = hw
    chip.regs[0x1B] = 0x08
    chip.regs[0x22] = 0x08
    code, out, _ = run(capsys, "--bus", "2", "--json", "status")
    data = json.loads(out)
    assert data["status"] == ["POWER_GOOD"]
    assert data["events"] == ["POWER_GOOD"]
    assert data["charge_voltage"] == 16.8


def test_adc(hw, capsys):
    chip, _ = hw
    chip.regs[0x3B:0x3D] = (13100).to_bytes(2, "big")
    code, out, _ = run(capsys, "--bus", "2", "adc")
    assert "battery_voltage" in out and "13.1 V" in out


def test_tps_package_missing(hw, capsys, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "tps25751", None)
    with pytest.raises(SystemExit, match=r"bq2579x\[tps\]"):
        cli.main(["--tps", "1", "info"])


def test_get_set(hw, capsys):
    chip, _ = hw
    code, out, err = run(capsys, "--bus", "2", "set", "charge_current", "2A")
    assert code == 0 and "2 A" in out
    assert "watchdog" in err  # ICHG is reset by the running watchdog
    code, out, err = run(capsys, "--bus", "2", "set", "charge_voltage", "14400mV")
    assert err == ""
    code, out, _ = run(capsys, "--bus", "2", "get", "charge_voltage", "cell_count")
    assert "14.4 V" in out and "S1" in out


@needs_tps
def test_set_through_tps(hw, capsys):
    chip, _ = hw
    code, out, _ = run(capsys, "--tps", "1", "set", "watchdog_timeout", "off")
    assert "OFF" in out and chip.regs[0x10] & 7 == 0


def test_set_errors(hw, capsys):
    code, _, err = run(capsys, "--bus", "2", "set", "charge_voltage", "30V")
    assert code == 1 and "3-18.8 V" in err
    with pytest.raises(SystemExit):
        cli.main(["--bus", "2", "set", "battery_voltage", "1"])
    with pytest.raises(SystemExit):
        cli.main(["--bus", "2", "get", "nonsense"])


def test_dump(hw, capsys):
    code, out, _ = run(capsys, "--bus", "2", "dump", "--raw")
    assert out.splitlines()[-1].startswith("48: 19")
    code, out, _ = run(capsys, "--bus", "2", "--json", "dump", "--raw")
    assert json.loads(out)["0x48"] == 0x19
    code, out, _ = run(capsys, "--bus", "2", "--json", "dump")
    assert json.loads(out)["part_number"] == "BQ25798"


def test_fields_offline(capsys):
    code, out, _ = run(capsys, "--part", "bq25798", "fields")
    assert "mppt_enabled" in out and "VREG" in out
    code, out, _ = run(capsys, "fields")
    assert "mppt_enabled" not in out
    code, out, _ = run(capsys, "--json", "fields")
    assert any(f["name"] == "charge_current" for f in json.loads(out))


def test_watchdog(hw, capsys):
    chip, _ = hw
    code, out, _ = run(capsys, "--bus", "2", "watchdog")
    assert "S_40" in out
    run(capsys, "--bus", "2", "watchdog", "160")
    assert chip.regs[0x10] & 7 == 7
    run(capsys, "--bus", "2", "watchdog", "0.5s")
    assert chip.regs[0x10] & 7 == 1
    run(capsys, "--bus", "2", "watchdog", "kick")
    run(capsys, "--bus", "2", "watchdog", "off")
    assert chip.regs[0x10] & 7 == 0
    with pytest.raises(SystemExit):
        cli.main(["--bus", "2", "watchdog", "7"])


def test_reset(hw, capsys):
    chip, _ = hw
    with pytest.raises(SystemExit):
        cli.main(["--bus", "2", "reset"])
    code, out, _ = run(capsys, "--bus", "2", "reset", "--yes")
    assert chip.writes[-1] == (0x09, bytes([0x40]))
