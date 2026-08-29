"""Reloj base, techo del silicio y BCLK cuando CPUID 0x16 no los da.

La hoja 0x16 solo existe en Intel de Skylake en adelante. En un AMD, en un
Intel anterior o en cualquier x86 viejo, tres filas de la tarjeta de Relojes
se quedaban vacías. Este proveedor las rellena con lo que sí hay, por orden
de fiabilidad:

- **ACPI CPPC** (`/sys/devices/system/cpu/cpuN/acpi_cppc/`), que el kernel
  publica para `amd-pstate` y para `intel_pstate` con HWP. Da el reloj nominal
  en MHz y una escala de rendimiento de la que sale el techo del silicio. No es
  una fuente de AMD: es ACPI 5.0, y la usa cualquier plataforma que la declare.
- **La cadena de marca**, que en los Intel de casi veinte años y en algunos AMD
  termina en «@ 3.30GHz». Es el único sitio donde mirar en un Core 2 o un
  Phenom, que no tienen ni 0x16 ni CPPC.

Nunca pisa lo que otra fuente ya dejó puesto: en un Intel moderno CPUID 0x16
va primero y esto no toca nada.

De paso saca de CPPC un dato que no es un reloj y que no publica ninguna otra
herramienta de Linux: **lo bien que salió cada núcleo de la oblea**. Los
núcleos de una misma pieza no son iguales, el firmware lo sabe y lo dice, y el
planificador lo usa para mandar el trabajo de un hilo suelto al mejor. Ryzen
Master lo enseña en Windows con estrellitas; aquí no lo enseñaba nadie.
"""

from __future__ import annotations

import dataclasses
import os
import re
from typing import Optional

from ..model import Clocks, Need
from .base import Draft, Provider, read_int, read_text
from ..i18n import _

SYS_CPU = "/sys/devices/system/cpu"

# Reloj de referencia de toda plataforma con CPPC: Nehalem y Zen en adelante
# lo fijaron en 100 MHz y ahí sigue. Los Core 2 y anteriores usaban un FSB de
# 133, 200, 266 o 333 MHz, y por eso el BCLK solo se deriva cuando hay CPPC:
# suponer 100 MHz en un Core 2 sería inventarse el dato.
REFERENCIA_HZ = 100_000_000

# El multiplicador se mueve en pasos de 0,25. Si el reloj que sale de dividir
# la base entre su multiplicador se aleja de los 100 MHz más que esto, la
# suposición no se sostiene y el dato se deja vacío en vez de mentir.
TOLERANCIA = 0.02

# «Intel(R) Core(TM) i5-4590 CPU @ 3.30GHz»
_MARCA_FRECUENCIA = re.compile(r"@\s*([\d.]+)\s*([GM])Hz", re.IGNORECASE)


class CppcClocks(Provider):
    """Completa los relojes que CPUID no supo dar, sin pisar los que sí."""

    name = "cppc-clocks"
    provides = "cpu.clocks.base_hz"
    # El reloj nominal y la escala de CPPC salen de tablas del firmware: no
    # cambian mientras la máquina esté encendida.
    static = True

    def available(self) -> bool:
        return os.path.isdir(SYS_CPU)

    def collect(self, draft: Draft) -> None:
        falta_base = False
        falta_bus = False

        for entry in draft.types.values():
            clocks: Clocks = entry.get("clocks") or Clocks()
            leader = (entry.get("cpus") or [0])[0]
            cppc = _leer_cppc(leader)
            if cppc:
                # Solo cuando el firmware la trae de verdad: la cadena de marca
                # no es una fuente nueva, sale del CPUID que ya se anunció.
                draft.capabilities.add("cppc")

            nominal = _nominal_hz(cppc)
            base = clocks.base_hz or nominal or _base_de_la_marca(entry.get("brand"))

            # El BCLK solo se deriva si la base viene de CPPC. Ver REFERENCIA_HZ.
            # Y solo en x86: ACPI CPPC también lo publica un ARM de servidor, y
            # allí no hay ningún reloj de referencia de 100 MHz del que colgar
            # un multiplicador.
            es_x86 = (entry.get("architecture") or "").startswith("x86")
            bus = clocks.bus_hz
            if bus is None and nominal and es_x86:
                bus = _reloj_de_referencia(nominal)

            techo = clocks.max_turbo_hz or _techo_del_silicio(leader, cppc, nominal)
            # Un techo por debajo de la base es un cálculo que salió mal.
            if techo and base and techo < base:
                techo = None

            if (base, bus, techo) != (clocks.base_hz, clocks.bus_hz, clocks.max_turbo_hz):
                entry["clocks"] = dataclasses.replace(
                    clocks, base_hz=base, bus_hz=bus, max_turbo_hz=techo
                )

            falta_base = falta_base or base is None
            falta_bus = falta_bus or (bus is None and es_x86)

        _anotar_calidad(draft)

        if falta_base:
            draft.note(
                "cpu.clocks.base_hz", Need.HARDWARE,
                _("prov.cppc.nobase"), _("prov.cppc.nobase.hint"),
            )
        if falta_bus:
            draft.note(
                "cpu.clocks.bus_hz", Need.HARDWARE,
                _("prov.cppc.nobclk"), _("prov.cppc.nobclk.hint"),
            )


# -- lectura ----------------------------------------------------------------

def _leer_cppc(cpu_index: int) -> dict[str, int]:
    """Los enteros de acpi_cppc para una CPU. Vacío si el firmware no lo trae."""
    directorio = f"{SYS_CPU}/cpu{cpu_index}/acpi_cppc"
    if not os.path.isdir(directorio):
        return {}
    campos = ("nominal_freq", "lowest_freq", "nominal_perf", "highest_perf")
    valores = {}
    for campo in campos:
        valor = read_int(f"{directorio}/{campo}")
        if valor:                      # un 0 es «el firmware no lo rellenó»
            valores[campo] = valor
    return valores


def _anotar_calidad(draft: Draft) -> None:
    """Reparte por CPU lógica la nota de silicio que publica el firmware.

    Es el mismo `highest_perf` que arriba se descarta para calcular el techo, y
    por el mismo motivo: cuando la plataforma ordena sus núcleos, ese campo deja
    de valer «hasta dónde llega la pieza» y pasa a valer «cuánto mejor es este
    núcleo que sus hermanos». Como cifra de frecuencia es una trampa; como nota
    comparativa es exactamente lo que dice.

    Solo se anota si de verdad hay diferencias entre núcleos, y **dentro de
    cada tipo**. Un firmware que devuelve el mismo número dieciséis veces no
    está midiendo nada: está rellenando el campo con la constante de la
    familia. Y en un Intel híbrido siempre hay diferencia entre un P-core y un
    E-core, pero esa no es la que interesa: un E-core no salió peor de la
    oblea, es otro núcleo. La comparación vale entre piezas equivalentes.
    """
    notas: dict[int, int] = {}
    for indice in draft.logical:
        base = f"{SYS_CPU}/cpu{indice}"
        # amd-pstate publica el ranking ya normalizado; donde no esté, el campo
        # de CPPC del que sale. En un Intel con HWP este es el `highest_perf`
        # de cada núcleo, que es la misma idea con otro nombre.
        nota = (read_int(f"{base}/cpufreq/amd_pstate_prefcore_ranking")
                or read_int(f"{base}/acpi_cppc/highest_perf"))
        if nota:
            notas[indice] = nota

    anotado = False
    for entrada in draft.types.values():
        suyas = {i: notas[i] for i in (entrada.get("cpus") or ()) if i in notas}
        if len(set(suyas.values())) < 2:
            continue
        for indice, nota in suyas.items():
            draft.cpu(indice)["quality"] = nota
        anotado = True
    if anotado:
        draft.capabilities.add("cppc-prefcore")


def _nominal_hz(cppc: dict[str, int]) -> Optional[int]:
    """`nominal_freq` viene en MHz; es el reloj base del procesador."""
    mhz = cppc.get("nominal_freq")
    return mhz * 1_000_000 if mhz else None


def _techo_del_silicio(cpu_index: int, cppc: dict[str, int],
                       nominal_hz: Optional[int]) -> Optional[int]:
    """El boost máximo del silicio, distinto del techo que aplica el kernel."""
    # amd-pstate ya publica el cálculo hecho, y con boost desactivado sigue
    # enseñando el techo real mientras `cpuinfo_max_freq` baja: justo la
    # discrepancia que la tarjeta de Relojes existe para explicar.
    khz = read_int(f"{SYS_CPU}/cpu{cpu_index}/cpufreq/amd_pstate_max_freq")
    if khz:
        return khz * 1000

    nominal_perf = cppc.get("nominal_perf")
    highest_perf = cppc.get("highest_perf")
    if not (nominal_hz and nominal_perf and highest_perf):
        return None
    # Con núcleos preferentes, el `highest_perf` de CPPC lleva el ranking del
    # mejor núcleo en vez del rendimiento máximo, y sale un techo inflado. Ese
    # caso es siempre amd-pstate, que ya se resolvió arriba.
    return int(nominal_hz * highest_perf / nominal_perf)


def _base_de_la_marca(brand: Optional[str]) -> Optional[int]:
    """Último recurso: la frecuencia que muchos Intel llevan en el nombre."""
    if not brand:
        return None
    encaje = _MARCA_FRECUENCIA.search(brand)
    if not encaje:
        return None
    escala = 1_000_000_000 if encaje.group(2).upper() == "G" else 1_000_000
    return int(float(encaje.group(1)) * escala)


def _reloj_de_referencia(base_hz: int) -> Optional[int]:
    """El BCLK del que cuelga el multiplicador, deducido del reloj base.

    Con 3401 MHz de base sale un multiplicador de 34,00 sobre 100,03 MHz, que
    es lo que enseña la BIOS. La división se hace de verdad en vez de dar por
    supuestos los 100 MHz: así el número guardado sigue saliendo de los datos.
    """
    multiplicador = round(base_hz / REFERENCIA_HZ * 4) / 4
    if multiplicador < 1:
        return None
    reloj = int(round(base_hz / multiplicador))
    if abs(reloj - REFERENCIA_HZ) > REFERENCIA_HZ * TOLERANCIA:
        return None
    return reloj
