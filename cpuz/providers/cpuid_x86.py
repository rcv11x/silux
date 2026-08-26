"""Identidad del procesador leyendo CPUID directamente, sin root.

Es lo único que sysfs no puede dar: fabricante real, cadena de marca, familia
y modelo, el juego de instrucciones y —en Intel moderno— el reloj base, el
techo de turbo del silicio y el BCLK, en la hoja 0x16. Ese último dato es el
que CPU-X saca leyendo MSR con un daemon privilegiado; aquí sale gratis.

CPUID responde por el núcleo que la ejecuta, así que en una CPU híbrida hay
que preguntar una vez por cada tipo de núcleo, fijando el hilo a uno de ellos.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .. import db, features
from ..model import Clocks, Need
from ..rawcpuid import CpuidError, CpuidReader, is_supported, pinned
from .base import Draft, Provider

# Hoja 0x1A: tipo de núcleo nativo en las CPU híbridas de Intel.
CORE_TYPE_ATOM = 0x20
CORE_TYPE_CORE = 0x40

VENDOR_NAMES = {
    "GenuineIntel": "Intel",
    "AuthenticAMD": "AMD",
    "HygonGenuine": "Hygon",
    "CentaurHauls": "Centaur",
    "GenuineTMx86": "Transmeta",
    "CyrixInstead": "Cyrix",
    "NexGenDriven": "NexGen",
    "UMC UMC UMC ": "UMC",
    "SiS SiS SiS ": "SiS",
    "Geode by NSC": "National Semiconductor",
    "  Shanghai  ": "Zhaoxin",
}


class CpuidIdentity(Provider):
    """Rellena la identidad de cada tipo de núcleo a partir de CPUID."""

    name = "cpuid-x86"
    provides = "cpu.identity"
    static = True

    def __init__(self) -> None:
        self._reader: Optional[CpuidReader] = None
        self._error: Optional[str] = None
        if is_supported():
            try:
                self._reader = CpuidReader()
            except CpuidError as exc:
                self._error = str(exc)

    def available(self) -> bool:
        return self._reader is not None

    def unavailable_reason(self):
        if self.available():
            return None
        if not is_supported():
            return ("cpu.identity", Need.PLATFORM,
                    "CPUID es una instrucción de x86; esta máquina no lo es.",
                    "En ARM la identidad se lee de /proc/cpuinfo.")
        return ("cpu.identity", Need.PLATFORM,
                f"No se pudo usar CPUID: {self._error}",
                "El entorno prohíbe ejecutar memoria anónima. Se usará /proc/cpuinfo.")

    def collect(self, draft: Draft) -> None:
        reader = self._reader
        if reader is None:
            return
        draft.capabilities.add("cpuid")

        for key, entry in draft.types.items():
            cpus = entry.get("cpus") or [0]
            try:
                with pinned(cpus[0]):
                    self._fill(reader, draft, entry)
            except CpuidError as exc:
                draft.note(f"cpu.types.{key}", Need.PLATFORM, str(exc))

    # -- interno ------------------------------------------------------------

    def _fill(self, reader: CpuidReader, draft: Draft, entry: dict) -> None:
        vendor_id = reader.vendor_id
        brand = reader.brand_string()

        eax = reader(1)[0]
        family = (eax >> 8) & 0xF
        model = (eax >> 4) & 0xF
        stepping = eax & 0xF
        ext_family_bits = (eax >> 20) & 0xFF
        ext_model_bits = (eax >> 16) & 0xF

        # Las hojas de datos del fabricante —y las bases de datos de
        # identificación— usan los valores compuestos, no los bits crudos.
        disp_family = family + ext_family_bits if family == 0xF else family
        disp_model = model + (ext_model_bits << 4) if family in (6, 0xF) else model

        feats = features.decode(reader)
        entry.update(
            vendor_id=vendor_id,
            vendor=VENDOR_NAMES.get(vendor_id, vendor_id),
            brand=brand,
            architecture="x86_64" if "lm" in feats else "x86",
            family=family,
            model=model,
            stepping=stepping,
            disp_family=disp_family,
            disp_model=disp_model,
            signature=eax,
            features=feats,
            virtualization=("VT-x" if "vmx" in feats else "AMD-V" if "svm" in feats else None),
            # El bit «hypervisor» lo pone el anfitrión: ningún procesador real
            # lo enciende, así que es la señal más directa de estar dentro de
            # una máquina virtual.
            in_virtual_machine="hypervisor" in feats,
        )

        self._fill_frequencies(reader, entry)
        self._fill_identity(draft, entry, vendor_id, disp_family, disp_model,
                            family, model, stepping, brand)

    @staticmethod
    def _fill_frequencies(reader: CpuidReader, entry: dict) -> None:
        """Hoja 0x16: reloj base, techo de turbo y BCLK. Skylake y posteriores."""
        if not reader.supports(0x16):
            return
        base_mhz, max_mhz, bus_mhz, _ = reader(0x16)
        if not any((base_mhz, max_mhz, bus_mhz)):
            return

        clocks: Clocks = entry.get("clocks") or Clocks()
        entry["clocks"] = dataclasses.replace(
            clocks,
            base_hz=clocks.base_hz or (base_mhz * 1_000_000 or None),
            max_turbo_hz=max_mhz * 1_000_000 or None,
            bus_hz=bus_mhz * 1_000_000 or None,
        )

    @staticmethod
    def _fill_identity(draft: Draft, entry: dict, vendor_id: str, disp_family: int,
                       disp_model: int, family: int, model: int, stepping: int,
                       brand: str) -> None:
        if not db.available():
            draft.note(
                "cpu.codename", Need.DATABASE,
                "No hay base de datos de identificación generada.",
                "Ejecuta:  python3 tools/gen_cpu_db.py",
            )
            return

        l2 = entry_cache_kb(entry, 2)
        l3 = entry_cache_kb(entry, 3)

        ident = db.identify_x86(
            vendor_id=vendor_id,
            family=family,
            model=model,
            stepping=stepping,
            ext_family=disp_family,
            ext_model=disp_model,
            cores=entry.get("cores", 0),
            brand=brand,
            l2_kb=l2 if l2 is not None else -1,
            l3_kb=l3 if l3 is not None else -1,
        )

        if ident.matched:
            entry["codename"] = ident.codename
            entry["technology"] = ident.technology
            entry["socket"] = db.find_socket(vendor_id, ident.codename, brand)
        else:
            draft.note(
                "cpu.codename", Need.DATABASE,
                f"Este procesador no está en la base de datos ({brand}).",
                "Regenera la base con tools/gen_cpu_db.py o añade una entrada.",
            )

        if entry.get("socket") is None and ident.matched:
            draft.note(
                "cpu.socket", Need.DATABASE,
                f"No hay encapsulado catalogado para «{ident.codename}».",
                "Se puede añadir una regla en cpuz/db/sockets.json.",
            )


def entry_cache_kb(entry: dict, level: int) -> Optional[int]:
    """Tamaño de una caché en KB, como lo espera la base de datos de libcpuid."""
    for cache in entry.get("caches", ()):
        if cache.level == level and cache.kind in ("unified", "data"):
            return cache.size_bytes // 1024
    return None
