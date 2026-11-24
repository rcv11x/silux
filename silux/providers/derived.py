"""Sensors derived from data already read.

Clocks, per-core usage and the power breakdown come from CPUID, cpufreq,
/proc/stat and RAPL rather than a hwmon chip, but in a sensor tree they are
the same kind of thing (changing values worth tracking with their minimum
and maximum), so they are reshaped here to match, as HWiNFO does under the
processor's node.

Runs last on purpose: it only reshapes what others collected and opens no
file.
"""

from __future__ import annotations

from typing import Optional

from ..i18n import _
from ..model import DeviceKind, Gpu, Need, Sensor, SensorKind, short_brand, thread_name
from .base import Draft, Provider

# Rounded to one decimal, 0.845 V becomes 0.8 and says nothing: each kind
# has its own precision.
DECIMALS = {SensorKind.VOLTAGE: 3, SensorKind.TEMPERATURE: 1, SensorKind.CLOCK: 1,
             SensorKind.USAGE: 1, SensorKind.MEMORY: 0, SensorKind.NETWORK: 1,
             SensorKind.DATA: 0}


def _mhz(hz: Optional[int]) -> Optional[float]:
    return round(hz / 1e6, 1) if hz else None


def _mebibytes(byte: Optional[int]) -> Optional[float]:
    return round(byte / 1024**2, 1) if byte else None


def _megabytes(byte: Optional[int]) -> Optional[float]:
    """Network totals, decimal like the Network page."""
    return round(byte / 1e6, 1) if byte else None


class DerivedSensors(Provider):
    name = "derived"
    provides = "sensors.derived"

    def collect(self, draft: Draft) -> None:
        self._shared_package(draft)
        self._power_from_rapl(draft)
        if not draft.types:
            # The GPUs may have data even without an identified processor.
            draft.sensors.extend(self._graphics(draft))
            return
        first = draft.types[next(iter(draft.types))]
        device = short_brand(first.get("brand"))

        draft.sensors.extend(self._power(draft, device))
        draft.sensors.extend(self._clocks(draft, device))
        draft.sensors.extend(self._usage(draft, device))
        draft.sensors.extend(self._graphics(draft))
        draft.sensors.extend(self._network(draft))

    @staticmethod
    def _power_from_rapl(draft: Draft) -> None:
        """An Intel GPU inside the processor gets its power from RAPL's PP1.
        Without RAPL, its page said nothing of why: it says so, with RAPL's
        reason. Missing for permissions, the padlock already says it."""
        rapl = next((n for n in draft.notes if n.path == "cpu.power"), None)
        if rapl is None or rapl.need is Need.ROOT:
            return
        for index, gpu in enumerate(draft.gpus):
            where = Gpu(vendor=gpu.get("vendor"), vendor_id=gpu.get("vendor_id"),
                        device_id=gpu.get("device_id"), integrated=gpu.get("integrated"))
            if (gpu.get("power_w") is None and where.built_in == "cpu"
                    and gpu.get("vendor") == "Intel"):
                draft.note(f"gpus.{index}.power_w", rapl.need, _("gpu.power.rapl.note"),
                           rapl.message)

    @staticmethod
    def _shared_package(draft: Draft) -> None:
        """An Intel GPU inside the processor has no temperature sensor (i915
        and xe only register hwmon for discrete cards), so it gets the
        package's, labelled as shared with the CPU. It never becomes its
        `temp_c`, so neither Sensors nor the alerts mistake it for the GPU's.
        Without a package sensor it has none, and says so."""
        degrees = draft.cpu_extra.get("package_sensor_temp_c")
        for index, gpu in enumerate(draft.gpus):
            if not (gpu.get("integrated") and gpu.get("no_temperature_sensor")
                    and gpu.get("temp_c") is None):
                continue
            gpu["package_temp_c"] = degrees
            if degrees is None:
                draft.note(f"gpus.{index}.temp_c", Need.HARDWARE, _("gpu.temp.none.note"),
                           detail=_("gpu.temp.detail"))
            else:
                draft.note(f"gpus.{index}.temp_c", Need.HARDWARE, _("gpu.temp.package.note"),
                           detail=_("gpu.temp.detail.package"))

    @staticmethod
    def _network(draft: Draft) -> list[Sensor]:
        """The rate of each interface that is up.

        Only those up: with Docker there can be fifteen idle virtual
        interfaces, and the tree gains nothing from them.
        """
        sensors: list[Sensor] = []
        for interface in draft.network:
            if not interface.up or interface.kind == "loopback":
                continue
            device = _("sensor.dev.net").format(chip=interface.name)
            traffic = interface.traffic
            fields = (
                ("rx", _("sensor.net.down"), SensorKind.NETWORK, traffic.rx_rate_bps, 0),
                ("tx", _("sensor.net.up"), SensorKind.NETWORK, traffic.tx_rate_bps, 1),
                ("rx_total", _("sensor.net.received"), SensorKind.DATA,
                 _megabytes(traffic.rx_bytes), 10),
                ("tx_total", _("sensor.net.sent"), SensorKind.DATA,
                 _megabytes(traffic.tx_bytes), 11),
            )
            for key, label, kind, value, order in fields:
                if value is None:
                    continue
                sensors.append(Sensor(
                    key=f"net/{interface.name}/{key}", chip="net", device=device,
                    device_key=f"net:{interface.name}",
                    device_kind=DeviceKind.NETWORK,
                    label=label, kind=kind,
                    value=round(float(value) / (1000 if kind is SensorKind.NETWORK else 1),
                                DECIMALS.get(kind, 1)),
                    order=order,
                ))
        return sensors

    @staticmethod
    def _graphics(draft: Draft) -> list[Sensor]:
        """The graphics card values that don't come from hwmon.

        A card's sensor chip gives temperatures, the fan and little else.
        Usage, used memory, firmware-only clocks and the regulators'
        temperatures come from the driver and its ioctl, and are just as
        worth tracking.
        """
        sensors: list[Sensor] = []
        for gpu in draft.gpus:
            device = gpu.get("name") or _("sensor.dev.gpu").format(
                n=gpu.get("index", 0))
            # The same key hwmon gives the card's chip: its PCI slot.
            device_key = (f"gpu:{gpu['pci_slot']}" if gpu.get("pci_slot")
                             else f"gpu-index:{gpu.get('index', 0)}")
            prefix = f"gpu{gpu.get('index', 0)}"
            clocks = gpu.get("clocks")
            memory = gpu.get("memory")

            fields: list[tuple[str, str, SensorKind, object, int]] = [
                ("busy", _("sensor.gpu.core"), SensorKind.USAGE,
                 gpu.get("busy_percent"), 0),
                ("mem_busy", _("sensor.gpu.mem"), SensorKind.USAGE,
                 gpu.get("memory_busy_percent"), 1),
                ("video_busy", _("sensor.gpu.video"), SensorKind.USAGE,
                 gpu.get("video_busy_percent"), 2),
                ("vr_gfx", _("sensor.gpu.vrgfx"), SensorKind.TEMPERATURE,
                 gpu.get("vr_gfx_c"), 10),
                ("vr_soc", _("sensor.gpu.vrsoc"), SensorKind.TEMPERATURE,
                 gpu.get("vr_soc_c"), 11),
                ("vr_mem", _("sensor.gpu.vrmem"), SensorKind.TEMPERATURE,
                 gpu.get("vr_memory_c"), 12),
                ("v_soc", "SoC", SensorKind.VOLTAGE, gpu.get("voltage_soc_v"), 20),
                ("v_mem", _("sensor.mem"), SensorKind.VOLTAGE,
                 gpu.get("voltage_memory_v"), 21),
                ("fan_pct", _("sensor.fan"), SensorKind.USAGE,
                 gpu.get("fan_percent"), 3),
            ]
            if gpu.get("driver") == "nvidia":
                # The proprietary driver has no hwmon: its temperature, power
                # and clocks reach the model only through NVML.
                fields += [
                    ("temp", _("sensor.gpucore"), SensorKind.TEMPERATURE,
                     gpu.get("temp_c"), 5),
                    ("power", _("sensor.power"), SensorKind.POWER, gpu.get("power_w"), 6),
                ]
                if clocks is not None:
                    fields += [
                        ("clk_core", _("sensor.gpucore"), SensorKind.CLOCK,
                         _mhz(clocks.core_hz), 30),
                        ("clk_mem", _("sensor.mem"), SensorKind.CLOCK,
                         _mhz(clocks.memory_hz), 33),
                    ]
            if clocks is not None:
                fields += [
                    ("clk_soc", "SoC", SensorKind.CLOCK, _mhz(clocks.soc_hz), 32),
                    ("clk_mem_eff", _("sensor.mem.effective"), SensorKind.CLOCK,
                     _mhz(clocks.memory_effective_hz), 31),
                ]
            if memory is not None:
                fields += [
                    ("vram_pct", _("sensor.vram"), SensorKind.USAGE,
                     memory.used_percent, 4),
                    ("vram_mb", _("sensor.vram"), SensorKind.MEMORY,
                     _mebibytes(memory.used_bytes), 40),
                    ("gtt_mb", _("sensor.gtt"), SensorKind.MEMORY,
                     _mebibytes(memory.gtt_used_bytes), 41),
                ]

            for key, label, kind, value, order in fields:
                if value is None:
                    continue
                sensors.append(Sensor(
                    key=f"{prefix}/{key}", chip="drm", device=device,
                    device_key=device_key,
                    device_kind=DeviceKind.GPU,
                    label=label, kind=kind,
                    value=round(float(value), DECIMALS.get(kind, 1)),
                    order=order,
                ))
        return sensors

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _power(draft: Draft, device: str) -> list[Sensor]:
        power = draft.cpu_extra.get("power")
        if power is None:
            return []
        fields = (
            ("package_w", _("sensor.package"), 0),
            ("core_w", _("sensor.cores"), 1),
            ("uncore_w", "Uncore", 2),
            ("graphics_w", _("sensor.igpu"), 2),
            ("dram_w", "DRAM", 3),
        )
        sensors = []
        for attribute, label, order in fields:
            value = getattr(power, attribute)
            if value is None:
                continue
            sensors.append(Sensor(
                key=f"rapl/{attribute}", chip="intel-rapl", device=device,
                device_key="cpu",
                device_kind=DeviceKind.CPU,
                label=label, kind=SensorKind.POWER, value=value, order=order,
                # The chip's own sustained limit is the natural threshold:
                # staying above it means the clock is about to drop.
                high=power.limit_long_w if attribute == "package_w" else None,
                critical=power.limit_short_w if attribute == "package_w" else None,
            ))
        return sensors

    @staticmethod
    def _clocks(draft: Draft, device: str) -> list[Sensor]:
        sensors = []
        for index, cpu in sorted(draft.logical.items()):
            frequency = cpu.get("freq_hz")
            if frequency is None:
                continue
            sensors.append(Sensor(
                key=f"clock/cpu{index}", chip="cpufreq", device=device,
                device_key="cpu",
                device_kind=DeviceKind.CPU,
                label=thread_name(index), kind=SensorKind.CLOCK,
                value=round(frequency / 1e6, 1), order=index,
            ))
        return sensors

    @staticmethod
    def _usage(draft: Draft, device: str) -> list[Sensor]:
        sensors = []
        total = draft.cpu_extra.get("usage_percent")
        if total is not None:
            sensors.append(Sensor(
                key="usage/total", chip="procfs", device=device,
                device_key="cpu",
                device_kind=DeviceKind.CPU,
                label=_("sensor.total"), kind=SensorKind.USAGE,
                value=total, order=-1,
            ))
        for index, cpu in sorted(draft.logical.items()):
            value = cpu.get("usage_percent")
            if value is None:
                continue
            sensors.append(Sensor(
                key=f"usage/cpu{index}", chip="procfs", device=device,
                device_key="cpu",
                device_kind=DeviceKind.CPU,
                label=thread_name(index), kind=SensorKind.USAGE,
                value=value, order=index,
            ))
        return sensors
