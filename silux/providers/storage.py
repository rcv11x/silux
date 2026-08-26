"""Los discos del equipo, desde /sys/block.

Casi todo se lee sin permisos: el modelo, el tamaño, si gira o no, por dónde
está conectado, sus particiones y cuánto ocupan. Lo único que el kernel reserva
al administrador son los comandos SMART, porque son los mismos que sirven para
borrar un disco; eso vive aparte y llega por el ayudante privilegiado.

Un detalle que cuesta más de lo que parece: **qué tipo de disco es**. No hay
ningún campo que lo diga. Hay que deducirlo de si el kernel lo considera
rotatorio y de por qué bus va conectado, porque un SSD SATA y un NVMe son las
dos cosas «no rotatorias» y no se parecen en nada.

Lo que no se puede saber, y por eso no se enseña, es el formato físico: si un
NVMe es M.2, U.2 o una tarjeta PCIe no está en ninguna parte. Inventarlo a
partir del tipo de conexión acertaría casi siempre y mentiría el resto.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import re
import time
from typing import Iterator, Optional

from .. import smart as smart_module
from ..model import Disk, DiskIo, Partition, PcieLink
from ..privileged.client import HelperError, PrivilegedClient
from .base import Draft, Provider, read_int, read_text

SYS_BLOCK = pathlib.Path("/sys/block")
PROC_MOUNTS = "/proc/mounts"

# Un sector son 512 bytes en las estadísticas del kernel, siempre, aunque el
# disco use sectores de 4 KB por dentro.
SECTOR = 512

# Lo que no es un disco: discos RAM, bucles, dispositivos de arranque de la
# distribución y la memoria comprimida.
VIRTUALES = re.compile(r"^(ram|loop|zram|dm-|md|sr|fd)\d*")

# Sistemas de archivos que no viven en un disco y solo ensucian la lista.
FS_VIRTUALES = {
    "proc", "sysfs", "devtmpfs", "tmpfs", "devpts", "cgroup", "cgroup2",
    "securityfs", "debugfs", "tracefs", "configfs", "fusectl", "pstore",
    "bpf", "mqueue", "hugetlbfs", "autofs", "efivarfs", "nsfs", "overlay",
    "squashfs", "ramfs", "binfmt_misc",
}


class Disks(Provider):
    """Identidad, particiones y ritmo de lectura y escritura de cada unidad."""

    name = "storage"
    provides = "disks"

    def __init__(self, client: Optional[PrivilegedClient] = None) -> None:
        # Contadores de la vuelta anterior, para restar y sacar el ritmo.
        self._previo: dict[str, tuple[float, int, int]] = {}
        self.client = client or PrivilegedClient()
        # El diagnóstico no cambia de un segundo a otro: son horas encendido y
        # terabytes escritos. Se lee una vez y se guarda.
        self._salud: dict[str, object] = {}
        self._sin_salud: set[str] = set()

    def available(self) -> bool:
        return SYS_BLOCK.is_dir()

    def collect(self, draft: Draft) -> None:
        nombres = [p.name for p in sorted(SYS_BLOCK.iterdir())
                   if not VIRTUALES.match(p.name)]
        if not nombres:
            return

        draft.capabilities.add("storage")
        montajes = _montajes()
        draft.disks = [self._leer(nombre, montajes) for nombre in nombres]
        self._diagnostico(draft)

    def _diagnostico(self, draft: Draft) -> None:
        """Pide el SMART de cada disco, si hay permisos para ello.

        Solo cuando el ayudante ya está conectado: conectarlo abre un diálogo
        de autenticación, y hacerlo por su cuenta para enseñar unas horas de
        encendido sería pedirle la contraseña a alguien que no la pidió. Quien
        eleve permisos para ver la memoria se lleva esto de propina.
        """
        if not self.client.connected():
            return

        for indice, disco in enumerate(draft.disks):
            nombre = disco.name
            if nombre in self._sin_salud:
                continue
            if nombre not in self._salud:
                try:
                    datos, familia = self.client.read_smart(nombre)
                except (HelperError, OSError):
                    self._sin_salud.add(nombre)
                    continue
                salud = smart_module.parse(datos, familia)
                if salud is None:
                    self._sin_salud.add(nombre)
                    continue
                self._salud[nombre] = salud
                # De paso, la temperatura de los discos que no la publican por
                # hwmon: los SATA sin `drivetemp` cargado sí la traen aquí.
                if disco.temp_c is None:
                    grados = (smart_module.nvme_temperature(datos)
                              if familia == "nvme"
                              else smart_module.ata_temperature(datos))
                    if grados is not None:
                        draft.disks[indice] = dataclasses.replace(disco, temp_c=grados)
                        disco = draft.disks[indice]
            draft.disks[indice] = dataclasses.replace(
                disco, health=self._salud[nombre])

    # -- interno ------------------------------------------------------------

    def _leer(self, nombre: str, montajes: dict[str, tuple[str, str]]) -> Disk:
        base = SYS_BLOCK / nombre
        sectores = read_int(str(base / "size")) or 0
        rotatorio = read_int(str(base / "queue" / "rotational"))
        transporte = _transporte(base, nombre)

        return Disk(
            name=nombre,
            model=_limpio(read_text(str(base / "device" / "model"))),
            vendor=_fabricante(base),
            firmware=_limpio(read_text(str(base / "device" / "firmware_rev"))
                             or read_text(str(base / "device" / "rev"))),
            serial=_limpio(read_text(str(base / "device" / "serial"))),
            size_bytes=sectores * SECTOR,
            kind=_tipo(rotatorio, transporte),
            transport=transporte,
            rotational=None if rotatorio is None else bool(rotatorio),
            logical_sector=read_int(str(base / "queue" / "logical_block_size")),
            physical_sector=read_int(str(base / "queue" / "physical_block_size")),
            scheduler=_planificador(base),
            removable=read_int(str(base / "removable")) == 1,
            pci_slot=_ranura(base) if transporte == "nvme" else None,
            link=_enlace(base) if transporte == "nvme" else None,
            temp_c=_temperatura(base),
            partitions=tuple(_particiones(base, nombre, montajes)),
            io=self._trafico(nombre, base),
        )

    def _trafico(self, nombre: str, base: pathlib.Path) -> DiskIo:
        crudo = read_text(str(base / "stat"))
        if not crudo:
            return DiskIo()
        campos = crudo.split()
        if len(campos) < 8:
            return DiskIo()

        leidos = int(campos[2]) * SECTOR
        escritos = int(campos[6]) * SECTOR
        ahora = time.monotonic()
        lectura = escritura = None

        anterior = self._previo.get(nombre)
        if anterior is not None:
            antes, rx, tx = anterior
            transcurrido = ahora - antes
            # Los contadores se reinician al reconectar un disco externo; un
            # delta negativo es eso, no un ritmo negativo.
            if transcurrido > 0 and leidos >= rx and escritos >= tx:
                lectura = (leidos - rx) / transcurrido
                escritura = (escritos - tx) / transcurrido
        self._previo[nombre] = (ahora, leidos, escritos)

        return DiskIo(
            read_bytes=leidos, write_bytes=escritos,
            read_ops=int(campos[0]), write_ops=int(campos[4]),
            read_rate_bps=lectura, write_rate_bps=escritura,
        )


# -- lectura suelta ----------------------------------------------------------

def _limpio(texto: Optional[str]) -> Optional[str]:
    """Los campos del disco vienen rellenos de espacios hasta su longitud fija."""
    return " ".join(texto.split()) if texto else None


def _fabricante(base: pathlib.Path) -> Optional[str]:
    """El campo `vendor` de un disco SATA dice «ATA», que no es un fabricante."""
    valor = _limpio(read_text(str(base / "device" / "vendor")))
    return None if valor in (None, "ATA", "NVME") else valor


def _transporte(base: pathlib.Path, nombre: str) -> Optional[str]:
    if nombre.startswith("nvme"):
        return "nvme"
    try:
        ruta = str((base / "device").resolve())
    except OSError:
        return None
    for marca, nombre_bus in (("/usb", "usb"), ("/ata", "sata"),
                              ("/nvme", "nvme"), ("/mmc", "mmc")):
        if marca in ruta:
            return nombre_bus
    return None


def _tipo(rotatorio: Optional[int], transporte: Optional[str]) -> Optional[str]:
    """HDD, SSD o NVMe.

    No hay ningún campo que lo diga. «No rotatorio» agrupa a un SSD SATA y a un
    NVMe, que no se parecen en nada ni en velocidad ni en cómo se conectan, así
    que el bus decide entre los dos.
    """
    if rotatorio is None:
        return None
    if rotatorio:
        return "HDD"
    return "NVMe" if transporte == "nvme" else "SSD"


def _planificador(base: pathlib.Path) -> Optional[str]:
    """El activo va entre corchetes: «none mq-deadline kyber [bfq]»."""
    crudo = read_text(str(base / "queue" / "scheduler"))
    if not crudo:
        return None
    encaje = re.search(r"\[([^\]]+)\]", crudo)
    return encaje.group(1) if encaje else None


def _ranura(base: pathlib.Path) -> Optional[str]:
    try:
        actual = (base / "device").resolve()
    except OSError:
        return None
    for _ in range(6):
        if re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]", actual.name):
            return actual.name
        if actual.parent == actual:
            break
        actual = actual.parent
    return None


def _enlace(base: pathlib.Path) -> Optional[PcieLink]:
    """El enlace PCIe de un NVMe, con la misma cuenta que el de una gráfica.

    Solo para NVMe. Un disco SATA no negocia PCIe: quien lo hace es su
    controladora, que además comparte con los otros discos del mismo cable.
    Subir por el árbol hasta encontrar una dirección PCI daba el enlace del
    controlador del chipset y lo enseñaba como si fuera del disco.
    """
    ranura = _ranura(base)
    if not ranura:
        return None
    nodo = pathlib.Path("/sys/bus/pci/devices") / ranura
    if not nodo.is_dir():
        return None

    def velocidad(campo: str) -> Optional[float]:
        crudo = read_text(str(nodo / campo))
        encaje = re.search(r"([\d.]+)\s*GT/s", crudo or "")
        return float(encaje.group(1)) if encaje else None

    actual = velocidad("current_link_speed")
    if actual is None:
        return None
    return PcieLink(
        current_speed_gts=actual,
        current_width=read_int(str(nodo / "current_link_width")),
        max_speed_gts=velocidad("max_link_speed"),
        max_width=read_int(str(nodo / "max_link_width")),
    )


def _temperatura(base: pathlib.Path) -> Optional[float]:
    """La temperatura del disco, si algún driver la publica.

    Cada tipo la cuelga en un sitio: los NVMe la traen de serie bajo su propio
    controlador, y los SATA solo aparecen si está cargado `drivetemp`, que no
    lo está por omisión en casi ninguna distribución. Así que se busca por el
    árbol en vez de dar por hecho una ruta.
    """
    try:
        raiz = (base / "device").resolve()
    except OSError:
        return None
    for nivel in range(4):
        for hwmon in sorted(raiz.glob("hwmon*")) + sorted(raiz.glob("hwmon/hwmon*")):
            milesimas = read_int(str(hwmon / "temp1_input"))
            if milesimas is not None:
                return round(milesimas / 1000, 1)
        if raiz.parent == raiz:
            break
        raiz = raiz.parent
    return None


def _particiones(base: pathlib.Path, disco: str,
                 montajes: dict[str, tuple[str, str]]) -> Iterator[Partition]:
    for entrada in sorted(base.iterdir()):
        if not entrada.name.startswith(disco) or not (entrada / "partition").exists():
            continue
        sectores = read_int(str(entrada / "size")) or 0
        sistema, punto = montajes.get(entrada.name, (None, None))
        usados = libres = None
        if punto:
            usados, libres = _ocupacion(punto)
        yield Partition(
            name=entrada.name,
            size_bytes=sectores * SECTOR,
            filesystem=sistema,
            mountpoint=punto,
            used_bytes=usados,
            free_bytes=libres,
        )


def _ocupacion(punto: str) -> tuple[Optional[int], Optional[int]]:
    """Cuánto ocupa un sistema de archivos montado.

    Se descuenta lo reservado para el administrador, que en ext4 son el 5 % del
    disco: contarlo como libre haría que la suma no cuadrara con lo que enseña
    cualquier otra herramienta.
    """
    try:
        st = os.statvfs(punto)
    except OSError:
        return None, None
    total = st.f_blocks * st.f_frsize
    libre = st.f_bavail * st.f_frsize
    return total - libre, libre


def _montajes() -> dict[str, tuple[str, str]]:
    """Qué partición está montada dónde y con qué sistema de archivos."""
    encontrados: dict[str, tuple[str, str]] = {}
    try:
        with open(PROC_MOUNTS, encoding="utf-8") as fichero:
            for linea in fichero:
                campos = linea.split()
                if len(campos) < 3:
                    continue
                origen, punto, sistema = campos[0], campos[1], campos[2]
                if sistema in FS_VIRTUALES or not origen.startswith("/dev/"):
                    continue
                nombre = os.path.basename(os.path.realpath(origen))
                # El primer montaje gana: con subvolúmenes de btrfs la misma
                # partición aparece muchas veces y la raíz es la que interesa.
                encontrados.setdefault(nombre, (sistema, _sin_escapes(punto)))
    except OSError:
        return {}
    return encontrados


def _sin_escapes(punto: str) -> str:
    """`/proc/mounts` escapa los espacios como \\040."""
    return punto.replace("\\040", " ").replace("\\011", "\t")
