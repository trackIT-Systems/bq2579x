"""Descriptors that turn register bit fields into typed properties.

A field reads and writes its register live on every access; writes are read-modify-write and keep
the other bits of the register. Values are SI units (V, A, °C, s), :class:`bool` or an
:class:`~enum.IntEnum`.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Any

WATCHDOG = "WATCHDOG"
REG_RST = "REG_RST"


class Field:
    """A bit field ``msb..lsb`` of a register that is ``size`` bytes wide (big-endian)."""

    kind = "field"

    def __init__(
        self,
        reg: int,
        msb: int,
        lsb: int | None = None,
        *,
        datasheet: str,
        size: int = 1,
        readonly: bool = False,
        volatile: bool = False,
        reset_by: tuple[str, ...] = (REG_RST,),
        doc: str = "",
    ):
        self.reg = reg
        self.msb = msb
        self.lsb = msb if lsb is None else lsb
        self.size = size
        self.datasheet = datasheet
        self.readonly = readonly
        self.volatile = volatile  # self-clearing or changed by the chip: not verified after a write
        self.reset_by = () if readonly else reset_by
        self.doc = doc
        self.name = ""
        self.__doc__ = f"{doc} ({datasheet}, REG{reg:02X}[{self.bits}])"

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    @property
    def width(self) -> int:
        return self.msb - self.lsb + 1

    @property
    def mask(self) -> int:
        return ((1 << self.width) - 1) << self.lsb

    @property
    def bits(self) -> str:
        return str(self.msb) if self.msb == self.lsb else f"{self.msb}:{self.lsb}"

    def extract(self, regs: bytes | bytearray, base: int = 0) -> int:
        """The raw field value from a block of registers starting at register ``base``."""
        start = self.reg - base
        word = int.from_bytes(regs[start : start + self.size], "big")
        return (word & self.mask) >> self.lsb

    def merge(self, current: bytes, raw: int) -> bytes:
        """The register bytes with the field set to ``raw`` and every other bit kept."""
        word = int.from_bytes(current, "big")
        word = (word & ~self.mask) | ((raw << self.lsb) & self.mask)
        return word.to_bytes(self.size, "big")

    def decode(self, raw: int) -> Any:
        return raw

    def encode(self, value: Any) -> int:
        return int(value)

    def describe(self) -> str:
        """The value range, for listings."""
        return ""

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        return self.decode(obj._read_field(self))

    def __set__(self, obj, value) -> None:
        if self.readonly:
            raise AttributeError(f"{self.name} ({self.datasheet}) is read-only")
        obj._write_field(self, self.encode(value))


class Number(Field):
    """A number: ``value = raw * step + offset``, in ``unit``, writable between ``min`` and ``max``."""

    kind = "number"

    def __init__(
        self,
        reg: int,
        msb: int,
        lsb: int,
        *,
        step: float,
        unit: str,
        offset: float = 0.0,
        min: float | None = None,
        max: float | None = None,
        signed: bool = False,
        **kw,
    ):
        super().__init__(reg, msb, lsb, **kw)
        self.step = step
        self.offset = offset
        self.unit = unit
        self.signed = signed
        self.min = offset if min is None else min
        self.max = ((1 << self.width) - 1) * step + offset if max is None else max

    def decode(self, raw: int) -> float:
        if self.signed and raw & (1 << (self.width - 1)):
            raw -= 1 << self.width
        return round(raw * self.step + self.offset, 6)

    def encode(self, value: float) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or math.isnan(value):
            raise TypeError(f"{self.name} takes a number in {self.unit}, not {value!r}")
        eps = self.step / 1000
        if not self.min - eps <= value <= self.max + eps:
            raise ValueError(f"{self.name} must be {self.describe()}, not {value:g} {self.unit}")
        raw = round((value - self.offset) / self.step)
        return raw & ((1 << self.width) - 1)

    def describe(self) -> str:
        return f"{self.min:g}-{self.max:g} {self.unit} in steps of {self.step:g}"


class Choice(Field):
    """One of the values of an :class:`~enum.IntEnum`."""

    kind = "choice"

    def __init__(self, reg: int, msb: int, lsb: int, enum_cls: type[enum.IntEnum], **kw):
        super().__init__(reg, msb, lsb, **kw)
        self.enum = enum_cls

    def decode(self, raw: int) -> enum.IntEnum | int:
        try:
            return self.enum(raw)
        except ValueError:
            return raw  # a reserved code

    def encode(self, value: Any) -> int:
        if isinstance(value, str):
            try:
                value = self.enum[value.strip().upper()]
            except KeyError:
                raise ValueError(f"{self.name} must be one of {self.describe()}, not {value!r}") from None
        elif isinstance(value, enum.IntEnum) and not isinstance(value, self.enum):
            raise TypeError(f"{self.name} takes a {self.enum.__name__}, not a {type(value).__name__}")
        try:
            return int(self.enum(value))
        except ValueError:
            raise ValueError(f"{self.name} must be one of {self.describe()}, not {value!r}") from None

    def describe(self) -> str:
        return ", ".join(m.name for m in self.enum)


class Bit(Field):
    """A single bit as :class:`bool`."""

    kind = "bit"

    def __init__(self, reg: int, bit: int, **kw):
        super().__init__(reg, bit, bit, **kw)

    def decode(self, raw: int) -> bool:
        return bool(raw)

    def encode(self, value: Any) -> int:
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("1", "true", "on", "yes", "enable", "enabled"):
                return 1
            if v in ("0", "false", "off", "no", "disable", "disabled"):
                return 0
            raise ValueError(f"{self.name} takes true or false, not {value!r}")
        return 1 if value else 0

    def describe(self) -> str:
        return "true, false"


class FlagGroup(Field):
    """A run of ``count`` 8-bit registers as one :class:`~enum.IntFlag`; bit ``(reg - start) * 8 + bit``.

    The registers are read in one transfer, so clear-on-read flags are not lost.
    """

    kind = "flags"

    def __init__(self, reg: int, count: int, flag_cls: type[enum.IntFlag], **kw):
        super().__init__(reg, count * 8 - 1, 0, size=count, **kw)
        self.flag_cls = flag_cls
        self.count = count

    @property
    def mask(self) -> int:
        mask = 0
        for m in self.flag_cls:
            mask |= m.value
        return mask

    def extract(self, regs: bytes | bytearray, base: int = 0) -> int:
        start = self.reg - base
        return int.from_bytes(regs[start : start + self.count], "little")

    def merge(self, current: bytes, raw: int) -> bytes:
        word = int.from_bytes(current, "little")
        word = (word & ~self.mask) | (raw & self.mask)
        return word.to_bytes(self.count, "little")

    def decode(self, raw: int) -> enum.IntFlag:
        return self.flag_cls(raw & self.mask)

    def encode(self, value: Any) -> int:
        if isinstance(value, str):
            flags = self.flag_cls(0)
            for name in filter(None, (n.strip().upper() for n in value.replace("|", ",").split(","))):
                try:
                    flags |= self.flag_cls[name]
                except KeyError:
                    raise ValueError(f"{self.name}: unknown flag {name!r}") from None
            value = flags
        return int(value) & self.mask

    def describe(self) -> str:
        return " | ".join(m.name for m in self.flag_cls)


@dataclass(frozen=True)
class FieldInfo:
    """Metadata of one property, for listings and documentation."""

    name: str
    datasheet: str
    reg: int
    bits: str
    kind: str
    unit: str
    range: str
    writable: bool
    reset_by: tuple[str, ...]
    doc: str


def field_info(field: Field) -> FieldInfo:
    return FieldInfo(
        name=field.name,
        datasheet=field.datasheet,
        reg=field.reg,
        bits=field.bits,
        kind=field.kind,
        unit=getattr(field, "unit", ""),
        range=field.describe(),
        writable=not field.readonly,
        reset_by=field.reset_by,
        doc=field.doc,
    )
