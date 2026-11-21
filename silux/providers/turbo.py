"""Si el turbo está activado o no.

Merece un proveedor propio porque explica una discrepancia que si no
desconcierta: CPUID dice que el silicio llega a 4,3 GHz y el kernel dice que
el techo son 2,9. Casi siempre es que el turbo está desactivado en la BIOS o
por el driver, y decirlo vale más que enseñar los dos números y callarse.
"""

from __future__ import annotations

import dataclasses
import os
from typing import Optional

from .. import sysroot
from ..model import Clocks
from .base import Draft, Provider, en_maquina_virtual, read_int, read_text

INTEL_PSTATE_NO_TURBO = "/sys/devices/system/cpu/intel_pstate/no_turbo"
CPUFREQ_BOOST = "/sys/devices/system/cpu/cpufreq/boost"
CPUINFO = "/proc/cpuinfo"
# The kernel's flags for a part that has a turbo: AMD's Core Performance
# Boost (CPUID 0x80000007 EDX bit 9) and Intel's Dynamic Acceleration
# (CPUID 6 EAX bit 1). Read from /proc/cpuinfo and not from CPUID: the dumps
# carry that file, and not those two leaves.
TURBO_FLAGS = ("cpb", "ida")


def _turbo_supported() -> Optional[bool]:
    """Whether the part has a turbo, by the kernel's flags; None without them
    (not x86)."""
    for line in (read_text(CPUINFO) or "").splitlines():
        key, _sep, value = line.partition(":")
        if key.strip() == "flags":
            return any(flag in value.split() for flag in TURBO_FLAGS)
    return None


class TurboState(Provider):
    name = "turbo"
    provides = "cpu.clocks.turbo_enabled"
    # NO es estático: los perfiles de energía del escritorio activan y
    # desactivan el turbo en caliente, y con él cambia el techo de frecuencia.
    static = False

    def __init__(self) -> None:
        # The part does not change: read once, not on every sample.
        self._supported: Optional[bool] = None
        self._supported_read = False

    def available(self) -> bool:
        return (os.path.exists(sysroot.ruta(INTEL_PSTATE_NO_TURBO))
                or os.path.exists(sysroot.ruta(CPUFREQ_BOOST))
                or os.path.exists(sysroot.ruta(CPUINFO)))

    def collect(self, draft: Draft) -> None:
        enabled = None
        if (value := read_int(INTEL_PSTATE_NO_TURBO)) is not None:
            enabled = value == 0
        elif (value := read_int(CPUFREQ_BOOST)) is not None:
            enabled = value == 1
        if not self._supported_read:
            self._supported, self._supported_read = _turbo_supported(), True
        # A virtual CPU's flags are the hypervisor's, not the host's part.
        supported = None if en_maquina_virtual(draft) else self._supported

        if enabled is None and supported is None:
            return

        for entry in draft.types.values():
            clocks: Clocks = entry.get("clocks") or Clocks()
            entry["clocks"] = dataclasses.replace(clocks, turbo_enabled=enabled,
                                                  turbo_supported=supported)

        # No se deja nota. El estado del turbo se enseña donde corresponde
        # (junto a las frecuencias, en la tarjeta de Relojes) y como cambia
        # solo con el perfil de energía, una tarjeta de aviso al pie aparecía
        # y desaparecía dando saltos por algo que ya estaba dicho arriba.
