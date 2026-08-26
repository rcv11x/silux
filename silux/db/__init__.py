"""Identificación del procesador contra la base de datos generada.

El algoritmo es el de libcpuid, reimplementado: a cada fila de la tabla se le
da una puntuación según cuántos campos coinciden con el procesador real, y
gana la más alta. No es una búsqueda exacta porque no puede serlo: dos CPUs
distintas comparten familia y modelo, y solo el número de núcleos, el tamaño
de caché o la cadena de marca las separan.

Pesos (de libcpuid): 2 puntos por familia, modelo, stepping, familia
extendida, modelo extendido y número de núcleos; 1 punto por tamaño de L2 y
de L3; y el peso propio de cada patrón de marca, que es el que desempata
entre modelos de la misma generación.
"""

from __future__ import annotations

import functools
import json
import pathlib
import re
from typing import Any, Optional

_DB_PATH = pathlib.Path(__file__).parent / "cpu_ids.json"

_FIELD_WEIGHTS = (
    ("f", 2), ("m", 2), ("s", 2), ("xf", 2), ("xm", 2),
    ("nc", 2), ("l2", 1), ("l3", 1),
)


class DatabaseMissing(FileNotFoundError):
    """No hay base de datos generada. Se arregla con tools/gen_cpu_db.py."""


@functools.lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    try:
        with _DB_PATH.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise DatabaseMissing(
            f"falta {_DB_PATH}. Genérala con:  python3 tools/gen_cpu_db.py"
        ) from exc


def available() -> bool:
    return _DB_PATH.exists()


def provenance() -> dict[str, Any]:
    """De qué commit de qué repositorio salieron los datos."""
    return load().get("sources", {})


# --------------------------------------------------------------------------
# patrones de marca
# --------------------------------------------------------------------------


@functools.lru_cache(maxsize=2048)
def _compile_pattern(pattern: str) -> re.Pattern[str]:
    """Traduce el mini-lenguaje de libcpuid a una expresión regular.

    `.` = cualquier carácter, `#` = cualquier dígito, `[abc]` = uno de esos.
    No hay rangos: dentro de los corchetes todo es literal.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == ".":
            out.append(".")
        elif char == "#":
            out.append(r"\d")
        elif char == "[":
            close = pattern.find("]", i)
            if close < 0:
                out.append(re.escape(char))
            else:
                chars = pattern[i + 1 : close]
                safe = chars.replace("\\", "\\\\").replace("]", "\\]").replace("^", "\\^")
                if "-" in safe:                    # el guion solo es literal al final
                    safe = safe.replace("-", "") + "-"
                out.append(f"[{safe}]")
                i = close
        else:
            out.append(re.escape(char))
        i += 1
    return re.compile("".join(out))


_NOISE = re.compile(r"\b(?:CPU|Processor)\b")


def normalize_brand(brand: str) -> str:
    """Quita las palabras de relleno igual que hace libcpuid antes de comparar."""
    return " ".join(_NOISE.sub("", brand).split())


# --------------------------------------------------------------------------
# búsqueda x86
# --------------------------------------------------------------------------


class Identification(dict):
    """Resultado de una búsqueda: nombre en clave, nodo y confianza."""

    @property
    def codename(self) -> Optional[str]:
        return self.get("codename")

    @property
    def technology(self) -> Optional[str]:
        return self.get("technology")

    @property
    def score(self) -> int:
        return self.get("score", 0)

    @property
    def matched(self) -> bool:
        return bool(self.get("matched"))


# La familia y el modelo identifican el silicio: los pone el propio procesador
# y no admiten interpretación. Si una entrada declara uno de ellos y no
# coincide, esa entrada no es de este chip por mucho que su nombre comercial se
# parezca, así que queda descartada en vez de sumar puntos por lo demás.
#
# Sin esto, un Ryzen 7 7445HS (modelo 0x7C) se identificaba como «Dragon Range»
# porque el patrón «Ryzen 7 7###H» de una entrada del modelo 0x61 le casaba el
# nombre. Salía un nombre en clave, una litografía y un encapsulado que eran de
# otro chip, y con toda la seguridad del mundo. Un dato ausente se ve; uno
# inventado que suena bien, no.
_DISCRIMINANTES = ("f", "xf", "xm")


def _score(entry: dict, probe: dict, brand: str) -> int:
    for key in _DISCRIMINANTES:
        declarado = entry.get(key, -1)
        if declarado >= 0 and declarado != probe.get(key):
            return 0

    total = 0
    for key, weight in _FIELD_WEIGHTS:
        expected = entry[key]
        if expected >= 0 and expected == probe.get(key):
            total += weight

    pattern, pattern_score = entry.get("bp"), entry.get("bs", 0)
    if pattern and pattern_score > 0 and _compile_pattern(pattern).search(brand):
        total += pattern_score
    return total


def identify_x86(
    *,
    vendor_id: str,
    family: int,
    model: int,
    stepping: int,
    ext_family: int,
    ext_model: int,
    cores: int,
    brand: str = "",
    l2_kb: int = -1,
    l3_kb: int = -1,
) -> Identification:
    """Busca el procesador en la tabla del fabricante y devuelve el mejor match."""
    table = load()["x86"].get(vendor_id)
    if not table:
        return Identification(codename=None, technology=None, score=0, matched=False)

    probe = {
        "f": family, "m": model, "s": stepping,
        "xf": ext_family, "xm": ext_model,
        "nc": cores, "l2": l2_kb, "l3": l3_kb,
    }
    clean_brand = normalize_brand(brand)

    best: Optional[dict] = None
    best_score = -1
    for entry in table:
        value = _score(entry, probe, clean_brand)
        if value > best_score:
            best, best_score = entry, value

    if best is None:
        return Identification(codename=None, technology=None, score=0, matched=False)

    # libcpuid usa «Unknown …» como comodín para lo que no reconoce. Enseñarlo
    # como nombre en clave sería contestar «no lo sé» con cara de saberlo: mejor
    # dar el procesador por no identificado y que la sección lo explique.
    nombre = best["name"]
    reconocido = best_score > 0 and not nombre.lower().startswith("unknown")
    if not reconocido:
        # La tabla por modelo no lo conoce. Antes de darse por vencido, la
        # tabla por rangos, que cubre las familias enteras.
        if regla := _por_familia(vendor_id, ext_family, ext_model):
            return Identification(
                codename=regla["name"],
                technology=regla.get("tech"),
                score=1,
                matched=True,
            )
    return Identification(
        codename=nombre if reconocido else None,
        technology=best.get("tech") if reconocido else None,
        score=best_score,
        matched=reconocido,
    )


def identify_arm(implementer: int, part_num: int) -> Identification:
    arm = load().get("arm", {})
    impl = arm.get(str(implementer))
    if not impl:
        return Identification(codename=None, technology=None, score=0, matched=False)
    part = impl["parts"].get(str(part_num))
    if not part:
        return Identification(
            codename=None, technology=None, score=0, matched=False, vendor=impl["vendor"]
        )
    return Identification(
        codename=part["codename"] or part["name"],
        technology=part.get("tech"),
        score=1,
        matched=True,
        vendor=impl["vendor"],
        part_name=part["name"],
    )


# --------------------------------------------------------------------------
# socket / encapsulado
# --------------------------------------------------------------------------


def find_socket(vendor_id: str, codename: Optional[str], brand: str) -> Optional[str]:
    """Busca el encapsulado en tres pasadas, de más específica a más general.

    1. La tabla por modelo concreto heredada de CPU-X: exacta pero diminuta.
    2. Nuestra tabla por microarquitectura: una regla cubre una generación
       entera, así que acierta con procesadores que nadie ha catalogado.
    3. Los sufijos de segmento: un "-U" o un "-H" en el nombre en clave
       significa BGA, y decir "soldado" es más útil que dejarlo en blanco.
    """
    if not codename and not brand:
        return None

    for entry in load().get("sockets", {}).get(vendor_id, ()):
        wants_codename = entry["codename"] is not None
        wants_model = entry["model"] is not None
        codename_ok = wants_codename and codename is not None and entry["codename"] in codename
        model_ok = wants_model and entry["model"] in brand

        if (codename_ok and model_ok) or (codename_ok and not wants_model) or (not wants_codename and model_ok):
            return entry["socket"]

    if not codename:
        return None

    overlay = _load_overlay()
    for rule in overlay.get("rules", ()):
        if rule["vendor"] == vendor_id and rule["match"] in codename:
            return rule["socket"]

    soldered = overlay.get("soldered_suffixes", {}).get(vendor_id, ())
    for marker in soldered:
        if marker in codename:
            return "BGA (soldado)"

    return None


@functools.lru_cache(maxsize=1)
def _load_overlay() -> dict[str, Any]:
    path = pathlib.Path(__file__).parent / "sockets.json"
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


@functools.lru_cache(maxsize=1)
def _load_families() -> list[dict]:
    """La tabla de microarquitecturas por rango de modelo."""
    path = pathlib.Path(__file__).parent / "families.json"
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh).get("rules", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _por_familia(vendor_id: str, ext_family: int, ext_model: int) -> Optional[dict]:
    """La microarquitectura de un procesador que la tabla por modelo no cubre.

    libcpuid va por modelo concreto y tarda meses en incorporar lo recién
    salido, así que un procesador nuevo se queda sin nombre en clave ni
    litografía. El fabricante, en cambio, documenta rangos enteros: toda la
    familia 19h de la 0x70 a la 0x7F es Phoenix. Una regla por rango cubre lo
    que vendrá, y como solo se consulta cuando la otra tabla no encuentra nada,
    nunca puede empeorar un dato que ya se sabía.
    """
    for regla in _load_families():
        if regla.get("vendor") != vendor_id or regla.get("family") != ext_family:
            continue
        if regla.get("from", 0) <= ext_model <= regla.get("to", -1):
            return regla
    return None
