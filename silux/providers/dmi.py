"""Placa base, firmware y chipset.

Tres orígenes distintos que responden a la misma pregunta («sobre qué está
montado esto») y por eso viven juntos:

* `/sys/class/dmi/id` da la placa, la BIOS y el equipo, tal y como los declara
  la tabla SMBIOS. Los números de serie y el UUID están ahí al lado pero con
  permisos de root; este proveedor ni los mira, porque no hacen falta.
* `/sys/firmware/efi` y `/sys/class/tpm` dicen cómo arranca la máquina.
* El bus PCI identifica el chipset: el puente LPC/eSPI del bus 0 *es* el
  chipset, y `pci.ids` le pone nombre.

Los fabricantes dejan campos SMBIOS sin rellenar con textos como «Default
string». Se filtran: enseñarlos como si fueran datos es peor que dejar el
hueco vacío.
"""

from __future__ import annotations

import os
import pathlib
import re
from typing import Optional

from .. import pciids
from ..model import Board, Need, clean_dmi
from .base import Draft, Provider, en_maquina_virtual, read_text
from ..i18n import _
from .. import sysroot

SYS_DMI = "/sys/class/dmi/id"
PCI_DEVICES = pathlib.Path("/sys/bus/pci/devices")
EFI = pathlib.Path("/sys/firmware/efi")
SECURE_BOOT = EFI / "efivars" / "SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"

# El número lo pone SMBIOS; el nombre lo pone este programa, así que va por
# claves y se traduce al pintarlo.
CHASSIS_TYPES = {
    "1": "chassis.other", "2": "chassis.unknown", "3": "chassis.desktop",
    "4": "chassis.lowdesktop", "5": "chassis.pizzabox", "6": "chassis.minitower",
    "7": "chassis.tower", "8": "chassis.laptop", "9": "chassis.laptop",
    "10": "chassis.notebook", "11": "chassis.handheld", "12": "chassis.dock",
    "13": "chassis.aio", "14": "chassis.subnotebook", "15": "chassis.compact",
    "16": "chassis.lunchbox", "17": "chassis.rack", "18": "chassis.expansion",
    "23": "chassis.rack", "24": "chassis.smalldesktop", "30": "chassis.tablet",
    "31": "chassis.convertible", "32": "chassis.detachable",
    "35": "chassis.minipc",
}

CLASS_HOST_BRIDGE = 0x060000
CLASS_ISA_BRIDGE = 0x060100
# Los chipsets modernos de Intel se presentan como controlador eSPI, que el
# kernel clasifica igual que el viejo puente ISA.
CHIPSET_CLASSES = (CLASS_ISA_BRIDGE,)

# "H510 Chipset eSPI Controller" -> "H510"; "B550 LPC Bridge" -> "B550".
_CHIPSET_MODEL = re.compile(
    r"\b([A-Z]{1,3}\d{2,4}[A-Z]*)\b(?=.*(chipset|lpc|espi|isa))", re.IGNORECASE
)


# En AM4 y AM5 el puente LPC del bus 0 es el FCH que va dentro del procesador
# y se llama igual en todas las placas. Ahí el chipset lo dice el nombre de la
# placa («B550M» es una B550 en microATX; «B650E-F», una B650E). La lista es
# cerrada a propósito: una letra y tres cifras también es un portátil («Aspire
# A515-45», «VivoBook X513EA»), y un chipset que falta se explica mejor que
# uno inventado.
_CHIPSETS_AMD = ("A320", "B350", "X370", "B450", "X470", "A520", "B550", "X570",
                 "A620", "B650", "X670", "B840", "B850", "X870",
                 "X399", "TRX40", "TRX50", "WRX80", "WRX90")
_CHIPSET_EN_LA_PLACA = re.compile(rf"\b({'|'.join(_CHIPSETS_AMD)})(E\b)?")
AMD = "Advanced Micro Devices"


def chipset_de_la_placa(placa: Optional[str]) -> Optional[str]:
    """El chipset de AMD que lleva escrito el nombre de una placa, si lo lleva."""
    match = _CHIPSET_EN_LA_PLACA.search(placa or "")
    return match.group(1) + (match.group(2) or "") if match else None


def chipset(puente: Optional[tuple[str, str]], placa: Optional[str]) -> Optional[str]:
    """«Intel H510», «AMD X570», o nada si no lo dice nadie.

    `puente` es lo que `pci.ids` dice del puente LPC/eSPI: fabricante y
    nombre. Si el de un AMD no trae modelo se mira la placa, y si tampoco, no
    se da por chipset el nombre de un dispositivo PCI.
    """
    if puente is None:
        return None
    fabricante, nombre = puente
    match = _CHIPSET_MODEL.search(nombre)
    modelo = match.group(1) if match else None
    if modelo is None and fabricante.startswith(AMD):
        modelo = chipset_de_la_placa(placa)
    marca = "AMD" if fabricante.startswith(AMD) else fabricante.split()[0]
    return f"{marca} {modelo}" if modelo else None


def _dmi(field: str) -> Optional[str]:
    return clean_dmi(read_text(f"{SYS_DMI}/{field}"))


class DmiBoard(Provider):
    name = "dmi"
    provides = "board"
    static = True

    def available(self) -> bool:
        return os.path.isdir(sysroot.ruta(SYS_DMI))

    def unavailable_reason(self):
        if self.available():
            return None
        return ("board", Need.PLATFORM,
                _("prov.dmi.none"), _("prov.dmi.none.hint"))

    def collect(self, draft: Draft) -> None:
        draft.capabilities.add("dmi")
        modelo, chipset_full, host_bridge = self._chipset(_dmi("board_name"))

        draft.board = Board(
            vendor=_dmi("board_vendor"),
            name=_dmi("board_name"),
            version=_dmi("board_version"),

            bios_vendor=_dmi("bios_vendor"),
            bios_version=_dmi("bios_version"),
            bios_date=_dmi("bios_date"),
            bios_release=_dmi("bios_release"),

            firmware=self._firmware(),
            secure_boot=self._secure_boot(),
            tpm_version=self._tpm(),

            chipset=modelo,
            chipset_full=chipset_full,
            host_bridge=host_bridge,

            system_vendor=_dmi("sys_vendor"),
            system_name=_dmi("product_name"),
            system_version=_dmi("product_version"),
            system_family=_dmi("product_family"),
            system_sku=_dmi("product_sku"),

            chassis_vendor=_dmi("chassis_vendor"),
            chassis=CHASSIS_TYPES.get(read_text(f"{SYS_DMI}/chassis_type") or ""),
        )

        # A virtual machine has no board to blame (QEMU declares none): the
        # board page says what it is instead.
        if not draft.board.name and not en_maquina_virtual(draft):
            draft.note(
                "board.name", Need.HARDWARE,
                _("prov.dmi.noboard"), _("prov.dmi.noboard.hint"),
            )

    # -- firmware -----------------------------------------------------------

    @staticmethod
    def _firmware() -> str:
        if not sysroot.ruta(EFI).is_dir():
            return "BIOS heredada"
        bits = read_text(str(sysroot.ruta(EFI) / "fw_platform_size"))
        return f"UEFI ({bits} bits)" if bits else "UEFI"

    @staticmethod
    def _secure_boot() -> Optional[bool]:
        """La variable EFI trae 4 bytes de atributos y luego el valor."""
        try:
            data = sysroot.ruta(SECURE_BOOT).read_bytes()
        except OSError:
            return None
        return bool(data[4]) if len(data) >= 5 else None

    @staticmethod
    def _tpm() -> Optional[str]:
        for entry in sorted(pathlib.Path(sysroot.ruta("/sys/class/tpm")).glob("tpm*")):
            major = read_text(str(entry / "tpm_version_major"))
            if major:
                return f"TPM {major}.0"
            # Los TPM 1.2 antiguos no publican ese fichero.
            if (entry / "caps").exists():
                return "TPM 1.2"
        return None

    # -- chipset ------------------------------------------------------------

    @staticmethod
    def _chipset(placa: Optional[str] = None) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """El puente LPC/eSPI del bus 0 identifica al chipset; el host bridge,
        al controlador de memoria integrado en la CPU."""
        if not sysroot.ruta(PCI_DEVICES).is_dir():
            return None, None, None

        candidates: dict[int, tuple[int, int]] = {}
        for entry in sorted(sysroot.ruta(PCI_DEVICES).iterdir()):
            if not entry.name.startswith("0000:00:"):
                continue                      # el chipset siempre está en el bus 0
            try:
                device_class = int(read_text(str(entry / "class")) or "0", 16)
                vendor = int(read_text(str(entry / "vendor")) or "0", 16)
                device = int(read_text(str(entry / "device")) or "0", 16)
            except ValueError:
                continue
            if device_class in CHIPSET_CLASSES and CLASS_ISA_BRIDGE not in candidates:
                candidates[CLASS_ISA_BRIDGE] = (vendor, device)
            elif device_class == CLASS_HOST_BRIDGE and CLASS_HOST_BRIDGE not in candidates:
                candidates[CLASS_HOST_BRIDGE] = (vendor, device)

        names = pciids.lookup(candidates.values())

        modelo = chipset_full = host = None
        if (pair := candidates.get(CLASS_ISA_BRIDGE)) and pair in names:
            chipset_full = names[pair][1]
            modelo = chipset(names[pair], placa)
        if (pair := candidates.get(CLASS_HOST_BRIDGE)) and pair in names:
            host = names[pair][1]

        return modelo, chipset_full, host
