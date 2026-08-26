"""Interpreta los datos de diagnóstico que devuelve un disco.

El ayudante privilegiado pide los bytes y no los mira; el análisis se hace
aquí, sin privilegios, porque analizar formatos binarios es de donde salen la
mayoría de los fallos de memoria y hacerlo como root sería regalar el problema.

Los dos formatos no se parecen:

- **NVMe** tiene un registro fijo y bien definido: cada campo está en su sitio
  y significa lo mismo en cualquier disco. Es de los pocos formatos de esta
  industria en los que uno puede fiarse sin comprobar el fabricante.
- **SATA** tiene una tabla de atributos numerados donde cada fabricante decide
  qué guarda en cuáles. Los números que importan son los mismos desde hace
  veinte años, pero el valor «en crudo» de un atributo puede significar horas
  en un disco y minutos en otro, así que aquí solo se leen los que tienen un
  significado acordado.
"""

from __future__ import annotations

import struct
from typing import Optional

from .model import DiskHealth

# Una «unidad de datos» de NVMe son mil sectores de 512 bytes.
NVME_UNIDAD = 1000 * 512
# Los sectores lógicos con los que SATA cuenta lo escrito.
ATA_SECTOR = 512

CERO_ABSOLUTO = 273.15


class _Nvme:
    """Posiciones del registro de salud de NVMe. Son fijas por especificación."""

    CRITICAL_WARNING = 0
    TEMPERATURE = 1
    AVAILABLE_SPARE = 3
    PERCENTAGE_USED = 5
    DATA_UNITS_READ = 32
    DATA_UNITS_WRITTEN = 48
    POWER_CYCLES = 112
    POWER_ON_HOURS = 128
    UNSAFE_SHUTDOWNS = 144
    MEDIA_ERRORS = 160


# Los atributos de SATA que significan lo mismo en todos los fabricantes.
ATA_HORAS = 9
ATA_CICLOS = 12
ATA_TEMPERATURA = 194
# El de siempre y el que usan Crucial y Micron para lo mismo.
ATA_ESCRITO = (241, 246)
ATA_LEIDO = (242, 247)

# Contadores que caben de sobra en 32 bits y donde varios fabricantes usan los
# dos bytes altos del contador para otra cosa. Un Seagate declaraba 132 billones
# de horas de encendido —quince mil millones de años— porque ahí guarda algo
# suyo; leídos los 32 bits bajos son 13 147 horas, que es un disco de año y
# medio. Es exactamente lo que avisa la cabecera de este módulo, y pasó igual.
ATA_32_BITS = (ATA_HORAS, ATA_CICLOS)

# Ningún disco fabricado ha estado encendido doscientos años. Si sale más, el
# contador no significa lo que se cree y es mejor no enseñarlo.
HORAS_PLAUSIBLES = 200 * 365 * 24
ATA_REASIGNADOS = 5
ATA_PENDIENTES = 197
ATA_INCORREGIBLES = 198
# El desgaste de un SSD lo publican con tres números distintos según la marca;
# los tres guardan lo mismo: cuánta vida queda, de 100 a 0.
ATA_VIDA = (231, 233, 177, 202)


def parse(data: bytes, kind: str) -> Optional[DiskHealth]:
    """Devuelve None si los datos no tienen la pinta que deberían."""
    if kind == "nvme":
        return _parse_nvme(data)
    if kind == "ata":
        return _parse_ata(data)
    return None


def _u128(data: bytes, offset: int) -> Optional[int]:
    """NVMe guarda los contadores en 128 bits. Nadie llega ni de lejos."""
    if offset + 16 > len(data):
        return None
    bajo, alto = struct.unpack_from("<QQ", data, offset)
    return bajo | (alto << 64)


def _parse_nvme(data: bytes) -> Optional[DiskHealth]:
    if len(data) < 512:
        return None

    kelvin = struct.unpack_from("<H", data, _Nvme.TEMPERATURE)[0]
    escrito = _u128(data, _Nvme.DATA_UNITS_WRITTEN)
    leido = _u128(data, _Nvme.DATA_UNITS_READ)
    horas = _u128(data, _Nvme.POWER_ON_HOURS)
    desgaste = data[_Nvme.PERCENTAGE_USED]

    salud = DiskHealth(
        power_on_hours=horas or None,
        power_cycles=_u128(data, _Nvme.POWER_CYCLES) or None,
        written_bytes=escrito * NVME_UNIDAD if escrito else None,
        read_bytes=leido * NVME_UNIDAD if leido else None,
        # Un disco puede pasar del 100 %: sigue funcionando, solo que ya ha
        # gastado toda la vida que el fabricante garantizaba.
        percentage_used=desgaste,
        spare_percent=data[_Nvme.AVAILABLE_SPARE],
        unsafe_shutdowns=_u128(data, _Nvme.UNSAFE_SHUTDOWNS) or None,
        media_errors=_u128(data, _Nvme.MEDIA_ERRORS),
        critical_warning=data[_Nvme.CRITICAL_WARNING],
    )
    # Un registro entero a ceros es un disco que no lo implementa, no uno
    # recién estrenado con cero horas.
    if not any((salud.power_on_hours, salud.written_bytes, kelvin)):
        return None
    return salud


def nvme_temperature(data: bytes) -> Optional[float]:
    """La temperatura del registro, que NVMe da en kelvin."""
    if len(data) < 3:
        return None
    kelvin = struct.unpack_from("<H", data, _Nvme.TEMPERATURE)[0]
    if not kelvin:
        return None
    return round(kelvin - CERO_ABSOLUTO, 1)


def _atributos(data: bytes) -> dict[int, tuple[int, int]]:
    """Los treinta atributos de la tabla: {id: (normalizado, en crudo)}.

    El normalizado va de 100 a 0 y lo interpreta el disco; el crudo es el
    contador de verdad. Cuál de los dos vale depende del atributo.
    """
    encontrados: dict[int, tuple[int, int]] = {}
    for indice in range(30):
        inicio = 2 + indice * 12
        if inicio + 12 > len(data):
            break
        identificador = data[inicio]
        if identificador == 0:                 # entrada vacía
            continue
        normalizado = data[inicio + 3]
        bytes_crudos = data[inicio + 5:inicio + 11]
        ancho = 4 if identificador in ATA_32_BITS else 6
        crudo = int.from_bytes(bytes_crudos[:ancho], "little")
        encontrados[identificador] = (normalizado, crudo)
    return encontrados


def _parse_ata(data: bytes) -> Optional[DiskHealth]:
    if len(data) < 362:
        return None
    tabla = _atributos(data)
    if not tabla:
        return None

    def crudo(*identificadores: int) -> Optional[int]:
        """El primero de estos atributos que el disco publique.

        Varios fabricantes guardan lo mismo en números distintos, así que se
        prueban en orden en vez de dar por hecho uno solo.
        """
        for identificador in identificadores:
            valor = tabla.get(identificador)
            if valor:
                return valor[1]
        return None

    vida = next((tabla[i][0] for i in ATA_VIDA if i in tabla), None)
    escrito = crudo(*ATA_ESCRITO)
    leido = crudo(*ATA_LEIDO)
    horas = crudo(ATA_HORAS)
    if horas is not None and horas > HORAS_PLAUSIBLES:
        horas = None

    return DiskHealth(
        power_on_hours=horas,
        power_cycles=crudo(ATA_CICLOS),
        written_bytes=escrito * ATA_SECTOR if escrito else None,
        read_bytes=leido * ATA_SECTOR if leido else None,
        # El atributo guarda la vida que queda; el modelo la guarda gastada.
        percentage_used=100 - vida if vida is not None else None,
        # Un sector reasignado es un trozo de disco que ya se estropeó y se
        # sustituyó por uno de repuesto. Que haya alguno no es fatal; que
        # crezcan con el tiempo sí.
        media_errors=(crudo(ATA_REASIGNADOS) or 0) + (crudo(ATA_PENDIENTES) or 0)
        + (crudo(ATA_INCORREGIBLES) or 0),
    )


def ata_temperature(data: bytes) -> Optional[float]:
    """La temperatura de la tabla de atributos, si el disco la publica."""
    if len(data) < 362:
        return None
    valor = _atributos(data).get(ATA_TEMPERATURA)
    if not valor:
        return None
    # Los bits altos del crudo llevan mínimos y máximos en muchos discos; la
    # temperatura actual está en el byte bajo.
    grados = valor[1] & 0xFF
    return float(grados) if 0 < grados < 120 else None
