"""Status, fault, flag and mask bits as :class:`~enum.IntFlag`.

Each class spans consecutive 8-bit registers; register ``start + n``, bit ``b`` is flag bit
``n * 8 + b``. Status and fault bits (0x1B-0x21) show the current state; flags (0x22-0x27) latch
a change and clear when read; masks (0x28-0x2D) keep an event from pulsing INT.
"""

from __future__ import annotations

from enum import IntFlag


def _bit(reg_index: int, bit: int) -> int:
    return 1 << (reg_index * 8 + bit)


class Status(IntFlag):
    """Single-bit status in REG1B-REG1F (the multi-bit states are separate properties)."""

    # REG1B
    VBUS_PRESENT = _bit(0, 0)
    AC1_PRESENT = _bit(0, 1)
    AC2_PRESENT = _bit(0, 2)
    POWER_GOOD = _bit(0, 3)
    POOR_SOURCE = _bit(0, 4)  # BQ25790, BQ25792
    WATCHDOG_EXPIRED = _bit(0, 5)
    VINDPM = _bit(0, 6)
    IINDPM = _bit(0, 7)
    # REG1C bit 0
    BC12_DONE = _bit(1, 0)
    # REG1D
    VBAT_PRESENT = _bit(2, 0)
    DPDM_ONGOING = _bit(2, 1)
    THERMAL_REGULATION = _bit(2, 2)
    # REG1E
    PRECHARGE_TIMER_EXPIRED = _bit(3, 1)
    TRICKLE_TIMER_EXPIRED = _bit(3, 2)
    CHARGE_TIMER_EXPIRED = _bit(3, 3)
    VSYSMIN_REGULATION = _bit(3, 4)
    ADC_DONE = _bit(3, 5)
    ACRB1_PLACED = _bit(3, 6)
    ACRB2_PLACED = _bit(3, 7)
    # REG1F
    TS_HOT = _bit(4, 0)
    TS_WARM = _bit(4, 1)
    TS_COOL = _bit(4, 2)
    TS_COLD = _bit(4, 3)
    VBAT_TOO_LOW_FOR_OTG = _bit(4, 4)


class Fault(IntFlag):
    """Fault status in REG20-REG21."""

    VAC1_OVP = _bit(0, 0)
    VAC2_OVP = _bit(0, 1)
    CONVERTER_OCP = _bit(0, 2)
    IBAT_OCP = _bit(0, 3)
    IBUS_OCP = _bit(0, 4)
    VBAT_OVP = _bit(0, 5)
    VBUS_OVP = _bit(0, 6)
    IBAT_REGULATION = _bit(0, 7)
    THERMAL_SHUTDOWN = _bit(1, 2)
    OTG_UVP = _bit(1, 4)
    OTG_OVP = _bit(1, 5)
    VSYS_OVP = _bit(1, 6)
    VSYS_SHORT = _bit(1, 7)


class Event(IntFlag):
    """Events, as latched by the flag registers REG22-REG27 and masked by REG28-REG2D."""

    # REG22 / REG28
    VBUS_PRESENT = _bit(0, 0)
    AC1_PRESENT = _bit(0, 1)
    AC2_PRESENT = _bit(0, 2)
    POWER_GOOD = _bit(0, 3)
    POOR_SOURCE = _bit(0, 4)
    WATCHDOG = _bit(0, 5)
    VINDPM = _bit(0, 6)
    IINDPM = _bit(0, 7)
    # REG23 / REG29
    BC12_DONE = _bit(1, 0)
    VBAT_PRESENT = _bit(1, 1)
    THERMAL_REGULATION = _bit(1, 2)
    VBUS_STATUS = _bit(1, 4)
    ICO = _bit(1, 6)
    CHARGE_STATUS = _bit(1, 7)
    # REG24 / REG2A
    TOPOFF_TIMER = _bit(2, 0)
    PRECHARGE_TIMER = _bit(2, 1)
    TRICKLE_TIMER = _bit(2, 2)
    CHARGE_TIMER = _bit(2, 3)
    VSYSMIN_REGULATION = _bit(2, 4)
    ADC_DONE = _bit(2, 5)
    DPDM_DONE = _bit(2, 6)
    # REG25 / REG2B
    TS_HOT = _bit(3, 0)
    TS_WARM = _bit(3, 1)
    TS_COOL = _bit(3, 2)
    TS_COLD = _bit(3, 3)
    VBAT_TOO_LOW_FOR_OTG = _bit(3, 4)
    # REG26 / REG2C
    VAC1_OVP = _bit(4, 0)
    VAC2_OVP = _bit(4, 1)
    CONVERTER_OCP = _bit(4, 2)
    IBAT_OCP = _bit(4, 3)
    IBUS_OCP = _bit(4, 4)
    VBAT_OVP = _bit(4, 5)
    VBUS_OVP = _bit(4, 6)
    IBAT_REGULATION = _bit(4, 7)
    # REG27 / REG2D
    THERMAL_SHUTDOWN = _bit(5, 2)
    OTG_UVP = _bit(5, 4)
    OTG_OVP = _bit(5, 5)
    VSYS_OVP = _bit(5, 6)
    VSYS_SHORT = _bit(5, 7)
