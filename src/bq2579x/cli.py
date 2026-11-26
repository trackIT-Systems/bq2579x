"""Command line interface: ``bq2579x [--bus N] [--tps BUS[:ADDR]] COMMAND``."""

from __future__ import annotations

import argparse
import enum
import json
import re
import sys
from typing import Any

from . import __version__
from .bus import BusError, SMBusDevice
from .device import ADDRESS, BQ2579x, Measurements, open
from .enums import WatchdogTimeout
from .fields import WATCHDOG, Field, Number
from .tps25751 import TPS25751, TPS25751I2CcDevice

UNIT_SCALE = {"m": 1e-3, "": 1.0}
_QUANTITY = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+))\s*(m?)(V|A|S|°C|C|%)?\s*$", re.IGNORECASE)


def parse_int(text: str) -> int:
    return int(text, 0)


def parse_tps(text: str) -> tuple[str, int]:
    """``BUS`` or ``BUS:ADDR``; the TPS25751 address defaults to 0x20."""
    bus, _, addr = text.partition(":")
    return bus, int(addr, 0) if addr else 0x20


def parse_quantity(text: str, unit: str) -> float:
    """A number with an optional unit and ``m`` prefix: ``14.4``, ``14.4V``, ``14400mV``, ``2A``."""
    m = _QUANTITY.match(text)
    if not m:
        raise ValueError(f"not a number: {text!r}")
    number, prefix, given = m.groups()
    if given:
        g = given.upper().replace("°", "")
        u = unit.upper().replace("°", "")
        if g != u:
            raise ValueError(f"expected a value in {unit}, got {text!r}")
    elif prefix:
        raise ValueError(f"not a number: {text!r}")
    return float(number) * UNIT_SCALE[prefix.lower()]


def bus_arg(text: str) -> int | str:
    return int(text) if text.isdigit() else text


def to_plain(value: Any) -> Any:
    """A JSON-friendly form: enums by name, flags as lists of names."""
    if isinstance(value, enum.IntFlag):
        return [m.name for m in type(value) if m in value and m.value]
    if isinstance(value, enum.Enum):
        return value.name
    return value


def to_text(value: Any, field: Field | None = None) -> str:
    if isinstance(value, enum.IntFlag):
        names = to_plain(value)
        return ", ".join(names) if names else "-"
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, float) and isinstance(field, Number):
        return f"{value:g} {field.unit}"
    return str(value)


def connect(args) -> tuple[BQ2579x, str]:
    """Open the charger directly (``--bus``), through the TPS25751 (``--tps``), or direct with fallback."""
    if args.bus is None and args.tps is None:
        raise SystemExit("bq2579x: give --bus and/or --tps")
    if args.bus is not None:
        try:
            dev = SMBusDevice(args.bus, args.address)
            return open(dev, args.part), f"I2C bus {args.bus}, address 0x{args.address:02X}"
        except (BusError, OSError) as e:
            if args.tps is None:
                raise
            print(f"bq2579x: direct access failed ({e}), using the TPS25751", file=sys.stderr)
    tps_bus, tps_addr = args.tps
    tps = TPS25751(bus_arg(tps_bus), tps_addr)
    dev = TPS25751I2CcDevice(tps, args.address)
    return open(dev, args.part), f"TPS25751 0x{tps_addr:02X} on I2C bus {tps_bus}, I2Cc address 0x{args.address:02X}"


def emit(args, data: dict[str, Any], fields: dict[str, Field] | None = None) -> None:
    if args.json:
        print(json.dumps({k: to_plain(v) for k, v in data.items()}, indent=2, ensure_ascii=False))
        return
    width = max((len(k) for k in data), default=0)
    for k, v in data.items():
        print(f"{k:<{width}}  {to_text(v, (fields or {}).get(k))}")


def cmd_info(args, charger: BQ2579x, transport: str) -> None:
    data: dict[str, Any] = {
        "part": charger.part_number,
        "revision": charger.device_revision,
        "transport": transport,
    }
    if isinstance(charger.device, TPS25751I2CcDevice):
        data["tps_mode"] = charger.device.tps.mode()
    data["watchdog_timeout"] = charger.watchdog_timeout
    emit(args, data)


def cmd_status(args, charger: BQ2579x, transport: str) -> None:
    st = charger.read_status()
    fields = charger.fields()
    data: dict[str, Any] = {
        "charge_status": st.charge_status,
        "vbus_status": st.vbus_status,
        "ico_status": st.ico_status,
        "status": st.status,
        "faults": st.faults,
        "events": charger.read_events(),
    }
    for name in ("charge_enabled", "charge_voltage", "charge_current", "input_voltage_limit",
                 "input_current_limit", "min_system_voltage", "cell_count", "watchdog_timeout"):
        data[name] = getattr(charger, name)
    emit(args, data, fields)


def cmd_adc(args, charger: BQ2579x, transport: str) -> None:
    m: Measurements = charger.measure()
    emit(args, m.as_dict(), charger.fields())


def _field(charger: BQ2579x, name: str) -> Field:
    fields = charger.fields()
    if name not in fields:
        raise SystemExit(f"bq2579x: {type(charger).__name__} has no property {name!r} (see 'bq2579x fields')")
    return fields[name]


def cmd_get(args, charger: BQ2579x, transport: str) -> None:
    fields = {n: _field(charger, n) for n in args.names}
    emit(args, {n: getattr(charger, n) for n in fields}, fields)


def cmd_set(args, charger: BQ2579x, transport: str) -> None:
    field = _field(charger, args.name)
    if field.readonly:
        raise SystemExit(f"bq2579x: {args.name} is read-only")
    value: Any = parse_quantity(args.value, field.unit) if isinstance(field, Number) else args.value
    setattr(charger, args.name, value)
    if WATCHDOG in field.reset_by and charger.watchdog_timeout != WatchdogTimeout.OFF:
        print(f"bq2579x: warning: {args.name} returns to its default when the watchdog "
              f"({charger.watchdog_timeout.name}) expires", file=sys.stderr)
    emit(args, {args.name: getattr(charger, args.name)}, {args.name: field})


def cmd_dump(args, charger: BQ2579x, transport: str) -> None:
    if args.raw:
        regs = charger.read_registers()
        if args.json:
            print(json.dumps({f"0x{i:02X}": b for i, b in enumerate(regs)}, indent=2))
        else:
            for i in range(0, len(regs), 8):
                print(f"{i:02X}: " + " ".join(f"{b:02X}" for b in regs[i : i + 8]))
        return
    emit(args, charger.dump(), charger.fields())


def cmd_fields(args, charger: BQ2579x | None, transport: str) -> None:
    from .device import PARTS
    from .enums import PartNumber

    cls = PARTS[PartNumber[args.part.upper()]] if args.part else type(charger) if charger else BQ2579x
    infos = cls.field_infos()
    if args.json:
        print(json.dumps([i.__dict__ for i in infos], indent=2, ensure_ascii=False))
        return
    for i in infos:
        rw = "rw" if i.writable else "r "
        wd = " (watchdog)" if WATCHDOG in i.reset_by else ""
        print(f"{i.name:<34} {rw} REG{i.reg:02X}[{i.bits}] {i.datasheet:<16} {i.range}{wd}")


def cmd_watchdog(args, charger: BQ2579x, transport: str) -> None:
    if args.value == "kick":
        charger.kick_watchdog()
    elif args.value is not None:
        v = args.value.lower().removesuffix("s")
        if v in ("off", "0"):
            timeout = WatchdogTimeout.OFF
        else:
            match = [t for t in WatchdogTimeout if t.seconds is not None and t.seconds == float(v)]
            if not match:
                raise SystemExit("bq2579x: watchdog takes off, 0.5, 1, 2, 20, 40, 80, 160 or kick")
            timeout = match[0]
        charger.watchdog_timeout = timeout
    emit(args, {"watchdog_timeout": charger.watchdog_timeout})


def cmd_reset(args, charger: BQ2579x, transport: str) -> None:
    if not args.yes:
        raise SystemExit("bq2579x: reset sets every register to its default (VREG, ICHG, ...); add --yes")
    charger.reset()
    print("registers reset")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bq2579x", description="TI BQ25790/BQ25792/BQ25798 battery charger tool")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("-b", "--bus", type=bus_arg, help="I2C bus of the charger (number or /dev path)")
    p.add_argument("--tps", type=parse_tps, metavar="BUS[:ADDR]",
                   help="reach the charger through a TPS25751 on this bus (address default 0x20); "
                        "with --bus, used only when direct access fails")
    p.add_argument("-a", "--address", type=parse_int, default=ADDRESS, help="charger address (default 0x6B)")
    p.add_argument("--part", choices=["bq25790", "bq25792", "bq25798"], type=str.lower,
                   help="skip the part number detection")
    p.add_argument("--json", action="store_true", help="JSON output")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("info", help="part, revision and transport").set_defaults(func=cmd_info)
    sub.add_parser("status", help="charge state, status, faults, events, main settings").set_defaults(func=cmd_status)
    sub.add_parser("adc", help="measure all ADC channels").set_defaults(func=cmd_adc)
    s = sub.add_parser("get", help="read properties")
    s.add_argument("names", nargs="+", metavar="NAME")
    s.set_defaults(func=cmd_get)
    s = sub.add_parser("set", help="write a property (e.g. charge_voltage 14.4V)")
    s.add_argument("name")
    s.add_argument("value")
    s.set_defaults(func=cmd_set)
    s = sub.add_parser("dump", help="all registers, decoded (clears the event flags)")
    s.add_argument("--raw", action="store_true", help="raw register bytes")
    s.set_defaults(func=cmd_dump)
    sub.add_parser("fields", help="list the properties (no hardware access with --part)").set_defaults(func=cmd_fields)
    s = sub.add_parser("watchdog", help="show or set the watchdog timeout, or kick it")
    s.add_argument("value", nargs="?", metavar="off|0.5|1|2|20|40|80|160|kick")
    s.set_defaults(func=cmd_watchdog)
    s = sub.add_parser("reset", help="reset all registers to their defaults (REG_RST)")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_reset)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "fields" and args.bus is None and args.tps is None:
            args.func(args, None, "")
            return 0
        charger, transport = connect(args)
        args.func(args, charger, transport)
    except (OSError, ValueError, TypeError, AttributeError) as e:
        print(f"bq2579x: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
