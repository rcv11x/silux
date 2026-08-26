"""Todos los sensores del equipo, desde /sys/class/hwmon.

Se enumera el árbol entero una sola vez y de ahí salen dos cosas: la lista
completa de sensores que consume la página de Monitor, y los valores concretos
—temperatura por núcleo, voltaje— que necesita la de CPU. Hacerlo en dos
pasadas sería leer los mismos ficheros dos veces por muestreo.

Aquí vive también la parte que más diferencia a un monitor de hardware en
Linux: **detectar qué driver falta**. La máquina no está limitada por lo que
el programa sepa leer, sino por los módulos que el kernel tenga cargados. Una
placa sin su módulo de Super I/O no enseña ni un ventilador ni un voltaje, y
decirlo vale más que cualquier sensor extra.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
from typing import Iterator, Optional

from ..model import DriverHint, Need, Sensor, SensorKind, short_brand
from .base import Draft, Provider, mean, read_int, read_text

HWMON = pathlib.Path("/sys/class/hwmon")
POWER_SUPPLY = pathlib.Path("/sys/class/power_supply")

# Prefijo del fichero -> (tipo, divisor para pasar a la unidad del modelo)
MEASUREMENTS: dict[str, tuple[SensorKind, float]] = {
    "temp": (SensorKind.TEMPERATURE, 1000.0),      # milésimas de grado
    "in": (SensorKind.VOLTAGE, 1000.0),            # milivoltios
    "fan": (SensorKind.FAN, 1.0),                  # ya viene en RPM
    "power": (SensorKind.POWER, 1_000_000.0),      # microvatios
    "curr": (SensorKind.CURRENT, 1000.0),          # miliamperios
    "energy": (SensorKind.ENERGY, 1_000_000.0),    # microjulios
}

# A qué aparato pertenece cada chip. El orden importa: gana la primera regla.
CPU_CHIP = re.compile(r"^(coretemp|k10temp|k8temp|zenpower|cpu_thermal)$")
BOARD_CHIP = re.compile(r"^(nct\d+|it\d+|w836\d+|f71\d+|smsc|lm\d+|nzxt|asus|acpitz|thermal)")
DISK_CHIP = re.compile(r"^(drivetemp|nvme)")
GPU_CHIP = re.compile(r"^(amdgpu|radeon|i915|xe|nouveau)")

# Chips de Super I/O: si no hay ninguno, la placa no está dando ventiladores.
SUPERIO_CHIPS = re.compile(r"^(nct\d+|it\d+|w836\d+|f71\d+|smsc|nzxt|asus)")

_CORE_LABEL = re.compile(r"^Core\s+(\d+)$", re.IGNORECASE)
_PACKAGE_LABEL = re.compile(r"^(Package id \d+|Tdie|Tctl|CPU Temperature)$", re.IGNORECASE)
_VCORE_LABEL = re.compile(r"(vcore|cpu\s*v(core|oltage)|vid)", re.IGNORECASE)

# Chips de la CPU, en orden de preferencia: los primeros miden el die.
CPU_CHIPS = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "k8temp", "acpitz")


def device_for(chip: str, entry: pathlib.Path, cpu_name: str, board_name: str) -> str:
    """A qué aparato del árbol cuelga este chip.

    El nombre importa: un árbol que dice "coretemp" y "nct6683" obliga a saber
    qué es cada cosa. Uno que dice "Intel Core i5-10400" y "MSI H510M PRO-E"
    se lee solo, que es lo que hacen HWMonitor y HWiNFO.
    """
    if CPU_CHIP.match(chip):
        return cpu_name
    if BOARD_CHIP.match(chip):
        return board_name
    if DISK_CHIP.match(chip):
        return _disk_name(entry) or "Almacenamiento"
    if GPU_CHIP.match(chip):
        return f"Gráfica ({chip})"
    return chip


def _disk_name(entry: pathlib.Path) -> Optional[str]:
    """El modelo del disco al que pertenece un chip de temperatura."""
    for candidate in (entry / "device" / "model", entry / "device" / "device" / "model"):
        if (model := read_text(str(candidate))):
            vendor = read_text(str(candidate.parent / "vendor")) or ""
            return " ".join(f"{vendor} {model}".split())
    return None


def _friendly(chip: str, prefix: str, index: str, label: Optional[str]) -> str:
    if label:
        return label
    fallback = {
        "temp": "Temperatura", "in": "Tensión", "fan": "Ventilador",
        "power": "Potencia", "curr": "Corriente", "energy": "Energía",
    }
    return f"{fallback.get(prefix, prefix)} {index}"


class HwmonSensors(Provider):
    """Enumera todos los chips y reparte lo que corresponde a la CPU."""

    name = "hwmon"
    provides = "sensors"

    def available(self) -> bool:
        return HWMON.is_dir()

    def unavailable_reason(self):
        if self.available():
            return None
        return ("sensors", Need.DRIVER,
                "No hay ningún chip de sensores expuesto en /sys/class/hwmon.",
                "En Intel se activa con el módulo coretemp; en AMD, k10temp.")

    def collect(self, draft: Draft) -> None:
        cpu_name = short_brand(draft.types[next(iter(draft.types), "")].get("brand")
                               if draft.types else None)
        board_name = draft.board.display_name

        sensors = list(self._read_hwmon(cpu_name, board_name))
        sensors += list(self._read_power_supplies())
        if not sensors:
            return

        draft.capabilities.add("hwmon")
        draft.sensors.extend(sensors)
        self._fill_cpu(draft, sensors)
        draft.driver_hints.extend(self._missing_drivers(sensors))

    # -- lectura ------------------------------------------------------------

    def _read_hwmon(self, cpu_name: str, board_name: str) -> Iterator[Sensor]:
        if not HWMON.is_dir():
            return
        for entry in sorted(HWMON.iterdir()):
            chip = read_text(str(entry / "name"))
            if not chip:
                continue
            device = device_for(chip, entry, cpu_name, board_name)
            for order, path in enumerate(sorted(entry.glob("*_input"))):
                sensor = self._parse(chip, device, path, order)
                if sensor is not None:
                    yield sensor

    @staticmethod
    def _parse(chip: str, device: str, path: pathlib.Path, order: int = 0) -> Optional[Sensor]:
        match = re.match(r"^([a-z]+)(\d+)_input$", path.name)
        if match is None:
            return None
        prefix, index = match.groups()
        if prefix not in MEASUREMENTS:
            return None

        raw = read_int(str(path))
        if raw is None:
            return None
        kind, divisor = MEASUREMENTS[prefix]

        def threshold(suffix: str) -> Optional[float]:
            value = read_int(str(path).replace("_input", f"_{suffix}"))
            return None if value is None else value / divisor

        return Sensor(
            key=f"{chip}/{prefix}{index}",
            chip=chip,
            device=device,
            label=_friendly(chip, prefix, index,
                            read_text(str(path).replace("_input", "_label"))),
            kind=kind,
            value=round(raw / divisor, 3),
            low=threshold("min"),
            high=threshold("max"),
            critical=threshold("crit"),
            order=order,
        )

    @staticmethod
    def _read_power_supplies() -> Iterator[Sensor]:
        """Baterías y adaptadores. En un sobremesa no hay ninguno; en un
        portátil son la mitad de lo interesante."""
        if not POWER_SUPPLY.is_dir():
            return
        fields = (
            ("voltage_now", SensorKind.VOLTAGE, 1_000_000.0, "Tensión"),
            ("current_now", SensorKind.CURRENT, 1_000_000.0, "Corriente"),
            ("power_now", SensorKind.POWER, 1_000_000.0, "Potencia"),
        )
        for entry in sorted(POWER_SUPPLY.iterdir()):
            name = entry.name
            for filename, kind, divisor, label in fields:
                raw = read_int(str(entry / filename))
                if raw is None:
                    continue
                yield Sensor(
                    key=f"power_supply/{name}/{filename}",
                    chip=name, device=f"Alimentación · {name}",
                    label=label, kind=kind,
                    value=round(abs(raw) / divisor, 3),
                )

    # -- reparto hacia la pestaña de CPU ------------------------------------

    def _fill_cpu(self, draft: Draft, sensors: list[Sensor]) -> None:
        by_chip: dict[str, list[Sensor]] = {}
        for sensor in sensors:
            by_chip.setdefault(sensor.chip, []).append(sensor)

        chip = next((name for name in CPU_CHIPS if name in by_chip), None)
        if chip is None:
            draft.note("cpu.temp_c", Need.DRIVER,
                       "Ningún chip de sensores parece corresponder a la CPU.",
                       f"Se vieron: {', '.join(sorted(by_chip))}.")
        else:
            self._spread_temperatures(draft, by_chip[chip])

        self._pick_voltage(draft, sensors)

    @staticmethod
    def _spread_temperatures(draft: Draft, sensors: list[Sensor]) -> None:
        per_core: dict[int, float] = {}
        package: list[float] = []
        unlabelled: list[float] = []

        for sensor in sensors:
            if sensor.kind is not SensorKind.TEMPERATURE:
                continue
            if match := _CORE_LABEL.match(sensor.label):
                per_core[int(match.group(1))] = sensor.value
            elif _PACKAGE_LABEL.match(sensor.label):
                package.append(sensor.value)
            else:
                unlabelled.append(sensor.value)

        if not package and not per_core:
            package = unlabelled            # chips de un solo sensor, como acpitz

        for cpu in draft.logical.values():
            if (value := per_core.get(cpu.get("core_id", -1))) is not None:
                cpu["temp_c"] = value

        if package:
            draft.cpu_extra["package_temp_c"] = round(max(package), 1)

        for entry in draft.types.values():
            average = mean([draft.logical[i].get("temp_c") for i in entry.get("cpus", ())])
            if average is not None:
                entry["temp_c"] = round(average, 1)
            elif package:
                entry["temp_c"] = round(max(package), 1)

    @staticmethod
    def _pick_voltage(draft: Draft, sensors: list[Sensor]) -> None:
        for sensor in sensors:
            if sensor.kind is SensorKind.VOLTAGE and _VCORE_LABEL.search(sensor.label):
                for entry in draft.types.values():
                    entry["voltage_v"] = sensor.value
                return

        draft.note(
            "cpu.voltage_v", Need.DRIVER,
            "Ningún sensor de esta máquina publica el voltaje del núcleo.",
            "Suele hacer falta el módulo del Super I/O de la placa "
            "(nct6775, nct6683, it87…) o leer el VID por MSR, que exige root.",
        )

    # -- drivers que faltan -------------------------------------------------

    @staticmethod
    def _module_exists(module: str) -> bool:
        if not shutil.which("modinfo"):
            return False
        result = subprocess.run(["modinfo", "-F", "filename", module],
                                capture_output=True, text=True)
        return result.returncode == 0 and bool(result.stdout.strip())

    def _missing_drivers(self, sensors: list[Sensor]) -> Iterator[DriverHint]:
        chips = {sensor.chip for sensor in sensors}

        if not any(SUPERIO_CHIPS.match(chip) for chip in chips):
            yield DriverHint(
                module="(Super I/O)",
                provides="ventiladores, voltajes de la placa y temperaturas del chipset",
                command="sudo sensors-detect",
                caution="No conviene adivinar el módulo: cada placa lleva un chip "
                        "distinto y cargar el que no es puede leer basura. "
                        "sensors-detect lo identifica y dice cuál cargar.",
            )

        if "drivetemp" not in chips and self._has_ata_disks() and self._module_exists("drivetemp"):
            yield DriverHint(
                module="drivetemp",
                provides="la temperatura de los discos SATA",
                command="sudo modprobe drivetemp",
                caution="",
            )

    @staticmethod
    def _has_ata_disks() -> bool:
        block = pathlib.Path("/sys/class/block")
        if not block.is_dir():
            return False
        return any("/ata" in str(entry.resolve()) for entry in block.glob("sd?"))
