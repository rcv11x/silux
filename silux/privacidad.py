"""Quitarle a una foto del equipo lo que identifica a quien la sacó.

El informe de fallos ya tapa estos campos al escribirlos, porque está pensado
para pegarlo en un issue público. Una captura de pantalla tiene el mismo
problema y no tenía la misma salida: el número de serie de la gráfica y el
nombre del equipo salen en la ventana, y de ahí a un foro o al README de un
repositorio hay un paso.

No se borran los datos: se sustituyen por algo del mismo largo y con la misma
pinta, para que la ventana siga midiendo lo mismo y la captura enseñe cómo se
ve el programa de verdad.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .model import Snapshot

EQUIPO = "equipo"
# De la TEST-NET-1 (RFC 5737) y del bloque que la RFC 7042 reserva para
# documentación. Son direcciones que no encaminan a ninguna parte.
IPV4 = "192.0.2.11"
IPV6 = "2001:db8::11"
MAC = "00:00:5e:00:53:af"
PUERTA = "192.0.2.1"


def _tapar(valor: Optional[str], relleno: str = "0") -> Optional[str]:
    """Mantiene el largo para que nada se recoloque al ocultarlo."""
    if not valor:
        return valor
    return relleno * len(valor)


def anonimizar(snapshot: Snapshot) -> Snapshot:
    """La misma foto sin lo que señala a un equipo concreto."""
    cambios: dict = {}

    if snapshot.system and snapshot.system.hostname:
        cambios["system"] = dataclasses.replace(snapshot.system, hostname=EQUIPO)

    if snapshot.gpus:
        cambios["gpus"] = tuple(
            dataclasses.replace(g, unique_id=_tapar(g.unique_id))
            for g in snapshot.gpus
        )

    if snapshot.network:
        cambios["network"] = tuple(
            dataclasses.replace(
                i,
                mac=MAC if i.mac else None,
                ipv4=IPV4 if i.ipv4 else None,
                ipv6=tuple(IPV6 for _ in i.ipv6),
                gateway=PUERTA if i.gateway else None,
            )
            for i in snapshot.network
        )

    if snapshot.disks:
        cambios["disks"] = tuple(
            dataclasses.replace(d, serial=_tapar(d.serial)) if hasattr(d, "serial")
            else d
            for d in snapshot.disks
        )

    return dataclasses.replace(snapshot, **cambios) if cambios else snapshot
