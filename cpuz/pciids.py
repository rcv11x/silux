"""Resolución de nombres de dispositivos PCI contra la base pci.ids.

El fichero lo mantiene el proyecto hwdata y viene instalado en casi cualquier
distribución, así que no hace falta empaquetar copia: se lee del sistema. Son
1,7 MB, pero como solo interesan un puñado de identificadores concretos se
recorre una sola vez buscándolos, en lugar de cargar el fichero entero en
memoria para consultarlo tres veces.

Formato del fichero:

    8086  Intel Corporation
    <tab>9b53  Comet Lake-S 6c Host Bridge/DRAM Controller
    <tab><tab>1462 7d23  Subsistema
"""

from __future__ import annotations

import pathlib
from typing import Iterable, Optional

CANDIDATE_PATHS = (
    "/usr/share/hwdata/pci.ids",
    "/usr/share/misc/pci.ids",
    "/usr/share/pci.ids",
    "/var/lib/pciutils/pci.ids",
)


def database_path() -> Optional[pathlib.Path]:
    for candidate in CANDIDATE_PATHS:
        path = pathlib.Path(candidate)
        if path.is_file():
            return path
    return None


def lookup(pairs: Iterable[tuple[int, int]]) -> dict[tuple[int, int], tuple[str, str]]:
    """Devuelve {(vendor, device): (nombre del fabricante, nombre del modelo)}.

    Los identificadores que no estén en la base simplemente no aparecen en el
    resultado; quien llama decide qué enseñar en su lugar.
    """
    wanted = {(int(v), int(d)) for v, d in pairs}
    if not wanted:
        return {}

    path = database_path()
    if path is None:
        return {}

    vendors_wanted = {vendor for vendor, _ in wanted}
    found: dict[tuple[int, int], tuple[str, str]] = {}
    vendor_names: dict[int, str] = {}

    current_vendor: Optional[int] = None
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line or line.startswith("#"):
                    continue
                if not line.startswith("\t"):
                    # Línea de fabricante. Al llegar a una sección que no
                    # interesa se marca como None y se saltan sus modelos.
                    code, _, name = line.partition("  ")
                    try:
                        current_vendor = int(code, 16)
                    except ValueError:
                        current_vendor = None
                        continue
                    if current_vendor in vendors_wanted:
                        vendor_names[current_vendor] = name.strip()
                    else:
                        current_vendor = None
                elif current_vendor is not None and not line.startswith("\t\t"):
                    code, _, name = line.strip().partition("  ")
                    try:
                        device = int(code, 16)
                    except ValueError:
                        continue
                    key = (current_vendor, device)
                    if key in wanted:
                        found[key] = (vendor_names[current_vendor], name.strip())
                        if len(found) == len(wanted):
                            return found
    except OSError:
        return found

    return found
