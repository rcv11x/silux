"""Consumo del paquete, desglosado, vía RAPL (powercap).

El kernel expone contadores de energía en microjulios que solo suben. Los
vatios son su derivada, así que este proveedor guarda la lectura anterior
igual que el del uso de CPU. El contador da la vuelta al llegar a
`max_energy_range_uj` y hay que tenerlo en cuenta o se ven picos absurdos.

Se leen también los subdominios y los límites que declara el propio
procesador. Sin eso, un "7 W" en reposo parece un error de medición; con el
desglose se ve que son los núcleos en reposo profundo, y que el límite
sostenido de este chip son 65 W. Es un dato que CPU-X no muestra.
"""

from __future__ import annotations

import pathlib
import time
from typing import Optional

from ..i18n import _
from ..model import Need, Power
from ..privileged.client import HelperError, PrivilegedClient
from .base import Draft, Provider, read_int, read_text
from .counters import increase, window_s
from .. import sysroot

POWERCAP = pathlib.Path("/sys/class/powercap")

# Nombres que usa el kernel para cada subdominio -> campo del modelo.
SUBDOMAINS = {"core": "core_w", "uncore": "uncore_w", "dram": "dram_w"}


# Donde el dominio `core` no es la suma de los núcleos. En Intel es PP0, un
# contador del paquete. En AMD el kernel lo saca de `MSR_AMD_CORE_ENERGY_STATUS`,
# que es de cada núcleo, y lo lee en uno solo: el primero del paquete. Medido
# en un 5800X3D con una carga atada a un hilo: en el núcleo 0 el dominio sube
# de 3,4 a 5,9 W, en el núcleo 5 no se mueve.
NUCLEO_SUELTO = frozenset(("AuthenticAMD", "HygonGenuine"))


def _core_es_de_un_nucleo(draft: Draft) -> bool:
    return any(t.get("vendor_id") in NUCLEO_SUELTO for t in draft.types.values())


# El framework se llama «intel-rapl» por su origen, pero AMD lo usa igual y
# según la versión del kernel aparece como «amd-rapl». Buscar solo el primero
# dejaba a las máquinas AMD sin lectura de consumo.
RAPL_ZONES = ("intel-rapl:*", "amd-rapl:*", "*-rapl:*")


def _packages() -> list[pathlib.Path]:
    if not sysroot.ruta(POWERCAP).is_dir():
        return []

    found: list[pathlib.Path] = []
    seen: set[str] = set()
    for pattern in RAPL_ZONES:
        for entry in sorted(sysroot.ruta(POWERCAP).glob(pattern)):
            if entry.name in seen:
                continue
            # Los subdominios (core, uncore, dram) llevan un segundo «:».
            if entry.name.count(":") > 1:
                continue
            if (read_text(str(entry / "name")) or "").startswith("package"):
                seen.add(entry.name)
                found.append(entry)
    return found


# Without any limit declared, no single package draws this for a second.
FALLBACK_CEILING_W = 1000.0
# Where a dropped reading is told: the report's Diagnóstico, no page.
DISCARDED_PATH = "report.power.discarded"


def package_ceiling_w() -> float:
    """The most a package can draw, from what RAPL declares: its PL4
    (`peak_power`) if declared; twice its highest limit if not (it goes above
    PL2 for an instant, never to twice); FALLBACK_CEILING_W without any."""
    packages = _packages()
    if not packages:
        return FALLBACK_CEILING_W
    limites: dict[str, float] = {}
    for constraint in packages[0].glob("constraint_*_name"):
        micro = read_int(str(constraint).replace("_name", "_power_limit_uw"))
        if micro:
            limites[(read_text(str(constraint)) or "").lower()] = micro / 1e6
    if "peak_power" in limites:
        return limites["peak_power"]
    return 2 * max(limites.values()) if limites else FALLBACK_CEILING_W


class Discarded:
    """The readings dropped as impossible, told in the report with their
    numbers: a negative watt, or more than the part can draw. A tester's
    Iris Xe drew 9 W and its chart got a point at 1336648637.3 W."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.count = 0
        self.last = ""

    def check(self, watts: float, ceiling: float, before: int, after: int,
              seconds: float) -> bool:
        """Whether those watts can be; if not, they are counted and kept."""
        if 0 <= watts <= ceiling:
            return True
        self.count += 1
        self.last = _("power.discarded.last").format(
            vatios=f"{watts:.1f}", techo=f"{ceiling:.0f}", antes=before, ahora=after,
            segundos=f"{seconds:.3f}")
        return False

    def note(self, draft: Draft) -> None:
        if self.count:
            draft.note(DISCARDED_PATH, Need.ERROR, _("power.discarded").format(
                n=self.count, fuente=self.source, ultima=self.last))


def _limits(package: pathlib.Path) -> dict[str, Optional[float]]:
    """PL1 y PL2, en vatios, tal y como los declara el procesador, con la
    ventana de tiempo de cada uno, en segundos: los campos de `Power`."""
    limits: dict[str, Optional[float]] = {}
    for constraint in sorted(package.glob("constraint_*_name")):
        name = (read_text(str(constraint)) or "").lower()
        micro = read_int(str(constraint).replace("_name", "_power_limit_uw"))
        if micro is None:
            continue
        window = read_int(str(constraint).replace("_name", "_time_window_us"))
        kind = "long" if "long" in name else "short" if "short" in name else None
        if kind:
            limits[f"limit_{kind}_w"] = round(micro / 1e6, 1)
            limits[f"window_{kind}_s"] = window / 1e6 if window else None
    return limits


class PowerLimits(Provider):
    """PL1 y PL2: los límites que el firmware programó, sin esperar al consumo.

    Están al lado de los contadores de energía, pero no son lo mismo: los
    contadores los reserva el kernel a root y los límites se leen con
    cualquier usuario. `RaplPower` solo los ponía cuando conseguía medir, así
    que sin permisos un Intel no decía sus límites teniéndolos a la vista.
    Va delante de él; cuando hay consumo, `RaplPower` escribe la ficha entera.
    """

    name = "power-limits"
    provides = "cpu.power.limits"

    def __init__(self) -> None:
        self._limites: Optional[dict] = None

    def available(self) -> bool:
        return bool(_packages())

    def collect(self, draft: Draft) -> None:
        if self._limites is None:
            self._limites = _limits(_packages()[0])
        if self._limites.get("limit_long_w") or self._limites.get("limit_short_w"):
            draft.cpu_extra["power"] = Power(**self._limites)


class RaplPower(Provider):
    name = "rapl"
    provides = "cpu.power"

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        self._previous: dict[str, tuple[int, float]] = {}
        self._limits: Optional[dict[str, Optional[float]]] = None
        # El mismo ayudante que ya usan los discos y la memoria. Desde el
        # kernel 5.10 `energy_uj` no se lee sin privilegios y en las máquinas
        # donde eso pasa —AMD sobre todo— el consumo del procesador salía en
        # blanco. Peor: la nota de «requiere permisos» no se iba nunca, porque
        # el usuario los daba, el ayudante arrancaba y nadie leía esto.
        self.client = client
        self._por_el_ayudante = False
        self._cache: dict[str, int] = {}
        # When the helper's reading was taken: it may wait up to 100 ms for
        # its pace, and timing it from before the request skewed the watts.
        self._cache_instant = 0.0
        self._ceiling: Optional[float] = None
        self._discarded = Discarded("RAPL")

    def available(self) -> bool:
        packages = _packages()
        if not packages:
            return False
        if read_int(str(packages[0] / "energy_uj")) is not None:
            return True
        # Con el ayudante conectado sí se puede, aunque el kernel se lo niegue
        # a este proceso.
        return bool(self.client and self.client.connected())

    def unavailable_reason(self):
        if self.available():
            return None
        if _packages():
            return ("cpu.power", Need.ROOT,
                    _("prov.rapl.denied"), _("prov.rapl.denied.hint"),
                    _("what.cpu.power"))
        return ("cpu.power", Need.HARDWARE,
                _("prov.rapl.none"), _("prov.rapl.none.hint"))

    def collect(self, draft: Draft) -> None:
        packages = _packages()
        if not packages:
            return

        # Una sola petición al ayudante por muestreo, no una por zona.
        self._cache: dict[str, int] = {}
        totals: dict[str, float] = {}

        suelto = _core_es_de_un_nucleo(draft)
        sin_nucleos = False
        for package in packages:
            self._accumulate(package, "package_w", totals, draft.interval_s)
            for child in sorted(package.glob(f"{package.name}:*")):
                field = SUBDOMAINS.get(read_text(str(child / "name")) or "")
                if field == "core_w" and suelto:
                    sin_nucleos = True
                elif field:
                    self._accumulate(child, field, totals, draft.interval_s)
        self._discarded.note(draft)

        if "package_w" not in totals:
            return                          # primera pasada: solo referencia
        if totals["package_w"] == 0:
            # Un paquete encendido siempre gasta algo: si su contador no ha
            # avanzado en todo un muestreo, está parado, y 0 W sería un dato
            # que parece bueno y no lo es. Los subdominios sí pueden quedarse
            # quietos (la gráfica integrada apagada), el paquete no.
            draft.note("cpu.power", Need.HARDWARE,
                       _("prov.rapl.frozen"), _("prov.rapl.frozen.hint"))
            return

        draft.capabilities.add("rapl")
        if sin_nucleos:
            draft.note("cpu.power.core_w", Need.HARDWARE,
                       _("prov.rapl.onecore"), _("prov.rapl.onecore.hint"))
        if self._limits is None:
            self._limits = _limits(packages[0])

        draft.cpu_extra["power"] = Power(
            package_w=round(totals["package_w"], 1),
            core_w=self._rounded(totals.get("core_w")),
            uncore_w=self._rounded(totals.get("uncore_w")),
            dram_w=self._rounded(totals.get("dram_w")),
            **self._limits,
        )

    # -- interno ------------------------------------------------------------

    @staticmethod
    def _rounded(value: Optional[float]) -> Optional[float]:
        return None if value is None else round(value, 2)

    def _por_ayudante(self, zona: str) -> Optional[int]:
        """Los microjulios de una zona cuando el kernel no deja leerlos.

        Se piden todas de una vez y se guardan: en un equipo con paquete,
        núcleos y DRAM son cuatro lecturas por muestreo, y cada una por su
        cuenta serían cuatro viajes al ayudante por segundo.
        """
        if not (self.client and self.client.connected()):
            return None
        if not self._cache:
            try:
                self._cache = self.client.rapl()
                self._cache_instant = time.monotonic()
                self._por_el_ayudante = True
            except HelperError:
                return None
        return self._cache.get(zona)

    def _read(self, zone: pathlib.Path) -> tuple[Optional[int], str, float]:
        """The zone's microjoules, where they came from and when."""
        microjoules = read_int(str(zone / "energy_uj"))
        if microjoules is not None:
            return microjoules, "sysfs", time.monotonic()
        microjoules = self._por_ayudante(zone.name)
        return microjoules, "helper", self._cache_instant

    def _accumulate(self, zone: pathlib.Path, field: str,
                    totals: dict[str, float], interval_s: float) -> None:
        microjoules, source, instant = self._read(zone)
        if microjoules is None:
            return

        key = zone.name
        before = self._previous.get(key)
        self._previous[key] = (microjoules, instant, source)
        # Not against a reading from the other source: they are the same
        # counter, but timed differently.
        if before is None or before[2] != source:
            return

        elapsed = window_s(before[1], instant, interval_s)
        if elapsed is None:
            return
        delta = increase(before[0], microjoules)
        if delta is None:
            # Gone round: the range is read only then.
            delta = increase(before[0], microjoules,
                             wrap=read_int(str(zone / "max_energy_range_uj")))
        if delta is None:
            return

        watts = delta / 1e6 / elapsed
        if self._ceiling is None:
            self._ceiling = package_ceiling_w()
        if self._discarded.check(watts, self._ceiling, before[0], microjoules, elapsed):
            totals[field] = totals.get(field, 0.0) + watts
