"""El voltaje del núcleo, preguntándoselo al procesador.

Es el dato que CPU-Z enseña arriba del todo y que aquí salía siempre con su
aviso de que ningún sensor lo publica. El aviso era cierto por donde miraba:
`k10temp` no publica ni un voltaje, y el chip Super I/O de una placa —el
it8688 de una Gigabyte, por ejemplo— publica nueve pero **sin etiqueta**, así
que quedarse con uno sería adivinar cuál. Comprobado en esa placa: `in0` es el
único que se mueve con la carga, pero eso vale para ese modelo y no para el
siguiente, y el driver no promete el orden.

Lo que sí es igual en cualquier equipo es preguntárselo al procesador. Hace
falta root, y para eso está el ayudante que ya pide la contraseña una vez.

- **En AMD** el registro `0xC0010063` dice qué P-state está activo y
  `0xC0010064 + n` trae su definición, con el VID en los bits 21:14. La
  conversión es `1,55 − 0,00625 × VID` y es la misma desde la familia 15h.
- **En Intel**, `MSR_PERF_STATUS` guarda el voltaje ya medido en los bits
  47:32, en coma fija de 16 bits: basta dividir entre 8192.

Los dos son de solo lectura y no tienen efectos al leerlos, que es la
condición para entrar en la lista blanca del ayudante.

**Es el voltaje que el procesador pide, no el que le llega.** Quien mide lo
que de verdad hay en los pines es el regulador de la placa, y ese sale por
hwmon cuando el chip etiqueta sus canales. Si aparecen los dos, manda el
medido: este se queda como respaldo. Contrastado en un 5800X3D: el P-state
activo pide 1,100 V y el it8688 de la placa mide 1,16.

**Y con el boost encendido se queda corto.** La tabla de P-states describe los
estados base —en ese 5800X3D, 3400 MHz a 1,100 V— y por encima de P0 manda el
microcontrolador de la pieza, que sube frecuencia y voltaje por su cuenta. Con
el procesador a 4,4 GHz, el VID de P0 sigue diciendo 1,100. La cifra no es
falsa, es de otro punto de la curva; para el instantáneo de verdad hace falta
el sensor del regulador.
"""

from __future__ import annotations

import platform
from typing import Optional

from ..i18n import _
from ..model import Need
from ..privileged.client import HelperError, PrivilegedClient
from .base import Draft, Provider

# Qué P-state está corriendo ahora mismo (bits 2:0).
AMD_PSTATE_STATUS = 0xC0010063
# La definición de cada uno. Hay ocho, pero solo los tres primeros se usan.
AMD_PSTATE_DEF = 0xC0010064
AMD_PSTATES = 3

# De la guía del programador de AMD: en PStateDef, CpuVid ocupa los bits 21:14.
AMD_VID_DESPLAZAMIENTO = 14
AMD_VID_MASCARA = 0xFF
AMD_VID_BASE = 1.55
AMD_VID_PASO = 0.00625

# Intel: IA32_PERF_STATUS. El voltaje va en los bits 47:32 en coma fija de 16
# bits, así que el divisor es 2^13 y no 2^16: los tres bits altos son enteros.
INTEL_PERF_STATUS = 0x198
INTEL_VOLTAJE_DESPLAZAMIENTO = 32
INTEL_VOLTAJE_MASCARA = 0xFFFF
INTEL_VOLTAJE_DIVISOR = 8192.0

# Por debajo o por encima de esto no es un voltaje de núcleo, es basura: un
# registro que no existe se lee como ceros y uno mal interpretado se dispara.
# Ningún procesador moderno funciona fuera de este rango.
MINIMO_V = 0.2
MAXIMO_V = 2.0


def _es_x86() -> bool:
    return platform.machine() in ("x86_64", "AMD64", "i686", "i386")


def _voltaje_amd(valores: dict) -> Optional[float]:
    """El VID del P-state que está activo."""
    estado = valores.get(AMD_PSTATE_STATUS)
    if estado is None:
        return None
    definicion = valores.get(AMD_PSTATE_DEF + (estado & 0x7))
    if not definicion:
        return None
    vid = (definicion >> AMD_VID_DESPLAZAMIENTO) & AMD_VID_MASCARA
    return AMD_VID_BASE - AMD_VID_PASO * vid


def _voltaje_intel(valores: dict) -> Optional[float]:
    crudo = valores.get(INTEL_PERF_STATUS)
    if not crudo:
        return None
    campo = (crudo >> INTEL_VOLTAJE_DESPLAZAMIENTO) & INTEL_VOLTAJE_MASCARA
    return campo / INTEL_VOLTAJE_DIVISOR if campo else None


class MsrVoltage(Provider):
    """El voltaje del núcleo por MSR, cuando ningún sensor lo publica."""

    name = "msr-voltage"
    provides = "cpu.voltage_v"

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        self.client = client

    def available(self) -> bool:
        return bool(self.client and self.client.connected())

    def unavailable_reason(self):
        """Sin ayudante no hay registro que leer, y eso sí tiene arreglo.

        El aviso va con `ROOT` a propósito: lleva botón para dar los permisos,
        y antes salía como `DRIVER`, que en esta pantalla se lee como «tu
        equipo no lo tiene» y no como «pulsa aquí».
        """
        if self.available():
            return None
        if not _es_x86():
            return ("cpu.voltage_v", Need.PLATFORM,
                    _("prov.msr.nox86"), _("prov.msr.nox86.hint"))
        return ("cpu.voltage_v", Need.ROOT,
                _("prov.msr.novolt"), _("prov.msr.novolt.hint"))

    def collect(self, draft: Draft) -> None:
        # Si hwmon ya encontró un sensor etiquetado, ese manda: mide lo que
        # llega al procesador y esto solo dice lo que pide.
        if any(entry.get("voltage_v") is not None
               for entry in draft.types.values()):
            return

        marcas = {(entry.get("vendor") or "").lower()
                  for entry in draft.types.values()}
        es_amd = any("amd" in m for m in marcas)
        registros = ([AMD_PSTATE_STATUS]
                     + [AMD_PSTATE_DEF + n for n in range(AMD_PSTATES)]
                     if es_amd else [INTEL_PERF_STATUS])
        try:
            valores = self.client.read_msr(0, registros)
        except HelperError:
            # Lo más común es que falte el módulo «msr», y eso se arregla con
            # una orden, así que se dice cuál en vez de callar.
            draft.note("cpu.voltage_v", Need.DRIVER,
                       _("prov.msr.nomodule"), _("prov.msr.nomodule.hint"))
            return
        except Exception:                                      # noqa: BLE001
            return

        voltaje = _voltaje_amd(valores) if es_amd else _voltaje_intel(valores)
        if voltaje is None or not MINIMO_V <= voltaje <= MAXIMO_V:
            return

        for entry in draft.types.values():
            entry["voltage_v"] = round(voltaje, 3)
