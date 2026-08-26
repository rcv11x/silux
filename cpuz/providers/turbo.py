"""Si el turbo está activado o no.

Merece un proveedor propio porque explica una discrepancia que si no
desconcierta: CPUID dice que el silicio llega a 4,3 GHz y el kernel dice que
el techo son 2,9. Casi siempre es que el turbo está desactivado en la BIOS o
por el driver, y decirlo vale más que enseñar los dos números y callarse.
"""

from __future__ import annotations

import dataclasses
import os

from ..model import Clocks
from .base import Draft, Provider, read_int

INTEL_PSTATE_NO_TURBO = "/sys/devices/system/cpu/intel_pstate/no_turbo"
CPUFREQ_BOOST = "/sys/devices/system/cpu/cpufreq/boost"


class TurboState(Provider):
    name = "turbo"
    provides = "cpu.clocks.turbo_enabled"
    # NO es estático: los perfiles de energía del escritorio activan y
    # desactivan el turbo en caliente, y con él cambia el techo de frecuencia.
    static = False

    def available(self) -> bool:
        return os.path.exists(INTEL_PSTATE_NO_TURBO) or os.path.exists(CPUFREQ_BOOST)

    def collect(self, draft: Draft) -> None:
        enabled = None
        if (value := read_int(INTEL_PSTATE_NO_TURBO)) is not None:
            enabled = value == 0
        elif (value := read_int(CPUFREQ_BOOST)) is not None:
            enabled = value == 1

        if enabled is None:
            return

        for entry in draft.types.values():
            clocks: Clocks = entry.get("clocks") or Clocks()
            entry["clocks"] = dataclasses.replace(clocks, turbo_enabled=enabled)

        # No se deja nota. El estado del turbo se enseña donde corresponde
        # —junto a las frecuencias, en la tarjeta de Relojes— y como cambia
        # solo con el perfil de energía, una tarjeta de aviso al pie aparecía
        # y desaparecía dando saltos por algo que ya estaba dicho arriba.
