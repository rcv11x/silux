"""Placa base, firmware y chipset.

Tres orígenes distintos que responden a la misma pregunta —«sobre qué está
montado esto»— y por eso viven juntos:

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
from .base import Draft, Provider, read_text

SYS_DMI = "/sys/class/dmi/id"
PCI_DEVICES = pathlib.Path("/sys/bus/pci/devices")
EFI = pathlib.Path("/sys/firmware/efi")
SECURE_BOOT = EFI / "efivars" / "SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"

CHASSIS_TYPES = {
    "1": "Otro", "2": "Desconocido", "3": "Sobremesa", "4": "Sobremesa bajo",
    "5": "Pizza box", "6": "Mini torre", "7": "Torre", "8": "Portátil",
    "9": "Portátil", "10": "Notebook", "11": "De mano", "12": "Base acoplable",
    "13": "Todo en uno", "14": "Subportátil", "15": "Compacto",
    "16": "Chasis lateral", "17": "Servidor en rack", "18": "Subchasis",
    "23": "Servidor en rack", "24": "PC compacto", "30": "Tablet",
    "31": "Convertible", "32": "Desmontable", "35": "Mini PC",
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


def _dmi(field: str) -> Optional[str]:
    return clean_dmi(read_text(f"{SYS_DMI}/{field}"))


class DmiBoard(Provider):
    name = "dmi"
    provides = "board"
    static = True

    def available(self) -> bool:
        return os.path.isdir(SYS_DMI)

    def unavailable_reason(self):
        if self.available():
            return None
        return ("board", Need.PLATFORM,
                "Este equipo no expone información DMI.",
                "Ocurre en máquinas virtuales sencillas y en muchos ARM.")

    def collect(self, draft: Draft) -> None:
        draft.capabilities.add("dmi")
        chipset, chipset_full, host_bridge = self._chipset()

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

            chipset=chipset,
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

        if not draft.board.name:
            draft.note(
                "board.name", Need.HARDWARE,
                "La BIOS no publica el modelo de la placa.",
                "Algunos fabricantes dejan el campo sin rellenar a propósito.",
            )

    # -- firmware -----------------------------------------------------------

    @staticmethod
    def _firmware() -> str:
        if not EFI.is_dir():
            return "BIOS heredada"
        bits = read_text(str(EFI / "fw_platform_size"))
        return f"UEFI ({bits} bits)" if bits else "UEFI"

    @staticmethod
    def _secure_boot() -> Optional[bool]:
        """La variable EFI trae 4 bytes de atributos y luego el valor."""
        try:
            data = SECURE_BOOT.read_bytes()
        except OSError:
            return None
        return bool(data[4]) if len(data) >= 5 else None

    @staticmethod
    def _tpm() -> Optional[str]:
        for entry in sorted(pathlib.Path("/sys/class/tpm").glob("tpm*")):
            major = read_text(str(entry / "tpm_version_major"))
            if major:
                return f"TPM {major}.0"
            # Los TPM 1.2 antiguos no publican ese fichero.
            if (entry / "caps").exists():
                return "TPM 1.2"
        return None

    # -- chipset ------------------------------------------------------------

    @staticmethod
    def _chipset() -> tuple[Optional[str], Optional[str], Optional[str]]:
        """El puente LPC/eSPI del bus 0 identifica al chipset; el host bridge,
        al controlador de memoria integrado en la CPU."""
        if not PCI_DEVICES.is_dir():
            return None, None, None

        candidates: dict[int, tuple[int, int]] = {}
        for entry in sorted(PCI_DEVICES.iterdir()):
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

        chipset = chipset_full = host = None
        if (pair := candidates.get(CLASS_ISA_BRIDGE)) and pair in names:
            vendor_name, chipset_full = names[pair]
            match = _CHIPSET_MODEL.search(chipset_full)
            short_vendor_name = vendor_name.split()[0]
            chipset = f"{short_vendor_name} {match.group(1)}" if match else chipset_full
        if (pair := candidates.get(CLASS_HOST_BRIDGE)) and pair in names:
            host = names[pair][1]

        return chipset, chipset_full, host
