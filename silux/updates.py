"""Buscar una versión nueva y, si el usuario lo pide, sustituir el AppImage.

Es lo único del programa que sale a la red, y solo cuando alguien lo pide: el
ajuste de buscar al iniciar viene apagado y el botón «Buscar ahora» se pulsa a
mano. A quién se conecta y por qué así: `docs/arquitectura.md#el-actualizador`.

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
MAX_LIST_BYTES = 1 << 20
MAX_SUMS_BYTES = 64 << 10
MAX_APPIMAGE_BYTES = 400 << 20
# Lo que se espera a que llegue algo. En la descarga cuenta por cada lectura,
# no por el total: una conexión lenta que avanza no se corta.
TIMEOUT_S = 15.0
DOWNLOAD_TIMEOUT_S = 60.0
CHUNK = 1 << 16


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
    # The test version's number (0.4.0rc3 is 3); None for a final.
    prerelease: Optional[int] = None

    @property
    def version_text(self) -> str:
        """«0.4.0» or «0.4.0rc3», as `__version__` writes it."""
        base = ".".join(str(n) for n in self.version)
        return f"{base}rc{self.prerelease}" if self.prerelease is not None else base

    @property
    def order(self) -> tuple[int, ...]:
        """To compare with `_orden`: a test version before its final."""
        return tuple(self.version) + ((0, self.prerelease) if self.prerelease is not None
                                      else (1, 0))


# -- versiones ----------------------------------------------------------------

# «0.4.0rc1» es la 0.4-prueba1: se entiende para saber qué va por delante,
# pero no se ofrece nunca como versión a la que actualizar.
_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:rc(\d+))?")


def parse_version(text: str) -> Optional[tuple[int, int, int]]:
    """«v0.5.0» o «0.5.0» como tres números; None si no es eso exactamente."""
    match = _VERSION.fullmatch((text or "").strip())
    if match is None or match.group(4) is not None:
        return None
    return tuple(int(n) for n in match.groups()[:3])  # type: ignore[return-value]


def _sort_key(text: str) -> Optional[tuple[int, ...]]:
    """Para comparar: una versión de prueba va por debajo de su final.

    0.4.0rc1 < 0.4.0rc2 < 0.4.0 < 0.4.1. Sin esto, la versión que corre en la
    0.4-prueba1 no se entendía y nunca había nada más nuevo.
    """
    match = _VERSION.fullmatch((text or "").strip())
    if match is None:
        return None
    base = tuple(int(n) for n in match.groups()[:3])
    rc = match.group(4)
    return base + ((0, int(rc)) if rc is not None else (1, 0))


CHANNELS = ("stable", "testing")


def channel_for(preference: str, current: str = __version__) -> str:
    """The channel to look in. Without a choice, a test version follows the
    tests: whoever runs the 0.4-prueba2 gets the prueba3 with «Buscar
    ahora», and a final, only finals."""
    if preference in CHANNELS:
        return preference
    return "testing" if (_sort_key(current) or (0, 0, 0, 1))[3] == 0 else "stable"


def latest(releases: object, channel: str = "stable") -> Optional[Release]:
    """La release publicada más alta de la lista que da la API.

    Fuera los borradores, y lo que no tenga la forma que se espera: la
    respuesta viene de fuera y no se da nada por hecho. The test versions
    (marked *prerelease*, or tagged «rcN») only on the testing channel.
    """
    best: Optional[Release] = None
    for entry in releases if isinstance(releases, list) else ():
        if not isinstance(entry, dict):
            continue
        if entry.get("draft"):
            continue
        match = _VERSION.fullmatch(str(entry.get("tag_name") or "").strip())
        if match is None:
            continue
        version = tuple(int(n) for n in match.groups()[:3])
        rc = int(match.group(4)) if match.group(4) is not None else None
        if (entry.get("prerelease") or rc is not None) and channel != "testing":
            continue
        assets_by_name = {}
        for asset in entry.get("assets") or ():
            if isinstance(asset, dict) and asset.get("name") and asset.get("browser_download_url"):
                assets_by_name[str(asset["name"])] = str(asset["browser_download_url"])
        url = str(entry.get("html_url") or f"{RELEASES_URL}/tag/{entry['tag_name']}")
        candidate = Release(version, str(entry["tag_name"]), url, assets_by_name, rc)
        if best is None or candidate.order > best.order:
            best = candidate
    return best


def is_newer(release: Optional[Release], current: str = __version__) -> bool:
    """Si la release va por delante de esta versión, comparada entera."""
    installed = _sort_key(current)
    return release is not None and installed is not None and release.order > installed


def is_current(release: Optional[Release], current: str = __version__) -> bool:
    """Whether this copy is that release: a test version or one ahead of
    the latest published is not «the latest version»."""
    return release is not None and _sort_key(current) == release.order


# -- qué copia es esta --------------------------------------------------------


def asset_name(build: Optional[str] = None) -> str:
    """El AppImage del mismo tipo que el que corre.

    El empaquetador deja en la marca de construcción un `-compat` al final en
    el compatible; es lo que hay dentro del paquete y no depende de cómo haya
    llamado el usuario al archivo.
    """
    build_mark = build_id() if build is None else build
    return COMPAT if build_mark.endswith("-compat") else NORMAL


def replaceable_path(environ: Optional[Mapping[str, str]] = None) -> Optional[pathlib.Path]:
    """El AppImage que se puede sustituir, o None si solo cabe avisar.

    None desde el código (no hay `$APPIMAGE`) y cuando su carpeta no se puede
    escribir: el temporal va al lado y `os.replace` necesita escribir en la
    carpeta, no en el archivo.
    """
    env = os.environ if environ is None else environ
    path = env.get("APPIMAGE")
    if not path:
        return None
    appimage = pathlib.Path(path)
    if not appimage.is_file() or not os.access(appimage.parent, os.W_OK | os.X_OK):
        return None
    return appimage


# -- la red -------------------------------------------------------------------


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
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
CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/ca-bundle.pem",
    "/etc/pki/tls/cacert.pem",
    "/etc/ssl/cert.pem",
)

_opener_built = None


def _opener():
    """El que abre las URL: solo HTTPS, verificando contra los certificados
    del sistema. Se monta la primera vez, no al importar: sin el módulo
    `ssl` (un Python sin OpenSSL) el error tiene que ser «no hay TLS» y no
    un «no hay conexión» que manda a mirar el router."""
    global _opener_built
    if _opener_built is None:
        try:
            import ssl
        except ImportError as error:
            raise UpdateError("notls", str(error)) from error
        # `create_default_context` ya mira `SSL_CERT_FILE` y lo que el
        # OpenSSL de dentro tenga por defecto; a eso se suma el almacén del
        # sistema que haya.
        context = ssl.create_default_context()
        for path in CA_BUNDLES:
            if os.path.isfile(path):
                context.load_verify_locations(cafile=path)
                break
        _opener_built = urllib.request.build_opener(
            _HttpsOnly, urllib.request.HTTPSHandler(context=context))
    return _opener_built


def user_agent() -> str:
    """Solo el nombre y la versión: nada del equipo ni de quien lo usa."""
    return f"silux/{__version__}"


def open_url(url: str, timeout: float) -> BinaryIO:
    """Abre una URL HTTPS y devuelve la respuesta, que se lee por trozos."""
    if not url.lower().startswith("https://"):
        raise UpdateError("insecure", url)
    request = urllib.request.Request(url, headers={
        "User-Agent": user_agent(),
        "Accept": "application/vnd.github+json" if url.startswith(API_URL) else "*/*",
    })
    return _opener().open(request, timeout=timeout)


Opener = Callable[[str, float], BinaryIO]


def _network_error(error: Exception) -> UpdateError:
    """«network», unless the connection failed because this system has no
    certificates to check GitHub's against: that is a package to install
    (ca-certificates in every family), not a network that is down."""
    reason = getattr(error, "reason", error)
    try:
        import ssl
    except ImportError:
        return UpdateError("network", str(error))
    if isinstance(reason, ssl.SSLCertVerificationError) and \
            not any(os.path.isfile(path) for path in CA_BUNDLES):
        return UpdateError("nocerts", str(error))
    return UpdateError("network", str(error))


def _read_all(opener: Opener, url: str, limit: int, timeout: float = TIMEOUT_S) -> bytes:
    """Toda la respuesta, o un error si pasa del tope."""
    try:
        with opener(url, timeout) as response:
            data = response.read(limit + 1)
    except UpdateError:
        raise
    except (OSError, ValueError) as error:
        raise _network_error(error) from error
    if len(data) > limit:
        raise UpdateError("toolarge", url)
    return data


def _open_download(opener: Opener, url: str) -> BinaryIO:
    try:
        return opener(url, DOWNLOAD_TIMEOUT_S)
    except UpdateError:
        raise
    except (OSError, ValueError) as error:
        raise _network_error(error) from error


def check(opener: Opener = open_url, channel: str = "stable") -> Optional[Release]:
    """La última release publicada en ese canal; None si no hay ninguna."""
    data = _read_all(opener, API_URL, MAX_LIST_BYTES)
    try:
        releases = json.loads(data.decode("utf-8"))
    except ValueError as error:
        raise UpdateError("badreply", str(error)) from error
    return latest(releases, channel)


def parse_sums(text: str) -> dict[str, str]:
    """Las líneas de `sha256sum`: «hash  nombre» (con `*` si es binario)."""
    sums = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            sums[parts[1].lstrip("*").strip()] = parts[0].lower()
    return sums


def expected_hash(release: Release, name: str, opener: Opener = open_url) -> str:
    """El SHA-256 publicado para ese adjunto. Sin él no se baja nada."""
    if name not in release.assets:
        raise UpdateError("noasset", name)
    if SUMS not in release.assets:
        raise UpdateError("nosums", release.tag)
    data = _read_all(opener, release.assets[SUMS], MAX_SUMS_BYTES)
    digest = parse_sums(data.decode("utf-8", errors="replace")).get(name)
    if digest is None:
        raise UpdateError("nosums", name)
    return digest


def install(release: Release, target: pathlib.Path, name: Optional[str] = None,
            opener: Opener = open_url,
            progress: Optional[Callable[[int], None]] = None) -> pathlib.Path:
    """Baja el AppImage, lo comprueba y lo pone en lugar de `destino`.

    El temporal va en la misma carpeta para que `os.replace` sea un cambio de
    nombre y no una copia: quien abra el programa en ese instante encuentra el
    viejo entero o el nuevo entero. Si algo falla, el temporal se borra y
    `destino` queda como estaba.
    """
    name = name or asset_name()
    expected = expected_hash(release, name, opener)
    descriptor, temp_path = tempfile.mkstemp(prefix=".silux-", suffix=".part",
                                            dir=str(target.parent))
    try:
        digest = hashlib.sha256()
        total = 0
        with os.fdopen(descriptor, "wb") as out, \
                _open_download(opener, release.assets[name]) as response:
            while True:
                try:
                    chunk = response.read(CHUNK)
                except (OSError, ValueError) as error:
                    raise UpdateError("network", str(error)) from error
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_APPIMAGE_BYTES:
                    raise UpdateError("toolarge", name)
                digest.update(chunk)
                out.write(chunk)
                if progress is not None:
                    progress(total)
            out.flush()
            os.fsync(out.fileno())
        if digest.hexdigest() != expected:
            raise UpdateError("badhash", name)
        os.chmod(temp_path, 0o755)
        os.replace(temp_path, target)
    except BaseException as error:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        if isinstance(error, OSError):
            # Lo de la red ya llega como UpdateError: esto es el disco.
            raise UpdateError("write", str(error)) from error
        raise
    # Que el cambio de nombre llegue al disco, no solo el contenido.
    try:
        folder_fd = os.open(str(target.parent), os.O_RDONLY)
        try:
            os.fsync(folder_fd)
        finally:
            os.close(folder_fd)
    except OSError:
        pass
    return target
