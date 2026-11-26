# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), the versioning follows [Semantic Versioning](https://semver.org/).

## [0.1.0] - unreleased

### Added

- Driver for the BQ25790, BQ25792 and BQ25798, with the part detected from REG48. Every register field is a typed property in SI units, `bool` or an `IntEnum`; status, faults, events and interrupt masks are `IntFlag`s read in one transfer.
- Access over a Linux I2C bus (smbus2) or through a TPS25751 USB PD controller (4CC tasks `I2Cr`/`I2Cw`), with queued writes read back. The TPS25751 path uses the separate [tps25751](https://github.com/trackIT-Systems/tps25751) package, an optional dependency (`bq2579x[tps]`).
- `bq2579x` command line tool: `info`, `status`, `adc`, `get`, `set`, `dump`, `fields`, `watchdog`, `reset`, optional JSON output, and fallback from direct access to the TPS25751.
