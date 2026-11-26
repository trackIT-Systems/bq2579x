"""The BQ2579x charger family: BQ25790, BQ25792 and BQ25798.

The three share one register map; the BQ25798 adds MPPT and backup mode, the BQ25790 has other
VAC_OVP thresholds. :func:`open` reads the part number and returns the matching class.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, fields as dc_fields
from typing import Any

from .bus import I2CDevice
from .enums import (
    AdcAverage,
    AdcAverageInit,
    AdcRate,
    AdcResolution,
    BackupThreshold,
    BatteryLowVoltage,
    CellCount,
    ChargeStatus,
    ChargeTimer,
    DischargeCurrentLimit,
    DpDmDac,
    IcoStatus,
    JeitaCurrent,
    JeitaVoltage,
    PartNumber,
    PrechargeTimer,
    PwmFrequency,
    RechargeDeglitch,
    ShipFetControl,
    ShipFetDelay,
    ThermalRegulation,
    ThermalShutdown,
    TopoffTimer,
    TsCold,
    TsCool,
    TsHot,
    TsWarm,
    VacOvp,
    VacOvp25790,
    VbusStatus,
    VocDelay,
    VocPercent,
    VocRate,
    WakeupDelay,
    WatchdogTimeout,
)
from .fields import REG_RST, WATCHDOG, Bit, Choice, Field, FieldInfo, FlagGroup, Number, field_info
from .flags import Event, Fault, Status

ADDRESS = 0x6B
REG_COUNT = 0x49  # REG00-REG48, readable in one transfer
REG_PART_INFO = 0x48

W = (WATCHDOG, REG_RST)  # reset by a watchdog expiry and by REG_RST
NONE: tuple[str, ...] = ()


class WriteVerifyError(OSError):
    """A written value did not read back."""


class UnknownPartError(OSError):
    """The part number in REG48 is not one of the BQ2579x family."""


@dataclass(frozen=True)
class ChargerStatus:
    """REG1B-REG21, read in one transfer."""

    charge_status: ChargeStatus | int
    vbus_status: VbusStatus | int
    ico_status: IcoStatus | int
    status: Status
    faults: Fault


@dataclass(frozen=True)
class Measurements:
    """The ADC channels in V, A, % (TS of REGN) and °C."""

    vbus_voltage: float
    vac1_voltage: float
    vac2_voltage: float
    battery_voltage: float
    system_voltage: float
    vbus_current: float
    battery_current: float
    ts_percent: float
    die_temperature: float
    dplus_voltage: float
    dminus_voltage: float

    def as_dict(self) -> dict[str, float]:
        return {f.name: getattr(self, f.name) for f in dc_fields(self)}


def _num(reg, msb, lsb, step, unit, datasheet, doc, **kw) -> Number:
    return Number(reg, msb, lsb, step=step, unit=unit, datasheet=datasheet, doc=doc, **kw)


def _adc(reg, datasheet, doc, step=0.001, unit="V", signed=False) -> Number:
    return Number(reg, 15, 0, size=2, step=step, unit=unit, signed=signed, readonly=True, datasheet=datasheet, doc=doc)


class BQ2579x:
    """Common driver for the BQ2579x family. Use :func:`open` to get the class of the actual chip.

    Every property reads or writes the chip on access. Writes are read-modify-write; when the
    device only queues writes (the TPS25751 tunnel), or with ``verify=True``, they are read back.
    """

    part: PartNumber | None = None

    # REG00-REG0A: charge parameters
    min_system_voltage = _num(0x00, 5, 0, 0.25, "V", "VSYSMIN", "Minimal system voltage", offset=2.5, max=16.0)
    charge_voltage = _num(0x01, 10, 0, 0.01, "V", "VREG", "Charge voltage limit", size=2, min=3.0, max=18.8)
    charge_current = _num(0x03, 8, 0, 0.01, "A", "ICHG", "Charge current limit", size=2, min=0.05, max=5.0, reset_by=W)
    input_voltage_limit = _num(0x05, 7, 0, 0.1, "V", "VINDPM", "Absolute input voltage limit (VINDPM)",
                               min=3.6, max=22.0, reset_by=NONE, volatile=True)
    input_current_limit = _num(0x06, 8, 0, 0.01, "A", "IINDPM", "Input current limit", size=2, min=0.1, max=3.3,
                               volatile=True)
    battery_low_voltage = Choice(0x08, 7, 6, BatteryLowVoltage, datasheet="VBAT_LOWV",
                                 doc="Precharge to fast charge threshold, fraction of VREG")
    precharge_current = _num(0x08, 5, 0, 0.04, "A", "IPRECHG", "Precharge current limit", min=0.04, max=2.0, reset_by=W)
    register_reset = Bit(0x09, 6, datasheet="REG_RST", volatile=True, doc="Reset all registers to their defaults")
    termination_current = _num(0x09, 4, 0, 0.04, "A", "ITERM", "Termination current", min=0.04, max=1.0, reset_by=W)
    cell_count = Choice(0x0A, 7, 6, CellCount, datasheet="CELL", doc="Battery cells in series")
    recharge_deglitch = Choice(0x0A, 5, 4, RechargeDeglitch, datasheet="TRECHG", reset_by=W,
                               doc="Battery recharge deglitch time")
    recharge_offset = _num(0x0A, 3, 0, 0.05, "V", "VRECHG", "Recharge threshold below VREG", offset=0.05, max=0.8,
                           reset_by=W)

    # REG0B-REG0E: OTG and timers
    otg_voltage = _num(0x0B, 10, 0, 0.01, "V", "VOTG", "OTG output voltage", size=2, offset=2.8, max=22.0, reset_by=W)
    precharge_timer = Choice(0x0D, 7, 7, PrechargeTimer, datasheet="PRECHG_TMR", reset_by=W,
                             doc="Precharge safety timer")
    otg_current = _num(0x0D, 6, 0, 0.04, "A", "IOTG", "OTG current limit", min=0.12, max=3.32, reset_by=W)
    topoff_timer = Choice(0x0E, 7, 6, TopoffTimer, datasheet="TOPOFF_TMR", reset_by=W, doc="Top-off timer")
    trickle_timer_enabled = Bit(0x0E, 5, datasheet="EN_TRICHG_TMR", reset_by=W, doc="Trickle charge timer enabled")
    precharge_timer_enabled = Bit(0x0E, 4, datasheet="EN_PRECHG_TMR", reset_by=W, doc="Precharge timer enabled")
    charge_timer_enabled = Bit(0x0E, 3, datasheet="EN_CHG_TMR", reset_by=W, doc="Fast charge timer enabled")
    charge_timer = Choice(0x0E, 2, 1, ChargeTimer, datasheet="CHG_TMR", reset_by=W, doc="Fast charge safety timer")
    timer_slowdown_enabled = Bit(0x0E, 0, datasheet="TMR2X_EN", reset_by=W,
                                 doc="Timers run at half speed during DPM and thermal regulation")

    # REG0F: charger control 0
    auto_battery_discharge_enabled = Bit(0x0F, 7, datasheet="EN_AUTO_IBATDIS",
                                         doc="Discharge the battery on battery OVP")
    force_battery_discharge = Bit(0x0F, 6, datasheet="FORCE_IBATDIS", doc="Force a battery discharge current")
    charge_enabled = Bit(0x0F, 5, datasheet="EN_CHG", reset_by=W, doc="Charging enabled")
    ico_enabled = Bit(0x0F, 4, datasheet="EN_ICO", doc="Input current optimizer enabled")
    force_ico = Bit(0x0F, 3, datasheet="FORCE_ICO", reset_by=W, volatile=True, doc="Start the input current optimizer")
    hiz_enabled = Bit(0x0F, 2, datasheet="EN_HIZ", volatile=True, doc="High impedance mode")
    termination_enabled = Bit(0x0F, 1, datasheet="EN_TERM", reset_by=W, doc="Charge termination enabled")

    # REG10: charger control 1
    vac_ovp = Choice(0x10, 5, 4, VacOvp, datasheet="VAC_OVP", doc="VAC1/VAC2 over-voltage threshold")
    watchdog_reset = Bit(0x10, 3, datasheet="WD_RST", reset_by=W, volatile=True, doc="Reset the watchdog timer")
    watchdog_timeout = Choice(0x10, 2, 0, WatchdogTimeout, datasheet="WATCHDOG", doc="Watchdog timeout")

    # REG11: charger control 2
    force_dpdm_detection = Bit(0x11, 7, datasheet="FORCE_INDET", reset_by=W, volatile=True,
                               doc="Start D+/D- detection")
    auto_dpdm_detection_enabled = Bit(0x11, 6, datasheet="AUTO_INDET_EN", reset_by=W,
                                      doc="D+/D- detection when VBUS is plugged in")
    hvdcp_12v_enabled = Bit(0x11, 5, datasheet="EN_12V", doc="12 V in HVDCP")
    hvdcp_9v_enabled = Bit(0x11, 4, datasheet="EN_9V", doc="9 V in HVDCP")
    hvdcp_enabled = Bit(0x11, 3, datasheet="HVDCP_EN", doc="HVDCP handshake")
    ship_fet_control = Choice(0x11, 2, 1, ShipFetControl, datasheet="SDRV_CTRL", volatile=True,
                              doc="Ship FET: shutdown, ship mode or system reset")
    ship_fet_delay = Choice(0x11, 0, 0, ShipFetDelay, datasheet="SDRV_DLY", doc="Delay before the ship FET action")

    # REG12: charger control 3
    acdrv_disabled = Bit(0x12, 7, datasheet="DIS_ACDRV", doc="ACDRV1 and ACDRV2 off")
    otg_enabled = Bit(0x12, 6, datasheet="EN_OTG", reset_by=W, doc="OTG mode")
    pfm_otg_disabled = Bit(0x12, 5, datasheet="PFM_OTG_DIS", reset_by=W, doc="No PFM in OTG mode")
    pfm_forward_disabled = Bit(0x12, 4, datasheet="PFM_FWD_DIS", doc="No PFM in forward mode")
    wakeup_delay = Choice(0x12, 3, 3, WakeupDelay, datasheet="WKUP_DLY", doc="QON low time to leave ship mode")
    ldo_disabled = Bit(0x12, 2, datasheet="DIS_LDO", reset_by=W, doc="BATFET LDO mode in precharge off")
    ooa_otg_disabled = Bit(0x12, 1, datasheet="DIS_OTG_OOA", reset_by=W, doc="Out-of-audio off in OTG mode")
    ooa_forward_disabled = Bit(0x12, 0, datasheet="DIS_FWD_OOA", doc="Out-of-audio off in forward mode")

    # REG13: charger control 4
    acdrv2_enabled = Bit(0x13, 7, datasheet="EN_ACDRV2", volatile=True, doc="ACFET2-RBFET2 on")
    acdrv1_enabled = Bit(0x13, 6, datasheet="EN_ACDRV1", volatile=True, doc="ACFET1-RBFET1 on")
    pwm_frequency = Choice(0x13, 5, 5, PwmFrequency, datasheet="PWM_FREQ", doc="Switching frequency")
    stat_pin_disabled = Bit(0x13, 4, datasheet="DIS_STAT", reset_by=W, doc="STAT pin output off")
    vsys_short_protection_disabled = Bit(0x13, 3, datasheet="DIS_VSYS_SHORT", doc="VSYS short hiccup off")
    otg_uvp_disabled = Bit(0x13, 2, datasheet="DIS_VOTG_UVP", doc="VOTG under-voltage protection off")
    force_vindpm_detection = Bit(0x13, 1, datasheet="FORCE_VINDPM_DET", volatile=True,
                                 doc="Measure VBUS and set VINDPM")
    ibus_ocp_enabled = Bit(0x13, 0, datasheet="EN_IBUS_OCP", doc="IBUS over-current protection")

    # REG14: charger control 5
    ship_fet_present = Bit(0x14, 7, datasheet="SFET_PRESENT", doc="A ship FET is fitted")
    battery_discharge_sensing_enabled = Bit(0x14, 5, datasheet="EN_IBAT", reset_by=W,
                                            doc="Measure the battery discharge current")
    discharge_current_limit = Choice(0x14, 4, 3, DischargeCurrentLimit, datasheet="IBAT_REG", reset_by=W,
                                     doc="Battery discharge current regulation in OTG mode")
    iindpm_enabled = Bit(0x14, 2, datasheet="EN_IINDPM", reset_by=W, doc="Internal input current limit")
    ilim_pin_enabled = Bit(0x14, 1, datasheet="EN_EXTILIM", doc="ILIM_HIZ pin current limit")
    battery_ocp_enabled = Bit(0x14, 0, datasheet="EN_BATOC", reset_by=W, doc="Battery discharge over-current protection")

    # REG16: temperature control
    thermal_regulation = Choice(0x16, 7, 6, ThermalRegulation, datasheet="TREG", reset_by=W,
                                doc="Junction temperature regulation")
    thermal_shutdown = Choice(0x16, 5, 4, ThermalShutdown, datasheet="TSHUT", reset_by=W, doc="Thermal shutdown")
    vbus_pulldown_enabled = Bit(0x16, 3, datasheet="VBUS_PD_EN", doc="VBUS pull-down")
    vac1_pulldown_enabled = Bit(0x16, 2, datasheet="VAC1_PD_EN", doc="VAC1 pull-down")
    vac2_pulldown_enabled = Bit(0x16, 1, datasheet="VAC2_PD_EN", doc="VAC2 pull-down")

    # REG17-REG18: NTC
    jeita_warm_voltage = Choice(0x17, 7, 5, JeitaVoltage, datasheet="JEITA_VSET", reset_by=W,
                                doc="Charge voltage in the warm range")
    jeita_warm_current = Choice(0x17, 4, 3, JeitaCurrent, datasheet="JEITA_ISETH", reset_by=W,
                                doc="Charge current in the warm range")
    jeita_cool_current = Choice(0x17, 2, 1, JeitaCurrent, datasheet="JEITA_ISETC", reset_by=W,
                                doc="Charge current in the cool range")
    ts_cool_threshold = Choice(0x18, 7, 6, TsCool, datasheet="TS_COOL", reset_by=W, doc="TS cool threshold (T2)")
    ts_warm_threshold = Choice(0x18, 5, 4, TsWarm, datasheet="TS_WARM", reset_by=W, doc="TS warm threshold (T3)")
    otg_hot_threshold = Choice(0x18, 3, 2, TsHot, datasheet="BHOT", reset_by=W, doc="OTG hot threshold")
    otg_cold_threshold = Choice(0x18, 1, 1, TsCold, datasheet="BCOLD", reset_by=W, doc="OTG cold threshold")
    ts_ignore = Bit(0x18, 0, datasheet="TS_IGNORE", reset_by=W, doc="Ignore the TS pin")

    # REG19-REG21: status
    ico_current_limit = _num(0x19, 8, 0, 0.01, "A", "ICO_ILIM", "Input current found by ICO", size=2, readonly=True)
    status = FlagGroup(0x1B, 5, Status, datasheet="REG1B-REG1F", readonly=True, doc="Status bits")
    charge_status = Choice(0x1C, 7, 5, ChargeStatus, datasheet="CHG_STAT", readonly=True, doc="Charge state")
    vbus_status = Choice(0x1C, 4, 1, VbusStatus, datasheet="VBUS_STAT", readonly=True, doc="Input source")
    ico_status = Choice(0x1D, 7, 6, IcoStatus, datasheet="ICO_STAT", readonly=True, doc="Input current optimizer")
    faults = FlagGroup(0x20, 2, Fault, datasheet="REG20-REG21", readonly=True, doc="Fault status")

    # REG28-REG2D: interrupt masks
    interrupt_mask = FlagGroup(0x28, 6, Event, datasheet="REG28-REG2D",
                               doc="Events that do not pulse INT (TS masks are also reset by the watchdog)")

    # REG2E-REG30: ADC control
    adc_enabled = Bit(0x2E, 7, datasheet="ADC_EN", reset_by=W, volatile=True,
                      doc="ADC on (cleared after a one-shot conversion)")
    adc_rate = Choice(0x2E, 6, 6, AdcRate, datasheet="ADC_RATE", doc="Continuous or one-shot")
    adc_resolution = Choice(0x2E, 5, 4, AdcResolution, datasheet="ADC_SAMPLE", doc="Effective resolution")
    adc_average = Choice(0x2E, 3, 3, AdcAverage, datasheet="ADC_AVG", doc="Single value or running average")
    adc_average_init = Choice(0x2E, 2, 2, AdcAverageInit, datasheet="ADC_AVG_INIT", doc="Running average start value")
    vbus_current_adc_disabled = Bit(0x2F, 7, datasheet="IBUS_ADC_DIS", doc="IBUS channel off")
    battery_current_adc_disabled = Bit(0x2F, 6, datasheet="IBAT_ADC_DIS", doc="IBAT channel off")
    vbus_voltage_adc_disabled = Bit(0x2F, 5, datasheet="VBUS_ADC_DIS", doc="VBUS channel off")
    battery_voltage_adc_disabled = Bit(0x2F, 4, datasheet="VBAT_ADC_DIS", doc="VBAT channel off")
    system_voltage_adc_disabled = Bit(0x2F, 3, datasheet="VSYS_ADC_DIS", doc="VSYS channel off")
    ts_adc_disabled = Bit(0x2F, 2, datasheet="TS_ADC_DIS", doc="TS channel off")
    die_temperature_adc_disabled = Bit(0x2F, 1, datasheet="TDIE_ADC_DIS", doc="TDIE channel off")
    dplus_adc_disabled = Bit(0x30, 7, datasheet="DP_ADC_DIS", doc="D+ channel off")
    dminus_adc_disabled = Bit(0x30, 6, datasheet="DM_ADC_DIS", doc="D- channel off")
    vac2_voltage_adc_disabled = Bit(0x30, 5, datasheet="VAC2_ADC_DIS", doc="VAC2 channel off")
    vac1_voltage_adc_disabled = Bit(0x30, 4, datasheet="VAC1_ADC_DIS", doc="VAC1 channel off")

    # REG31-REG45: ADC results
    vbus_current = _adc(0x31, "IBUS_ADC", "VBUS current (negative in OTG mode)", unit="A", signed=True)
    battery_current = _adc(0x33, "IBAT_ADC", "Battery current (negative when discharging)", unit="A", signed=True)
    vbus_voltage = _adc(0x35, "VBUS_ADC", "VBUS voltage")
    vac1_voltage = _adc(0x37, "VAC1_ADC", "VAC1 voltage")
    vac2_voltage = _adc(0x39, "VAC2_ADC", "VAC2 voltage")
    battery_voltage = _adc(0x3B, "VBAT_ADC", "Battery voltage")
    system_voltage = _adc(0x3D, "VSYS_ADC", "System voltage")
    ts_percent = _adc(0x3F, "TS_ADC", "TS voltage as percentage of REGN", step=0.0976563, unit="%")
    die_temperature = _adc(0x41, "TDIE_ADC", "Die temperature", step=0.5, unit="°C", signed=True)
    dplus_voltage = _adc(0x43, "D+_ADC", "D+ voltage")
    dminus_voltage = _adc(0x45, "D-_ADC", "D- voltage")

    # REG47-REG48
    dplus_dac = Choice(0x47, 7, 5, DpDmDac, datasheet="DPLUS_DAC", doc="D+ output driver")
    dminus_dac = Choice(0x47, 4, 2, DpDmDac, datasheet="DMINUS_DAC", doc="D- output driver")
    part_number = Choice(0x48, 5, 3, PartNumber, datasheet="PN", readonly=True, doc="Part number")
    device_revision = Field(0x48, 2, 0, datasheet="DEV_REV", readonly=True, doc="Device revision")

    _events = FlagGroup(0x22, 6, Event, datasheet="REG22-REG27", readonly=True,
                        doc="Latched events (cleared when read); use read_events()")

    def __init__(self, device: I2CDevice, verify: bool | None = None):
        self.device = device
        self.verify = device.queued_writes if verify is None else verify

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.device!r})"

    # --- field access ---

    def _read_field(self, field: Field) -> int:
        return field.extract(self.device.read(field.reg, field.size), field.reg)

    def _write_field(self, field: Field, raw: int) -> None:
        new = field.merge(self.device.read(field.reg, field.size), raw)
        self.device.write(field.reg, new)
        if not self.verify or field.volatile:
            return
        for _ in range(10):
            if self._read_field(field) == raw & (field.mask >> field.lsb):
                return
            time.sleep(0.01)
        raise WriteVerifyError(f"{field.name} ({field.datasheet}) did not read back after the write")

    @classmethod
    def fields(cls) -> dict[str, Field]:
        """All properties of this part, in register order."""
        found: dict[str, Field] = {}
        for klass in reversed(cls.__mro__):
            for name, attr in vars(klass).items():
                if isinstance(attr, Field) and not name.startswith("_"):
                    found[name] = attr
        return dict(sorted(found.items(), key=lambda kv: (kv[1].reg, -kv[1].msb)))

    @classmethod
    def field_infos(cls) -> list[FieldInfo]:
        return [field_info(f) for f in cls.fields().values()]

    # --- bulk access ---

    def read_registers(self) -> bytes:
        """REG00-REG48 in one transfer. This clears the flag registers REG22-REG27."""
        return self.device.read(0x00, REG_COUNT)

    def dump(self) -> dict[str, Any]:
        """Every property decoded from one transfer, plus ``events`` (cleared by the read)."""
        regs = self.read_registers()
        values = {name: f.decode(f.extract(regs)) for name, f in self.fields().items()}
        events = type(self)._events
        values["events"] = events.decode(events.extract(regs))
        return values

    def read_status(self) -> ChargerStatus:
        """Status and faults (REG1B-REG21) in one transfer."""
        base = 0x1B
        regs = self.device.read(base, 0x21 - base + 1)
        get = type(self)

        def dec(f: Field) -> Any:
            return f.decode(f.extract(regs, base))

        return ChargerStatus(
            charge_status=dec(get.charge_status),
            vbus_status=dec(get.vbus_status),
            ico_status=dec(get.ico_status),
            status=dec(get.status),
            faults=dec(get.faults),
        )

    def read_events(self) -> Event:
        """The latched events (REG22-REG27); reading clears them."""
        return self._events

    def measure(self, timeout: float = 1.0) -> Measurements:
        """All ADC channels. Starts a one-shot conversion unless the ADC runs continuously."""
        if not (self.adc_enabled and self.adc_rate == AdcRate.CONTINUOUS):
            self.adc_rate = AdcRate.ONE_SHOT
            self.adc_enabled = True
            deadline = time.monotonic() + timeout
            time.sleep(self.adc_resolution.conversion_time * 11)
            while self.adc_enabled:  # cleared when the one-shot conversion is done
                if time.monotonic() > deadline:
                    raise TimeoutError("ADC conversion not done in time")
                time.sleep(0.01)
        base = 0x31
        regs = self.device.read(base, 0x46 - base + 1)
        cls = type(self)
        return Measurements(**{
            f.name: getattr(cls, f.name).decode(getattr(cls, f.name).extract(regs, base))
            for f in dc_fields(Measurements)
        })

    # --- actions ---

    def kick_watchdog(self) -> None:
        """Reset the watchdog timer."""
        self.watchdog_reset = True

    def reset(self) -> None:
        """Reset every register to its default (REG_RST)."""
        self.register_reset = True


class BQ25790(BQ2579x):
    """BQ25790 (DSBGA): VAC_OVP code 1 is 22 V."""

    part = PartNumber.BQ25790
    vac_ovp = Choice(0x10, 5, 4, VacOvp25790, datasheet="VAC_OVP", doc="VAC1/VAC2 over-voltage threshold")


class BQ25792(BQ2579x):
    """BQ25792 (QFN)."""

    part = PartNumber.BQ25792


class BQ25798(BQ2579x):
    """BQ25798: adds solar MPPT and backup mode."""

    part = PartNumber.BQ25798

    stop_charge_on_watchdog = Bit(0x09, 5, datasheet="STOP_WD_CHG",
                                  doc="A watchdog expiry clears EN_CHG (stops charging)")
    otg_current = _num(0x0D, 6, 0, 0.04, "A", "IOTG", "OTG current limit", min=0.16, max=3.36, reset_by=W)
    backup_enabled = Bit(0x0F, 0, datasheet="EN_BACKUP", reset_by=W, doc="Backup mode enabled")
    backup_threshold = Choice(0x10, 7, 6, BackupThreshold, datasheet="VBUS_BACKUP",
                              doc="VBUS level that starts backup mode, fraction of VINDPM")
    mppt_voc_percent = Choice(0x15, 7, 5, VocPercent, datasheet="VOC_PCT",
                              doc="MPPT: VINDPM as a fraction of the open-circuit voltage")
    mppt_voc_delay = Choice(0x15, 4, 3, VocDelay, datasheet="VOC_DLY", doc="MPPT: settling time before measuring VOC")
    mppt_voc_rate = Choice(0x15, 2, 1, VocRate, datasheet="VOC_RATE", doc="MPPT: interval between VOC measurements")
    mppt_enabled = Bit(0x15, 0, datasheet="EN_MPPT", doc="MPPT enabled")
    backup_acfet1_on = Bit(0x16, 0, datasheet="BKUP_ACFET1_ON", volatile=True,
                           doc="Turn ACFET1 on in backup mode")


PARTS: dict[PartNumber, type[BQ2579x]] = {cls.part: cls for cls in (BQ25790, BQ25792, BQ25798)}


def open(device: I2CDevice, part: PartNumber | str | None = None, verify: bool | None = None) -> BQ2579x:  # noqa: A001
    """The driver for the chip on ``device``, chosen by its part number (REG48) unless ``part`` is given."""
    if part is None:
        pn = (device.read(REG_PART_INFO, 1)[0] >> 3) & 0x7
        try:
            part = PartNumber(pn)
        except ValueError:
            raise UnknownPartError(f"unknown part number {pn} in REG48, not a BQ2579x") from None
    elif isinstance(part, str):
        part = PartNumber[part.upper()]
    return PARTS[PartNumber(part)](device, verify=verify)
