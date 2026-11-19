"""Buscar una versión nueva y, si el usuario lo pide, sustituir el AppImage.

Es lo único del programa que sale a la red, y solo cuando alguien lo pide: el
ajuste de buscar al iniciar viene apagado y el botón «Buscar ahora» se pulsa a
mano. A quién se conecta y por qué así: `docs/propuesta-actualizaciones.md`.

Sin Qt: la interfaz llama a esto desde un hilo. La red pasa por `abrir`, que
los tests sustituyen por uno falso; ninguno sale a GitHub.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import BinaryIO, Callable, Mapping, Optional

from . import __version__, build_id

REPO = "rcv11x/silux"
API_URL = f"https://api.github.com/repos/{REPO}/releases"
RELEASES_URL = f"https://github.com/{REPO}/releases"
SUMS = "SHA256SUMS"
NORMAL = "silux-x86_64.AppImage"
COMPAT = "silux-x86_64-compat.AppImage"

# Topes de lo que se acepta de cada respuesta. La lista de releases ocupa unos
# kilobytes por versión; un AppImage, unos 120 MB.
TOPE_DE_LA_LISTA = 1 << 20
TOPE_DE_LAS_SUMAS = 64 << 10
TOPE_DEL_APPIMAGE = 400 << 20
# Lo que se espera a que llegue algo. En la descarga cuenta por cada lectura,
# no por el total: una conexión lenta que avanza no se corta.
ESPERA = 15.0
ESPERA_DE_LA_DESCARGA = 60.0
BLOQUE = 1 << 16


class UpdateError(Exception):
    """Lo que impide buscar o actualizar. `code` es lo que traduce la
    interfaz; el texto, el detalle técnico para el globo."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True)
class Release:
    version: tuple[int, int, int]
    tag: str
    url: str
    # Nombre del adjunto -> su URL de descarga.
    assets: Mapping[str, str] = field(default_factory=dict)

    @property
    def version_text(self) -> str:
        return ".".join(str(n) for n in self.version)


# -- versiones ----------------------------------------------------------------

# «0.4.0rc1» es la 0.4-prueba1: se entiende para saber qué va por delante,
# pero no se ofrece nunca como versión a la que actualizar.
_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:rc(\d+))?")


def parse_version(texto: str) -> Optional[tuple[int, int, int]]:
    """«v0.5.0» o «0.5.0» como tres números; None si no es eso exactamente."""
    encontrada = _VERSION.fullmatch((texto or "").strip())
    if encontrada is None or encontrada.group(4) is not None:
        return None
    return tuple(int(n) for n in encontrada.groups()[:3])  # type: ignore[return-value]


def _orden(texto: str) -> Optional[tuple[int, ...]]:
    """Para comparar: una versión de prueba va por debajo de su final.

    0.4.0rc1 < 0.4.0rc2 < 0.4.0 < 0.4.1. Sin esto, la versión que corre en la
    0.4-prueba1 no se entendía y nunca había nada más nuevo.
    """
    encontrada = _VERSION.fullmatch((texto or "").strip())
    if encontrada is None:
        return None
    base = tuple(int(n) for n in encontrada.groups()[:3])
    prueba = encontrada.group(4)
    return base + ((0, int(prueba)) if prueba is not None else (1, 0))


def latest(releases: object) -> Optional[Release]:
    """La release publicada más alta de la lista que da la API.

    Fuera los borradores y las *prereleases*, y lo que no tenga la forma que
    se espera: la respuesta viene de fuera y no se da nada por hecho.
    """
    mejor: Optional[Release] = None
    for entrada in releases if isinstance(releases, list) else ():
        if not isinstance(entrada, dict):
            continue
        if entrada.get("draft") or entrada.get("prerelease"):
            continue
        version = parse_version(str(entrada.get("tag_name") or ""))
        if version is None:
            continue
        adjuntos = {}
        for adjunto in entrada.get("assets") or ():
            if isinstance(adjunto, dict) and adjunto.get("name") and adjunto.get("browser_download_url"):
                adjuntos[str(adjunto["name"])] = str(adjunto["browser_download_url"])
        url = str(entrada.get("html_url") or f"{RELEASES_URL}/tag/{entrada['tag_name']}")
        if mejor is None or version > mejor.version:
            mejor = Release(version, str(entrada["tag_name"]), url, adjuntos)
    return mejor


def is_newer(release: Optional[Release], current: str = __version__) -> bool:
    """Si la release va por delante de esta versión, comparada entera."""
    actual = _orden(current)
    return (release is not None and actual is not None
            and tuple(release.version) + (1, 0) > actual)


# -- qué copia es esta --------------------------------------------------------


def asset_name(build: Optional[str] = None) -> str:
    """El AppImage del mismo tipo que el que corre.

    El empaquetador deja en la marca de construcción un `-compat` al final en
    el compatible; es lo que hay dentro del paquete y no depende de cómo haya
    llamado el usuario al archivo.
    """
    marca = build_id() if build is None else build
    return COMPAT if marca.endswith("-compat") else NORMAL


def replaceable_path(environ: Optional[Mapping[str, str]] = None) -> Optional[pathlib.Path]:
    """El AppImage que se puede sustituir, o None si solo cabe avisar.

    None desde el código (no hay `$APPIMAGE`) y cuando su carpeta no se puede
    escribir: el temporal va al lado y `os.replace` necesita escribir en la
    carpeta, no en el archivo.
    """
    env = os.environ if environ is None else environ
    ruta = env.get("APPIMAGE")
    if not ruta:
        return None
    archivo = pathlib.Path(ruta)
    if not archivo.is_file() or not os.access(archivo.parent, os.W_OK | os.X_OK):
        return None
    return archivo


# -- la red -------------------------------------------------------------------


class _SoloHttps(urllib.request.HTTPRedirectHandler):
    """GitHub redirige los adjuntos a otro dominio; a `http://`, nunca."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Un `UpdateError` y no un `URLError`: este último es un `OSError`, y
        # quien abre lo tomaba por un corte de red y decía «no hay conexión».
        if not newurl.lower().startswith("https://"):
            raise UpdateError("insecure", newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Dónde guarda cada familia de distribuciones los certificados en que
# confía: Debian, Ubuntu y Arch; Fedora y RHEL; openSUSE; y el resto. El
# OpenSSL que va dentro del AppImage es el de Ubuntu 22.04 y los busca en
# `/usr/lib/ssl`, que solo existe en Debian y sus derivadas: en Fedora o en
# Arch no encontraba ninguno y no podía verificar a GitHub.
CERTIFICADOS = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/ca-bundle.pem",
    "/etc/pki/tls/cacert.pem",
    "/etc/ssl/cert.pem",
)

_abridor_hecho = None


def _abridor():
    """El que abre las URL: solo HTTPS, verificando contra los certificados
    del sistema. Se monta la primera vez, no al importar: sin el módulo
    `ssl` (un Python sin OpenSSL) el error tiene que ser «no hay TLS» y no
    un «no hay conexión» que manda a mirar el router."""
    global _abridor_hecho
    if _abridor_hecho is None:
        try:
            import ssl
        except ImportError as error:
            raise UpdateError("notls", str(error)) from error
        # `create_default_context` ya mira `SSL_CERT_FILE` y lo que el
        # OpenSSL de dentro tenga por defecto; a eso se suma el almacén del
        # sistema que haya.
        contexto = ssl.create_default_context()
        for ruta in CERTIFICADOS:
            if os.path.isfile(ruta):
                contexto.load_verify_locations(cafile=ruta)
                break
        _abridor_hecho = urllib.request.build_opener(
            _SoloHttps, urllib.request.HTTPSHandler(context=contexto))
    return _abridor_hecho


def user_agent() -> str:
    """Solo el nombre y la versión: nada del equipo ni de quien lo usa."""
    return f"silux/{__version__}"


def abrir(url: str, espera: float) -> BinaryIO:
    """Abre una URL HTTPS y devuelve la respuesta, que se lee por trozos."""
    if not url.lower().startswith("https://"):
        raise UpdateError("insecure", url)
    peticion = urllib.request.Request(url, headers={
        "User-Agent": user_agent(),
        "Accept": "application/vnd.github+json" if url.startswith(API_URL) else "*/*",
    })
    return _abridor().open(peticion, timeout=espera)


Abrir = Callable[[str, float], BinaryIO]


def _leer(abrir_url: Abrir, url: str, tope: int, espera: float = ESPERA) -> bytes:
    """Toda la respuesta, o un error si pasa del tope."""
    try:
        with abrir_url(url, espera) as respuesta:
            datos = respuesta.read(tope + 1)
    except UpdateError:
        raise
    except (OSError, ValueError) as error:
        raise UpdateError("network", str(error)) from error
    if len(datos) > tope:
        raise UpdateError("toolarge", url)
    return datos


def _abierta(abrir_url: Abrir, url: str) -> BinaryIO:
    try:
        return abrir_url(url, ESPERA_DE_LA_DESCARGA)
    except UpdateError:
        raise
    except (OSError, ValueError) as error:
        raise UpdateError("network", str(error)) from error


def check(abrir_url: Abrir = abrir) -> Optional[Release]:
    """La última release publicada; None si no hay ninguna."""
    datos = _leer(abrir_url, API_URL, TOPE_DE_LA_LISTA)
    try:
        lista = json.loads(datos.decode("utf-8"))
    except ValueError as error:
        raise UpdateError("badreply", str(error)) from error
    return latest(lista)


def parse_sums(texto: str) -> dict[str, str]:
    """Las líneas de `sha256sum`: «hash  nombre» (con `*` si es binario)."""
    sumas = {}
    for linea in texto.splitlines():
        partes = linea.strip().split(None, 1)
        if len(partes) == 2 and re.fullmatch(r"[0-9a-fA-F]{64}", partes[0]):
            sumas[partes[1].lstrip("*").strip()] = partes[0].lower()
    return sumas


def expected_hash(release: Release, nombre: str, abrir_url: Abrir = abrir) -> str:
    """El SHA-256 publicado para ese adjunto. Sin él no se baja nada."""
    if nombre not in release.assets:
        raise UpdateError("noasset", nombre)
    if SUMS not in release.assets:
        raise UpdateError("nosums", release.tag)
    datos = _leer(abrir_url, release.assets[SUMS], TOPE_DE_LAS_SUMAS)
    suma = parse_sums(datos.decode("utf-8", errors="replace")).get(nombre)
    if suma is None:
        raise UpdateError("nosums", nombre)
    return suma


def install(release: Release, destino: pathlib.Path, nombre: Optional[str] = None,
            abrir_url: Abrir = abrir,
            progreso: Optional[Callable[[int], None]] = None) -> pathlib.Path:
    """Baja el AppImage, lo comprueba y lo pone en lugar de `destino`.

    El temporal va en la misma carpeta para que `os.replace` sea un cambio de
    nombre y no una copia: quien abra el programa en ese instante encuentra el
    viejo entero o el nuevo entero. Si algo falla, el temporal se borra y
    `destino` queda como estaba.
    """
    nombre = nombre or asset_name()
    esperado = expected_hash(release, nombre, abrir_url)
    descriptor, temporal = tempfile.mkstemp(prefix=".silux-", suffix=".part",
                                            dir=str(destino.parent))
    try:
        resumen = hashlib.sha256()
        total = 0
        with os.fdopen(descriptor, "wb") as salida, \
                _abierta(abrir_url, release.assets[nombre]) as respuesta:
            while True:
                try:
                    bloque = respuesta.read(BLOQUE)
                except (OSError, ValueError) as error:
                    raise UpdateError("network", str(error)) from error
                if not bloque:
                    break
                total += len(bloque)
                if total > TOPE_DEL_APPIMAGE:
                    raise UpdateError("toolarge", nombre)
                resumen.update(bloque)
                salida.write(bloque)
                if progreso is not None:
                    progreso(total)
            salida.flush()
            os.fsync(salida.fileno())
        if resumen.hexdigest() != esperado:
            raise UpdateError("badhash", nombre)
        os.chmod(temporal, 0o755)
        os.replace(temporal, destino)
    except BaseException as error:
        try:
            os.unlink(temporal)
        except OSError:
            pass
        if isinstance(error, OSError):
            # Lo de la red ya llega como UpdateError: esto es el disco.
            raise UpdateError("write", str(error)) from error
        raise
    # Que el cambio de nombre llegue al disco, no solo el contenido.
    try:
        carpeta = os.open(str(destino.parent), os.O_RDONLY)
        try:
            os.fsync(carpeta)
        finally:
            os.close(carpeta)
    except OSError:
        pass
    return destino
