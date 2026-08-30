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

POWERCAP = pathlib.Path("/sys/class/powercap")

# Nombres que usa el kernel para cada subdominio -> campo del modelo.
SUBDOMAINS = {"core": "core_w", "uncore": "uncore_w", "dram": "dram_w"}


# El framework se llama «intel-rapl» por su origen, pero AMD lo usa igual y
# según la versión del kernel aparece como «amd-rapl». Buscar solo el primero
# dejaba a las máquinas AMD sin lectura de consumo.
RAPL_ZONES = ("intel-rapl:*", "amd-rapl:*", "*-rapl:*")


def _packages() -> list[pathlib.Path]:
    if not POWERCAP.is_dir():
        return []

    found: list[pathlib.Path] = []
    seen: set[str] = set()
    for pattern in RAPL_ZONES:
        for entry in sorted(POWERCAP.glob(pattern)):
            if entry.name in seen:
                continue
            # Los subdominios (core, uncore, dram) llevan un segundo «:».
            if entry.name.count(":") > 1:
                continue
            if (read_text(str(entry / "name")) or "").startswith("package"):
                seen.add(entry.name)
                found.append(entry)
    return found


def _limits(package: pathlib.Path) -> tuple[Optional[float], Optional[float]]:
    """PL1 y PL2, en vatios, tal y como los declara el procesador."""
    long_term = short_term = None
    for constraint in sorted(package.glob("constraint_*_name")):
        name = (read_text(str(constraint)) or "").lower()
        micro = read_int(str(constraint).replace("_name", "_power_limit_uw"))
        if micro is None:
            continue
        if "long" in name:
            long_term = round(micro / 1e6, 1)
        elif "short" in name:
            short_term = round(micro / 1e6, 1)
    return long_term, short_term


class RaplPower(Provider):
    name = "rapl"
    provides = "cpu.power"

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        self._previous: dict[str, tuple[int, float]] = {}
        self._limits: Optional[tuple[Optional[float], Optional[float]]] = None
        # El mismo ayudante que ya usan los discos y la memoria. Desde el
        # kernel 5.10 `energy_uj` no se lee sin privilegios y en las máquinas
        # donde eso pasa —AMD sobre todo— el consumo del procesador salía en
        # blanco. Peor: la nota de «requiere permisos» no se iba nunca, porque
        # el usuario los daba, el ayudante arrancaba y nadie leía esto.
        self.client = client
        self._por_el_ayudante = False
        self._cache: dict[str, int] = {}

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
                    _("prov.rapl.denied"), _("prov.rapl.denied.hint"))
        return ("cpu.power", Need.HARDWARE,
                _("prov.rapl.none"), _("prov.rapl.none.hint"))

    def collect(self, draft: Draft) -> None:
        packages = _packages()
        if not packages:
            return

        # Una sola petición al ayudante por muestreo, no una por zona.
        self._cache: dict[str, int] = {}
        now = time.monotonic()
        totals: dict[str, float] = {}

        for package in packages:
            self._accumulate(package, "package_w", now, totals)
            for child in sorted(package.glob(f"{package.name}:*")):
                field = SUBDOMAINS.get(read_text(str(child / "name")) or "")
                if field:
                    self._accumulate(child, field, now, totals)

        if "package_w" not in totals:
            return                          # primera pasada: solo referencia

        draft.capabilities.add("rapl")
        if self._limits is None:
            self._limits = _limits(packages[0])
        long_term, short_term = self._limits

        draft.cpu_extra["power"] = Power(
            package_w=round(totals["package_w"], 1),
            core_w=self._rounded(totals.get("core_w")),
            uncore_w=self._rounded(totals.get("uncore_w")),
            dram_w=self._rounded(totals.get("dram_w")),
            limit_long_w=long_term,
            limit_short_w=short_term,
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
                self._por_el_ayudante = True
            except HelperError:
                return None
        return self._cache.get(zona)

    def _accumulate(self, zone: pathlib.Path, field: str, now: float,
                    totals: dict[str, float]) -> None:
        microjoules = read_int(str(zone / "energy_uj"))
        if microjoules is None:
            microjoules = self._por_ayudante(zone.name)
        if microjoules is None:
            return

        key = zone.name
        before = self._previous.get(key)
        self._previous[key] = (microjoules, now)
        if before is None:
            return

        elapsed = now - before[1]
        delta = microjoules - before[0]
        if delta < 0:                        # el contador dio la vuelta
            ceiling = read_int(str(zone / "max_energy_range_uj"))
            if not ceiling:
                return
            delta += ceiling
        if elapsed <= 0:
            return

        totals[field] = totals.get(field, 0.0) + delta / 1e6 / elapsed
