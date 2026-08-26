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


def lookup(
    pairs: Iterable[tuple[int, int]],
    subsystems: Iterable[tuple[int, int, int, int]] = (),
) -> dict[tuple[int, int], tuple[str, str]]:
    """Devuelve {(vendor, device): (nombre del fabricante, nombre del modelo)}.

    Los identificadores que no estén en la base simplemente no aparecen en el
    resultado; quien llama decide qué enseñar en su lugar.

    `subsystems` pide además las líneas anidadas de tercer nivel, con las que
    una tarjeta deja de ser «Radeon RX 9070/9070 XT/9070 GRE» (tres modelos a
    la vez) y pasa a ser la que de verdad hay puesta. Se resuelven en la misma
    pasada, y sus resultados vuelven con la clave de cuatro números.
    """
    wanted = {(int(v), int(d)) for v, d in pairs}
    subs_wanted = {tuple(int(n) for n in key) for key in subsystems}
    # El fabricante de la tarjeta es un fabricante de primer nivel como
    # cualquier otro, así que basta con pedir su sección al recorrer.
    wanted |= {(key[0], key[1]) for key in subs_wanted}
    if not wanted and not subs_wanted:
        return {}

    path = database_path()
    if path is None:
        return {}

    vendors_wanted = {vendor for vendor, _ in wanted}
    vendors_wanted |= {key[2] for key in subs_wanted}
    found: dict = {}
    vendor_names: dict[int, str] = {}
    # Los subsistemas se apuntan al vuelo y se nombran al final: la sección del
    # fabricante de la tarjeta puede venir después de la del chip en el fichero.
    subs_crudos: dict[tuple[int, int, int, int], str] = {}

    current_vendor: Optional[int] = None
    current_device: Optional[int] = None
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
                    current_device = None
                    if current_vendor in vendors_wanted:
                        vendor_names[current_vendor] = name.strip()
                    else:
                        current_vendor = None
                elif current_vendor is not None and not line.startswith("\t\t"):
                    code, _, name = line.strip().partition("  ")
                    try:
                        device = int(code, 16)
                    except ValueError:
                        current_device = None
                        continue
                    current_device = device
                    key = (current_vendor, device)
                    if key in wanted:
                        found[key] = (vendor_names[current_vendor], name.strip())
                        # Ya no se puede salir en cuanto estén todos: puede
                        # quedar por leer la sección del fabricante de la tarjeta.
                        if len(found) == len(wanted) and not subs_wanted:
                            return found
                elif current_device is not None and current_vendor is not None:
                    code, _, name = line.strip().partition("  ")
                    subvendor, _, subdevice = code.partition(" ")
                    try:
                        clave = (current_vendor, current_device,
                                 int(subvendor, 16), int(subdevice, 16))
                    except ValueError:
                        continue
                    if clave in subs_wanted:
                        subs_crudos[clave] = name.strip()
    except OSError:
        return found

    for clave, nombre in subs_crudos.items():
        found[clave] = (vendor_names.get(clave[2], ""), nombre)
    return found
