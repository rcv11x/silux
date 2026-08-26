"""Lectura del SPD y emparejado con los módulos de SMBIOS.

Son dos fuentes que describen los mismos módulos desde ángulos distintos:
SMBIOS dice dónde está cada uno y a qué velocidad lo ha puesto la BIOS; el SPD
dice de qué es capaz. Juntarlas es lo que permite decir «va a 2667 de los 3200
que admite», que es la frase que la gente busca al abrir esta pestaña.

No hace falta ningún permiso: en la mayoría de distribuciones el chip SPD queda
legible por cualquiera en cuanto el kernel carga su driver.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .. import spd as spd_module
from ..model import DriverHint, MemoryModule, Need
from .base import Draft, Provider


class SpdModules(Provider):
    name = "spd"
    provides = "spd"
    static = True

    def available(self) -> bool:
        return spd_module.available()

    def unavailable_reason(self):
        if self.available():
            return None
        return ("spd", Need.DRIVER,
                "Los chips SPD de los módulos no están expuestos por el kernel.",
                "Se activan con el módulo ee1004 (DDR4) o spd5118 (DDR5).")

    def collect(self, draft: Draft) -> None:
        readings = spd_module.read_all()
        if not readings:
            return

        draft.capabilities.add("spd")
        draft.spd = readings
        self._merge(draft, readings)

        if any(not r.decoded for r in readings):
            tipos = {r.dram_type for r in readings if not r.decoded and r.dram_type}
            draft.note(
                "spd", Need.PLATFORM,
                f"El SPD de {' y '.join(sorted(tipos)) or 'estos módulos'} "
                "todavía no se sabe interpretar.",
                "De momento solo está implementado el formato de DDR4.",
            )

    @staticmethod
    def _merge(draft: Draft, readings: list) -> None:
        """Pega cada lectura de SPD al módulo de SMBIOS que le corresponde.

        No hay ninguna correspondencia oficial entre la dirección del chip en
        el bus y el nombre del zócalo que da la BIOS, así que primero se
        intenta casar por referencia (que es fiable cuando ambas la publican)
        y si no, por orden, que es lo que hacen todas las herramientas y
        acierta salvo en placas muy raras.
        """
        populated = [i for i, m in enumerate(draft.modules) if m.populated]
        if not populated:
            return

        pending = list(readings)
        for index in populated:
            module = draft.modules[index]
            match: Optional[object] = None

            if module.part_number:
                match = next(
                    (r for r in pending
                     if r.part_number and r.part_number.strip() == module.part_number.strip()),
                    None,
                )
            if match is None and pending:
                match = pending[0]
            if match is None:
                continue

            pending.remove(match)
            draft.modules[index] = dataclasses.replace(module, spd=match)
