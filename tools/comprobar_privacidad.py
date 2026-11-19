#!/usr/bin/env python3
"""Busca en lo que se va a publicar datos de una máquina de verdad.

Se escribió después de encontrar el nombre del equipo, la dirección física de
la tarjeta de red y el número de serie de la gráfica dentro de los archivos de
prueba, puestos ahí sin pensar al montar un caso. Uno de esos archivos era,
precisamente, el que comprueba que el informe de fallos no publica nada de eso.

    python3 tools/comprobar_privacidad.py

Mira dos cosas, porque cada una caza lo que la otra no ve:

- **Lo de esta máquina**: su nombre, sus direcciones IPv4 e IPv6 (también la
  mitad de una, que ya identifica), sus MAC, los números de serie que se leen
  sin permisos (discos, USB, monitores, la gráfica), el `machine-id`, las
  interfaces con nombre puesto a mano y la carpeta personal. Solo sirve donde
  se trabaja: en el CI mira el runner.
- **Lo que no es de documentación**, sea de la máquina que sea: IP privadas,
  MAC, IPv6 globales o de enlace con identificador, claves y tokens, correos,
  y en los volcados de `tests/fixtures`, números de serie, EDID y nombres de
  equipo que no estén puestos a cero. Esto es lo que vigila el CI.

Siempre mira el repositorio donde está el propio archivo, se lance desde
donde se lance, y si no encuentra nada versionado sale con 2: un visto bueno
sin haber mirado no es un visto bueno. Devuelve 1 si encuentra algo.
"""

from __future__ import annotations

import ipaddress
import os
import pathlib
import pwd
import re
import socket
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent

RANGOS_DE_DOCUMENTACION = (
    re.compile(r"^192\.0\.2\."), re.compile(r"^198\.51\.100\."),
    re.compile(r"^203\.0\.113\."), re.compile(r"^2001:db8", re.I),
    re.compile(r"^00:00:5e:00:53:", re.I),
)

# Los nombres de interfaz que pone el sistema. Lo demás lo puso alguien a mano
# y suele llevar su nombre o el del equipo (una WireGuard «nombre_wg0»).
_INTERFAZ_DEL_SISTEMA = re.compile(
    r"^(lo|en\w+|eth\d+|wl\w+|ww\w+|docker\d+|br-[0-9a-f]+|veth\w+|virbr\d+(-nic)?"
    r"|tailscale\d+|tun\d+|tap\d+|wg\d+|zt\w+|vmnet\d+|vboxnet\d+|lxcbr\d+|lxdbr\d+"
    r"|podman\d+|cni\d+|flannel\.\d+|bond\d+|team\d+|dummy\d+|sit\d+|ip6tnl\d+"
    r"|ip_vti\d+|ip6_vti\d+|gre\d+|gretap\d+|erspan\d+|nlmon\d+|can\d+|usb\d+|rndis\d+"
    r"|p2p-[\w-]+|interfaz\d+)$")


def _leer(ruta: pathlib.Path) -> str:
    try:
        return ruta.read_text(errors="ignore").strip()
    except OSError:
        return ""


def _versionados() -> list[pathlib.Path]:
    salida = subprocess.run(["git", "-C", str(RAIZ), "ls-files", "-z"],
                            capture_output=True, text=True)
    return [RAIZ / l for l in salida.stdout.split("\0") if l]


# -- lo de esta máquina ----------------------------------------------------------

def _trozos_de_ipv6(direccion: ipaddress.IPv6Address) -> dict[str, str]:
    """La dirección y lo que de ella basta para reconocer la máquina.

    La mitad baja (el identificador de interfaz) es estable en una conexión y
    no cambia con la red; en una global, además, la mitad alta dice de quién
    es la conexión. Un test llegó a llevar una `fe80::` con los dos primeros
    grupos del identificador de la máquina del autor y el resto a mano.
    """
    trozos = {}
    hexa = direccion.exploded.replace(":", "")
    trozos[hexa] = "una dirección IPv6 de este equipo"
    trozos[str(direccion)] = "una dirección IPv6 de este equipo"
    grupos = direccion.exploded.split(":")
    identificador = grupos[4:]
    for i in range(3):
        par = identificador[i:i + 2]
        if all(int(g, 16) == 0 for g in par):
            continue
        trozos["".join(par)] = "parte del identificador IPv6 de este equipo"
        trozos[":".join(f"{int(g, 16):x}" for g in par)] = \
            "parte del identificador IPv6 de este equipo"
    if direccion.is_global:
        prefijo = ":".join(f"{int(g, 16):x}" for g in grupos[:3])
        trozos[prefijo] = "el prefijo IPv6 de la conexión de este equipo"
    return trozos


def _direcciones_propias() -> dict[str, str]:
    datos: dict[str, str] = {}
    for linea in _leer(pathlib.Path("/proc/net/if_inet6")).splitlines():
        campos = linea.split()
        if not campos:
            continue
        try:
            direccion = ipaddress.IPv6Address(int(campos[0], 16))
        except ValueError:
            continue
        if direccion.is_loopback:
            continue
        datos.update(_trozos_de_ipv6(direccion))
    # /proc/net/fib_trie dice cada dirección local con «/32 host LOCAL» debajo.
    anterior = None
    for linea in _leer(pathlib.Path("/proc/net/fib_trie")).splitlines():
        if (m := re.search(r"\|-- (\d+\.\d+\.\d+\.\d+)$", linea)):
            anterior = m.group(1)
        elif "/32 host LOCAL" in linea and anterior and not anterior.startswith("127."):
            datos[anterior] = "una dirección IPv4 de este equipo"
    return datos


# Lo que el firmware pone cuando no hay número de serie. Buscarlo daría por
# delatora cualquier línea de código que lo reconozca.
_RELLENO = re.compile(r"(?i)filled by o\.?e\.?m|default string|not specified|system serial|"
                      r"chassis serial|^none$|^n/a$|0123456789|^unknown$")


# Un concentrador raíz de USB da como «número de serie» su dirección PCI
# («0000:00:14.0»), que está en cualquier ruta de sysfs y no es de nadie.
_DIRECCION_PCI = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")


def _series_propias() -> dict[str, str]:
    """Los números de serie que se leen sin permisos (y los otros, si se puede)."""
    datos: dict[str, str] = {}
    sitios = {
        "/sys/block/*/device/serial": "el número de serie de un disco",
        "/sys/class/nvme/*/serial": "el número de serie de un disco",
        "/sys/block/*/device/wwid": "el identificador de un disco",
        "/sys/bus/usb/devices/*/serial": "el número de serie de algo enchufado por USB",
        "/sys/class/drm/card*/device/unique_id": "el número de serie de la gráfica",
        "/sys/class/dmi/id/product_uuid": "el UUID del equipo",
        "/sys/class/dmi/id/product_serial": "el número de serie del equipo",
        "/sys/class/dmi/id/board_serial": "el número de serie de la placa",
        "/sys/class/dmi/id/chassis_serial": "el número de serie del chasis",
        "/etc/machine-id": "el machine-id",
    }
    for patron, que_es in sitios.items():
        for ruta in pathlib.Path("/").glob(patron.lstrip("/")):
            valor = _leer(ruta)
            for trozo in {valor, valor.split()[-1] if valor.split() else ""}:
                if (len(trozo) >= 6 and trozo.strip("0 ") and not _RELLENO.search(trozo)
                        and not _DIRECCION_PCI.match(trozo)):
                    datos[trozo] = que_es
    for ruta in pathlib.Path("/sys/class/drm").glob("card*-*/edid"):
        try:
            edid = ruta.read_bytes()
        except OSError:
            continue
        for texto in _series_de_edid(edid):
            datos[texto] = "el número de serie de un monitor"
    return datos


def _series_de_edid(edid: bytes) -> list[str]:
    """El texto del descriptor de número de serie (0xFF), si no está a ceros."""
    series = []
    for inicio in range(54, 126, 18):
        bloque = edid[inicio:inicio + 18]
        if len(bloque) == 18 and bloque[:3] == b"\0\0\0" and bloque[3] == 0xFF:
            texto = bloque[5:].split(b"\n")[0].decode("latin-1").strip()
            if len(texto) >= 4 and texto.strip("0 "):
                series.append(texto)
    return series


def _de_esta_maquina() -> dict[str, str]:
    """Lo que identifica al equipo donde se está trabajando ahora mismo."""
    datos = {socket.gethostname(): "el nombre de este equipo"}
    for ruta in pathlib.Path("/sys/class/net").glob("*/address"):
        mac = _leer(ruta)
        if mac and not mac.startswith("00:00:00"):
            datos[mac] = f"la dirección física de {ruta.parent.name}"
        nombre = ruta.parent.name
        if not _INTERFAZ_DEL_SISTEMA.match(nombre):
            datos[nombre] = "una interfaz de red con nombre puesto a mano"
    datos.update(_direcciones_propias())
    datos.update(_series_propias())
    if (casa := pathlib.Path.home()).name:
        datos[str(casa)] = "la carpeta personal"
    try:
        nombre_real = pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0].strip()
    except KeyError:
        nombre_real = ""
    if len(nombre_real) >= 4 and nombre_real != pwd.getpwuid(os.getuid()).pw_name:
        datos[nombre_real] = "el nombre de quien usa este equipo"
    return {d: q for d, q in datos.items() if d and len(d) >= 4}


# -- lo que no es de documentación, sea de quien sea -----------------------------

_IPV4_PRIVADA = re.compile(
    r"\b(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")
_MAC = re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:])")
_IPV6_TEXTO = re.compile(r"(?<![0-9A-Za-z:.])(?:fe80|[23][0-9a-f]{3}):[0-9a-f:]*[0-9a-f](?![0-9A-Za-z:])", re.I)
_IPV6_HEXA = re.compile(r"\b(?:fe80[0-9a-f]{28}|[23][0-9a-f]{31})\b")
_CORREO = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CORREOS_PERMITIDOS = re.compile(
    r"(noreply@anthropic\.com|noreply@github\.com|git@github\.com"
    r"|@example\.(com|org|net)|@kernel\.org)$", re.I)
_SECRETOS = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "una clave privada"),
    (re.compile(r"PrivateKey\s*=\s*[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]="), "una clave de WireGuard"),
    (re.compile(r"\bssh-(?:ed25519|rsa|dss) AAAA[0-9A-Za-z+/]{20,}"), "una clave SSH"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{40,}"), "un token de GitHub"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "un token de Slack"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "una clave de AWS"),
    (re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{30,}"), "una clave de API"),
)


def _ipv6_con_identificador(texto: str) -> bool:
    """Una IPv6 global o de enlace que identifica algo, no un `fe80::1` de ejemplo."""
    try:
        direccion = ipaddress.IPv6Address(texto if ":" in texto else int(texto, 16))
    except ValueError:
        return False
    if any(r.match(direccion.compressed) for r in RANGOS_DE_DOCUMENTACION):
        return False
    if not (direccion.is_link_local or direccion.is_global):
        return False
    identificador = direccion.exploded.split(":")[4:]
    return sum(1 for g in identificador if int(g, 16)) >= 2


def _en_el_texto(texto: str) -> list[tuple[int, str]]:
    """Lo que no es de documentación, venga de la máquina que venga.

    Cada hallazgo es (línea, qué es), sin el dato: esto se imprime en el
    registro del CI, que es público.
    """
    def linea(posicion: int) -> int:
        return texto.count("\n", 0, posicion) + 1

    hallazgos = []
    for m in _IPV4_PRIVADA.finditer(texto):
        if not any(r.match(m.group()) for r in RANGOS_DE_DOCUMENTACION):
            hallazgos.append((linea(m.start()), "una dirección IPv4 privada"))
    for m in _MAC.finditer(texto):
        baja = m.group().lower()
        if not (any(r.match(baja) for r in RANGOS_DE_DOCUMENTACION)
                or baja in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff")):
            hallazgos.append((linea(m.start()), "una dirección física"))
    for patron in (_IPV6_TEXTO, _IPV6_HEXA):
        for m in patron.finditer(texto):
            if _ipv6_con_identificador(m.group()):
                hallazgos.append((linea(m.start()), "una dirección IPv6 con identificador"))
    for m in _CORREO.finditer(texto):
        if not _CORREOS_PERMITIDOS.search(m.group()):
            hallazgos.append((linea(m.start()), "un correo"))
    for patron, que_es in _SECRETOS:
        for m in patron.finditer(texto):
            hallazgos.append((linea(m.start()), que_es))
    return hallazgos


# En un volcado, estos archivos son de la pieza y no de quien la tiene: el
# volcado los deja a ceros o con un valor inventado, y uno que no lo esté se
# escapó al anonimizar.
_SERIES_EN_VOLCADOS = {"serial", "unique_id", "product_uuid", "product_serial",
                       "board_serial", "chassis_serial", "wwid", "eui", "nguid",
                       "uuid", "machine-id", "boot_id"}


def _en_un_volcado(ruta: pathlib.Path, relativa: str) -> list[str]:
    if not relativa.startswith("tests/fixtures/"):
        return []
    nombre = ruta.name
    if nombre == "edid" or nombre.endswith(".bin") and "edid" in relativa:
        try:
            edid = ruta.read_bytes()
        except OSError:
            return []
        if len(edid) >= 16 and int.from_bytes(edid[12:16], "little") != 0:
            return ["un número de serie de monitor (EDID, bytes 12-15)"]
        if _series_de_edid(edid):
            return ["un número de serie de monitor (EDID, descriptor 0xFF)"]
        return []
    if nombre in _SERIES_EN_VOLCADOS:
        valor = _leer(ruta)
        if valor.strip("0-: \n"):
            return [f"un {nombre} sin poner a cero"]
    if nombre == "hostname" and relativa.endswith("kernel/hostname"):
        if _leer(ruta) not in ("", "equipo"):
            return ["un nombre de equipo que no es «equipo»"]
    return []


# Lo que el programa escribe dentro del PNG al hacer una captura, diciendo si
# tapó lo que identifica al equipo. Va como chunk `tEXt`, que en un PNG es
# texto plano y se encuentra sin descomprimir nada.
MARCA = b"silux-anonimo"
ANONIMA = MARCA + b"\x00anonima"


def _capturas_delatoras(rutas: list[pathlib.Path] | None = None) -> list[str]:
    """Imágenes publicadas que no se hicieron con `--anonimo`.

    Lo de arriba busca texto, y una captura es un mapa de píxeles: la MAC que
    se ve en pantalla no está escrita en ninguna parte del archivo. Así que
    esta comprobación no mira lo que enseña la imagen sino cómo se hizo, que
    es lo que sí se puede saber. Mira todos los PNG versionados, no solo los
    del README: la primera captura que se publicó, en la raíz, llevaba el
    nombre del equipo.
    """
    if rutas is None:
        rutas = [r for r in _versionados() if r.suffix.lower() == ".png"]
    avisos = []
    for ruta in sorted(rutas):
        try:
            crudo = ruta.read_bytes()
        except OSError:
            continue
        nombre = ruta.relative_to(RAIZ) if ruta.is_relative_to(RAIZ) else ruta
        if ANONIMA in crudo:
            continue
        if MARCA in crudo:
            avisos.append(f"{nombre}: hecha sin --anonimo")
        else:
            # Las de antes de que se escribiera la marca. No se puede afirmar
            # que lleven nada, pero tampoco que no: hay que rehacerlas.
            avisos.append(f"{nombre}: no dice cómo se hizo; rehacerla con --anonimo")
    return avisos


def _direcciones_sospechosas(texto: str) -> list[str]:
    """IP privadas que no sean de los rangos reservados para documentación."""
    return [d for d in _IPV4_PRIVADA.findall(texto)
            if not any(r.match(d) for r in RANGOS_DE_DOCUMENTACION)]


def revisar(rutas: list[pathlib.Path], propios: dict[str, str]) -> list[str]:
    """Cada hallazgo como «archivo: qué es». No dice el dato: se publicaría."""
    hallazgos: list[str] = []
    for ruta in rutas:
        relativa = str(ruta.relative_to(RAIZ)) if ruta.is_relative_to(RAIZ) else str(ruta)
        hallazgos += [f"{relativa}: {q}" for q in _en_un_volcado(ruta, relativa)]
        try:
            crudo = ruta.read_bytes()
        except OSError:
            continue
        if b"\0" in crudo[:8192]:
            # Binario: solo lo de esta máquina, byte a byte.
            for dato, que_es in propios.items():
                if dato.encode() in crudo:
                    hallazgos.append(f"{relativa}: {que_es}")
            continue
        texto = crudo.decode("utf-8", errors="ignore")
        for dato, que_es in propios.items():
            if (posicion := texto.find(dato)) >= 0:
                hallazgos.append(f"{relativa}:{texto.count(chr(10), 0, posicion) + 1}: {que_es}")
        hallazgos += [f"{relativa}:{n}: {q}" for n, q in _en_el_texto(texto)]
    return hallazgos


def main() -> int:
    rutas = _versionados()
    if not rutas:
        print(f"No hay nada versionado en {RAIZ}: no se ha mirado nada.", file=sys.stderr)
        return 2

    propios = _de_esta_maquina()
    hallazgos = revisar([r for r in rutas if r.suffix.lower() != ".png"], propios)
    hallazgos += _capturas_delatoras([r for r in rutas if r.suffix.lower() == ".png"])

    autores = subprocess.run(
        ["git", "-C", str(RAIZ), "log", "--all", "--format=%ae%n%ce"],
        capture_output=True, text=True).stdout.split()
    autores = [a for a in autores if a != "noreply@github.com"]
    if len(set(autores)) > 1:
        hallazgos.append(f"el historial tiene {len(set(autores))} correos "
                         f"distintos: {', '.join(sorted(set(autores)))}")

    if not hallazgos:
        print(f"Nada que delate a una máquina en lo que se va a publicar "
              f"({len(rutas)} archivos, {len(propios)} datos de este equipo).")
        return 0

    print("Esto se publicaría:", file=sys.stderr)
    for linea in sorted(set(hallazgos)):
        print(f"  {linea}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
