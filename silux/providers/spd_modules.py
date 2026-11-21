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

from .. import spd as spd_module
from ..model import DriverHint, MemoryModule, Need
from .base import Draft, Provider
from ..i18n import _


class SpdModules(Provider):
    name = "spd"
    provides = "spd"
    static = True

    def available(self) -> bool:
        return spd_module.available()

    def unavailable_reason(self):
        if self.available():
            return None
        # El motivo no es siempre el mismo y la solución tampoco: puede faltar
        # el bus entero, puede estar reservado por el firmware o puede que solo
        # falte cargar un módulo. Decir siempre «carga ee1004» era inútil en la
        # mayoría de las placas AMD, donde ese módulo ya está y no hay bus.
        causa = spd_module.unreadable_cause()
        motivo, solucion = spd_module.diagnostico(causa)
        # Sin bus, o con el bus reservado por el firmware, es la placa. Con
        # el bus y sin driver, el SPD está y se lee cargándolo, que pide
        # permisos: eso no se le puede achacar al equipo.
        need = Need.DRIVER if causa == spd_module.CAUSE_NO_DRIVER else Need.HARDWARE
        return ("spd", need, motivo, solucion)

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
                _("prov.spd.unsupported").format(
                    tipos=" y ".join(sorted(tipos))
                          or _("prov.spd.thesemodules")),
                _("prov.spd.unsupported.hint"),
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
        matches: dict[int, object] = {}
        # Every module by part number first: module by module, a ThinkPad's
        # soldered memory took the slot's only reading by order before the
        # slot's module could match it (F-M16).
        for index in populated:
            part = (draft.modules[index].part_number or "").strip()
            match = next((r for r in pending
                          if part and r.part_number and r.part_number.strip() == part), None)
            if match is not None:
                pending.remove(match)
                matches[index] = match
        # Then the rest in order, a slot before memory soldered on the board:
        # that has no SPD chip of its own on the bus.
        rest = sorted((i for i in populated if i not in matches),
                      key=lambda i: not draft.modules[i].in_a_slot)
        for index in rest:
            if not pending:
                break
            matches[index] = pending.pop(0)
        for index, match in matches.items():
            draft.modules[index] = dataclasses.replace(draft.modules[index], spd=match)
