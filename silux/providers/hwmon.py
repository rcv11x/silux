"""Todos los sensores del equipo, desde /sys/class/hwmon.

Se enumera el árbol entero una sola vez y de ahí salen dos cosas: la lista
completa de sensores que consume la página de Monitor, y los valores concretos
(temperatura por núcleo, voltaje) que necesita la de CPU. Hacerlo en dos
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
    # Las gráficas publican aquí sus relojes, en hercios. Se pasan a megahercios
    # porque es la unidad en la que el árbol guarda todos los relojes, incluidos
    # los del procesador. Sin esta línea la tarjeta enseñaba temperaturas y
    # ventilador pero ninguna frecuencia.
    "freq": (SensorKind.CLOCK, 1_000_000.0),
}

# Canales que no se llaman `_input`. amdgpu publica el consumo como
# `power1_average` (es una media de la última ventana, no una lectura
# instantánea) y sin mirar aquí la tarjeta se quedaba sin consumo.
ALTERNATIVAS = ("_average",)

# A qué aparato pertenece cada chip. El orden importa: gana la primera regla.
CPU_CHIP = re.compile(r"^(coretemp|k10temp|k8temp|zenpower|cpu_thermal)$")
# Los `*_wmi` son los sensores que el fabricante de la placa expone por su
# propia interfaz: `gigabyte_wmi` salía en crudo en el árbol al lado de la
# misma placa nombrada por su Super I/O.
BOARD_CHIP = re.compile(
    r"^(nct\d+|it\d+|w836\d+|f71\d+|smsc|lm\d+|nzxt|asus|acpitz|thermal"
    r"|\w+_wmi)")
DISK_CHIP = re.compile(r"^(drivetemp|nvme)")
NET_CHIP = re.compile(r"^(r8\d+|e1000|igb|ixgbe|iwlwifi|mt79|ath\d+k?)")
GPU_CHIP = re.compile(r"^(amdgpu|radeon|i915|xe|nouveau)")

# Chips de Super I/O: si no hay ninguno, la placa no está dando ventiladores.
SUPERIO_CHIPS = re.compile(r"^(nct\d+|it\d+|w836\d+|f71\d+|smsc|nzxt|asus)")

_CORE_LABEL = re.compile(r"^Core\s+(\d+)$", re.IGNORECASE)
_PACKAGE_LABEL = re.compile(r"^(Package id \d+|Tdie|Tctl|CPU Temperature)$", re.IGNORECASE)
_VCORE_LABEL = re.compile(r"(vcore|cpu\s*v(core|oltage)|vid)", re.IGNORECASE)

# Chips de la CPU, en orden de preferencia: los primeros miden el die.
CPU_CHIPS = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "k8temp", "acpitz")


def device_for(chip: str, entry: pathlib.Path, cpu_name: str, board_name: str,
               gpu_names: Optional[dict[str, str]] = None) -> str:
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
        # El nombre de verdad si se sabe cuál es: un árbol que dice «amdgpu» no
        # sirve de nada en un equipo con dos gráficas, y en uno con una sola
        # obliga igualmente a saber qué driver lleva.
        if nombre := (gpu_names or {}).get(_ranura_pci(entry) or ""):
            return nombre
        return f"Gráfica ({chip})"
    if NET_CHIP.match(chip):
        return _net_name(entry) or f"Red ({chip})"
    if (energia := _nombre_de_alimentacion(chip)):
        return energia
    return chip


# Lo que un portátil publica como chip de sensores y que sale en crudo si no
# se traduce. `ucsi_source_psy_USBC000:001` es el nombre que el kernel le da al
# puerto USB-C que negocia la carga, y en el árbol no lo reconoce nadie.
_ALIMENTACION = (
    (re.compile(r"^(?:BAT|CMB)(\d*)$", re.I), "Batería"),
    (re.compile(r"^(?:AC|ADP)(\d*)$", re.I), "Adaptador de corriente"),
    # Sin número: lo que sigue a `USBC` es un identificador de ACPI, no el
    # puerto número tantos. «Puerto USB-C 2» en un portátil con uno solo.
    (re.compile(r"^(ucsi)[-_].*$", re.I), "Puerto USB-C"),
)


def _nombre_de_alimentacion(chip: str) -> Optional[str]:
    """«Batería» en vez de «BAT0», «Puerto USB-C» en vez del nombre del kernel.

    Se conserva el número cuando lo hay: un portátil con dos baterías las
    tiene que poder distinguir, y con una sola el número sobra.
    """
    for patron, nombre in _ALIMENTACION:
        if (encaje := patron.match(chip)):
            sufijo = encaje.group(1)
            if sufijo.isdigit() and int(sufijo):
                return f"{nombre} {int(sufijo) + 1}"
            return nombre
    return None


def _ranura_pci(entry: pathlib.Path) -> Optional[str]:
    """La dirección PCI del aparato al que cuelga un chip de sensores."""
    try:
        destino = (entry / "device").resolve()
    except OSError:
        return None
    while destino.name and destino.name != "/":
        if re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]", destino.name):
            return destino.name
        destino = destino.parent
    return None


def _net_name(entry: pathlib.Path) -> Optional[str]:
    """El nombre de la interfaz de red a la que pertenece un sensor.

    El sensor de temperatura de una Realtek no cuelga de la tarjeta sino del
    bus MDIO por el que se habla con el chip físico, un par de niveles más
    abajo. Así que se sube hasta dar con el `net/` de la interfaz.

    Las interfaces virtuales no cuentan. Subiendo a ciegas se llegaba a
    `/sys/devices/virtual`, que también tiene un `net/` dentro —con el bucle
    local y los puentes— y acababa colgando de «Red (lo)» la temperatura de
    cualquier sensor virtual: un ThinkPad enseñaba el loopback a 34 °C, y el
    bucle local no tiene con qué calentarse. No vale parar donde se acaben los
    dispositivos, porque el bus MDIO por el que se sube es un contenedor sin
    `uevent` y está justo en medio del camino bueno.
    """
    try:
        actual = (entry / "device").resolve()
    except OSError:
        return None
    for _ in range(6):
        red = actual / "net"
        if red.is_dir() and "/virtual/" not in f"{red}/":
            interfaces = sorted(p.name for p in red.iterdir())
            if interfaces:
                return f"Red ({interfaces[0]})"
        if actual.parent == actual:
            break
        actual = actual.parent
    return None


def _disk_name(entry: pathlib.Path) -> Optional[str]:
    """El modelo del disco al que pertenece un chip de temperatura."""
    for candidate in (entry / "device" / "model", entry / "device" / "device" / "model"):
        if (model := read_text(str(candidate))):
            vendor = read_text(str(candidate.parent / "vendor")) or ""
            return " ".join(f"{vendor} {model}".split())
    return None


# Las etiquetas que pone amdgpu son las del firmware. Dicen algo si uno sabe
# qué es un «sclk», y nada si no.
ETIQUETAS_GPU = {
    "sclk": "Núcleo", "mclk": "Memoria", "fclk": "Fabric", "socclk": "SoC",
    "vddgfx": "Núcleo", "vddnb": "Northbridge", "vddc": "Núcleo",
    "edge": "Borde", "junction": "Punto caliente", "mem": "Memoria",
    "PPT": "Paquete",
}


def _friendly(chip: str, prefix: str, index: str, label: Optional[str]) -> str:
    if label:
        if GPU_CHIP.match(chip):
            return ETIQUETAS_GPU.get(label, label)
        return label
    fallback = {
        "temp": "Temperatura", "in": "Tensión", "fan": "Ventilador",
        "power": "Potencia", "curr": "Corriente", "energy": "Energía",
    }
    return f"{fallback.get(prefix, prefix)} {index}"


# Hasta dónde puede llegar razonablemente un umbral de cada tipo. Los chips
# dejan sin usar los campos que no aplican y el kernel los devuelve tal cual:
# un NVMe publicaba «alto = 65261.85 °C», que son 0xFFFF en kelvin, o sea el
# valor de fábrica de un umbral que nadie rellenó. Sin filtrarlos, la mitad de
# los sensores tendría un límite que no se alcanza ni fundiendo la placa, y un
# aviso que nunca salta es igual de inútil que no tenerlo.
TOPES = {
    SensorKind.TEMPERATURE: 200.0,      # °C
    SensorKind.VOLTAGE: 30.0,           # V
    SensorKind.FAN: 30_000.0,           # RPM
    SensorKind.POWER: 2_000.0,          # W
    SensorKind.CURRENT: 200.0,          # A
    SensorKind.USAGE: 100.0,            # %
}


# Cuando el sensor no publica sus límites, los pone silux por el chip que es.
# Hace falta: de las 28 temperaturas de un equipo corriente, solo 7 traen
# umbral, y el procesador —que es el que importa— no suele traer ninguno.
#
# Las cifras son conservadoras a propósito, y del punto en que el fabricante
# empieza a recortar, no del que rompe. Un aviso que salta antes de tiempo
# quema la confianza en todos los demás, así que donde hay duda no se pone
# nada: los sensores de placa (it87, nct, acpitz, gigabyte_wmi) miden puntos
# que solo conoce quien diseñó la placa, y ahí no hay forma de acertar.
LIMITES_ESTIMADOS = {
    # AMD: Tctl llega a 90 por diseño en Zen 3 y no es una avería.
    "k10temp": (88.0, 95.0),
    "zenpower": (88.0, 95.0),
    # Intel: Tjmax anda por 100 en las de escritorio.
    "coretemp": (95.0, 100.0),
    # NVMe que no declara el suyo. Los que lo declaran ganan ellos.
    "nvme": (75.0, 85.0),
    # Discos mecánicos: aquí sí hay consenso, y es más bajo de lo que parece.
    "drivetemp": (55.0, 60.0),
}


def _plausible(valor, kind):
    """Descarta un umbral fuera de lo que ese tipo de sensor puede dar."""
    if valor is None:
        return None
    tope = TOPES.get(kind)
    if tope is not None and not -tope <= valor <= tope:
        return None
    return valor


def _umbrales(kind, bajo, alto, critico, chip=None) -> dict:
    """Los tres límites de un sensor, ya limpios de los que no valen.

    Los chips traen de fábrica los campos que nadie configuró, y el kernel los
    devuelve tal cual. Un nct6798 publica `temp_min = 127` y `temp_max = 127`
    para sus seis temperaturas: con eso, una placa a 34 °C queda «por debajo
    del mínimo» y saltan seis avisos a la vez. Un aviso falso gasta más
    confianza de la que gana uno acertado.

    De los ventiladores no se avisa. Que uno vaya a tope no es un problema —es
    lo que se espera bajo carga— y que esté parado tampoco, porque casi todas
    las tarjetas modernas los paran a propósito en reposo.

    Y tampoco de lo que se enchufa por fuera. Un puerto USB-C sin nada
    conectado marca 0 V, y eso está por debajo de cualquier mínimo que declare
    el chip: un ThinkPad saltaba con un aviso permanente por tener el cargador
    desenchufado. Cero ahí no es una avería, es que no hay nada puesto.
    """
    if kind is SensorKind.FAN:
        return {"low": None, "high": None, "critical": None}
    if _nombre_de_alimentacion(chip or ""):
        return {"low": None, "high": None, "critical": None}

    bajo = _plausible(bajo, kind)
    alto = _plausible(alto, kind)
    critico = _plausible(critico, kind)

    # Un mínimo por encima del máximo es un par que nadie rellenó.
    if bajo is not None and alto is not None and bajo >= alto:
        bajo = alto = None

    if (alto is None and critico is None
            and kind is SensorKind.TEMPERATURE
            and (estimado := LIMITES_ESTIMADOS.get(chip or ""))):
        return {"low": bajo, "high": estimado[0], "critical": estimado[1],
                "estimated_limits": True}
    return {"low": bajo, "high": alto, "critical": critico}


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
        # Las gráficas ya están enumeradas cuando esto corre: el orden de los
        # proveedores en `collector.py` lo garantiza.
        gpu_names = {gpu["pci_slot"]: (gpu.get("name") or f"Gráfica {gpu['index']}")
                     for gpu in draft.gpus if gpu.get("pci_slot")}

        sensors = list(self._read_hwmon(cpu_name, board_name, gpu_names))
        sensors += list(self._read_power_supplies())
        if not sensors:
            return

        draft.capabilities.add("hwmon")
        draft.sensors.extend(sensors)
        self._fill_cpu(draft, sensors)
        draft.driver_hints.extend(self._missing_drivers(sensors))

    # -- lectura ------------------------------------------------------------

    def _read_hwmon(self, cpu_name: str, board_name: str,
                    gpu_names: Optional[dict[str, str]] = None) -> Iterator[Sensor]:
        if not HWMON.is_dir():
            return
        for entry in sorted(HWMON.iterdir()):
            chip = read_text(str(entry / "name"))
            if not chip:
                continue
            device = device_for(chip, entry, cpu_name, board_name, gpu_names)
            canales = sorted(entry.glob("*_input"))
            vistos = {ruta.name.replace("_input", "") for ruta in canales}
            for sufijo in ALTERNATIVAS:
                canales += [ruta for ruta in sorted(entry.glob(f"*{sufijo}"))
                            if ruta.name.replace(sufijo, "") not in vistos]
            for order, path in enumerate(canales):
                sensor = self._parse(chip, device, path, order)
                if sensor is not None:
                    yield sensor

    @staticmethod
    def _parse(chip: str, device: str, path: pathlib.Path, order: int = 0) -> Optional[Sensor]:
        match = re.match(r"^([a-z]+)(\d+)_(?:input|average)$", path.name)
        if match is None:
            return None
        prefix, index = match.groups()
        sufijo = "_average" if path.name.endswith("_average") else "_input"
        if prefix not in MEASUREMENTS:
            return None

        raw = read_int(str(path))
        if raw is None:
            return None
        kind, divisor = MEASUREMENTS[prefix]

        def threshold(nombre: str) -> Optional[float]:
            value = read_int(str(path).replace(sufijo, f"_{nombre}"))
            return None if value is None else value / divisor

        return Sensor(
            key=f"{chip}/{prefix}{index}",
            chip=chip,
            device=device,
            label=_friendly(chip, prefix, index,
                            read_text(str(path).replace(sufijo, "_label"))),
            kind=kind,
            value=round(raw / divisor, 3),
            **_umbrales(kind, threshold("min"), threshold("max"),
                        threshold("crit"), chip),
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
