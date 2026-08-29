"""Módulos de memoria, a través del ayudante privilegiado.

Sin permisos solo se sabe cuánta RAM hay en total, porque eso lo cuenta el
kernel. Quién la fabrica, de qué tipo es, a qué velocidad va y cuántos
zócalos quedan libres está en la tabla SMBIOS, que el kernel reserva a root
por buenos motivos: junto a esos campos van los números de serie del equipo.

Este proveedor no eleva permisos por su cuenta. Se queda esperando a que el
usuario lo pida desde la interfaz, y hasta entonces deja una nota explicando
qué falta y por qué. Un programa de diagnóstico que abre un diálogo de
contraseña nada más arrancar es un programa que se desinstala.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
from typing import Iterator, Optional

from ..model import DriverHint, MemoryArray, MemoryModule, Need, PrivilegedState
from ..privileged import smbios
from ..privileged.client import (
    HelperDenied,
    HelperError,
    HelperUnavailable,
    PrivilegedClient,
    already_root,
)
from .base import Draft, Provider
from ..i18n import _


def _module(raw: dict) -> MemoryModule:
    return MemoryModule(
        locator=raw.get("locator"),
        bank=raw.get("bank"),
        populated=bool(raw.get("populated")),
        size_bytes=raw.get("size_bytes") or 0,
        type=raw.get("type"),
        form_factor=raw.get("form_factor"),
        details=tuple(raw.get("details") or ()),
        speed_mts=raw.get("speed_mts"),
        configured_mts=raw.get("configured_mts"),
        manufacturer=raw.get("manufacturer"),
        part_number=raw.get("part_number"),
        rank=raw.get("rank"),
        data_width=raw.get("data_width"),
        total_width=raw.get("total_width"),
        voltage_min_mv=raw.get("voltage_min_mv"),
        voltage_max_mv=raw.get("voltage_max_mv"),
        voltage_configured_mv=raw.get("voltage_configured_mv"),
    )


class PrivilegedMemory(Provider):
    name = "smbios-memory"
    provides = "modules"
    static = True

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        self.client = client or PrivilegedClient()
        self.requested = False
        self._error: Optional[str] = None

    def collect(self, draft: Draft) -> None:
        draft.driver_hints.extend(self._spd_hint())
        draft.privileged = PrivilegedState(
            supported=self.client.supported(),
            connected=self.client.connected(),
            already_root=already_root(),
            message=self._error,
        )

        if already_root():
            # Sin ayudante de por medio: la tabla ya se puede leer.
            self._read_directly(draft)
            return

        if not self.requested:
            self._explain(draft)
            return

        try:
            self.client.connect()
            self._parse(draft, self.client.smbios_table())
            self._error = None
        except HelperDenied as exc:
            self.requested = False
            self._error = str(exc)
            draft.note("modules", Need.ROOT,
                       _("prov.mem.denied"), _("prov.mem.denied.hint"))
        except (HelperUnavailable, HelperError) as exc:
            self.requested = False
            self._error = str(exc)
            draft.note("modules", Need.ROOT,
                       _("prov.mem.helperfail").format(error=exc), "")

        draft.privileged = PrivilegedState(
            supported=self.client.supported(),
            connected=self.client.connected(),
            already_root=already_root(),
            message=self._error,
        )

    # -- SPD ----------------------------------------------------------------

    # Los chips de SPD de un módulo DDR4 viven en el bus SMBus, en las
    # direcciones 0x50 a 0x57: una por zócalo.
    _SPD_ADDRESS = re.compile(r"^\d+-00(5[0-7])$")

    @classmethod
    def _spd_hint(cls) -> Iterator[DriverHint]:
        """La tabla SMBIOS dice a qué velocidad va la memoria; el SPD dice a
        cuánto podría ir.

        Son datos distintos: SMBIOS refleja lo que la BIOS ha negociado, y sin
        XMP activado eso son los valores JEDEC conservadores. Los perfiles del
        fabricante están en el chip SPD del propio módulo, al que se llega por
        el bus SMBus cuando está cargado el driver correspondiente.
        """
        devices = pathlib.Path("/sys/bus/i2c/devices")
        if not devices.is_dir():
            return

        candidates = [entry for entry in devices.iterdir()
                      if cls._SPD_ADDRESS.match(entry.name)]
        if not candidates:
            return
        if any((entry / "eeprom").exists() for entry in candidates):
            return                            # ya está leído

        # De la más nueva a la más vieja: el driver que sobra no encuentra
        # nada y no molesta, pero sin el que toca no se lee el módulo.
        for module in ("spd5118", "ee1004", "at24"):
            if not shutil.which("modinfo"):
                return
            result = subprocess.run(["modinfo", "-F", "filename", module],
                                    capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                yield DriverHint(
                    module=module,
                    provides=_("prov.hint.spd").format(n=len(candidates)),
                    command=f"sudo modprobe {module}",
                    caution=_("prov.hint.spd.caution"),
                )
                return

    # -- interno ------------------------------------------------------------

    @staticmethod
    def _explain(draft: Draft) -> None:
        draft.note(
            "modules", Need.ROOT,
            _("prov.mem.smbios"), _("prov.mem.smbios.hint"),
        )

    def _read_directly(self, draft: Draft) -> None:
        try:
            with open("/sys/firmware/dmi/tables/DMI", "rb") as handle:
                self._parse(draft, handle.read())
        except OSError as exc:
            self._error = str(exc)
            draft.note("modules", Need.HARDWARE,
                       _("prov.mem.smbiosfail").format(error=exc), "")

    @staticmethod
    def _parse(draft: Draft, table: bytes) -> None:
        if not table:
            return
        structures = list(smbios.parse_table(table))
        draft.modules = [_module(raw) for raw in smbios.memory_devices(structures)]

        arrays = smbios.memory_arrays(structures)
        if arrays:
            first = arrays[0]
            draft.memory_array = MemoryArray(
                slots=first.get("slots"),
                max_capacity_bytes=first.get("max_capacity_bytes") or 0,
                error_correction=first.get("error_correction"),
            )
        draft.capabilities.add("smbios")
