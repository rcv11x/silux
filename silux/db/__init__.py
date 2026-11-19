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

import dataclasses
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


def _casa_la_marca(entry: dict, brand: str) -> bool:
    pattern, pattern_score = entry.get("bp"), entry.get("bs", 0)
    return bool(pattern and pattern_score > 0 and _compile_pattern(pattern).search(brand))


def _del_kernel(vendor_id: str, ext_family: int, ext_model: int) -> Optional[dict]:
    """La microarquitectura de Intel por familia y modelo, de `intel-family.h`."""
    if vendor_id != "GenuineIntel":
        return None
    for fila in load().get("intel_family", ()):
        if fila["family"] == ext_family and fila["model"] == ext_model:
            return fila
    return None


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

    if _casa_la_marca(entry, brand):
        total += entry["bs"]
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
    empatadas: list[dict] = []
    for entry in table:
        value = _score(entry, probe, clean_brand)
        if value > best_score:
            best, best_score, empatadas = entry, value, [entry]
        elif value == best_score:
            empatadas.append(entry)

    if best is None:
        return Identification(codename=None, technology=None, score=0, matched=False)

    # libcpuid usa «Unknown …» como comodín para lo que no reconoce. Enseñarlo
    # como nombre en clave sería contestar «no lo sé» con cara de saberlo: mejor
    # dar el procesador por no identificado y que la sección lo explique.
    nombre = _sin_desempatar_por_el_orden(best["name"], empatadas)
    reconocido = (nombre is not None and best_score > 0
                  and not nombre.lower().startswith("unknown"))
    # Una fila sin modelo extendido es de los procesadores que no lo tienen
    # (el extendido y el base coinciden: un Dothan, un Presler). Si este sí
    # lo tiene y la marca tampoco casa, la fila solo ha acertado la familia y
    # el modelo base, que no dicen qué procesador es: un Panther Lake (6,
    # 0xCC) salía «Atom (Cedarview)» por la fila de familia 6 y modelo 12. Si
    # el kernel conoce ese modelo, manda él.
    if (reconocido and best["xm"] < 0 and ext_model != model
            and not _casa_la_marca(best, clean_brand)):
        if (fila := _del_kernel(vendor_id, ext_family, ext_model)) is not None:
            return Identification(codename=fila["name"], technology=None,
                                  score=1, matched=True)
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
        # Y después, la de Intel del kernel, que va por delante de libcpuid.
        # Da el nombre en clave y nada más: el nodo no sale de ahí.
        if (fila := _del_kernel(vendor_id, ext_family, ext_model)) is not None:
            return Identification(codename=fila["name"], technology=None,
                                  score=1, matched=True)
    return Identification(
        codename=nombre if reconocido else None,
        technology=best.get("tech") if reconocido else None,
        score=best_score,
        matched=reconocido,
    )


# El nombre en clave de verdad, que varias entradas comparten: «Ryzen 5
# (Cezanne)» y «Ryzen 9 PRO (Cezanne)» describen el mismo silicio y solo se
# diferencian en a qué gama se vendió cada pieza.
_ENTRE_PARENTESIS = re.compile(r"\(([^)]+)\)\s*$")


def _sin_desempatar_por_el_orden(nombre: str,
                                 empatadas: list[dict]) -> Optional[str]:
    """Lo que se puede afirmar cuando varias entradas puntúan igual.

    Las ocho entradas de Cezanne llevan el mismo silicio —familia, modelo y
    extensiones idénticas— y solo se distinguen por el patrón de la cadena de
    marca, que en todas termina en H o U: son las de portátil. Un 5600G, que
    es de sobremesa y acaba en G, no casa con ninguna, así que las ocho quedan
    empatadas con la puntuación del silicio y ganaba la primera del archivo.
    Salía «Ryzen 9 PRO (Cezanne)» en un Ryzen 5 de sobremesa, y el orden de la
    tabla no es un criterio: es el orden en que las escribió otro.

    Lo único cierto cuando empatan es lo que todas dicen igual, que es el
    nombre en clave entre paréntesis. Se devuelve ese a secas; y si ni en eso
    coinciden —el mismo silicio se vendió como Cezanne y como Barceló—, se
    devuelve `None` para que decida la tabla por rangos, que va por familia y
    no por gama comercial.
    """
    if len(empatadas) < 2:
        return nombre
    nombres = {e["name"] for e in empatadas}
    if len(nombres) == 1:
        return nombre
    claves = {m.group(1) for n in nombres if (m := _ENTRE_PARENTESIS.search(n))}
    # Si no comparten uno solo, no hay nada que se pueda afirmar de todas a la
    # vez, y quedarse con una sería volver a elegir por el orden del archivo.
    return claves.pop() if len(claves) == 1 else None


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


# --------------------------------------------------------------------------
# máximo oficial de memoria
# --------------------------------------------------------------------------

# El modelo de Intel dentro de la cadena de marca: «i5-10400» en «Intel(R)
# Core(TM) i5-10400 CPU @ 2.90GHz». Entero, con su letra: «i5-10400H» es un
# portátil y no puede casar con la fila del de sobremesa.
_MODELO_INTEL = re.compile(r"\b(i[3579]-\d{3,5}[A-Z]{0,2}\d?)\b")
# La primera generación escribe el modelo de otra forma en CPUID: «Core(TM)
# i7 CPU 920», «i5 CPU M 520» (portátil), y su ficha «i7-920», «i5-520M».
_MODELO_INTEL_1 = re.compile(r"\b(i[3579]) CPU\s+(?:([A-Z]{1,2})\s+)?(\d{3})\b")
# Las Core Ultra y las Core 3/5/7, sin guion: «Core(TM) Ultra 7 155H».
_MODELO_INTEL_SIN_I = re.compile(
    r"\bCore(?:\(TM\)|™)?\s+(Ultra\s+)?([3579])\s+(?:Processor\s+)?(\d{3}[A-Z]{0,2})\b")
# Lo que sobra alrededor del modelo de AMD, en la tabla del fabricante
# («AMD Ryzen™ 7 5800X3D») y en la cadena de CPUID («AMD Ryzen 7 5800X3D
# 8-Core Processor», «… with Radeon Graphics»).
_RUIDO_AMD = re.compile(
    r"\(R\)|\(TM\)|™|®|^AMD\s+|\s+\d+-Core Processor.*$|\s+(with|w/) Radeon.*$"
    r"|\s*\(OEM Only\)|\s+Processor\b",
    re.IGNORECASE)


def normalize_cpu_model(name: str) -> str:
    """El modelo por el que se busca en la tabla de máximos de memoria.

    La misma función para la tabla (al generarla) y para la cadena de marca
    del procesador (al buscar): «i5-10400» o «Ryzen 7 5800X3D».
    """
    nombre = name or ""
    if (encaje := _MODELO_INTEL.search(nombre)):
        return encaje.group(1)
    if (encaje := _MODELO_INTEL_1.search(nombre)):
        gama, letra, numero = encaje.groups()
        return f"{gama}-{numero}{letra or ''}"
    if (encaje := _MODELO_INTEL_SIN_I.search(nombre)):
        ultra, gama, numero = encaje.groups()
        return f"Core {'Ultra ' if ultra else ''}{gama} {numero}"
    return " ".join(_RUIDO_AMD.sub("", nombre).split())


@dataclasses.dataclass(frozen=True)
class MemoryLimit:
    """El máximo oficial de memoria de un procesador para estos módulos."""

    model: str
    mts: int
    source: str
    # La disposición con la que vale, en AMD: «2x1R» son dos módulos de un
    # rango. None si el fabricante da una sola cifra.
    layout: Optional[str] = None


@functools.lru_cache(maxsize=1)
def _load_memory_limits() -> dict[str, dict]:
    path = pathlib.Path(__file__).parent / "memory_limits.json"
    try:
        with path.open(encoding="utf-8") as fh:
            filas = json.load(fh).get("cpus", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {modelo: fila for fila in filas for modelo in fila["models"]}


def memory_layout(ranks: tuple[Optional[int], ...]) -> Optional[str]:
    """«2x1R» para dos módulos de un rango; None si no se puede decir.

    `ranks`: los rangos de cada módulo puesto. Con rangos distintos, o alguno
    sin saber, no hay disposición de la ficha de AMD que case.
    """
    rangos = set(ranks)
    if not ranks or len(rangos) != 1 or None in rangos:
        return None
    return f"{len(ranks)}x{rangos.pop()}R"


def memory_limit(brand: str, memory_type: Optional[str],
                 ranks: tuple[Optional[int], ...] = ()) -> Optional[MemoryLimit]:
    """El máximo oficial de memoria de este procesador con estos módulos, o None.

    Solo lo que dice la tabla, para ese modelo exacto y ese tipo de memoria.
    En AMD la cifra depende de la disposición de los módulos (`ranks`, los
    rangos de cada módulo puesto): sin una que case con la ficha no hay
    máximo conocido, y quien llama sigue sin afirmar nada.
    """
    if not brand or not memory_type:
        return None
    modelo = normalize_cpu_model(brand)
    fila = _load_memory_limits().get(modelo)
    if fila is None or memory_type not in fila["types"]:
        return None
    cifra = fila["types"][memory_type]
    if isinstance(cifra, int):
        return MemoryLimit(modelo, cifra, fila["source"])
    disposicion = memory_layout(tuple(ranks))
    if disposicion is None or disposicion not in cifra:
        return None
    return MemoryLimit(modelo, cifra[disposicion], fila["source"], disposicion)


# Los Intel de antes de Nehalem (2008) que llevan el controlador de memoria
# en el chipset de la placa (el northbridge) y no en el procesador: los
# Pentium 4 y Pentium D de 64 bits (familia 15) y los Core 2 de familia 6
# —Merom y Conroe (0x0F), Merom-L (0x16), Penryn, Wolfdale y Yorkfield
# (0x17), Dunnington (0x1D)—. Los Atom de entonces no entran: Diamondville
# lo tiene en el chipset y Pineview ya integrado, con modelos que se cruzan.
_CONTROLADOR_EN_EL_CHIPSET = {0x0F, 0x16, 0x17, 0x1D}


def memory_controller_in_chipset(cpu_type) -> bool:
    """Si la memoria de este equipo la controla el chipset y no el procesador.

    Entonces no hay «máximo del procesador» del que hablar: hasta dónde llega
    la memoria lo decide la placa.
    """
    if getattr(cpu_type, "vendor", "") != "Intel":
        return False
    familia, modelo = cpu_type.disp_family, cpu_type.disp_model
    return familia == 15 or (familia == 6 and modelo in _CONTROLADOR_EN_EL_CHIPSET)
