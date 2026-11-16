#!/usr/bin/env python3
"""Vuelca lo que leen los proveedores de este equipo, para la suite.

    python3 tools/volcar_equipo.py NOMBRE

Deja en `tests/fixtures/equipos/NOMBRE/` una copia de lo que el Collector lee
de `/sys`, `/proc` y `/etc` —y nada más—, y en `grabado.json` lo que no sale
de un archivo: la CPUID de cada tipo de núcleo, los ioctl de la gráfica, lo que
contestan OpenGL y Vulkan, el espacio de cada montaje, las direcciones. Con
`SILUX_SYSROOT` apuntando ahí, el Collector da este equipo en cualquier otro.

Solo lee. No pide permisos ni usa el ayudante: el volcado es el de un equipo
sin permisos, que es como lo abre la mayoría de la gente.

**Qué se copia lo decide el propio Collector**, no una lista escrita aquí: se
ejecuta de verdad mientras se apunta cada archivo que abre, cada directorio
que recorre, cada `stat` y cada enlace. Una lista a mano se quedaría vieja el
día que un proveedor leyera un archivo nuevo, y el volcado diría que el equipo
no lo tiene.

**Lo que identifica a alguien se sustituye** por lo mismo que pone
`privacidad.anonimizar` —el nombre del equipo, las direcciones, los números de
serie, las interfaces con nombre puesto a mano, los puntos de montaje que no
son del sistema, el usuario—, y antes de dar el volcado por bueno se
comprueban dos cosas: que `privacidad.anonimizar` no encuentra nada más que
tapar en la foto que sale de él, y que ninguno de los identificadores de esta
máquina que busca `tools/comprobar_privacidad.py` aparece en ningún byte. Si
algo falla, no se deja nada escrito.
"""

from __future__ import annotations

import argparse
import builtins
import contextlib
import dataclasses
import getpass
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from silux import privacidad, sysroot  # noqa: E402

DESTINO = RAIZ / "tests" / "fixtures" / "equipos"
VIGILADO = ("/sys/", "/proc/", "/etc/")
# Un archivo de sysfs o de procfs de más de esto no es lo que se lee para
# describir un equipo; copiarlo solo engordaría el repositorio.
TOPE = 512 * 1024
MANIFIESTO = "manifiesto.json"

# Archivos cuyo contenido identifica a una pieza concreta y no dice nada del
# modelo: se cambian por ceros del mismo largo.
SERIALES = {"serial", "serial_number", "wwid", "vpd_pg80", "vpd_pg83",
            "unique_id", "product_uuid", "product_serial", "board_serial",
            "chassis_serial", "uuid", "eui", "nguid", "perm_addr"}
DIRECCIONES = {"address", "perm_address"}
MAC = re.compile(r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I)
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)


# -- qué lee el Collector ------------------------------------------------------

def _vigilado(camino) -> str | None:
    try:
        texto = os.fspath(camino)
    except TypeError:
        return None
    if isinstance(texto, bytes):
        texto = texto.decode(errors="replace")
    return texto if texto.startswith(VIGILADO) else None


@contextlib.contextmanager
def _apuntando():
    """Apunta qué toca el Collector: archivos, directorios, `stat` y enlaces."""
    leidos: set[str] = set()
    listados: set[str] = set()
    mirados: set[str] = set()

    def apuntar(conjunto, funcion):
        def envuelta(camino, *args, **kwargs):
            if (texto := _vigilado(camino)) is not None:
                conjunto.add(texto)
            return funcion(camino, *args, **kwargs)
        return envuelta

    parches = {
        (builtins, "open"): apuntar(leidos, builtins.open),
        (io, "open"): apuntar(leidos, io.open),
        (os, "listdir"): apuntar(listados, os.listdir),
        (os, "scandir"): apuntar(listados, os.scandir),
        (os, "stat"): apuntar(mirados, os.stat),
        (os, "lstat"): apuntar(mirados, os.lstat),
        (os, "readlink"): apuntar(mirados, os.readlink),
    }
    originales = {clave: getattr(*clave) for clave in parches}
    try:
        for (modulo, nombre), funcion in parches.items():
            setattr(modulo, nombre, funcion)
        yield leidos, listados, mirados
    finally:
        for (modulo, nombre), funcion in originales.items():
            setattr(modulo, nombre, funcion)


def _recoger():
    """Ejecuta el Collector de verdad, apuntando y grabando lo que pregunta."""
    from silux.collector import Collector

    sysroot.empezar_a_grabar()
    with _apuntando() as (leidos, listados, mirados):
        recolector = Collector()
        try:
            recolector.snapshot()
            recolector.snapshot()
        finally:
            recolector.close()
    return leidos, listados, mirados, sysroot.lo_grabado()


# -- copiar ---------------------------------------------------------------------

class _Copia:
    """Reproduce caminos del sistema dentro del volcado, con sus enlaces."""

    def __init__(self, destino: pathlib.Path):
        self.destino = destino
        self.ilegibles: set[str] = set()

    def _dentro(self, camino: str) -> pathlib.Path:
        return self.destino / camino.lstrip("/")

    def _enlace(self, camino: str) -> None:
        dentro = self._dentro(camino)
        if dentro.is_symlink() or dentro.exists():
            return
        try:
            destino = os.readlink(camino)
        except OSError:
            # `/proc/1/exe` sin permisos: se deja fuera, y quien lo lea recibe
            # un error igual que en el equipo de verdad.
            return
        dentro.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(destino, dentro)

    def camino(self, camino: str) -> str | None:
        """Recrea cada enlace del camino y devuelve dónde está de verdad."""
        actual = "/"
        for trozo in pathlib.PurePosixPath(camino).parts[1:]:
            siguiente = os.path.join(actual, trozo)
            vueltas = 0
            while os.path.islink(siguiente) and vueltas < 40:
                self._enlace(siguiente)
                try:
                    destino = os.readlink(siguiente)
                except OSError:
                    return None
                siguiente = os.path.normpath(os.path.join(os.path.dirname(siguiente), destino))
                vueltas += 1
            if not os.path.lexists(siguiente):
                return None
            if not siguiente.startswith(VIGILADO) and siguiente not in ("/sys", "/proc", "/etc"):
                # Un enlace que sale del sistema (`/proc/1/exe`): basta con él.
                return None
            actual = siguiente
        return actual

    def archivo(self, camino: str) -> None:
        real = self.camino(camino)
        if real is None:
            self._de_fuera(camino)
            return
        dentro = self._dentro(real)
        if os.path.isdir(real):
            dentro.mkdir(parents=True, exist_ok=True)
            return
        if dentro.exists():
            return
        dentro.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(real, "rb") as origen:
                datos = origen.read(TOPE)
        except PermissionError:
            # Se deja el archivo y se apunta: al montar el volcado se le
            # quitan los permisos para que leerlo dé el mismo error que aquí.
            dentro.write_bytes(b"")
            self.ilegibles.add(real)
            return
        except OSError:
            return
        dentro.write_bytes(datos)

    def _de_fuera(self, camino: str) -> None:
        """Un enlace que sale de lo volcado y acaba en un archivo.

        `/etc/os-release` apunta a `../usr/lib/os-release`. Copiar `/usr` no
        tiene sentido, así que en el sitio del enlace va el archivo.
        """
        real = os.path.realpath(camino)
        if real.startswith(VIGILADO) or not os.path.isfile(real):
            return
        try:
            with open(real, "rb") as origen:
                datos = origen.read(TOPE)
        except OSError:
            return
        dentro = self._dentro(camino)
        if dentro.is_symlink():
            dentro.unlink()
        dentro.parent.mkdir(parents=True, exist_ok=True)
        dentro.write_bytes(datos)

    def directorio(self, camino: str) -> None:
        real = self.camino(camino)
        if real is None or not os.path.isdir(real):
            return
        dentro = self._dentro(real)
        dentro.mkdir(parents=True, exist_ok=True)
        try:
            entradas = os.listdir(real)
        except OSError:
            return
        for nombre in entradas:
            hijo = os.path.join(real, nombre)
            if os.path.islink(hijo):
                self._enlace(hijo)
            elif os.path.isdir(hijo):
                (dentro / nombre).mkdir(exist_ok=True)
            # Los archivos de un directorio recorrido y no leídos no se
            # copian: no los mira nadie, y en /proc serían miles.


# -- anonimizar -----------------------------------------------------------------

def _texto(ruta: pathlib.Path) -> str | None:
    try:
        datos = ruta.read_bytes()
    except OSError:
        return None
    if b"\x00" in datos:
        return None
    try:
        return datos.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _edid_sin_serie(datos: bytes) -> bytes:
    """El EDID con el número de serie a ceros y la suma de control al día."""
    if len(datos) < 128 or datos[:8] != b"\x00\xff\xff\xff\xff\xff\xff\x00":
        return datos
    bloque = bytearray(datos[:128])
    bloque[12:16] = b"\x00\x00\x00\x00"
    for inicio in range(54, 126, 18):
        if bloque[inicio:inicio + 3] == b"\x00\x00\x00" and bloque[inicio + 3] == 0xFF:
            bloque[inicio + 5:inicio + 18] = b"0" * 13
    bloque[127] = (-sum(bloque[:127])) % 256
    return bytes(bloque) + datos[128:]


# Dónde lleva el SPD el número de serie del módulo, según el tipo de memoria
# (byte 2). Ninguna suma de control lo cubre: la de DDR4 acaba en el 253 y la
# de DDR5 en el 509. silux no lo decodifica, y por eso ni la foto ni el
# comprobador lo verían: se borra aquí, por posición.
SERIE_SPD = {0x0C: (325, 329), 0x12: (517, 521)}


def _spd_sin_serie(datos: bytes) -> tuple[bytes, bytes]:
    """El SPD con el número de serie a ceros, y el número que se quitó."""
    if len(datos) < 3 or datos[2] not in SERIE_SPD:
        return datos, b""
    inicio, fin = SERIE_SPD[datos[2]]
    if len(datos) < fin:
        return datos, b""
    return datos[:inicio] + bytes(fin - inicio) + datos[fin:], datos[inicio:fin]


def _ipv4_hex(ip: str) -> str:
    """Una dirección como la escribe /proc/net/route: hexadecimal al revés."""
    return "".join(f"{int(x):02X}" for x in reversed(ip.split(".")))


class _Anonimizador:
    def __init__(self, destino: pathlib.Path, grabado: dict):
        self.destino = destino
        self.grabado = grabado
        self.secretos: set[str] = set()
        # Lo quitado de un archivo binario, que no se busca como texto.
        self.crudos: set[bytes] = set()
        self.equipo = (pathlib.Path("/proc/sys/kernel/hostname").read_text().strip()
                       if os.path.exists("/proc/sys/kernel/hostname") else "")
        self.usuario = getpass.getuser()
        self.casa = str(pathlib.Path.home())
        self.interfaces = self._interfaces()
        self.montajes: dict[str, str] = {}

    def _interfaces(self) -> dict[str, str]:
        nombres = {}
        red = self.destino / "sys" / "class" / "net"
        for entrada in sorted(red.iterdir()) if red.is_dir() else ():
            if not privacidad.de_sistema(entrada.name):
                nombres[entrada.name] = privacidad.INTERFAZ.format(len(nombres) + 1)
        return nombres

    def _cambiar_texto(self, texto: str) -> str:
        for viejo, nuevo in self.interfaces.items():
            texto = re.sub(rf"(?<![\w.-]){re.escape(viejo)}(?![\w.-])", nuevo, texto)
        texto = privacidad._sin_el_equipo(texto, self.equipo) or texto
        texto = texto.replace(self.casa, "/home/usuario")
        if len(self.usuario) >= 3:
            texto = re.sub(rf"(?<![\w.-]){re.escape(self.usuario)}(?![\w.-])", "usuario", texto)
        texto = MAC.sub(lambda m: m.group(0) if m.group(0) in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff")
                        else privacidad.MAC, texto)
        texto = UUID.sub("00000000-0000-0000-0000-000000000000", texto)
        return texto

    def _montaje(self, punto: str) -> str:
        if punto in privacidad._MONTAJES_DEL_SISTEMA:
            return punto
        return self.montajes.setdefault(punto, privacidad.MONTAJE.format(len(self.montajes) + 1))

    def contenidos(self) -> None:
        for ruta in sorted(self.destino.rglob("*")):
            if ruta.is_symlink() or not ruta.is_file():
                continue
            nombre = ruta.name
            relativo = "/" + str(ruta.relative_to(self.destino))
            datos = ruta.read_bytes()
            if nombre in SERIALES and datos.strip():
                self.secretos.add(datos.strip().decode(errors="replace"))
                ruta.write_bytes(re.sub(rb"[^\n\x00]", b"0", datos))
                continue
            if nombre == "edid":
                if len(datos) >= 16 and any(datos[12:16]):
                    self.crudos.add(datos[12:16])
                ruta.write_bytes(_edid_sin_serie(datos))
                continue
            if nombre == "eeprom":
                limpio, serie = _spd_sin_serie(datos)
                if any(serie):
                    self.crudos.add(serie)
                ruta.write_bytes(limpio)
                continue
            if nombre in DIRECCIONES and "/net/" in relativo:
                if datos.strip() and datos.strip() not in (b"00:00:00:00:00:00",):
                    self.secretos.add(datos.strip().decode(errors="replace"))
                    ruta.write_text(privacidad.MAC + "\n")
                continue
            if relativo == "/proc/sys/kernel/hostname":
                ruta.write_text(privacidad.EQUIPO + "\n")
                continue
            # /proc/net es un enlace a self/net: el archivo de verdad acaba en
            # /proc/<pid>/net/, así que se reconoce por cómo termina.
            if relativo.startswith("/proc/") and relativo.endswith("/net/route"):
                ruta.write_text(self._ruta_de_red(datos.decode()))
                continue
            if relativo.startswith("/proc/") and relativo.endswith("/net/if_inet6"):
                ruta.write_text(self._ipv6(datos.decode()))
                continue
            if relativo.startswith("/proc/") and relativo.endswith("/mounts"):
                ruta.write_text(self._cambiar_texto(self._mounts(datos.decode())))
                continue
            texto = _texto(ruta)
            if texto is not None:
                cambiado = self._cambiar_texto(texto)
                if cambiado != texto:
                    ruta.write_text(cambiado)

    def _ruta_de_red(self, texto: str) -> str:
        lineas = texto.splitlines()
        salida = lineas[:1]
        for linea in lineas[1:]:
            campos = linea.split("\t")
            if len(campos) > 2:
                if campos[1] != "00000000":
                    campos[1] = _ipv4_hex("192.0.2.0")
                if campos[2] != "00000000":
                    self.secretos.add(campos[2])
                    campos[2] = _ipv4_hex(privacidad.PUERTA)
            salida.append("\t".join(campos))
        return "\n".join(salida) + "\n"

    def _ipv6(self, texto: str) -> str:
        # privacidad.IPV6, 2001:db8::11, en los 32 dígitos de /proc/net/if_inet6.
        sustituta = "20010db8" + "0" * 20 + "0011"
        salida = []
        for linea in texto.splitlines():
            campos = linea.split()
            if campos and campos[0] != "0" * 31 + "1":
                self.secretos.add(campos[0])
                linea = linea.replace(campos[0], sustituta, 1)
            salida.append(linea)
        return "\n".join(salida) + "\n"

    def _mounts(self, texto: str) -> str:
        """Los montajes de los discos, con los puntos que puso alguien tapados.

        Solo se quedan las líneas de un dispositivo, que son las que lee el
        proveedor. Las demás no describen el equipo sino la sesión: el
        AppImage abierto, los contenedores, la carpeta del usuario.
        """
        salida = []
        for linea in texto.splitlines():
            campos = linea.split(" ")
            if not campos[0].startswith("/dev/"):
                continue
            if len(campos) > 1:
                punto = campos[1].replace("\\040", " ")
                nuevo = self._montaje(punto)
                if nuevo != punto:
                    campos[1] = nuevo
            salida.append(" ".join(campos))
        return "\n".join(salida) + "\n"

    def nombres(self) -> None:
        """Las interfaces con nombre propio, también en carpetas y enlaces."""
        if not self.interfaces:
            return
        for ruta in sorted(self.destino.rglob("*"), key=lambda r: -len(r.parts)):
            if ruta.is_symlink():
                destino = os.readlink(ruta)
                nuevo = self._cambiar_texto(destino)
                if nuevo != destino:
                    ruta.unlink()
                    os.symlink(nuevo, ruta)
            if ruta.name in self.interfaces:
                ruta.rename(ruta.with_name(self.interfaces[ruta.name]))

    def grabado_limpio(self) -> dict:
        limpio = json.loads(self._cambiar_texto(json.dumps(self.grabado, ensure_ascii=False)))
        for clave in list(limpio.get("ioctl_red", {})):
            valor = limpio["ioctl_red"][clave]
            nombre, _sep, codigo = clave.partition(":")
            if valor and codigo == "0x8915" and not valor.startswith("127."):
                self.secretos.add(valor)
                limpio["ioctl_red"][clave] = privacidad.IPV4
        if "statvfs" in limpio:
            limpio["statvfs"] = {self._montaje(p): v for p, v in limpio["statvfs"].items()}
        entorno = limpio.get("plataforma", {}).get("uname")
        if isinstance(entorno, dict) and entorno.get("node"):
            entorno["node"] = privacidad.EQUIPO
        return limpio


# -- comprobar ------------------------------------------------------------------

def _comprobador():
    ruta = RAIZ / "tools" / "comprobar_privacidad.py"
    spec = importlib.util.spec_from_file_location("comprobar_privacidad", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def comprobar(destino: pathlib.Path, secretos: set[str],
              crudos: frozenset[bytes] = frozenset()) -> list[str]:
    """Lo que delata a esta máquina dentro del volcado. Vacío si nada."""
    buscados = {d.encode(): q for d, q in _comprobador()._de_esta_maquina().items() if d}
    buscados |= {s.encode(): "dato sustituido" for s in secretos if s and len(s) >= 4}
    buscados |= {c: "número de serie de una pieza" for c in crudos if any(c)}
    hallazgos = []
    for ruta in sorted(destino.rglob("*")):
        if ruta.is_symlink():
            contenido = os.readlink(ruta).encode()
        elif ruta.is_file():
            contenido = ruta.read_bytes()
        else:
            contenido = b""
        texto_ruta = str(ruta.relative_to(destino)).encode()
        for crudo, que in buscados.items():
            if crudo in contenido or crudo in texto_ruta:
                hallazgos.append(f"{ruta.relative_to(destino)}: {que}")
    return hallazgos


@contextlib.contextmanager
def montado(carpeta: pathlib.Path):
    """El volcado listo para leer: una copia con los ilegibles sin permiso."""
    with tempfile.TemporaryDirectory(prefix="silux-equipo-") as tmp:
        copia = pathlib.Path(tmp) / "raiz"
        shutil.copytree(carpeta, copia, symlinks=True)
        manifiesto = json.loads((copia / MANIFIESTO).read_text())
        for vacio in manifiesto.get("vacios", []):
            (copia / vacio.lstrip("/")).mkdir(parents=True, exist_ok=True)
        for ilegible in manifiesto.get("ilegibles", []):
            camino = copia / ilegible.lstrip("/")
            if camino.exists():
                camino.chmod(0)
        anterior = os.environ.get(sysroot.VARIABLE)
        os.environ[sysroot.VARIABLE] = str(copia)
        sysroot.olvidar()
        try:
            yield copia
        finally:
            for ilegible in manifiesto.get("ilegibles", []):
                camino = copia / ilegible.lstrip("/")
                if camino.exists():
                    camino.chmod(0o600)
            if anterior is None:
                os.environ.pop(sysroot.VARIABLE, None)
            else:
                os.environ[sysroot.VARIABLE] = anterior
            sysroot.olvidar()


def foto_de(carpeta: pathlib.Path):
    """La foto que da el Collector leyendo el volcado."""
    from silux.collector import Collector

    with montado(carpeta):
        recolector = Collector()
        try:
            recolector.snapshot()
            return recolector.snapshot()
        finally:
            recolector.close()


# -- principal ------------------------------------------------------------------

def volcar(nombre: str, destino_base: pathlib.Path = DESTINO) -> pathlib.Path:
    destino = destino_base / nombre
    if destino.exists():
        raise SystemExit(f"ya existe {destino}: bórralo antes para volcar otra vez")
    if sysroot.activo():
        raise SystemExit(f"{sysroot.VARIABLE} está puesta: esto vuelca el equipo de verdad")

    leidos, listados, mirados, grabado = _recoger()
    with tempfile.TemporaryDirectory(prefix="silux-volcado-") as tmp:
        trabajo = pathlib.Path(tmp) / nombre
        trabajo.mkdir()
        copia = _Copia(trabajo)
        for camino in sorted(listados):
            copia.directorio(camino)
        for camino in sorted(leidos):
            copia.archivo(camino)
        for camino in sorted(mirados - leidos - listados):
            # Un `exists()` o un `is_dir()` que salió que sí: que siga saliendo.
            if os.path.lexists(camino):
                copia.archivo(camino) if not os.path.isdir(camino) else copia.directorio(camino)

        limpio = _Anonimizador(trabajo, grabado)
        limpio.contenidos()
        limpio.nombres()
        (trabajo / sysroot.GRABADO).write_text(
            json.dumps(limpio.grabado_limpio(), ensure_ascii=False, indent=1, sort_keys=True) + "\n")

        # Git no guarda directorios vacíos, y algunos cuentan: los procesos de
        # /proc, o un /sys/firmware/efi que solo se mira si existe. Se apuntan
        # y se recrean al montar.
        vacios = sorted("/" + str(d.relative_to(trabajo)) for d in trabajo.rglob("*")
                        if d.is_dir() and not d.is_symlink() and not any(d.iterdir()))
        (trabajo / MANIFIESTO).write_text(json.dumps({
            "herramienta": 1,
            "vacios": vacios,
            "ilegibles": sorted(limpio._cambiar_texto(c) for c in copia.ilegibles),
            "sin_grabar": [
                "NVML (NVIDIA propietaria)",
                "todo lo que lee el ayudante privilegiado",
                "el uso de cada hilo: sale de restar dos lecturas de /proc/stat, "
                "y el volcado guarda una",
                "el consumo (RAPL): sale de restar dos lecturas del contador de "
                "energía, y el volcado guarda una",
            ],
        }, ensure_ascii=False, indent=1) + "\n")

        foto = foto_de(trabajo)
        if quedan := _lo_que_anonimizar_taparia(foto):
            raise SystemExit("anonimizar todavía encuentra qué tapar: "
                             + "; ".join(quedan[:10]) + ". No se escribe nada.")
        if hallazgos := comprobar(trabajo, limpio.secretos, frozenset(limpio.crudos)):
            raise SystemExit("El volcado delata a esta máquina; no se escribe nada:\n  "
                             + "\n  ".join(hallazgos[:20]))

        manifiesto = json.loads((trabajo / MANIFIESTO).read_text())
        cpu = foto.cpu.types[0].brand if foto.cpu.types else None
        manifiesto.update(cpu=cpu, kernel=foto.system.kernel if foto.system else None,
                          gpus=[g.name for g in foto.gpus], fuentes=sorted(foto.capabilities))
        (trabajo / MANIFIESTO).write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1) + "\n")
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(trabajo, destino, symlinks=True)
    return destino


# Lo que `anonimizar` sustituye aunque no identifique a nadie: el bucle local
# y una MAC a ceros. Que lo cambie no significa que el volcado se lo dejara.
INOFENSIVOS = {"127.0.0.1", "::1", "00:00:00:00:00:00", None, ()}
YA_SUSTITUIDO = re.compile(re.escape(privacidad.MONTAJE).replace(r"\{\}", r"\d+"))


def _sin_numerar(discos):
    """Los discos con los montajes ya sustituidos sin su número.

    `anonimizar` numera por el orden de los discos y el volcado por el de
    `/proc/mounts`: un `/media/unidad3` que pasa a `/media/unidad1` no es un
    dato que quedara por tapar.
    """
    return tuple(
        dataclasses.replace(d, partitions=tuple(
            dataclasses.replace(p, mountpoint=privacidad.MONTAJE.format(""))
            if p.mountpoint and YA_SUSTITUIDO.fullmatch(p.mountpoint) else p
            for p in d.partitions))
        for d in discos)


def _lo_que_anonimizar_taparia(foto) -> list[str]:
    """Lo que `privacidad.anonimizar` cambiaría en la foto del volcado.

    Si cambia algo, es que el volcado dejó un dato que identifica a alguien.
    Lo único que se acepta es lo que anonimizar tapa por sistema sin que sea
    de nadie, como `127.0.0.1`.
    """
    tapada = privacidad.anonimizar(foto)
    quedan = []
    for campo in dataclasses.fields(foto):
        antes, despues = getattr(foto, campo.name), getattr(tapada, campo.name)
        if antes == despues:
            continue
        if campo.name == "network":
            for i, j in zip(antes, despues):
                for sub in dataclasses.fields(i):
                    a, b = getattr(i, sub.name), getattr(j, sub.name)
                    restos = [x for x in (a if isinstance(a, tuple) else (a,))
                              if x not in INOFENSIVOS]
                    if a != b and restos:
                        quedan.append(f"network.{i.name}.{sub.name}")
            continue
        if campo.name == "disks" and _sin_numerar(antes) == _sin_numerar(despues):
            continue
        quedan.append(campo.name)
    return quedan


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("nombre", help="cómo se llama la carpeta: i5-10400, 5800x3d…")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", args.nombre):
        parser.error("el nombre, en minúsculas, cifras, puntos y guiones")
    destino = volcar(args.nombre)
    tamano = sum(f.stat().st_size for f in destino.rglob("*") if f.is_file() and not f.is_symlink())
    print(f"  volcado en {destino.relative_to(RAIZ)} ({tamano / 1024:.0f} KB)")
    print("  pasado por privacidad.anonimizar y por los identificadores de "
          "comprobar_privacidad.py: limpio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
