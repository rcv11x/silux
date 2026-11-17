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
import re
from typing import Optional

from .model import Snapshot

EQUIPO = "equipo"
# De la TEST-NET-1 (RFC 5737) y del bloque que la RFC 7042 reserva para
# documentación. Son direcciones que no encaminan a ninguna parte.
IPV4 = "192.0.2.11"
IPV6 = "2001:db8::11"
MAC = "00:00:5e:00:53:af"
# La de una interfaz que no tiene: el bucle local. No es de nadie.
SIN_MAC = "00:00:00:00:00:00"
PUERTA = "192.0.2.1"
# Lo que se pone en lugar de una interfaz con un nombre elegido por alguien.
INTERFAZ = "interfaz{}"

# Los nombres que pone el sistema y no una persona: los predecibles de systemd
# (`enp6s0`, `wlo1`, `enx001122334455`), los clásicos del kernel y los de las
# herramientas que crean interfaces solas —Docker, libvirt, Tailscale,
# WireGuard con su nombre de ejemplo—. Son los que hacen falta para
# diagnosticar y no dicen nada de nadie. Lo demás lo eligió alguien, y eso es
# justo lo que puede llevar su nombre: un `wg-quick` con el fichero
# `ana_wg0.conf` crea una interfaz `ana_wg0`, y ningún sustituto del hostname
# sabe que «ana» es una persona. Por eso aquí se enumera lo permitido, no lo
# prohibido, y los patrones son estrictos: con `en*` a secas, `enrique-vpn`
# pasaría por una tarjeta de red.
_DEL_SISTEMA = re.compile(r"""
    lo
  | (?:en|wl|ww|ib|sl)(?:x[0-9a-f]{12}|[oPpscvabui]\d+(?:[fdnsupcvi]\d+)*)
  | (?:eth|wlan|wwan|usb|bond|team|dummy|tun|tap|ppp|wg|vmnet|vboxnet|virbr
      |lxcbr|lxdbr|incusbr|podman|docker|tailscale|cni|vxlan|macvtap|can|sit
      |gre|ip6tnl|ipip|br)\d+(?:-nic)?
  | br-[0-9a-f]{12}
  | veth[0-9a-f]+
  | zt[0-9a-z]{8,10}
  | flannel\.\d+
  | cali[0-9a-f]{11}
  | nordlynx
""", re.VERBOSE)


# Los puntos de montaje que pone el sistema y no dicen nada de nadie. Los
# demás llevan el nombre del usuario o la etiqueta que alguien le puso a un
# disco: `/run/media/ana/FOTOS`, `/home/ana/datos`.
_MONTAJES_DEL_SISTEMA = frozenset((
    "/", "/boot", "/boot/efi", "/efi", "/home", "/root", "/usr", "/var",
    "/var/log", "/var/lib", "/var/cache", "/opt", "/srv", "/tmp", "/nix",
    "/gnu", "/snap", "/swap", "/recovery",
))
MONTAJE = "/media/unidad{}"


def de_sistema(nombre: str) -> bool:
    """Si una interfaz se llama como la llama el sistema y no una persona."""
    return bool(_DEL_SISTEMA.fullmatch(nombre))


def _cambiar_nombres(texto: Optional[str], cambios: dict[str, str]) -> Optional[str]:
    """Sustituye cada nombre de interfaz cuando aparece como nombre entero."""
    if not texto:
        return texto
    for viejo, nuevo in cambios.items():
        texto = re.sub(rf"(?<![\w.-]){re.escape(viejo)}(?![\w.-])", nuevo, texto)
    return texto


def _mac_falsa(orden: int) -> str:
    """La dirección de documentación número `orden`, empezando por `MAC`.

    El bloque que reserva la RFC 7042 tiene 256, y se da la vuelta: con más
    tarjetas distintas que eso se repetiría alguna, que es mejor que salirse
    de él.
    """
    prefijo, _sep, ultimo = MAC.rpartition(":")
    return f"{prefijo}:{(int(ultimo, 16) + orden) % 256:02x}"


def _tapar(valor: Optional[str], relleno: str = "0") -> Optional[str]:
    """Mantiene el largo para que nada se recoloque al ocultarlo."""
    if not valor:
        return valor
    return relleno * len(valor)


def _sin_el_equipo(texto: Optional[str], equipo: Optional[str]) -> Optional[str]:
    """Quita el nombre del equipo de donde se haya colado.

    Hace falta porque el nombre no vive solo en su campo: una interfaz de
    Tailscale, de ZeroTier o un puente creado a mano se llaman como la
    máquina, y lo mismo el aparato de sensores que la nombra.

    Se busca como nombre entero y sin distinguir mayúsculas, que es como lo
    trata el propio sistema. Como subcadena exacta se escapaba
    «PORTATIL-ANA» y, con un hostname corto, destrozaba lo que no tenía nada
    que ver: «lan» convertía `wlan0` en `wequipo0`. Entero, un nombre de dos
    letras ya no rompe nada, así que tampoco hay que dejar de taparlo.
    """
    if not texto or not equipo or len(equipo) < 2:
        return texto
    return re.sub(rf"(?<![0-9A-Za-z]){re.escape(equipo)}(?![0-9A-Za-z])",
                  EQUIPO, texto, flags=re.IGNORECASE)


def _limpiar(texto: Optional[str], equipo: Optional[str],
             nombres: dict[str, str]) -> Optional[str]:
    return _sin_el_equipo(_cambiar_nombres(texto, nombres), equipo)


def anonimizar(snapshot: Snapshot) -> Snapshot:
    """La misma foto sin lo que señala a un equipo concreto."""
    cambios: dict = {}
    equipo = snapshot.system.hostname if snapshot.system else None
    # Las interfaces con nombre puesto por alguien, numeradas en el orden en
    # que vienen. El mismo cambio se aplica después a todo lo que las nombra:
    # la red crea una rama del árbol de sensores por interfaz, y un aviso
    # puede citar una por su nombre.
    nombres: dict[str, str] = {}
    for interfaz in snapshot.network:
        if not de_sistema(interfaz.name) and interfaz.name not in nombres:
            nombres[interfaz.name] = INTERFAZ.format(len(nombres) + 1)

    if snapshot.system and snapshot.system.hostname:
        cambios["system"] = dataclasses.replace(snapshot.system, hostname=EQUIPO)

    if snapshot.gpus:
        # El monitor también lleva su número de serie, en el EDID: se enseña
        # en la ficha de cada pantalla.
        cambios["gpus"] = tuple(
            dataclasses.replace(
                g, unique_id=_tapar(g.unique_id),
                displays=tuple(
                    dataclasses.replace(d, monitor=dataclasses.replace(
                        d.monitor, serial=_tapar(d.monitor.serial)))
                    if d.monitor else d
                    for d in g.displays))
            for g in snapshot.gpus
        )

    if snapshot.batteries:
        cambios["batteries"] = tuple(
            dataclasses.replace(b, serial=_tapar(b.serial))
            for b in snapshot.batteries)

    if snapshot.network:
        # Cada dirección física distinta, una falsa distinta: con la misma en
        # todas, dos tarjetas salían con una sola dirección. Y la misma de
        # verdad da la misma falsa, que es lo que pasa con un puente y la
        # tarjeta que tiene debajo.
        macs: dict[str, str] = {}

        def _mac(real: Optional[str]) -> Optional[str]:
            if not real or real == SIN_MAC:
                return real
            return macs.setdefault(real.lower(), _mac_falsa(len(macs)))

        cambios["network"] = tuple(
            dataclasses.replace(
                i,
                # El nombre también: las interfaces virtuales se llaman como
                # la máquina más veces de lo que parece.
                # Las del sistema se quedan como están, aunque el equipo se
                # llame «lo» o «docker»; las demás, por su sustituto.
                name=(i.name if de_sistema(i.name)
                      else _limpiar(i.name, equipo, nombres) or i.name),
                mac=_mac(i.mac),
                ipv4=IPV4 if i.ipv4 else None,
                ipv6=tuple(IPV6 for _direccion in i.ipv6),
                gateway=PUERTA if i.gateway else None,
            )
            for i in snapshot.network
        )

    if snapshot.disks:
        montajes: dict[str, str] = {}

        def _montaje(ruta: Optional[str]) -> Optional[str]:
            if not ruta or ruta in _MONTAJES_DEL_SISTEMA:
                return ruta
            return montajes.setdefault(ruta, MONTAJE.format(len(montajes) + 1))

        cambios["disks"] = tuple(
            dataclasses.replace(
                d, serial=_tapar(d.serial),
                partitions=tuple(dataclasses.replace(p, mountpoint=_montaje(p.mountpoint))
                                 for p in d.partitions))
            for d in snapshot.disks
        )

    if snapshot.sensors and (nombres or equipo):
        sensores = tuple(
            # La clave también, aunque no se pinte: va en la foto y en lo que
            # se exporte de ella. El cambio es el mismo en cada muestreo, así
            # que los mínimos y máximos que cuelgan de ella no se pierden.
            dataclasses.replace(s, key=_limpiar(s.key, equipo, nombres),
                                device=_limpiar(s.device, equipo, nombres),
                                label=_limpiar(s.label, equipo, nombres))
            for s in snapshot.sensors)
        if sensores != snapshot.sensors:
            cambios["sensors"] = sensores

    if snapshot.notes and (nombres or equipo):
        avisos = tuple(
            dataclasses.replace(n, message=_limpiar(n.message, equipo, nombres),
                                hint=_limpiar(n.hint, equipo, nombres))
            for n in snapshot.notes)
        if avisos != snapshot.notes:
            cambios["notes"] = avisos

    return dataclasses.replace(snapshot, **cambios) if cambios else snapshot
