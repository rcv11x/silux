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

import functools
import pathlib
from typing import Iterable, Optional

from . import sysroot

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


def _clave(numeros) -> str:
    return ":".join(f"{n:04x}" for n in numeros)


# Devices pci.ids does not list. QEMU's standard VGA uses vendor 0x1234, which
# was never registered: without this a tester's VM showed «Gráfica 0».
NOT_IN_PCI_IDS = {(0x1234, 0x1111): ("QEMU", "QEMU Standard VGA")}


def lookup(
    pairs: Iterable[tuple[int, int]],
    subsystems: Iterable[tuple[int, int, int, int]] = (),
) -> dict[tuple[int, int], tuple[str, str]]:
    """Lo mismo que `_lookup`, pero contestando lo grabado en un equipo volcado.

    `pci.ids` es de la máquina que ejecuta, no del equipo volcado, y cambia
    con la distribución: la Radeon del 5800X3D se llama «Radeon RX 9070 XT
    16GB» con el de CachyOS y «AMD Radeon RX 9070 XT» con el de una Ubuntu
    22.04, que no trae esa tarjeta. El volcado guarda lo que contestó aquí.
    """
    pares = sorted({(int(v), int(d)) for v, d in pairs})
    subs = sorted({tuple(int(n) for n in key) for key in subsystems})
    if sysroot.activo() and not sysroot.grabo("pciids"):
        nombres = _lookup(pares, subs)           # un volcado de antes de grabarlo
    else:
        pregunta = "|".join(_clave(k) for k in (*pares, *subs))
        plano = sysroot.a_traves(
            "pciids", pregunta,
            lambda: {_clave(k): list(v) for k, v in _lookup(pares, subs).items()})
        nombres = {tuple(int(n, 16) for n in clave.split(":")): tuple(valor)
                   for clave, valor in (plano or {}).items()}
    for par in pares:
        if par not in nombres and par in NOT_IN_PCI_IDS:
            nombres[par] = NOT_IN_PCI_IDS[par]
    return nombres


# Lo ya contestado, por pregunta y por versión del fichero (ruta, fecha y
# tamaño). Recorrer pci.ids entero son milisegundos de Python, y la red
# pregunta por el nombre de su tarjeta en cada muestreo: con la ventana
# escondida era el 7 % de lo que gastaba silux.
_contestado: dict[tuple, dict] = {}


def _lookup(
    pairs: Iterable[tuple[int, int]],
    subsystems: Iterable[tuple[int, int, int, int]] = (),
) -> dict[tuple[int, int], tuple[str, str]]:
    """`_recorrer`, recordando lo contestado mientras el fichero no cambie."""
    pares = tuple(sorted({(int(v), int(d)) for v, d in pairs}))
    subs = tuple(sorted({tuple(int(n) for n in key) for key in subsystems}))
    path = database_path()
    if path is None:
        return {}
    try:
        estado = path.stat()
    except OSError:
        return {}
    clave = (str(path), estado.st_mtime_ns, estado.st_size, pares, subs)
    if clave not in _contestado:
        _contestado[clave] = _recorrer(path, pares, subs)
    return dict(_contestado[clave])


def _recorrer(
    path: pathlib.Path,
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


def vendor_name(vendor: int) -> Optional[str]:
    """El nombre de un fabricante, o el que se grabó en un equipo volcado."""
    if sysroot.activo() and not sysroot.grabo("pciids"):
        return _vendor_name(int(vendor))
    return sysroot.a_traves("pciids_fabricante", f"{int(vendor):04x}",
                            _vendor_name, int(vendor))


@functools.lru_cache(maxsize=64)
def _vendor_name(vendor: int) -> Optional[str]:
    """Solo el nombre de un fabricante, sin pedir ningún modelo.

    Hace falta para el «Ensamblada por» de una gráfica: pci.ids trae la línea
    del subsistema completo solo para las combinaciones que alguien se ha
    molestado en añadir, y una placa reciente no suele estar. Pero el
    fabricante sí: el 0x1462 es MSI aunque no aparezca esa tarjeta suya
    concreta, y decir quién la montó vale más que un guion.
    """
    path = database_path()
    if path is None:
        return None
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line or line.startswith(("#", "\t")):
                    continue
                code, _, name = line.partition("  ")
                try:
                    if int(code, 16) == vendor:
                        return name.strip() or None
                except ValueError:
                    continue
    except OSError:
        return None
    return None
