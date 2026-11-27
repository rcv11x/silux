"""Look for a new version and, if the user asks, replace the AppImage.

The only part of the program that goes on the network: it asks for the
latest version on opening (a setting turns that off) and with «Check now»,
and downloads only when «Update» is pressed. Who it connects to and why:
`docs/arquitectura.md#el-actualizador`.

No Qt: the interface calls this from a thread. The network goes through
`open_url`, which the tests replace with a fake; none reaches GitHub.
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

# Caps on what each reply may bring. The release list is a few kilobytes per
# version; an AppImage, about 120 MB.
MAX_LIST_BYTES = 1 << 20
MAX_SUMS_BYTES = 64 << 10
MAX_APPIMAGE_BYTES = 400 << 20
# How long to wait for something to arrive. For the download it counts per
# read, not for the total: a slow connection that keeps moving isn't cut.
TIMEOUT_S = 15.0
DOWNLOAD_TIMEOUT_S = 60.0
CHUNK = 1 << 16


class UpdateError(Exception):
    """What prevents checking or updating. `code` is what the interface
    translates; the text, the technical detail for the tooltip."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True)
class Release:
    version: tuple[int, int, int]
    tag: str
    url: str
    # Asset name -> its download URL.
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
        """To compare with `_sort_key`: a test version before its final."""
        return tuple(self.version) + ((0, self.prerelease) if self.prerelease is not None
                                      else (1, 0))


# -- versions -----------------------------------------------------------------

# A version is the day it was published, «2026.11.28»: three numbers, like
# the pruebas before it, «0.4.0rc14», which are read to compare with.
_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:rc(\d+))?")


def parse_version(text: str) -> Optional[tuple[int, int, int]]:
    """«v0.5.0» or «0.5.0» as three numbers; None if it isn't exactly that."""
    match = _VERSION.fullmatch((text or "").strip())
    if match is None or match.group(4) is not None:
        return None
    return tuple(int(n) for n in match.groups()[:3])  # type: ignore[return-value]


def _sort_key(text: str) -> Optional[tuple[int, ...]]:
    """For comparing: a test version sorts below its final.

    0.4.0rc1 < 0.4.0rc2 < 0.4.0 < 0.4.1.
    """
    match = _VERSION.fullmatch((text or "").strip())
    if match is None:
        return None
    base = tuple(int(n) for n in match.groups()[:3])
    rc = match.group(4)
    return base + ((0, int(rc)) if rc is not None else (1, 0))


def latest(releases: object) -> Optional[Release]:
    """The highest version published as a normal release in the list the
    API gives.

    A rolling release has no channels: every version is published as a
    normal release. Drafts and prereleases are left out (the pruebas were
    prereleases, and are behind anyway), and anything not shaped as
    expected: the reply comes from outside and nothing is taken for granted.
    """
    best: Optional[Release] = None
    for entry in releases if isinstance(releases, list) else ():
        if not isinstance(entry, dict):
            continue
        if entry.get("draft") or entry.get("prerelease"):
            continue
        match = _VERSION.fullmatch(str(entry.get("tag_name") or "").strip())
        if match is None:
            continue
        version = tuple(int(n) for n in match.groups()[:3])
        rc = int(match.group(4)) if match.group(4) is not None else None
        if rc is not None:
            continue                     # a prueba is never offered
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
    """Whether the release is ahead of this version, compared in full."""
    installed = _sort_key(current)
    return release is not None and installed is not None and release.order > installed


def is_current(release: Optional[Release], current: str = __version__) -> bool:
    """Whether this copy is that release: a test version or one ahead of
    the latest published is not «the latest version»."""
    return release is not None and _sort_key(current) == release.order


# -- which copy this is -------------------------------------------------------


def asset_name(build: Optional[str] = None) -> str:
    """The AppImage of the same kind as the one running.

    The packager leaves a trailing `-compat` in the compatible one's build
    mark; it is inside the package and doesn't depend on what the user named
    the file.
    """
    build_mark = build_id() if build is None else build
    return COMPAT if build_mark.endswith("-compat") else NORMAL


def normal_would_run(build: Optional[str] = None) -> bool:
    """Whether this is the compatible AppImage on a processor that runs the
    normal one: it carries an older Python and Qt for no reason there."""
    from .ui import guarda

    return asset_name(build) == COMPAT and guarda.has_x86_64_v2() is True


def replaceable_path(environ: Optional[Mapping[str, str]] = None) -> Optional[pathlib.Path]:
    """The AppImage that can be replaced, or None if all that's left is to
    tell.

    None from source (no `$APPIMAGE`) and when its folder isn't writable: the
    temporary file goes next to it, and `os.replace` needs to write to the
    folder, not the file.
    """
    env = os.environ if environ is None else environ
    path = env.get("APPIMAGE")
    if not path:
        return None
    appimage = pathlib.Path(path)
    if not appimage.is_file() or not os.access(appimage.parent, os.W_OK | os.X_OK):
        return None
    return appimage


# -- the network --------------------------------------------------------------


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    """GitHub redirects assets to another domain; never to `http://`."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # An `UpdateError`, not a `URLError`: the latter is an `OSError`, and
        # the caller took it for a network outage and said «no connection».
        if not newurl.lower().startswith("https://"):
            raise UpdateError("insecure", newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Where each family of distributions keeps the certificates it trusts:
# Debian, Ubuntu and Arch; Fedora and RHEL; openSUSE; and the rest. The
# OpenSSL inside the AppImage looks only where it was built to look, which
# not every family uses: with Ubuntu's, Fedora and Arch found none and
# couldn't verify GitHub.
CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/ca-bundle.pem",
    "/etc/pki/tls/cacert.pem",
    "/etc/ssl/cert.pem",
)

_opener_built = None


def _opener():
    """What opens the URLs: HTTPS only, verified against the system's
    certificates. Built on first use, not on import: without the `ssl`
    module (a Python without OpenSSL) the error must be «no TLS», not a «no
    connection» that sends people to check their router."""
    global _opener_built
    if _opener_built is None:
        try:
            import ssl
        except ImportError as error:
            raise UpdateError("notls", str(error)) from error
        # `create_default_context` already looks at `SSL_CERT_FILE` and the
        # bundled OpenSSL's defaults; the system's store, if any, is added.
        context = ssl.create_default_context()
        for path in CA_BUNDLES:
            if os.path.isfile(path):
                context.load_verify_locations(cafile=path)
                break
        _opener_built = urllib.request.build_opener(
            _HttpsOnly, urllib.request.HTTPSHandler(context=context))
    return _opener_built


def user_agent() -> str:
    """Only the name and version: nothing about the machine or its user."""
    return f"silux/{__version__}"


def open_url(url: str, timeout: float) -> BinaryIO:
    """Open an HTTPS URL and return the reply, read in chunks."""
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
    """The whole reply, or an error if it goes over the limit."""
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


def check(opener: Opener = open_url) -> Optional[Release]:
    """The latest release published; None if there is none."""
    data = _read_all(opener, API_URL, MAX_LIST_BYTES)
    try:
        releases = json.loads(data.decode("utf-8"))
    except ValueError as error:
        raise UpdateError("badreply", str(error)) from error
    return latest(releases)


def parse_sums(text: str) -> dict[str, str]:
    """`sha256sum`'s lines: «hash  name» (with `*` if binary)."""
    sums = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            sums[parts[1].lstrip("*").strip()] = parts[0].lower()
    return sums


def expected_hash(release: Release, name: str, opener: Opener = open_url) -> str:
    """The SHA-256 published for that asset. Without it nothing is downloaded."""
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
    """Download the AppImage, check it and put it in place of `target`.

    The temporary file goes in the same folder so `os.replace` is a rename,
    not a copy: whoever opens the program at that instant finds the old one
    whole or the new one whole. If anything fails, the temporary file is
    removed and `target` is left as it was.
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
            # Network failures already arrive as UpdateError: this is the disk.
            raise UpdateError("write", str(error)) from error
        raise
    # Make the rename reach the disk, not only the content.
    try:
        folder_fd = os.open(str(target.parent), os.O_RDONLY)
        try:
            os.fsync(folder_fd)
        finally:
            os.close(folder_fd)
    except OSError:
        pass
    return target
