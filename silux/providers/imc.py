"""El tráfico que mueve el controlador de memoria, leído de su PMU.

No es una prueba: es un sensor. Nadie provoca este tráfico, es el que hay, y
por eso vive al lado del ancho de banda que mide `membench` y no dentro. Aquel
dice lo que la memoria *puede* dar y para saberlo tiene que ocupar la máquina;
este dice lo que está moviendo ahora mismo, mientras el equipo hace lo suyo.

Es el mismo contador que `intel_gpu_top` enseña junto a la gráfica, y su sitio
no es aquella página: la integrada usa la RAM del sistema como VRAM, pero lo
que se cuenta aquí es el controlador entero, con el tráfico del procesador
dentro. De ahí que se lea también `ia_requests`, que es la parte que piden los
núcleos.

**Solo Intel.** AMD no publica estos contadores con nombre: de Zen 4 en
adelante existe el PMU `amd_umc_N` pero el kernel no le registra un grupo
`events/`, así que habría que escribir el número de evento a mano y afirmar lo
que significa sin ninguna pieza donde comprobarlo; y de Zen 3 para atrás no
hay nada documentado. Ante la duda no se inventa una cifra: se dice que este
equipo no lo publica, en gris y sin botón que pulsar.

Hace falta el ayudante privilegiado. `perf_event_paranoid` viene a 2 en
cualquier distribución y a los contadores del uncore les hace falta
CAP_PERFMON, que es el valor 0; bajarlo sería abrirle el perfilado de la
máquina entera a cualquier proceso, así que se pide por donde ya se pide todo
lo demás.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from ..i18n import _
from ..model import DeviceKind, MemoryTraffic, Need, Sensor, SensorKind
from ..privileged.client import HelperError, PmuUnsupported, PrivilegedClient
from ..privileged.protocol import PMU_IMC, PMU_ROOT
from .base import Draft, Provider

_PMU_IMC = re.compile(PMU_IMC)

# Cómo llama cada generación a lo mismo. Las dos primeras filas son la
# dirección del tráfico; la tercera es ese mismo tráfico visto por origen.
LECTURA = frozenset({"data_reads", "data_read", "cas_count_read"})
ESCRITURA = frozenset({"data_writes", "data_write", "cas_count_write"})
NUCLEOS = frozenset({"ia_requests"})

# La unidad en la que el kernel publica estos contadores. Se comprueba en vez
# de darse por sabida: la escala sola no dice de qué es factor, y multiplicar
# por un mega lo que viniera en otra cosa daría una cifra creíble y falsa.
UNIDAD = "MiB"
BYTES_POR_UNIDAD = 1 << 20

# El aparato bajo el que cuelgan estos sensores: el mismo que ya usa el uso de
# RAM, con su misma clave, para que sean uno y no dos. Escribir «Memoria» a
# pelo los juntaba en español y los partía en inglés, donde el otro se llama
# «Memory». Quién va antes en el árbol no lo decide este nombre sino la clase
# que lleva cada sensor.
DISPOSITIVO = "sensor.mem"


def hay_controlador() -> bool:
    """Si esta máquina publica algún PMU de controlador de memoria.

    Se mira sin privilegios —listar el directorio sí se puede, abrir el
    contador no— y es lo que separa las dos respuestas: «hace falta permiso»
    de «este equipo no lo tiene». Sin esta comprobación, un Ryzen pediría la
    contraseña para no enseñar nada.
    """
    try:
        return any(_PMU_IMC.match(nombre) for nombre in os.listdir(PMU_ROOT))
    except OSError:
        return False


class ImcTraffic(Provider):
    """Bytes por segundo que van y vienen de la RAM, por el PMU del uncore."""

    name = "imc"
    provides = "memory.traffic"

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        self.client = client
        self._previo: Optional[tuple[int, dict[str, dict[str, int]]]] = None
        self._mudo = False          # esta máquina no los tiene: no insistir

    def available(self) -> bool:
        if self._mudo or not hay_controlador():
            return False
        return bool(self.client and self.client.connected())

    def unavailable_reason(self):
        if self.available():
            return None
        if hay_controlador() and not self._mudo:
            return ("memory.traffic", Need.ROOT,
                    _("prov.imc.denied"), _("prov.imc.denied.hint"))
        return ("memory.traffic", Need.HARDWARE,
                _("prov.imc.none"), _("prov.imc.none.hint"))

    def collect(self, draft: Draft) -> None:
        if not self.available():
            return
        try:
            lectura = self.client.imc()       # type: ignore[union-attr]
        except PmuUnsupported:
            # No los tiene. Se deja de preguntar, y el aviso pasa a ser el
            # gris de «esta máquina no lo publica».
            self._mudo = True
            self._previo = None
            return
        except HelperError:
            # Un fallo suelto no da nada por perdido: la tubería puede haberse
            # cortado y el usuario volver a autorizar.
            return

        if lectura.truncated:
            # Faltan canales por abrir, así que la suma saldría corta. Una
            # cifra baja y creíble es peor que ninguna.
            draft.note("memory.traffic", Need.ERROR,
                       _("prov.imc.truncated"), _("prov.imc.truncated.hint"))
            return

        previo, self._previo = self._previo, (lectura.monotonic_ns, lectura.counters)
        draft.capabilities.add("imc")
        if previo is None:
            return                            # la primera solo fija referencia

        reloj_previo, contadores_previos = previo
        ventana = lectura.monotonic_ns - reloj_previo
        if ventana <= 0:
            return

        totales = {"lectura": 0, "escritura": 0, "nucleos": 0}
        visto = {"lectura": False, "escritura": False, "nucleos": False}
        for pmu, eventos in lectura.counters.items():
            anteriores = contadores_previos.get(pmu, {})
            for evento, valor in eventos.items():
                if evento in LECTURA:
                    campo = "lectura"
                elif evento in ESCRITURA:
                    campo = "escritura"
                elif evento in NUCLEOS:
                    campo = "nucleos"
                else:
                    continue
                antes = anteriores.get(evento)
                if antes is None or valor < antes:
                    return          # contador nuevo o reiniciado: esta vuelta no
                if lectura.units.get(pmu, {}).get(evento) != UNIDAD:
                    continue        # unidad desconocida: no se convierte
                escala = lectura.scales.get(pmu, {}).get(evento)
                if not escala:
                    continue
                movido = (valor - antes) * escala * BYTES_POR_UNIDAD
                totales[campo] += int(movido * 1e9 / ventana)
                visto[campo] = True

        if not (visto["lectura"] and visto["escritura"]):
            return
        draft.memory_traffic = MemoryTraffic(
            read_bytes_s=totales["lectura"],
            write_bytes_s=totales["escritura"],
            cpu_bytes_s=totales["nucleos"] if visto["nucleos"] else None,
        )
        draft.resolve("memory.traffic")

        # Y al árbol de sensores, donde lo que aporta es el máximo de la
        # sesión: el pico que ha llegado a mover esta máquina. Aquí sí, al
        # revés que el voltaje del núcleo: eso es el escalón de un P-state y
        # esto es una medida continua, así que su historial significa algo.
        # «Del procesador» no sube: en el árbol, al lado de la lectura y la
        # escritura, se leería como una tercera dirección del tráfico.
        for clave, etiqueta, bytes_s, orden in (
                ("read", "sensor.imc.read", totales["lectura"], 0),
                ("write", "sensor.imc.write", totales["escritura"], 1)):
            draft.sensors.append(Sensor(
                key=f"imc/{clave}",
                chip="uncore_imc",
                device=_(DISPOSITIVO),
                device_kind=DeviceKind.MEMORY,
                label=_(etiqueta),
                kind=SensorKind.BANDWIDTH,
                value=bytes_s / 1e6,
                order=orden,
            ))
