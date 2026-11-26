# bq2579x

[![Tests](https://github.com/trackIT-Systems/bq2579x/actions/workflows/ci.yml/badge.svg)](https://github.com/trackIT-Systems/bq2579x/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A Python driver and command line tool for the Texas Instruments BQ2579x buck-boost battery chargers (1-4 cells, 5 A, dual input), on Linux over I2C. The charger can be reached directly, or through a TPS25751 USB PD controller that shares its I2C bus, as on boards where the PD controller owns the charger while USB-C power is present.

## Supported chips

| Chip | Part number (REG48 PN) | Differences |
|---|---|---|
| BQ25790 | 0 | VAC_OVP code 1 is 22 V, default 7 V |
| BQ25792 | 1 | |
| BQ25798 | 3 | adds solar MPPT (REG15), backup mode, `STOP_WD_CHG`; no poor-source status |

All three share one register map. `bq2579x.open()` reads the part number and returns `BQ25790`, `BQ25792` or `BQ25798`.

## Install

```bash
pip install git+https://github.com/trackIT-Systems/bq2579x
pip install "bq2579x[tps] @ git+https://github.com/trackIT-Systems/bq2579x"  # with access through a TPS25751
```

Python 3.12+, Linux with `/dev/i2c-*` (the only dependency is [smbus2](https://pypi.org/project/smbus2/)). The `tps` extra adds [tps25751](https://github.com/trackIT-Systems/tps25751) for access through a TPS25751 USB PD controller.

## Library

```python
import bq2579x

charger = bq2579x.open(bq2579x.SMBusDevice(1, bq2579x.ADDRESS))  # bus 1, address 0x6B

charger.charge_voltage = 14.4            # V (VREG)
charger.charge_current = 2.0             # A (ICHG)
charger.watchdog_timeout = bq2579x.WatchdogTimeout.OFF

print(charger.charge_status)             # ChargeStatus.FAST_CC
print(charger.measure().battery_voltage) # one-shot ADC conversion of all channels

st = charger.read_status()
if bq2579x.Fault.VBAT_OVP in st.faults:
    ...
```

- **Properties** have descriptive names; the datasheet name is in each docstring and in `BQ25798.field_infos()` (or `bq2579x fields`). Values are SI units (V, A, °C, %), `bool` or an `IntEnum`; writes are range-checked and rounded to the register step.
- **Every access is live**: reading a property reads the chip, writing does a read-modify-write of its register and keeps the other bits.
- **Status bits** (`status`, `faults`), **events** (`read_events()`) and **interrupt masks** (`interrupt_mask`) are `IntFlag`s, each group read in one transfer. The event flags (REG22-REG27) clear when read, so read them only through `read_events()` or `dump()`.
- `dump()` decodes every property from a single read of the whole register map.

### Through a TPS25751

This needs the [tps25751](https://github.com/trackIT-Systems/tps25751) package (`bq2579x[tps]`).

```python
import tps25751

tps = tps25751.TPS25751(1, address=0x20)
charger = bq2579x.open(tps25751.I2CcDevice(tps, bq2579x.ADDRESS))
print(tps.mode())  # 'APP ' when the PD controller runs its configuration
```

The PD controller runs single I2C transactions on its controller port with the 4CC tasks `I2Cr` (up to 64 bytes) and `I2Cw` (up to 11 bytes); longer transfers are split. `I2Cw` only queues the write behind the controller's own charger transactions (`queued_writes`), so the driver reads every written field back and raises `WriteVerifyError` if it does not arrive (`verify=` on `open()` overrides this).

### Watchdog

The charger's I2C watchdog (default 40 s) resets some registers when it expires without host access: among them ICHG, IPRECHG, ITERM, EN_CHG, the safety timers, the OTG settings and the JEITA/TS settings. VREG, VSYSMIN, IINDPM and the MPPT settings stay; they are reset only by `REG_RST` (VINDPM by neither). `bq2579x fields` marks the affected fields with `(watchdog)`. Either disable the watchdog (`watchdog_timeout = WatchdogTimeout.OFF`) or call `kick_watchdog()` regularly.

## Command line

```
bq2579x [--bus N] [--tps BUS[:ADDR]] [--address 0x6B] [--part P] [--json] COMMAND
```

| Command | |
|---|---|
| `info` | part, revision, transport (and the TPS25751 mode) |
| `status` | charge state, input source, status bits, faults, events, main settings |
| `adc` | one-shot measurement of all ADC channels |
| `get NAME...` | read properties |
| `set NAME VALUE` | write a property: `14.4`, `14.4V`, `14400mV`, `2A`, an enum name, `on`/`off` |
| `dump [--raw]` | every property, or the raw registers |
| `fields` | all properties with datasheet name, register, range (offline with `--part`) |
| `watchdog [off\|0.5\|1\|2\|20\|40\|80\|160\|kick]` | show or set the timeout, or reset the timer |
| `reset --yes` | reset all registers to their defaults |

`--bus` talks to the charger directly, `--tps` through a TPS25751 (address 0x20 unless given; needs `bq2579x[tps]`). With both, the direct path is tried first and the TPS25751 is used when the charger does not answer.

```bash
bq2579x --bus 2 --tps 1 status
bq2579x --bus 2 set charge_voltage 14.4V
bq2579x --tps 1 --json adc
```

## Development

```bash
pip install -e ".[dev]"
pytest --cov
```

The tests run against simulated hardware (`tests/fakes.py`): a charger register file and an smbus2 bus with a TPS25751 host interface. The tests of the TPS25751 path are skipped when `tps25751` is not installed.

## Credits

The register map follows the Texas Instruments datasheets SLUSDV2 (BQ25798), BQ25792 and BQ25790, and the PD controller interface the TPS25751 Technical Reference Manual (SLVUCR8). This project is not affiliated with Texas Instruments.
