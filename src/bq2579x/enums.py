"""Enumerations for the choice fields; the values are the register codes."""

from __future__ import annotations

from enum import IntEnum


class BatteryLowVoltage(IntEnum):
    """VBAT_LOWV: the precharge-to-fast-charge threshold, as a fraction of VREG."""

    PCT_15 = 0
    PCT_62_2 = 1
    PCT_66_7 = 2
    PCT_71_4 = 3


class CellCount(IntEnum):
    """CELL: number of cells in series."""

    S1 = 0
    S2 = 1
    S3 = 2
    S4 = 3


class RechargeDeglitch(IntEnum):
    """TRECHG: battery recharge deglitch time."""

    MS_64 = 0
    MS_256 = 1
    MS_1024 = 2
    MS_2048 = 3


class PrechargeTimer(IntEnum):
    """PRECHG_TMR: precharge safety timer."""

    H_2 = 0
    H_0_5 = 1


class TopoffTimer(IntEnum):
    """TOPOFF_TMR: top-off timer after termination."""

    DISABLED = 0
    MIN_15 = 1
    MIN_30 = 2
    MIN_45 = 3


class ChargeTimer(IntEnum):
    """CHG_TMR: fast charge safety timer."""

    H_5 = 0
    H_8 = 1
    H_12 = 2
    H_24 = 3


class BackupThreshold(IntEnum):
    """VBUS_BACKUP (BQ25798): VBUS level that triggers backup mode, as a fraction of VINDPM."""

    PCT_40 = 0
    PCT_60 = 1
    PCT_80 = 2
    PCT_100 = 3


class VacOvp(IntEnum):
    """VAC_OVP: VAC1/VAC2 over-voltage threshold (BQ25792, BQ25798)."""

    V_26 = 0
    V_18 = 1
    V_12 = 2
    V_7 = 3


class VacOvp25790(IntEnum):
    """VAC_OVP on the BQ25790, where code 1 is 22 V."""

    V_26 = 0
    V_22 = 1
    V_12 = 2
    V_7 = 3


class WatchdogTimeout(IntEnum):
    """WATCHDOG: I2C watchdog timeout."""

    OFF = 0
    S_0_5 = 1
    S_1 = 2
    S_2 = 3
    S_20 = 4
    S_40 = 5
    S_80 = 6
    S_160 = 7

    @property
    def seconds(self) -> float | None:
        return (None, 0.5, 1, 2, 20, 40, 80, 160)[self]


class ShipFetControl(IntEnum):
    """SDRV_CTRL: ship FET mode."""

    IDLE = 0
    SHUTDOWN = 1
    SHIP = 2
    SYSTEM_RESET = 3


class ShipFetDelay(IntEnum):
    """SDRV_DLY: delay before the ship FET action."""

    S_10 = 0
    NONE = 1


class WakeupDelay(IntEnum):
    """WKUP_DLY: QON low time to leave ship mode."""

    S_1 = 0
    MS_15 = 1


class PwmFrequency(IntEnum):
    """PWM_FREQ: converter switching frequency."""

    MHZ_1_5 = 0
    KHZ_750 = 1


class DischargeCurrentLimit(IntEnum):
    """IBAT_REG: battery discharge current regulation in OTG mode."""

    A_3 = 0
    A_4 = 1
    A_5 = 2
    DISABLED = 3


class VocPercent(IntEnum):
    """VOC_PCT (BQ25798): MPPT operating point as a fraction of the open-circuit voltage."""

    PCT_56_25 = 0
    PCT_62_5 = 1
    PCT_68_75 = 2
    PCT_75 = 3
    PCT_81_25 = 4
    PCT_87_5 = 5
    PCT_93_75 = 6
    PCT_100 = 7


class VocDelay(IntEnum):
    """VOC_DLY (BQ25798): settling time before VOC is measured."""

    MS_50 = 0
    MS_300 = 1
    S_2 = 2
    S_5 = 3


class VocRate(IntEnum):
    """VOC_RATE (BQ25798): interval between VOC measurements."""

    S_30 = 0
    MIN_2 = 1
    MIN_10 = 2
    MIN_30 = 3


class ThermalRegulation(IntEnum):
    """TREG: junction temperature regulation threshold."""

    C_60 = 0
    C_80 = 1
    C_100 = 2
    C_120 = 3


class ThermalShutdown(IntEnum):
    """TSHUT: thermal shutdown threshold."""

    C_150 = 0
    C_130 = 1
    C_120 = 2
    C_85 = 3


class JeitaVoltage(IntEnum):
    """JEITA_VSET: charge voltage in the warm range (TWARM-THOT)."""

    SUSPEND = 0
    VREG_MINUS_800MV = 1
    VREG_MINUS_600MV = 2
    VREG_MINUS_400MV = 3
    VREG_MINUS_300MV = 4
    VREG_MINUS_200MV = 5
    VREG_MINUS_100MV = 6
    UNCHANGED = 7


class JeitaCurrent(IntEnum):
    """JEITA_ISETH / JEITA_ISETC: charge current in the warm / cool range."""

    SUSPEND = 0
    PCT_20 = 1
    PCT_40 = 2
    UNCHANGED = 3


class TsCool(IntEnum):
    """TS_COOL: T2 threshold, as TS/REGN ratio (temperature with a 103AT NTC)."""

    PCT_71_1 = 0  # 5 °C
    PCT_68_4 = 1  # 10 °C
    PCT_65_5 = 2  # 15 °C
    PCT_62_4 = 3  # 20 °C


class TsWarm(IntEnum):
    """TS_WARM: T3 threshold, as TS/REGN ratio (temperature with a 103AT NTC)."""

    PCT_48_4 = 0  # 40 °C
    PCT_44_8 = 1  # 45 °C
    PCT_41_2 = 2  # 50 °C
    PCT_37_7 = 3  # 55 °C


class TsHot(IntEnum):
    """BHOT: OTG hot temperature threshold."""

    C_55 = 0
    C_60 = 1
    C_65 = 2
    DISABLED = 3


class TsCold(IntEnum):
    """BCOLD: OTG cold temperature threshold."""

    C_MINUS_10 = 0
    C_MINUS_20 = 1


class ChargeStatus(IntEnum):
    """CHG_STAT."""

    NOT_CHARGING = 0
    TRICKLE = 1
    PRECHARGE = 2
    FAST_CC = 3
    TAPER_CV = 4
    TOPOFF = 6
    DONE = 7


class VbusStatus(IntEnum):
    """VBUS_STAT: the detected input source."""

    NO_INPUT = 0
    USB_SDP = 1
    USB_CDP = 2
    USB_DCP = 3
    HVDCP = 4
    UNKNOWN_ADAPTER = 5
    NON_STANDARD_ADAPTER = 6
    OTG = 7
    NOT_QUALIFIED = 8
    DIRECT_VBUS = 0xB
    BACKUP = 0xC  # BQ25798


class IcoStatus(IntEnum):
    """ICO_STAT."""

    DISABLED = 0
    IN_PROGRESS = 1
    MAX_CURRENT_DETECTED = 2


class AdcRate(IntEnum):
    """ADC_RATE."""

    CONTINUOUS = 0
    ONE_SHOT = 1


class AdcResolution(IntEnum):
    """ADC_SAMPLE: effective resolution (24/12/6/3 ms per channel)."""

    BITS_15 = 0
    BITS_14 = 1
    BITS_13 = 2
    BITS_12 = 3

    @property
    def conversion_time(self) -> float:
        return (0.024, 0.012, 0.006, 0.003)[self]


class AdcAverage(IntEnum):
    """ADC_AVG."""

    SINGLE = 0
    RUNNING = 1


class AdcAverageInit(IntEnum):
    """ADC_AVG_INIT: start value of the running average."""

    EXISTING = 0
    NEW_CONVERSION = 1


class DpDmDac(IntEnum):
    """DPLUS_DAC / DMINUS_DAC: D+/D- output driver."""

    HIZ = 0
    V_0 = 1
    V_0_6 = 2
    V_1_2 = 3
    V_2_0 = 4
    V_2_7 = 5
    V_3_3 = 6
    SHORT = 7  # D+ only: D+/D- short


class PartNumber(IntEnum):
    """PN in REG48."""

    BQ25790 = 0
    BQ25792 = 1
    BQ25798 = 3
