"""Lo que silux lee y no existe en todos los kernels que admite.

El mínimo es Linux 5.15. Algunos datos aparecieron después, y cuando faltan
en un kernel anterior no es que el equipo no los tenga: es que su kernel no
los publica todavía. Esa ausencia se dice distinta de «este equipo no lo
tiene» —«Tu kernel (5.15) no publica esto; existe desde Linux 6.10»—, porque
tiene arreglo y el arreglo no es otro hardware.

La versión de cada dato, con su fuente (el commit o la documentación del
kernel), está en `docs/kernel.md`; `tests/test_kernel.py` comprueba que las
dos tablas dicen lo mismo.
"""

from __future__ import annotations

import platform
import re
from typing import Optional

from . import sysroot
from .i18n import _

MINIMO = (5, 15)

# Dato → primera versión de mainline que lo publica. Solo lo que es posterior
# al mínimo; lo anterior está en todos los kernels que silux admite.
DESDE = {
    "cpufreq.cpuinfo_avg_freq": (6, 15),
    "amd_pstate": (5, 17),
    "amd_pstate.epp": (6, 3),
    "amd_pstate.prefcore_ranking": (6, 9),
    "amdgpu.power1_input": (6, 6),
    "amdgpu.vcn_busy_percent": (6, 10),
    "i915.gt": (5, 19),
    "i915.throttle_reason": (5, 19),
    "spd5118": (6, 11),
    "xe": (6, 8),
}


def version(texto: Optional[str]) -> Optional[tuple[int, int]]:
    """(6, 10) de «6.10.3-arch1-1» o de «Linux 6.10.3-arch1-1»."""
    encaje = re.search(r"(\d+)\.(\d+)", texto or "")
    return (int(encaje.group(1)), int(encaje.group(2))) if encaje else None


def running() -> Optional[tuple[int, int]]:
    """La del kernel en marcha; en un equipo volcado, la de cuando se volcó."""
    uname = sysroot.recorded("plataforma", "uname", lambda: platform.uname()._asdict())
    return version((uname or {}).get("release"))


def too_old(clave: str, actual: Optional[tuple[int, int]] = None,
            dato: str = "") -> Optional[str]:
    """La frase que explica la ausencia si el kernel es anterior al dato.

    None si el kernel ya lo publica, o si no se sabe cuál es: entonces la
    ausencia es del equipo y se explica como siempre. Con `dato`, la frase lo
    nombra, para un pie que dice varias cosas a la vez.
    """
    desde = DESDE[clave]
    actual = actual or running()
    if actual is None or actual >= desde:
        return None
    tuyo, desde = f"{actual[0]}.{actual[1]}", f"{desde[0]}.{desde[1]}"
    if dato:
        return _("kernel.tooold.what").format(dato=dato, tuyo=tuyo, desde=desde)
    return _("kernel.tooold").format(tuyo=tuyo, desde=desde)
