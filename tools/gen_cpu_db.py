#!/usr/bin/env python3
"""Genera `silux/db/cpu_ids.json` a partir de las fuentes de libcpuid y CPU-X.

La identificación de un procesador (nombre en clave, nodo de fabricación,
socket) no se puede deducir del hardware: es una tabla de correspondencias que
alguien tiene que mantener. libcpuid lleva más de una década manteniéndola, y
sus tablas son datos tabulares regulares, no lógica. Este script las convierte
a JSON para que actualizar la base de datos sea volver a ejecutarlo, no editar
código y recompilar.

    python3 tools/gen_cpu_db.py                # clona/actualiza y genera
    python3 tools/gen_cpu_db.py --offline      # usa lo que ya haya en caché

Fuentes y licencias:
  · libcpuid  ( BSD 2 cláusulas ) https://github.com/anrieff/libcpuid
  · CPU-X     ( GPL-3.0 o posterior ) https://github.com/TheTumultuousUnicornOfDarkness/CPU-X

Sus avisos van en `silux/db/THIRD_PARTY_NOTICES.md`, en el paquete y dentro
de cada AppImage. Una fuente nueva necesita el suyo ahí:
`tests/test_avisos_de_terceros.py` lo compara con `sources` de la tabla.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_CACHE = pathlib.Path.home() / ".cache" / "silux" / "sources"

REPOS = {
    # El fork del autor y no el original: el original lleva desde septiembre
    # de 2026 sin actividad, y quien más lo mantenía archivó CPU-X.
    "libcpuid": "https://github.com/rcv11x/libcpuid.git",
    "cpu-x": "https://github.com/TheTumultuousUnicornOfDarkness/CPU-X.git",
}

# --------------------------------------------------------------------------
# utilidades de texto C
# --------------------------------------------------------------------------

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")


def strip_comments(source: str) -> str:
    """Quita comentarios para que una fila comentada no acabe en la base."""
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", source))


def extract_array(source: str, declaration: str) -> str:
    """Devuelve el cuerpo de un array de C, desde `= {` hasta su `};`."""
    start = source.find(declaration)
    if start < 0:
        raise LookupError(f"no encuentro la declaración: {declaration!r}")
    open_brace = source.index("{", start)
    depth = 0
    for i in range(open_brace, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace + 1 : i]
    raise LookupError(f"array sin cerrar: {declaration!r}")


def unquote(token: str) -> str | None:
    """Traduce un literal de C a un valor de Python (`UNKN_STR`/`NULL` -> None)."""
    token = token.strip()
    if token in ("UNKN_STR", "NULL", ""):
        return None
    if token.startswith('"') and token.endswith('"'):
        value = token[1:-1].encode().decode("unicode_escape")
        return value or None
    return token


# --------------------------------------------------------------------------
# tablas x86 de libcpuid: struct match_entry_t
# --------------------------------------------------------------------------

# Las tablas mezclan decimal y hexadecimal en el mismo campo (ext_model de AMD).
_INT = r"\s*(-?(?:0[xX][0-9A-Fa-f]+|\d+))\s*"
_STR = r'\s*"((?:[^"\\]|\\.)*)"\s*'
_X86_ROW = re.compile(
    r"\{" + _INT + r"," + _INT + r"," + _INT + r"," + _INT + r"," + _INT + r","
    + _INT + r"," + _INT + r"," + _INT + r","
    r"\s*\{" + _STR + r"," + _INT + r"\}\s*,"
    + _STR + r","
    r"\s*(UNKN_STR|\"(?:[^\"\\]|\\.)*\")\s*\}"
)


def parse_x86_table(source: str, declaration: str) -> list[dict]:
    body = extract_array(strip_comments(source), declaration)
    rows: list[dict] = []
    for m in _X86_ROW.finditer(body):
        (family, model, stepping, ext_family, ext_model, ncores, l2, l3,
         brand_pattern, brand_score, name, technology) = m.groups()
        rows.append(
            {
                "f": int(family, 0), "m": int(model, 0), "s": int(stepping, 0),
                "xf": int(ext_family, 0), "xm": int(ext_model, 0),
                "nc": int(ncores, 0), "l2": int(l2, 0), "l3": int(l3, 0),
                "bp": brand_pattern or None,
                "bs": int(brand_score, 0),
                "name": name,
                "tech": unquote(technology),
            }
        )
    if not rows:
        raise LookupError(f"la tabla {declaration!r} salió vacía; ¿cambió el formato?")
    return rows


# --------------------------------------------------------------------------
# tablas ARM de libcpuid: implementer -> part number -> nombre
# --------------------------------------------------------------------------

_ARM_PART_ROW = re.compile(
    r"\{\s*(-?(?:0x)?[0-9A-Fa-f]+)\s*,"
    + _STR + r","
    r"\s*(UNKN_STR|\"(?:[^\"\\]|\\.)*\")\s*,"
    r"\s*(UNKN_STR|\"(?:[^\"\\]|\\.)*\")\s*\}"
)
_ARM_IMPL_ROW = re.compile(
    r"\{\s*(-?(?:0x)?[0-9A-Fa-f]+)\s*,\s*VENDOR_\w+\s*,\s*(\w+)\s*," + _STR + r"\}"
)


def parse_arm_tables(source: str) -> dict:
    clean = strip_comments(source)

    parts_by_symbol: dict[str, dict[str, dict]] = {}
    for m in re.finditer(r"static const struct arm_id_part (\w+)\[\]", clean):
        symbol = m.group(1)
        body = extract_array(clean[m.start():], f"arm_id_part {symbol}[]")
        entries: dict[str, dict] = {}
        for row in _ARM_PART_ROW.finditer(body):
            part_id = int(row.group(1), 0)
            if part_id < 0:            # centinela de fin de tabla
                continue
            entries[str(part_id)] = {
                "name": row.group(2),
                "codename": unquote(row.group(3)),
                "tech": unquote(row.group(4)),
            }
        parts_by_symbol[symbol] = entries

    implementers: dict[str, dict] = {}
    for row in _ARM_IMPL_ROW.finditer(extract_array(clean, "arm_hw_impl hw_implementer[]")):
        impl_id = int(row.group(1), 0)
        if impl_id < 0:
            continue
        implementers[str(impl_id)] = {
            "vendor": row.group(3),
            "parts": parts_by_symbol.get(row.group(2), {}),
        }
    return implementers


# --------------------------------------------------------------------------
# tabla de sockets de CPU-X: struct Package_DB
# --------------------------------------------------------------------------

_SOCKET_ROW = re.compile(
    r"\{\s*(NULL|\"(?:[^\"\\]|\\.)*\")\s*,"
    r"\s*(NULL|\"(?:[^\"\\]|\\.)*\")\s*,"
    r"\s*(NULL|\"(?:[^\"\\]|\\.)*\")\s*\}"
)


def parse_socket_table(source: str, declaration: str) -> list[dict]:
    body = extract_array(strip_comments(source), declaration)
    rows = []
    for m in _SOCKET_ROW.finditer(body):
        codename, model, socket = (unquote(g) for g in m.groups())
        if socket is None:
            continue                   # centinela de fin de tabla
        rows.append({"codename": codename, "model": model, "socket": socket})
    return rows


# --------------------------------------------------------------------------
# obtención de las fuentes
# --------------------------------------------------------------------------


def git(*args: str, cwd: pathlib.Path | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def ensure_source(name: str, cache: pathlib.Path, offline: bool) -> pathlib.Path:
    path = cache / name
    if path.exists():
        if not offline:
            print(f"  actualizando {name}…", file=sys.stderr)
            try:
                # La caché puede venir de cuando la fuente era otra: que
                # apunte siempre a la de `REPOS`.
                git("remote", "set-url", "origin", REPOS[name], cwd=path)
                git("fetch", "--depth", "1", "origin", cwd=path)
                git("reset", "--hard", "FETCH_HEAD", cwd=path)
            except subprocess.CalledProcessError as exc:
                print(f"  aviso: no se pudo actualizar {name} ({exc}); sigo con la copia local",
                      file=sys.stderr)
        return path
    if offline:
        raise SystemExit(f"no hay copia de {name} en {path} y se pidió --offline")
    print(f"  clonando {name}…", file=sys.stderr)
    cache.mkdir(parents=True, exist_ok=True)
    git("clone", "--depth", "1", REPOS[name], str(path))
    return path


def provenance(path: pathlib.Path, url: str) -> dict:
    return {
        "repo": url,
        "commit": git("rev-parse", "--short", "HEAD", cwd=path),
        "date": git("log", "-1", "--format=%cd", "--date=short", cwd=path),
    }


# --------------------------------------------------------------------------
# intel-family.h del kernel: familia y modelo -> microarquitectura
# --------------------------------------------------------------------------

# Una etiqueta fija y no `master`: lo que se genera tiene que poder repetirse.
# Una generación nueva de Intel es subir esto y volver a generar.
KERNEL_TAG = "v7.3"
KERNEL_REPO = "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"
INTEL_FAMILY = "arch/x86/include/asm/intel-family.h"

_IFM = re.compile(r"^#define\s+INTEL_(\w+)\s+IFM\(\s*(\d+)\s*,\s*(0x[0-9A-Fa-f]+|\d+)\s*\)"
                  r"\s*(?:/\*\s*(.*?)\s*\*/)?", re.M)
# El segmento de mercado que el kernel pone al final del nombre: `_L` portátil,
# `_X` servidor… No es parte del nombre en clave.
_SEGMENTOS = {"L", "G", "X", "D", "EP", "EX", "H", "U", "M", "P", "S", "R", "N", "NNPI"}
# Prefijos de familia: de «CORE2_MEROM» el nombre es «Merom».
_PREFIJOS = ("PENTIUM_III_", "PENTIUM_II_", "PENTIUM_M_", "PENTIUM_", "CORE2_", "CORE_", "P4_")
# Solo se parte por estas palabras, y solo al final: «HASWELL» no es «Has Well»
# ni «LAKEFIELD» es «Lake Field».
_PALABRA_FINAL = re.compile(r"^(.+?)(LAKE|BRIDGE|RAPIDS|FOREST)$")
# Los que Intel escribe de otra forma.
_COMO_SE_ESCRIBEN = {"SKYLAKE": "Skylake", "P4_CEDARMILL": "Cedar Mill",
                     "P4_PRESCOTT_2M": "Prescott-2M"}
# El kernel usa el mismo modelo para varias plataformas: 0x9E es Kaby Lake,
# Coffee Lake y Coffee Lake Refresh; 0x8E, también Whiskey y Amber Lake; 0x55,
# Skylake-SP y Cascade Lake. Con ese nombre se acertaría la mitad de las
# veces, así que no se usa.
_COMPARTIDOS = {"KABYLAKE", "KABYLAKE_L", "SKYLAKE_X"}
# Antes de Nehalem el kernel nombra el núcleo y no la plataforma: 0x0F es
# «Merom» también en un Conroe de sobremesa, y 0x17 «Penryn» en un Wolfdale.
# Todo eso lo tiene libcpuid con su nombre de verdad.
_ANTERIORES = ("PENTIUM_", "CORE_", "CORE2_", "P4_")


def nombre_de_intel(simbolo: str) -> tuple[str, str]:
    """«PANTHERLAKE_L» -> («Panther Lake», «L»); «CORE2_MEROM» -> («Merom», «»)."""
    partes = simbolo.split("_")
    segmento = ""
    if simbolo in _COMO_SE_ESCRIBEN:
        return _COMO_SE_ESCRIBEN[simbolo], ""
    if len(partes) > 1 and partes[-1] in _SEGMENTOS:
        segmento = partes.pop()
    base = "_".join(partes)
    for prefijo in _PREFIJOS:
        if base.startswith(prefijo) and base != prefijo.rstrip("_"):
            base = base[len(prefijo):]
            break
    palabras = []
    for trozo in base.split("_"):
        if encaje := _PALABRA_FINAL.match(trozo):
            palabras += [encaje.group(1).capitalize(), encaje.group(2).capitalize()]
        else:
            palabras.append(trozo.capitalize() if not trozo[:1].isdigit() else trozo)
    nombre = " ".join(palabras) if palabras else simbolo
    return _COMO_SE_ESCRIBEN.get(base, nombre), segmento


def parse_intel_family(source: str) -> list[dict]:
    """Los núcleos grandes de `intel-family.h`, con su microarquitectura.

    Fuera los Atom y los Xeon Phi: el kernel los nombra por el núcleo
    («GRACEMONT») y no por la plataforma, y eso no es un nombre en clave que
    se pueda poner junto a «Comet Lake» sin confundir.
    """
    filas = []
    for simbolo, familia, modelo, comentario in _IFM.findall(source):
        if (simbolo.startswith(("ATOM_", "XEON_PHI_", *_ANTERIORES))
                or simbolo.endswith(("_START", "_LAST"))
                or simbolo in _COMPARTIDOS or int(familia) < 6):
            continue
        nombre, segmento = nombre_de_intel(simbolo)
        filas.append({"family": int(familia), "model": int(modelo, 0), "name": nombre,
                      "segment": segmento, "cores": comentario or None,
                      "define": f"INTEL_{simbolo}"})
    if not filas:
        raise LookupError("intel-family.h salió vacío; ¿cambió el formato?")
    return filas


def kernel_file(path: str, cache: pathlib.Path, offline: bool) -> str:
    """Un archivo del kernel en `KERNEL_TAG`, guardado en la caché."""
    import urllib.request
    destino = cache / "linux" / KERNEL_TAG / path
    if destino.is_file():
        return destino.read_text(encoding="utf-8")
    if offline:
        raise SystemExit(f"no hay copia de {path} ({KERNEL_TAG}) en {destino} y se pidió --offline")
    url = f"{KERNEL_REPO}/plain/{path}?h={KERNEL_TAG}"
    print(f"  bajando {path} de {KERNEL_TAG}…", file=sys.stderr)
    # kernel.org contesta 403 al User-Agent de serie de urllib.
    pedido = urllib.request.Request(url, headers={"User-Agent": "silux-gen-cpu-db"})
    with urllib.request.urlopen(pedido, timeout=60) as respuesta:
        texto = respuesta.read().decode("utf-8")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return texto


# --------------------------------------------------------------------------
# amd.com: the official specifications table
# --------------------------------------------------------------------------

AMD_SPECS_URL = "https://www.amd.com/en/products/specifications/processors.html"
# amd.com uses these as the "former codename" of whole families: they don't
# name a chip, and showing them would read as if they did.
_AMD_NOT_A_CODENAME = {"", "none", "[]", "athlon legacy", "fx legacy", "phenom",
                       "sempron", "threadripper"}
_TRADEMARKS = re.compile(r"\s*(™|®|\(TM\)|\(R\))\s*", re.IGNORECASE)


def fetch_amd_specs(cache: pathlib.Path, offline: bool) -> str:
    """The amd.com table, as the page that carries it in a JSON attribute."""
    import urllib.request

    path = cache / "amd" / "processors.html"
    if offline:
        if not path.is_file():
            raise SystemExit(f"no hay copia de la tabla de amd.com en {path} y se pidió --offline")
        return path.read_text(encoding="utf-8")
    print("  bajando la tabla de amd.com…", file=sys.stderr)
    request = urllib.request.Request(AMD_SPECS_URL, headers={"User-Agent": "Mozilla/5.0 silux-gen-cpu-db"})
    with urllib.request.urlopen(request, timeout=60) as response:
        page = response.read().decode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return page


def _amd_value(item: dict, key: str):
    field = item.get("elements", {}).get(key)
    value = None if field is None else field.get("value", field.get("values"))
    if isinstance(value, list):
        value = value[0] if len(value) == 1 else (", ".join(map(str, value)) or None)
    return str(value).strip() if value not in (None, "") else None


def _amd_mhz(item: dict, key: str) -> "int | None":
    """A number field («3500.0», «95») rounded to a whole, or None."""
    try:
        return round(float(_amd_value(item, key) or ""))
    except ValueError:
        return None


def parse_amd_specs(page: str) -> list[dict]:
    """One row per model: codename, socket and node as amd.com gives them."""
    import html as html_lib
    sys.path.insert(0, str(ROOT))
    from silux.db import amd_model_key

    raw = re.search(r'data-json="([^"]*)"', page)
    if raw is None:
        raise LookupError("la tabla de amd.com no trae su JSON: ha cambiado de forma")
    rows: dict[str, dict] = {}
    for item in json.loads(html_lib.unescape(raw.group(1))).get("items", []):
        name = _amd_value(item, "name")
        if not name:
            continue
        codename = _amd_value(item, "formerCodename")
        if codename and codename.lower() in _AMD_NOT_A_CODENAME:
            codename = None
        if codename:
            # «Granite Ridge AM5»: the socket goes in its own field.
            codename = re.sub(r"\s+AM[45]$", "", codename)
        key = amd_model_key(name)
        # The same model is listed twice for a few APUs (boxed and tray):
        # the first one is enough.
        rows.setdefault(key, {
            "model": key,
            "name": " ".join(_TRADEMARKS.sub(" ", name).split()),
            "codename": codename,
            "socket": _amd_value(item, "cpuSocket"),
            "node": _amd_value(item, "processorTechnologyForCpuCores"),
            # In MHz; a model listed with a base clock and no boost has none.
            "base_mhz": _amd_mhz(item, "baseClock"),
            "boost_mhz": _amd_mhz(item, "maxBoostClock"),
            # In °C. Comparable with what k10temp reads only from Zen 2 on;
            # whoever reads it decides by family.
            "tjmax_c": _amd_mhz(item, "maxOperatingTemperatureTjmax"),
            "source": (item.get("productPages") or {}).get("en") or AMD_SPECS_URL,
        })
    if len(rows) < 100:
        raise LookupError(f"la tabla de amd.com trae solo {len(rows)} modelos: ¿ha cambiado de forma?")
    return sorted(rows.values(), key=lambda row: row["model"])


# --------------------------------------------------------------------------
# cpuid by Todd Allen: process node by family and model
# --------------------------------------------------------------------------

# A fixed release, so what is generated can be repeated; a new one is
# raising the version and the hash (the error says the new one) and
# regenerating.
CPUID_VERSION = "20260503"
CPUID_SHA256 = "8ee10fb48d4aa20c484a75d6852883710286ed2975c314bda6d0b0383908cbfe"
CPUID_URL = "https://etallen.com/cpuid.html"
# etallen.com answers GitHub's runners with an HTML page instead of the
# tarball; Debian keeps the same file byte for byte. The hash is what makes
# either one trustworthy.
CPUID_TARBALLS = (
    f"https://etallen.com/cpuid/cpuid-{CPUID_VERSION}.src.tar.gz",
    f"https://deb.debian.org/debian/pool/main/c/cpuid/cpuid_{CPUID_VERSION}.orig.tar.gz",
)

# One line of `decode_uarch_intel` / `decode_uarch_amd`:
#   FMQ (    0, 6, 12,12,     Ha, *u = "Cougar Cove", ...  *p = "Intel 18A");
_UARCH_LINE = re.compile(
    r"^\s*(FMS|FMm|FM|FMSQ|FMmQ|FMQ)\s*\(\s*([^*]*?)\s*,\s*\*u\s*=\s*\"([^\"]*)\"(.*?)\);", re.M)
_PROCESS = re.compile(r"\*p\s*=\s*\"([^\"]*)\"")


def fetch_cpuid_source(cache: pathlib.Path, offline: bool) -> str:
    """cpuid.c of the pinned release, from its tarball."""
    import io
    import tarfile
    import urllib.request

    path = cache / "cpuid" / CPUID_VERSION / "cpuid.c"
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    if offline:
        raise SystemExit(f"no hay copia de cpuid {CPUID_VERSION} en {path} y se pidió --offline")
    print(f"  bajando cpuid {CPUID_VERSION}…", file=sys.stderr)
    failures = []
    for url in CPUID_TARBALLS:
        request = urllib.request.Request(url, headers={"User-Agent": "silux-gen-cpu-db"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
        except OSError as error:
            failures.append(f"{url}: {error}")
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest == CPUID_SHA256:
            break
        failures.append(f"{url}: no es el tar esperado (sha256 {digest}, empieza por {data[:16]!r})")
    else:
        raise SystemExit(f"no se pudo bajar cpuid {CPUID_VERSION}:\n  " + "\n  ".join(failures))
    archive = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    member = next(m for m in archive.getmembers() if m.name.endswith("/cpuid.c"))
    text = archive.extractfile(member).read().decode("utf-8", errors="replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def _function_body(source: str, name: str) -> str:
    start = source.index(f"\n{name}(")
    end = source.index("\n}\n", start)
    return source[start:end]


def parse_cpuid_nodes(source: str) -> list[dict]:
    """Process node by vendor, family and model, from cpuid's uarch tables.

    Only what doesn't depend on more than family, model and stepping: the
    qualified rows (hybrid core type, brand) agree on the node for a model,
    and when they don't, the model is left out.
    """
    found: dict[tuple, set] = {}
    for vendor, function in (("GenuineIntel", "decode_uarch_intel"),
                             ("AuthenticAMD", "decode_uarch_amd")):
        for macro, args, _uarch, rest in _UARCH_LINE.findall(_function_body(source, function)):
            process = _PROCESS.search(rest)
            numbers = [a.strip() for a in args.split(",")]
            if process is None or len(numbers) < 4 or not all(n.isdigit() for n in numbers[:4]):
                continue
            xf, f, xm, m = (int(n) for n in numbers[:4])
            stepping = int(numbers[4]) if macro.startswith("FMS") else -1
            family = f + xf if f == 15 else f
            first = (xm << 4) + (m & 0x8 if macro.startswith("FMm") else m)
            last = first + 7 if macro.startswith("FMm") else first
            # «939-pin, 90nm»: the old AMD rows mix the socket in; the node is
            # the part after the comma.
            node = process.group(1).split(",")[-1].strip()
            found.setdefault((vendor, family, first, last, stepping), set()).add(node)
    rows = [{"vendor": vendor, "family": family, "model_from": first, "model_to": last,
             "stepping": stepping, "node": nodes.pop()}
            for (vendor, family, first, last, stepping), nodes in sorted(found.items())
            if len(nodes) == 1]
    if len(rows) < 50:
        raise LookupError(f"las tablas de cpuid dieron {len(rows)} filas: ¿ha cambiado el formato?")
    return rows


# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", type=pathlib.Path, default=DEFAULT_CACHE,
                        help=f"dónde guardar los clones (por defecto {DEFAULT_CACHE})")
    parser.add_argument("--libcpuid", type=pathlib.Path, help="ruta a un clon de libcpuid ya existente")
    parser.add_argument("--cpux", type=pathlib.Path, help="ruta a un clon de CPU-X ya existente")
    parser.add_argument("--offline", action="store_true", help="no tocar la red")
    parser.add_argument("--out", type=pathlib.Path, default=ROOT / "silux" / "db" / "cpu_ids.json")
    args = parser.parse_args()

    print("Obteniendo fuentes:", file=sys.stderr)
    libcpuid = args.libcpuid or ensure_source("libcpuid", args.cache, args.offline)
    cpux = args.cpux or ensure_source("cpu-x", args.cache, args.offline)

    print("Parseando tablas:", file=sys.stderr)
    intel_src = (libcpuid / "libcpuid" / "recog_intel.c").read_text(encoding="utf-8")
    amd_src = (libcpuid / "libcpuid" / "recog_amd.c").read_text(encoding="utf-8")
    arm_src = (libcpuid / "libcpuid" / "recog_arm.c").read_text(encoding="utf-8")
    databases_src = (cpux / "src" / "core" / "databases.h").read_text(encoding="utf-8")
    intel_family = parse_intel_family(kernel_file(INTEL_FAMILY, args.cache, args.offline))
    amd_models = parse_amd_specs(fetch_amd_specs(args.cache, args.offline))
    cpuid_nodes = parse_cpuid_nodes(fetch_cpuid_source(args.cache, args.offline))

    x86 = {
        "GenuineIntel": parse_x86_table(intel_src, "match_entry_t cpudb_intel[]"),
        "AuthenticAMD": parse_x86_table(amd_src, "match_entry_t cpudb_amd[]"),
    }
    arm = parse_arm_tables(arm_src)
    sockets = {
        "GenuineIntel": parse_socket_table(databases_src, "Package_DB package_intel[]"),
        "AuthenticAMD": parse_socket_table(databases_src, "Package_DB package_amd[]"),
    }

    payload = {
        "schema": 1,
        "sources": {
            "libcpuid": provenance(libcpuid, REPOS["libcpuid"]),
            "cpu-x": provenance(cpux, REPOS["cpu-x"]),
            "linux": {"repo": KERNEL_REPO, "tag": KERNEL_TAG, "file": INTEL_FAMILY},
            "amd.com": {"repo": AMD_SPECS_URL},
            "cpuid": {"repo": CPUID_URL, "version": CPUID_VERSION},
        },
        "counts": {
            "x86_intel": len(x86["GenuineIntel"]),
            "x86_amd": len(x86["AuthenticAMD"]),
            "arm_implementers": len(arm),
            "arm_parts": sum(len(v["parts"]) for v in arm.values()),
            "sockets": sum(len(v) for v in sockets.values()),
            "intel_family": len(intel_family),
            "amd_models": len(amd_models),
            "cpuid_nodes": len(cpuid_nodes),
        },
        "x86": x86,
        "arm": arm,
        "sockets": sockets,
        # Lo que libcpuid no tiene todavía: la microarquitectura de Intel por
        # familia y modelo, del kernel. `silux/db` la mira solo cuando la
        # tabla de libcpuid no reconoce el procesador.
        "intel_family": intel_family,
        # AMD's own specifications, by model: they fill in what libcpuid
        # doesn't know and name the chips it doesn't have.
        "amd_models": amd_models,
        # cpuid's process node by family and model: for chips the other
        # sources name but don't give a node for (Panther Lake, from the
        # kernel).
        "cpuid_nodes": cpuid_nodes,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                        encoding="utf-8")

    size_kb = args.out.stat().st_size / 1024
    print(f"\nEscrito {args.out} ({size_kb:.0f} KB)", file=sys.stderr)
    for key, value in payload["counts"].items():
        print(f"  {key:<18} {value:>5}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
