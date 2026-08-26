"""Identidad del procesador en ARM, donde no hay CPUID.

Lo que en x86 responde una instrucción, aquí lo publica el kernel ya leído
del registro MIDR_EL1: quién fabricó el núcleo, cuál es y en qué revisión va.
Con eso sale el nombre («ARM Cortex-A55 r0p0»), que es lo que un aarch64
tiene en lugar de la cadena de marca, porque el silicio de ARM no la lleva.

Lo demás no tiene equivalente y no se finge: no hay familia ni modelo al modo
de x86, ni cadena comercial grabada, ni socket. Sí hay banderas de juego de
instrucciones, que el kernel lista en «Features», y suele haber un árbol de
dispositivos que dice de qué aparato se trata.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import platform
import re
from typing import Optional

from .. import db
from ..model import Need
from .base import Draft, Provider, read_text

CPUINFO = "/proc/cpuinfo"
DEVICE_TREE = "/sys/firmware/devicetree/base"

def es_arm() -> bool:
    return platform.machine().lower().startswith(("aarch64", "arm"))


def _cpuinfo() -> list[dict[str, str]]:
    """Los bloques de /proc/cpuinfo, uno por CPU lógica, en orden.

    En aarch64 cada bloque trae los cuatro campos del MIDR. En big.LITTLE no
    son iguales entre sí, y esa es justamente la gracia: los bloques dicen qué
    núcleo es cada CPU.
    """
    try:
        crudo = pathlib.Path(CPUINFO).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    bloques, actual = [], {}
    for linea in crudo.splitlines():
        if not linea.strip():
            if actual:
                bloques.append(actual)
                actual = {}
            continue
        if ":" not in linea:
            continue
        clave, _, valor = linea.partition(":")
        actual[clave.strip()] = valor.strip()
    if actual:
        bloques.append(actual)
    return bloques


def _entero(bloque: dict[str, str], clave: str) -> Optional[int]:
    crudo = bloque.get(clave)
    if not crudo:
        return None
    try:
        return int(crudo, 16) if crudo.startswith("0x") else int(crudo)
    except ValueError:
        return None


def midr_por_cpu() -> dict[int, tuple[Optional[int], Optional[int]]]:
    """Para cada CPU lógica, su (implementer, part).

    Es lo que permite separar los núcleos grandes de los pequeños sin
    depender de los PMU de Intel, que en ARM no existen.
    """
    salida: dict[int, tuple[Optional[int], Optional[int]]] = {}
    for bloque in _cpuinfo():
        indice = _entero(bloque, "processor")
        if indice is None:
            continue
        salida[indice] = (_entero(bloque, "CPU implementer"),
                          _entero(bloque, "CPU part"))
    return salida


def _del_arbol(nombre: str) -> Optional[str]:
    """Una cadena del árbol de dispositivos, sin el cero final que llevan."""
    crudo = read_text(f"{DEVICE_TREE}/{nombre}")
    if not crudo:
        return None
    # Son cadenas de C, y «compatible» encadena varias separadas por ceros.
    limpio = crudo.split("\x00")[0].strip()
    return limpio or None


def modelo_del_equipo() -> Optional[str]:
    """De qué aparato se trata: «Raspberry Pi 4 Model B Rev 1.4».

    En x86 esto lo da el DMI de la placa. Una máquina ARM no suele tener
    SMBIOS, pero casi siempre trae árbol de dispositivos, que cumple el
    mismo papel.
    """
    return _del_arbol("model")


class ArmIdentity(Provider):
    """Rellena la identidad de cada tipo de núcleo desde /proc/cpuinfo."""

    name = "arm-cpuinfo"
    provides = "cpu.identity"
    static = True

    def available(self) -> bool:
        return es_arm() and os.path.exists(CPUINFO)

    def unavailable_reason(self):
        return None          # en x86 no falta nada: lo cubre CPUID

    def collect(self, draft: Draft) -> None:
        bloques = _cpuinfo()
        if not bloques:
            return
        draft.capabilities.add("arm-cpuinfo")
        # CPUID ya dejó dicho que aquí no existe. Existe la identidad, que es
        # de lo que iba la nota, solo que se lee por otro sitio.
        draft.resolve("cpu.identity")

        por_cpu = midr_por_cpu()
        for key, entry in draft.types.items():
            cpus = entry.get("cpus") or [0]
            implementer, part = por_cpu.get(cpus[0], (None, None))
            bloque = next((b for b in bloques
                           if _entero(b, "processor") == cpus[0]), bloques[0])
            self._rellenar(entry, bloque, implementer, part)

        # El árbol de dispositivos hace en ARM el papel que el DMI hace en
        # x86: decir de qué aparato se trata. No es un dato del procesador,
        # así que va donde iría el de la placa.
        modelo = modelo_del_equipo()
        if modelo and not draft.board.name:
            draft.board = dataclasses.replace(
                draft.board, name=modelo,
                vendor=draft.board.vendor or _del_arbol("compatible"))

    # -- interno ------------------------------------------------------------

    @staticmethod
    def _rellenar(entry: dict, bloque: dict[str, str],
                  implementer: Optional[int], part: Optional[int]) -> None:
        # La base de datos generada ya trae la tabla de MIDR de libcpuid, con
        # el nombre en clave de cada núcleo y su litografía.
        identidad = (db.identify_arm(implementer, part)
                     if None not in (implementer, part) else {})
        fabricante = identidad.get("vendor")
        nucleo = identidad.get("part_name")
        variante = _entero(bloque, "CPU variant")
        revision = _entero(bloque, "CPU revision")

        # rXpY es como ARM nombra las revisiones de su silicio, y como las
        # nombran sus propias erratas.
        paso = (f"r{variante}p{revision}"
                if variante is not None and revision is not None else None)

        entry.update(
            vendor=fabricante,
            vendor_id=f"0x{implementer:02x}" if implementer is not None else None,
            brand=" ".join(p for p in (fabricante, nucleo, paso) if p) or None,
            codename=identidad.get("codename"),
            technology=identidad.get("technology"),
            architecture=platform.machine(),
            # El equivalente ARM de la firma de CPUID: los dos números que
            # identifican el silicio, sin inventarles una familia y un modelo
            # que aquí no significan lo mismo.
            signature=(implementer << 24 | part << 4) if None not in (implementer, part) else None,
            features=_banderas(bloque),
        )
        if nucleo is None and part is not None:
            entry["brand"] = " ".join(
                p for p in (fabricante, f"núcleo 0x{part:03x}", paso) if p)


def _banderas(bloque: dict[str, str]) -> tuple[str, ...]:
    crudo = bloque.get("Features") or bloque.get("flags") or ""
    # Tal como las nombra el kernel. Ponerles nombre bonito es cosa de
    # render, que es el único sitio donde un valor se convierte en texto.
    return tuple(f for f in re.split(r"\s+", crudo) if f)
