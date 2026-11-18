"""Lo que cuelga del bus PCI, y lo que la placa tiene activado.

Dos proveedores. `PlatformInfo` se lee una vez: IOMMU, virtualización, el
chip de sensores, el códec de sonido. `PciDevices` se lee en cada muestreo
porque el enlace de un dispositivo cambia solo: una gráfica en reposo baja
el suyo para gastar menos.

Los nombres no salen en bruto de `pci.ids` cuando silux ya llama a esa pieza
de otra manera: el disco se llama como en Almacenamiento, la gráfica como en
Gráficos y la tarjeta de red como en Red (regla 1). Por eso `PciDevices` va
detrás de esos tres en `collector.py`.
"""

from __future__ import annotations

import glob
import os
import pathlib
import re
from typing import Optional

from .. import pciids, sysroot
from ..model import PciDevice, Platform
from .base import Draft, Provider, en_reposo, read_text
from .drm import VENDORS, _cadena_pcie, _enlace

DISPOSITIVOS = "/sys/bus/pci/devices"

# La clase PCI (los cuatro primeros dígitos) de lo que se enseña. Los puentes
# y lo demás no son dispositivos que nadie busque por su nombre.
CLASES = {
    "0300": "gpu", "0302": "gpu", "0380": "gpu",
    "0108": "nvme", "0106": "sata", "0104": "sata",
    "0200": "ethernet", "0280": "wifi",
    "0c03": "usb", "0403": "audio", "0401": "audio",
}
# En qué orden salen: lo que va en una ranura primero, los controladores de
# la placa después.
EN_RANURA = ("gpu", "nvme", "ethernet", "wifi")
ORDEN = ("gpu", "nvme", "ethernet", "wifi", "sata", "usb", "audio")

_DIRECCION = re.compile(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]")


def _hex(camino: str) -> Optional[int]:
    crudo = read_text(camino)
    try:
        return int(crudo, 16) if crudo else None
    except ValueError:
        return None


class PciDevices(Provider):
    """Los dispositivos PCI con nombre, driver y enlace."""

    name = "pci"
    provides = "pci_devices"

    def __init__(self) -> None:
        # Qué hay no cambia mientras el programa está abierto; el enlace sí.
        self._fijos: Optional[list[dict]] = None

    def available(self) -> bool:
        return os.path.isdir(sysroot.ruta(DISPOSITIVOS))

    def collect(self, draft: Draft) -> None:
        if self._fijos is None:
            self._fijos = self._enumerar()
        propios = self._nombres_propios(draft)
        salida = []
        for fijo in self._fijos:
            nodo = pathlib.Path(sysroot.ruta(f"{DISPOSITIVOS}/{fijo['slot']}"))
            # El enlace solo dice algo de lo que va en una ranura. Un
            # controlador USB, SATA o de sonido vive dentro del chipset o del
            # procesador: lo que publica su nodo es el enlace interno del
            # chipset, y enseñarlo («PCIe 4.0 × 4, máximo × 8») se leería
            # como una ranura que va a medias.
            # Una tarjeta suspendida no se pregunta: leer su enlace la saca
            # del reposo desde Linux 6.18 (`en_reposo`).
            enlace = (_enlace(nodo) if fijo["kind"] in EN_RANURA
                      and not en_reposo(nodo) else None)
            # Una integrada de Intel no publica enlace: no cuelga de ninguno,
            # va dentro del procesador. Un enlace sin una sola cifra no es un
            # enlace del que no se sabe nada, es que no lo hay.
            if enlace is not None and not any((enlace.current_speed_gts, enlace.max_speed_gts,
                                               enlace.current_width, enlace.max_width)):
                enlace = None
            salida.append(PciDevice(
                slot=fijo["slot"], kind=fijo["kind"],
                name=propios.get(fijo["slot"]) or fijo["name"],
                vendor=fijo["vendor"], driver=fijo["driver"],
                link=enlace,
                slot_name=self._ranura(nodo, draft.pci_slot_names),
                vendor_id=fijo["ids"][0], device_id=fijo["ids"][1], pci_class=fijo["clase"]))
        salida.sort(key=lambda d: (ORDEN.index(d.kind), d.slot))
        draft.pci_devices = salida

    @staticmethod
    def _enumerar() -> list[dict]:
        crudos = []
        for camino in sorted(glob.glob(os.path.join(sysroot.ruta(DISPOSITIVOS), "*"))):
            slot = os.path.basename(camino)
            if not _DIRECCION.fullmatch(slot):
                continue
            base = sysroot.fuera(camino)
            clase = (read_text(f"{base}/class") or "")[2:6]
            tipo = CLASES.get(clase)
            if tipo is None:
                continue
            driver = None
            try:
                enlace = pathlib.Path(camino, "driver")
                driver = enlace.resolve().name if enlace.exists() else None
            except OSError:
                pass
            crudos.append({"slot": slot, "kind": tipo, "driver": driver, "clase": clase,
                           "ids": (_hex(f"{base}/vendor"), _hex(f"{base}/device"))})
        pares = [c["ids"] for c in crudos if None not in c["ids"]]
        nombres = pciids.lookup(pares) if pares else {}
        for crudo in crudos:
            marca, modelo = nombres.get(crudo["ids"], (None, None))
            # Un dispositivo que pci.ids aún no tiene (el audio del H510,
            # 8086:f0c8, en el de Fedora 44) sigue siendo de alguien.
            crudo["vendor"] = marca or VENDORS.get(crudo["ids"][0])
            crudo["name"] = modelo
        return crudos

    @staticmethod
    def _nombres_propios(draft: Draft) -> dict[str, str]:
        """El nombre que cada pieza ya tiene en su página, por dirección."""
        propios: dict[str, str] = {}
        for gpu in draft.gpus:
            if gpu.get("pci_slot") and gpu.get("name"):
                propios[gpu["pci_slot"]] = gpu["name"]
        for disco in draft.disks:
            if getattr(disco, "pci_slot", None) and disco.model:
                propios[disco.pci_slot] = disco.model
        for interfaz in draft.network:
            ranura = getattr(interfaz, "pci_slot", None)
            nombre = getattr(interfaz, "display_name", None)
            if ranura and nombre and nombre != interfaz.name:
                propios[ranura] = nombre
        return propios

    @staticmethod
    def _ranura(nodo: pathlib.Path, nombres: dict) -> Optional[str]:
        """El nombre de la ranura, si la tabla del firmware señala a este
        dispositivo o a un puente de su cadena (una gráfica lleva los suyos)."""
        if not nombres:
            return None
        for eslabon in _cadena_pcie(nodo):
            if (nombre := nombres.get(eslabon.name)):
                return nombre
        return None


class PlatformInfo(Provider):
    """IOMMU, virtualización, decodificación por encima de 4 GB y los chips
    de la placa. Una vez."""

    name = "platform"
    provides = "platform"
    static = True

    def collect(self, draft: Draft) -> None:
        tipo, estado = self._virtualizacion()
        draft.platform = Platform(
            iommu_groups=self._iommu(),
            virtualization=estado, virtualization_kind=tipo,
            above_4g_devices=self._por_encima_de_4g(),
            sensor_chip=self._chip_de_sensores(),
            audio_codec=self._codec(),
        )

    @staticmethod
    def _iommu() -> Optional[int]:
        grupos = glob.glob(os.path.join(sysroot.ruta("/sys/kernel/iommu_groups"), "*"))
        return len(grupos) or None

    @staticmethod
    def _virtualizacion() -> tuple[Optional[str], Optional[str]]:
        banderas = ""
        for linea in (read_text("/proc/cpuinfo") or "").splitlines():
            if linea.startswith("flags"):
                banderas = linea.partition(":")[2]
                break
        palabras = banderas.split()
        tipo = "AMD-V" if "svm" in palabras else "VT-x" if "vmx" in palabras else None
        if tipo is None:
            return None, None
        # `/dev/kvm` no es de /sys ni de /proc: se pregunta por `a_traves`
        # para que un volcado guarde lo que contestó su equipo.
        en_uso = sysroot.a_traves("plataforma", "kvm", lambda: os.path.exists("/dev/kvm"))
        return tipo, "active" if en_uso else "present"

    @staticmethod
    def _por_encima_de_4g() -> int:
        cuantos = 0
        for camino in glob.glob(os.path.join(sysroot.ruta(DISPOSITIVOS), "*", "resource")):
            for linea in (read_text(sysroot.fuera(camino)) or "").splitlines():
                campos = linea.split()
                try:
                    if len(campos) >= 2 and int(campos[1], 16) and int(campos[0], 16) >= 1 << 32:
                        cuantos += 1
                        break
                except ValueError:
                    continue
        return cuantos

    @staticmethod
    def _chip_de_sensores() -> Optional[str]:
        from .hwmon import BOARD_CHIP

        for camino in sorted(glob.glob(os.path.join(sysroot.ruta("/sys/class/hwmon"), "*", "name"))):
            nombre = read_text(sysroot.fuera(camino)) or ""
            if BOARD_CHIP.match(nombre) and not nombre.startswith(("acpitz", "thermal")) \
                    and not nombre.endswith("_wmi"):
                return nombre
        return None

    @staticmethod
    def _codec() -> Optional[str]:
        """El códec de sonido de la placa. Los de HDMI son de la gráfica."""
        for camino in sorted(glob.glob(os.path.join(sysroot.ruta("/proc/asound"), "card*", "codec#*"))):
            primera = (read_text(sysroot.fuera(camino)) or "").split("\n", 1)[0]
            nombre = primera.partition(":")[2].strip()
            if nombre and "HDMI" not in nombre:
                return nombre
        return None
