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
from ..model import Disk, DiskHealth, DiskIo, Need, Partition, PcieLink
from ..privileged.client import HelperError, PrivilegedClient
from .base import Draft, Provider, read_int, read_text
from ..i18n import _
from .. import sysroot

# Cada cuánto se le vuelve a pedir el diagnóstico a un disco, en segundos.
# Las horas y lo escrito cambian despacio, pero la temperatura no.
INTERVALO_SALUD = 30.0

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
        # La temperatura que vino con el diagnóstico, guardada aparte. El
        # disco se reconstruye desde sysfs en cada muestreo: sin guardarla,
        # aparecía un instante al desbloquear y volvía a «—» en la siguiente.
        self._temperatura: dict[str, float] = {}
        # Cuándo se pidió el último diagnóstico de cada disco.
        self._leido_en: dict[str, float] = {}
        # La pone el colector cuando el usuario pulsa el botón. Sin ella el
        # diagnóstico solo se lee si alguien elevó permisos por otra cosa.
        self.requested = False

    def available(self) -> bool:
        return sysroot.ruta(SYS_BLOCK).is_dir()

    def collect(self, draft: Draft) -> None:
        nombres = [p.name for p in sorted(sysroot.ruta(SYS_BLOCK).iterdir())
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
        # A virtual disk's SMART is the hypervisor's invention: nothing to
        # unlock, nothing to read.
        if draft.disks and all(d.kind == "Virtual" for d in draft.disks):
            return
        if not self.client.connected() and self.requested:
            self.requested = False
            try:
                self.client.connect()
            except Exception:                          # noqa: BLE001
                pass
        if not self.client.connected():
            # Sin esta nota el contador de la barra de estado decía «1 dato
            # requiere permisos» cuando eran dos: el detalle de la memoria y
            # el diagnóstico de los discos. A cancelled window keeps it too.
            draft.note(
                "disks.health", Need.ROOT,
                _("prov.disk.health"), _("prov.disk.health.hint"),
                _("what.disks.health"),
            )
            return

        for indice, disco in enumerate(draft.disks):
            nombre = disco.name
            if nombre in self._sin_salud or disco.kind == "Virtual":
                continue
            if self._toca_releer(nombre):
                try:
                    datos, familia = self.client.read_smart(nombre)
                except (HelperError, OSError):
                    datos = None
                salud = (smart_module.parse(
                    datos, familia, vendor=disco.vendor,
                    model=_modelo_ata(sysroot.ruta(SYS_BLOCK) / nombre) or disco.model,
                    firmware=disco.firmware)
                         if datos is not None else None)
                salud = _cuadra_con_lo_ocupado(salud, disco)
                self._leido_en[nombre] = time.monotonic()

                if salud is None:
                    # Un fallo al refrescar no borra lo que ya se sabía: se
                    # deja el dato anterior y se reintenta al rato. Solo se da
                    # el disco por mudo si nunca llegó a contestar.
                    if nombre not in self._salud:
                        self._sin_salud.add(nombre)
                        continue
                else:
                    self._salud[nombre] = salud
                    # De paso, la temperatura de los discos que no la publican
                    # por hwmon: los SATA sin `drivetemp` cargado la traen aquí.
                    grados = (smart_module.nvme_temperature(datos)
                              if familia == "nvme"
                              else smart_module.ata_temperature(datos))
                    if grados is not None:
                        self._temperatura[nombre] = grados

            # Lo que publique hwmon manda, porque se relee en cada muestreo;
            # la del diagnóstico solo rellena el hueco cuando no hay otra.
            if disco.temp_c is None and nombre in self._temperatura:
                disco = dataclasses.replace(disco, temp_c=self._temperatura[nombre])
            draft.disks[indice] = dataclasses.replace(
                disco, health=self._salud[nombre])

    def _toca_releer(self, nombre: str) -> bool:
        """Si hay que volver a pedirle el diagnóstico a este disco.

        Se relee de tanto en tanto en vez de una sola vez porque, aunque las
        horas y los terabytes escritos cambian despacio, la temperatura no:
        leerla una vez al desbloquear y no volver a mirarla dejaba un número
        congelado con la etiqueta «Temperatura», que engaña más que el hueco.

        El intervalo es largo a propósito. Cada lectura es un viaje al proceso
        con privilegios y una orden al disco; hacerlo cada segundo no aportaría
        nada porque el propio disco actualiza esos contadores despacio.
        """
        anterior = self._leido_en.get(nombre)
        return anterior is None or (time.monotonic() - anterior) >= INTERVALO_SALUD

    # -- interno ------------------------------------------------------------

    def _leer(self, nombre: str, montajes: dict[str, tuple[str, str]]) -> Disk:
        base = sysroot.ruta(SYS_BLOCK) / nombre
        sectores = read_int(str(base / "size")) or 0
        rotatorio = read_int(str(base / "queue" / "rotational"))
        transporte = _transporte(base, nombre)

        modelo = _limpio(read_text(str(base / "device" / "model")))
        virtual = es_virtual(nombre, modelo, read_text(str(base / "device" / "vendor")))
        return Disk(
            name=nombre,
            model=modelo,
            vendor=_fabricante(base, modelo),
            firmware=_limpio(read_text(str(base / "device" / "firmware_rev"))
                             or read_text(str(base / "device" / "rev"))),
            serial=_limpio(read_text(str(base / "device" / "serial"))),
            size_bytes=sectores * SECTOR,
            kind=_tipo(rotatorio, transporte, virtual),
            transport=transporte,
            rotational=None if rotatorio is None else bool(rotatorio),
            logical_sector=read_int(str(base / "queue" / "logical_block_size")),
            physical_sector=read_int(str(base / "queue" / "physical_block_size")),
            scheduler=_planificador(base),
            removable=read_int(str(base / "removable")) == 1,
            pci_slot=_ranura(base) if transporte == "nvme" else None,
            link=_enlace(base) if transporte == "nvme" else None,
            temp_c=_temperatura(base),
            discard=_admite_descartes(base),
            discard_mounted=any(nombre_montado.startswith(nombre)
                                for nombre_montado in _con_discard()),
            fstrim_timer=_fstrim_activo(),
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

def _modelo_ata(base: pathlib.Path) -> Optional[str]:
    """The whole model, from the ATA IDENTIFY the kernel publishes.

    sysfs's `model` is the SCSI one, cut to 16 characters («KINGSTON
    SA400S3»), and smartmontools' patterns need the whole one to know the
    unit of the counters. `ata_device/*/id` is the IDENTIFY in hex words,
    readable by anyone; the model is words 27 to 46, two characters each.
    """
    try:
        real = (base / "device").resolve()
    except OSError:
        return None
    puerto = next((p for p in (real, *real.parents) if re.fullmatch(r"ata\d+", p.name)), None)
    if puerto is None:
        return None
    for ruta in sorted(puerto.glob("link*/dev*/ata_device/dev*/id")):
        try:
            palabras = [int(p, 16) for p in (read_text(str(ruta)) or "").split()]
        except ValueError:
            continue
        if len(palabras) >= 47:
            crudo = b"".join(p.to_bytes(2, "big") for p in palabras[27:47])
            return crudo.decode("ascii", "replace").strip() or None
    return None


def _cuadra_con_lo_ocupado(salud: Optional[DiskHealth], disco: Disk) -> Optional[DiskHealth]:
    """No counter shown that says less was ever written than the disk holds.

    A unit nobody knows looks like a believable figure: 33 MB written by a
    disk with 316 GB on it. Whatever the unit, what is stored was written.
    """
    ocupado = disco.used_bytes
    if salud is None or salud.written_bytes is None or not ocupado:
        return salud
    if salud.written_bytes >= ocupado:
        return salud
    return dataclasses.replace(salud, written_bytes=None, read_bytes=None,
                               counters_unit_unknown=True)


def _limpio(texto: Optional[str]) -> Optional[str]:
    """Los campos del disco vienen rellenos de espacios hasta su longitud fija."""
    return " ".join(texto.split()) if texto else None


# Cómo empieza el modelo de cada fabricante y cómo se llama de verdad. Los
# discos no publican quién los hace: el campo `vendor` de sysfs dice «ATA» en
# SATA y nada en NVMe, así que el nombre solo está dentro del modelo.
MARCAS = {
    "samsung": "Samsung", "kingston": "Kingston", "crucial": "Crucial",
    "wdc": "Western Digital", "wd_black": "Western Digital",
    "wd_blue": "Western Digital", "wd_green": "Western Digital",
    "wd_red": "Western Digital", "wd ": "Western Digital",
    "seagate": "Seagate", "st1": "Seagate", "st2": "Seagate",
    "st3": "Seagate", "st4": "Seagate", "st5": "Seagate", "st6": "Seagate",
    "st8": "Seagate", "kioxia": "Kioxia", "toshiba": "Toshiba",
    "intel": "Intel", "micron": "Micron", "sandisk": "SanDisk",
    "adata": "ADATA", "xpg": "ADATA", "corsair": "Corsair",
    "sk hynix": "SK hynix", "hynix": "SK hynix", "patriot": "Patriot",
    "pny": "PNY", "team": "Team Group", "transcend": "Transcend",
    "lexar": "Lexar", "intenso": "Intenso", "netac": "Netac",
    "silicon power": "Silicon Power", "sabrent": "Sabrent",
    "gigabyte": "Gigabyte", "hgst": "HGST", "hitachi": "Hitachi",
    "apacer": "Apacer", "verbatim": "Verbatim", "goodram": "GOODRAM",
    "solidigm": "Solidigm", "phison": "Phison", "ct": "Crucial",
}


def _de_la_marca(modelo: Optional[str]) -> Optional[str]:
    """Quién fabrica un disco, a partir de cómo empieza su modelo."""
    if not modelo:
        return None
    bajo = modelo.strip().lower()
    # Del más largo al más corto: «wd_black» antes que «wd », «sk hynix»
    # antes que «hynix», o el prefijo corto se lleva la coincidencia.
    for prefijo in sorted(MARCAS, key=len, reverse=True):
        if bajo.startswith(prefijo):
            return MARCAS[prefijo]
    return None


def _fabricante(base: pathlib.Path, modelo: Optional[str] = None) -> Optional[str]:
    """El campo `vendor` de un disco SATA dice «ATA», que no es un fabricante."""
    valor = _limpio(read_text(str(base / "device" / "vendor")))
    if valor not in (None, "ATA", "NVME"):
        return valor
    return _de_la_marca(modelo)


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


# The disks a hypervisor makes up: their model, their vendor or their name
# says so. QEMU's say they spin (rotational 1) unless told otherwise, and
# with discard on they admit TRIM: it read «HDD» and «disco SMR».
_VIRTUALES = re.compile(r"^(QEMU |VBOX |VMware|Virtual (disk|HD)|Msft Virtual)", re.I)


def es_virtual(nombre: str, modelo: Optional[str], vendor: Optional[str]) -> bool:
    return (nombre.startswith(("vd", "xvd"))
            or bool(modelo and _VIRTUALES.match(modelo))
            or (vendor or "").strip().upper() in ("QEMU", "VBOX", "VMWARE", "MSFT"))


def _tipo(rotatorio: Optional[int], transporte: Optional[str],
          virtual: bool = False) -> Optional[str]:
    """HDD, SSD, NVMe or Virtual.

    No hay ningún campo que lo diga. «No rotatorio» agrupa a un SSD SATA y a un
    NVMe, que no se parecen en nada ni en velocidad ni en cómo se conectan, así
    que el bus decide entre los dos.
    """
    if virtual:
        return "Virtual"
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
    for _nivel in range(6):
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
    nodo = pathlib.Path(sysroot.ruta("/sys/bus/pci/devices")) / ranura
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
    """Cuánto ocupa un sistema de archivos montado, y cuánto tiene libre.

    Ocupado es lo que no está libre para nadie (f_blocks − f_bfree) y libre lo
    que puede usar cualquiera (f_bavail), como los cuenta `df`. Lo que ext4
    guarda para root (el 5 % por defecto) no es ninguna de las dos cosas: queda
    fuera, con las tablas, y `render.space` lo llama «Reservado». Contado como
    ocupado, un portátil decía «Ocupado 40.6 GB» de unos 17.
    """
    def medir() -> tuple[Optional[int], Optional[int]]:
        try:
            st = os.statvfs(punto)
        except OSError:
            return None, None
        return (st.f_blocks - st.f_bfree) * st.f_frsize, st.f_bavail * st.f_frsize

    # Con un equipo volcado, lo grabado: el punto de montaje es de otra máquina.
    return sysroot.a_traves("statvfs", punto, medir) or (None, None)


def _admite_descartes(base: pathlib.Path) -> Optional[bool]:
    """Si la unidad acepta que le digan qué bloques ya no se usan (TRIM)."""
    maximo = read_int(str(base / "queue" / "discard_max_bytes"))
    return None if maximo is None else maximo > 0


def _con_discard() -> set[str]:
    """Las particiones montadas con la opción `discard`."""
    encontradas: set[str] = set()
    for linea in (read_text(PROC_MOUNTS) or "").splitlines():
        campos = linea.split()
        if len(campos) >= 4 and campos[0].startswith("/dev/") \
                and "discard" in campos[3].replace("=", ",").split(","):
            encontradas.add(campos[0][len("/dev/"):])
    return encontradas


# Dónde deja systemd el enlace de un temporizador activado.
FSTRIM_ACTIVADO = "/etc/systemd/system/timers.target.wants/fstrim.timer"


def _fstrim_activo() -> bool:
    return os.path.lexists(sysroot.ruta(FSTRIM_ACTIVADO))


def _montajes() -> dict[str, tuple[str, str]]:
    """Qué partición está montada dónde y con qué sistema de archivos."""
    encontrados: dict[str, tuple[str, str]] = {}
    try:
        with open(sysroot.ruta(PROC_MOUNTS), encoding="utf-8") as fichero:
            for linea in fichero:
                campos = linea.split()
                if len(campos) < 3:
                    continue
                origen, punto, sistema = campos[0], campos[1], campos[2]
                if sistema in FS_VIRTUALES or not origen.startswith("/dev/"):
                    continue
                # Un /dev/mapper/… acaba en dm-N: se graba, porque /dev no se vuelca.
                nombre = os.path.basename(
                    sysroot.a_traves("realpath", origen, os.path.realpath, origen) or origen)
                # El primer montaje gana: con subvolúmenes de btrfs la misma
                # partición aparece muchas veces y la raíz es la que interesa.
                encontrados.setdefault(nombre, (sistema, _sin_escapes(punto)))
    except OSError:
        return {}
    return encontrados


def _sin_escapes(punto: str) -> str:
    """`/proc/mounts` escapa los espacios como \\040."""
    return punto.replace("\\040", " ").replace("\\011", "\t")
