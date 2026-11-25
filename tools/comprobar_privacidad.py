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
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from silux import privacidad  # noqa: E402  (lo que pone el anonimizado)
from silux.privacidad import _edid_serials, _read  # noqa: E402

_CORREO = privacidad.EMAIL
_CORREOS_PERMITIDOS = privacidad.ALLOWED_EMAILS
# Addresses that are part of someone else's copyright line, which their
# licence asks to be kept as it is: only in the notices, nowhere else. In
# two pieces, so that this file doesn't carry one itself.
_CORREOS_DE_AVISOS = {"silux/db/THIRD_PARTY_NOTICES.md": ("quininer@" + "live.com",)}

# Lo que el anonimizado pone en lugar de lo de cada uno: parece de verdad a
# propósito, y por eso se nombra. Cualquier otra IPv4 privada es de alguien.
_SUSTITUTOS = {privacidad.IPV4, privacidad.GATEWAY}
_NOMBRES_DE_EQUIPO_FALSOS = {"", privacidad.HOST_NAME, *privacidad.OLD_SUBSTITUTES}

RANGOS_DE_DOCUMENTACION = (
    re.compile(r"^192\.0\.2\."), re.compile(r"^198\.51\.100\."),
    re.compile(r"^203\.0\.113\."), re.compile(r"^2001:db8", re.I),
    re.compile(r"^00:00:5e:00:53:", re.I),
)

def _versionados() -> list[pathlib.Path]:
    salida = subprocess.run(["git", "-C", str(RAIZ), "ls-files", "-z"],
                            capture_output=True, text=True)
    return [RAIZ / l for l in salida.stdout.split("\0") if l]


def _privados() -> dict[str, str]:
    """Lo que alguien no quiere publicado y no está en esta máquina.

    El nombre de otro equipo suyo, por ejemplo. No puede escribirse en el
    repositorio, que es justo donde se busca, así que sale de `.privado`
    (ignorado por git; un dato por línea) o de `SILUX_PRIVADO` (separados por
    comas).
    """
    datos: list[str] = os.environ.get("SILUX_PRIVADO", "").split(",")
    datos += _read(RAIZ / ".privado").splitlines()
    return {d.strip(): "un dato de .privado" for d in datos if len(d.strip()) >= 4}



def _de_esta_maquina() -> dict[str, str]:
    """Lo de esta máquina, y lo de `.privado`."""
    return {**privacidad.of_this_machine(), **_privados()}


# -- lo que no es de documentación, sea de quien sea -----------------------------

_IPV4_PRIVADA = re.compile(
    r"\b(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")
_MAC = re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:])")
_IPV6_TEXTO = re.compile(r"(?<![0-9A-Za-z:.])(?:fe80|[23][0-9a-f]{3}):[0-9a-f:]*[0-9a-f](?![0-9A-Za-z:])", re.I)
_IPV6_HEXA = re.compile(r"\b(?:fe80[0-9a-f]{28}|[23][0-9a-f]{31})\b")
_BUILD_HOST = "mockbuild@"
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


def _en_el_texto(texto: str, de_aviso: tuple[str, ...] = ()) -> list[tuple[int, str]]:
    """Lo que no es de documentación, venga de la máquina que venga.

    Cada hallazgo es (línea, qué es), sin el dato: esto se imprime en el
    registro del CI, que es público.
    """
    def linea(posicion: int) -> int:
        return texto.count("\n", 0, posicion) + 1

    hallazgos = []
    for m in _IPV4_PRIVADA.finditer(texto):
        if m.group() in _SUSTITUTOS:
            continue
        if not any(r.match(m.group()) for r in RANGOS_DE_DOCUMENTACION):
            hallazgos.append((linea(m.start()), "una dirección IPv4 privada"))
    for m in _MAC.finditer(texto):
        baja = m.group().lower()
        if not (any(r.match(baja) for r in RANGOS_DE_DOCUMENTACION)
                or baja in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff")):
            hallazgos.append((linea(m.start()), "una dirección física"))
    for patron in (_IPV6_TEXTO, _IPV6_HEXA):
        for m in patron.finditer(texto):
            # The container Fedora's builders compile a kernel in: in its
            # version string, the same for whoever runs that kernel.
            if texto.endswith(_BUILD_HOST, 0, m.start()):
                continue
            if _ipv6_con_identificador(m.group()):
                hallazgos.append((linea(m.start()), "una dirección IPv6 con identificador"))
    for m in _CORREO.finditer(texto):
        if not _CORREOS_PERMITIDOS.search(m.group()) and m.group() not in de_aviso:
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
        if _edid_serials(edid):
            return ["un número de serie de monitor (EDID, descriptor 0xFF)"]
        return []
    if nombre in _SERIES_EN_VOLCADOS:
        valor = _read(ruta)
        if valor.strip("0-: \n"):
            return [f"un {nombre} sin poner a cero"]
    # De lo USB quedan vendor:product; lo que escribe el propio aparato, no.
    if nombre in ("product", "manufacturer") and re.search(r"/usb\d+/", relativa):
        return [f"el {nombre} de un aparato USB"]
    if nombre == "hostname" and relativa.endswith("kernel/hostname"):
        if _read(ruta) not in _NOMBRES_DE_EQUIPO_FALSOS:
            return [f"un nombre de equipo que no es «{privacidad.HOST_NAME}»"]
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
            if d not in _SUSTITUTOS
            and not any(r.match(d) for r in RANGOS_DE_DOCUMENTACION)]


def revisar(rutas: list[pathlib.Path], propios: dict[str, str],
            where=None) -> list[str]:
    """Cada hallazgo como «archivo: qué es». No dice el dato: se publicaría.

    `where(ruta)`, dónde acabará en el repositorio lo que aún no está en él
    (lo que importa un informe).
    """
    hallazgos: list[str] = []
    for ruta in rutas:
        if where is not None:
            relativa = where(ruta)
        else:
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
        hallazgos += [f"{relativa}:{n}: {q}" for n, q in
                      _en_el_texto(texto, _CORREOS_DE_AVISOS.get(str(relativa), ()))]
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
