"""Identifying the processor against the generated database.

libcpuid's algorithm, reimplemented: each table row gets a score by how many
fields match the real processor, and the highest wins. Not an exact lookup
because it can't be: two different CPUs share family and model, and only
the core count, the cache size or the brand string tell them apart.

Weights (libcpuid's): 2 points each for family, model, stepping, extended
family, extended model and core count; 1 point each for L2 and L3 size; and
each brand pattern's own weight, which breaks ties between models of the
same generation.
"""

from __future__ import annotations

import dataclasses
import functools
import json
import pathlib
import re
from typing import Any, Optional

_DB_PATH = pathlib.Path(__file__).parent / "cpu_ids.json"

# Who sends reports and has said they can be named. Only the author adds a
# name, and only with that person's permission: the About page, the README
# and the CHANGELOG's «Con informes de…» lines take theirs from here, and
# tests/test_thanks.py keeps the last two to it.
THANKS = pathlib.Path(__file__).parent / "thanks.json"

_FIELD_WEIGHTS = (
    ("f", 2), ("m", 2), ("s", 2), ("xf", 2), ("xm", 2),
    ("nc", 2), ("l2", 1), ("l3", 1),
)


class DatabaseMissing(FileNotFoundError):
    """No generated database. Fixed with tools/gen_cpu_db.py."""


@functools.lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    try:
        with _DB_PATH.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise DatabaseMissing(
            f"falta {_DB_PATH}. Genérala con:  python3 tools/gen_cpu_db.py"
        ) from exc


@functools.lru_cache(maxsize=1)
def thanks() -> tuple[str, ...]:
    """The names in thanks.json, as written there, once each."""
    try:
        names = json.loads(THANKS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    found: list[str] = []
    for name in names if isinstance(names, list) else ():
        if isinstance(name, str) and name.strip() and name.strip() not in found:
            found.append(name.strip())
    return tuple(found)


def available() -> bool:
    return _DB_PATH.exists()


def provenance() -> dict[str, Any]:
    """Which commit of which repository the data came from."""
    return load().get("sources", {})


# --------------------------------------------------------------------------
# brand patterns
# --------------------------------------------------------------------------


@functools.lru_cache(maxsize=2048)
def _compile_pattern(pattern: str) -> re.Pattern[str]:
    """Translate libcpuid's mini-language into a regular expression.

    `.` = any character, `#` = any digit, `[abc]` = one of those. No ranges:
    inside the brackets everything is literal.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        character = pattern[i]
        if character == ".":
            out.append(".")
        elif character == "#":
            out.append(r"\d")
        elif character == "[":
            close = pattern.find("]", i)
            if close < 0:
                out.append(re.escape(character))
            else:
                characters = pattern[i + 1 : close]
                safe = characters.replace("\\", "\\\\").replace("]", "\\]").replace("^", "\\^")
                if "-" in safe:                    # a hyphen is only literal at the end
                    safe = safe.replace("-", "") + "-"
                out.append(f"[{safe}]")
                i = close
        else:
            out.append(re.escape(character))
        i += 1
    return re.compile("".join(out))


_NOISE = re.compile(r"\b(?:CPU|Processor)\b")


def normalize_brand(brand: str) -> str:
    """Drop the filler words as libcpuid does before comparing."""
    return " ".join(_NOISE.sub("", brand).split())


# --------------------------------------------------------------------------
# x86 lookup
# --------------------------------------------------------------------------


class Identification(dict):
    """A lookup's result: codename, node and confidence."""

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


# Family and model identify the silicon: the processor itself sets them and
# they admit no interpretation. An entry that declares one of them and
# doesn't match isn't this chip, however alike its commercial name, so it is
# discarded instead of scoring points for the rest. Without this, a
# processor took the codename, node and package of another chip whose brand
# pattern its name happened to match. A missing datum shows; a made-up one
# that sounds right doesn't.
_DISTINGUISHING_FIELDS = ("f", "xf", "xm")


def _brand_matches(entry: dict, brand: str) -> bool:
    pattern, pattern_score = entry.get("bp"), entry.get("bs", 0)
    return bool(pattern and pattern_score > 0 and _compile_pattern(pattern).search(brand))


def _from_kernel(vendor_id: str, ext_family: int, ext_model: int) -> Optional[dict]:
    """Intel's microarchitecture by family and model, from `intel-family.h`."""
    if vendor_id != "GenuineIntel":
        return None
    for row in load().get("intel_family", ()):
        if row["family"] == ext_family and row["model"] == ext_model:
            return row
    return None


def _score(entry: dict, probe: dict, brand: str) -> int:
    for key in _DISTINGUISHING_FIELDS:
        declared = entry.get(key, -1)
        if declared >= 0 and declared != probe.get(key):
            return 0

    total = 0
    for key, weight in _FIELD_WEIGHTS:
        expected = entry[key]
        if expected >= 0 and expected == probe.get(key):
            total += weight

    if _brand_matches(entry, brand):
        total += entry["bs"]
    return total


def identify_x86(**probe) -> Identification:
    """Look the processor up in its maker's table and return the best match.

    When the chip is named but no source gives its node, cpuid's table by
    family and model fills it in (Panther Lake, named by the kernel).
    """
    ident = _identify_x86(**probe)
    if ident.matched and ident.technology is None:
        node = cpuid_node(probe["vendor_id"], probe["ext_family"], probe["ext_model"],
                          probe.get("stepping", -1))
        if node is not None:
            return Identification(codename=ident.codename, technology=node,
                                  score=ident.score, matched=True)
    return ident


def cpuid_node(vendor_id: str, ext_family: int, ext_model: int,
               stepping: int = -1) -> Optional[str]:
    """The process node cpuid (Todd Allen) gives for this family and model,
    preferring a row for this exact stepping."""
    rows = [row for row in load().get("cpuid_nodes", ())
            if row["vendor"] == vendor_id and row["family"] == ext_family
            and row["model_from"] <= ext_model <= row["model_to"]
            and row["stepping"] in (-1, stepping)]
    rows.sort(key=lambda row: row["stepping"] == -1)
    return rows[0]["node"] if rows else None


def _identify_x86(
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
    tied: list[dict] = []
    for entry in table:
        value = _score(entry, probe, clean_brand)
        if value > best_score:
            best, best_score, tied = entry, value, [entry]
        elif value == best_score:
            tied.append(entry)

    if best is None:
        return Identification(codename=None, technology=None, score=0, matched=False)

    # libcpuid uses «Unknown …» as a catch-all for what it doesn't recognize.
    # Showing it as a codename would answer «I don't know» looking like it
    # knows: better to leave the processor unidentified and let the section
    # say so.
    name = _common_to_the_tie(best["name"], tied)
    recognized = (name is not None and best_score > 0
                  and not name.lower().startswith("unknown"))
    # A row without an extended model belongs to processors that have none
    # (extended and base model match: a Dothan, a Presler). If this one has
    # it and the brand doesn't match either, the row only got family and base
    # model right, which don't say which processor it is: a Panther Lake (6,
    # 0xCC) came out as «Atom (Cedarview)» from the family 6 model 12 row. If
    # the kernel knows that model, it rules.
    if (recognized and best["xm"] < 0 and ext_model != model
            and not _brand_matches(best, clean_brand)):
        if (row := _from_kernel(vendor_id, ext_family, ext_model)) is not None:
            return Identification(codename=row["name"], technology=None,
                                  score=1, matched=True)
        # Without the kernel the row has nothing else, and when not even its
        # base model is this one it matched on family alone: QEMU's virtual
        # CPU (15, 0xB) came out as a Cranford (15, 4).
        if best["m"] >= 0 and best["m"] != model:
            recognized = False
    official = amd_model(brand) if vendor_id == "AuthenticAMD" else None
    if not recognized:
        # Not in libcpuid: the official amd.com row for this exact model
        # first, then the per-family ranges.
        if official is not None and official.get("codename"):
            return Identification(codename=official["codename"],
                                  technology=official.get("node"),
                                  score=1, matched=True)
        # The per-model table doesn't know it. Before giving up, the range
        # table, which covers whole families.
        if rule := _by_family(vendor_id, ext_family, ext_model):
            return Identification(
                codename=rule["name"],
                technology=rule.get("tech"),
                score=1,
                matched=True,
            )
        # Then the kernel's Intel table, which is ahead of libcpuid. It gives
        # the codename and nothing else: the node doesn't come from there.
        if (row := _from_kernel(vendor_id, ext_family, ext_model)) is not None:
            return Identification(codename=row["name"], technology=None,
                                  score=1, matched=True)
    technology = best.get("tech") if recognized else None
    if recognized and technology is None and official is not None:
        # libcpuid knew the chip but not its node; amd.com says it.
        technology = official.get("node")
    return Identification(
        codename=name if recognized else None,
        technology=technology,
        score=best_score,
        matched=recognized,
    )


# The real codename, which several entries share: «Ryzen 5 (Cezanne)» and
# «Ryzen 9 PRO (Cezanne)» describe the same silicon and only differ in the
# tier each part was sold in.
_IN_PARENTHESES = re.compile(r"\(([^)]+)\)\s*$")


def _common_to_the_tie(name: str,
                                 tied: list[dict]) -> Optional[str]:
    """What can be stated when several entries score the same.

    The same silicon can have several entries (identical family, model and
    extensions) told apart only by the brand pattern. A processor matching
    none of the patterns leaves them all tied on the silicon's score, and
    the table's order isn't a criterion: it's the order someone else wrote
    them in.

    What's certain on a tie is what they all say alike, the codename in
    parentheses: that alone is returned. If not even that matches (the same
    silicon sold as Cezanne and as Barceló), `None`, so the range table
    decides, which goes by family and not by commercial tier.
    """
    if len(tied) < 2:
        return name
    names = {e["name"] for e in tied}
    if len(names) == 1:
        return name
    codenames = {m.group(1) for n in names if (m := _IN_PARENTHESES.search(n))}
    # If they don't share a single one, nothing can be said of all of them at
    # once, and keeping one would be choosing by the file's order again.
    return codenames.pop() if len(codenames) == 1 else None


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
# socket / package
# --------------------------------------------------------------------------


def find_socket(vendor_id: str, codename: Optional[str], brand: str) -> Optional[str]:
    """Find the package in three passes, most specific first.

    1. The per-model table inherited from CPU-X: exact but tiny.
    2. Our per-microarchitecture table: one rule covers a whole generation,
       so it gets processors nobody has catalogued.
    3. Segment suffixes: a "-U" or "-H" in the codename means BGA, and
       saying "soldered" is more useful than leaving it blank.
    """
    if not codename and not brand:
        return None

    # From the most precise to the least: a CPU-X row for this very model, the
    # one amd.com lists for it, a CPU-X row for the whole codename, and then
    # the rules. A codename-wide row can list two packages where amd.com gives
    # the model's exact one.
    rows = load().get("sockets", {}).get(vendor_id, ())
    for entry in rows:
        wants_codename = entry["codename"] is not None
        model_ok = entry["model"] is not None and entry["model"] in brand
        codename_ok = wants_codename and codename is not None and entry["codename"] in codename
        if model_ok and (codename_ok or not wants_codename):
            return entry["socket"]

    wide = next((entry["socket"] for entry in rows
                 if entry["model"] is None and entry["codename"] is not None
                 and codename is not None and entry["codename"] in codename), None)
    official = amd_model(brand) if vendor_id == "AuthenticAMD" else None
    if official is not None and official.get("socket"):
        # CPU-X's «AM4 (PGA-1331)» says what amd.com's «AM4» says, and more;
        # anything else that disagrees loses.
        if wide is not None and wide.startswith(official["socket"] + " ("):
            return wide
        return official["socket"]
    if wide is not None:
        return wide

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


# What a CPUID brand string carries on top of the model amd.com names:
# «64-Cores», «Eight-Core», «APU», «Radeon R7, 12 Compute Cores 4C+8G».
_AMD_EXTRA = re.compile(
    r"\s+\d+-Cores?\b.*$|\s+(Dual|Triple|Quad|Six|Eight|Twelve|Sixteen)-Core\b.*$"
    r"|\s+APU\b.*$|,?\s+(Radeon\s+)?R\d+E?,\s+\d+\s+Compute Cores.*$|\s+Radeon\s+R\d.*$",
    re.IGNORECASE)


def amd_model_key(name: str) -> str:
    """The model an amd.com row and a CPUID brand string share.

    «AMD Ryzen™ 7 5800X3D» and «AMD Ryzen 7 5800X3D 8-Core Processor» are
    both «RYZEN 7 5800X3D». The same function builds the table and looks
    it up, so the two can't drift apart.
    """
    return " ".join(_AMD_EXTRA.sub("", normalize_cpu_model(name or "")).split()).upper()


def amd_model(brand: str) -> Optional[dict]:
    """The amd.com row for this processor's exact model, if AMD lists it."""
    key = amd_model_key(brand)
    if not key:
        return None
    for row in load().get("amd_models", ()):
        if row["model"] == key:
            return row
    return None


def amd_turbo(brand: str) -> Optional[bool]:
    """Whether AMD's specifications list a boost clock for this model.

    False only for a model listed with its base clock and no boost; None
    when AMD doesn't list it.
    """
    row = amd_model(brand)
    if row is None or not row.get("base_mhz"):
        return None
    return row.get("boost_mhz") is not None


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
    """The microarchitecture table by model range."""
    path = pathlib.Path(__file__).parent / "families.json"
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh).get("rules", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _by_family(vendor_id: str, ext_family: int, ext_model: int) -> Optional[dict]:
    """The microarchitecture of a processor the per-model table doesn't cover.

    libcpuid goes model by model and takes months to add what's just out, so
    a new processor is left without codename or node. The maker, instead,
    documents whole ranges: all of family 19h from 0x70 to 0x7F is Phoenix.
    A rule per range covers what's to come, and since it's only asked when
    the other table finds nothing, it can never worsen a datum already
    known.
    """
    for rule in _load_families():
        if rule.get("vendor") != vendor_id or rule.get("family") != ext_family:
            continue
        if rule.get("from", 0) <= ext_model <= rule.get("to", -1):
            return rule
    return None


# --------------------------------------------------------------------------
# official memory maximum
# --------------------------------------------------------------------------

# Intel's model inside the brand string: «i5-10400» in «Intel(R) Core(TM)
# i5-10400 CPU @ 2.90GHz». Whole, with its letter: «i5-10400H» is a laptop
# and can't match the desktop part's row.
_INTEL_MODEL = re.compile(r"\b(i[3579]-\d{3,5}[A-Z]{0,2}\d?)\b")
# The first generation writes the model differently in CPUID: «Core(TM) i7
# CPU 920», «i5 CPU M 520» (laptop), and its spec sheet «i7-920», «i5-520M».
_MODELO_INTEL_1 = re.compile(r"\b(i[3579]) CPU\s+(?:([A-Z]{1,2})\s+)?(\d{3})\b")
# Core Ultra and Core 3/5/7, without a hyphen: «Core(TM) Ultra 7 155H».
_INTEL_MODEL_WITHOUT_I = re.compile(
    r"\bCore(?:\(TM\)|™)?\s+(Ultra\s+)?([3579])\s+(?:Processor\s+)?(\d{3}[A-Z]{0,2})\b")
# What surrounds AMD's model, in the maker's table («AMD Ryzen™ 7 5800X3D»)
# and in the CPUID string («AMD Ryzen 7 5800X3D 8-Core Processor», «… with
# Radeon Graphics»).
_AMD_NOISE = re.compile(
    r"\(R\)|\(TM\)|™|®|^AMD\s+|\s+\d+-Core Processor.*$|\s+(with|w/) Radeon.*$"
    r"|\s*\(OEM Only\)|\s+Processor\b",
    re.IGNORECASE)


def normalize_cpu_model(name: str) -> str:
    """The model looked up in the memory maximum table.

    The same function for the table (when generating it) and the processor's
    brand string (when looking up): «i5-10400» or «Ryzen 7 5800X3D».
    """
    model_name = name or ""
    if (match := _INTEL_MODEL.search(model_name)):
        return match.group(1)
    if (match := _MODELO_INTEL_1.search(model_name)):
        tier, letter, number = match.groups()
        return f"{tier}-{number}{letter or ''}"
    if (match := _INTEL_MODEL_WITHOUT_I.search(model_name)):
        ultra, tier, number = match.groups()
        return f"Core {'Ultra ' if ultra else ''}{tier} {number}"
    return " ".join(_AMD_NOISE.sub("", model_name).split())


@dataclasses.dataclass(frozen=True)
class MemoryLimit:
    """A processor's official memory maximum for these modules."""

    model: str
    mts: int
    source: str
    # The layout it holds for, on AMD: «2x1R» is two single-rank modules.
    # None if the maker gives a single figure.
    layout: Optional[str] = None


@functools.lru_cache(maxsize=1)
def _load_memory_limits() -> dict[str, dict]:
    path = pathlib.Path(__file__).parent / "memory_limits.json"
    try:
        with path.open(encoding="utf-8") as fh:
            rows = json.load(fh).get("cpus", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {model: row for row in rows for model in row["models"]}


def memory_layout(ranks: tuple[Optional[int], ...]) -> Optional[str]:
    """«2x1R» for two single-rank modules; None if it can't be said.

    `ranks`: each fitted module's ranks. With different ranks, or one
    unknown, no layout on AMD's spec sheet matches.
    """
    distinct = set(ranks)
    if not ranks or len(distinct) != 1 or None in distinct:
        return None
    return f"{len(ranks)}x{distinct.pop()}R"


def memory_limit(brand: str, memory_type: Optional[str],
                 ranks: tuple[Optional[int], ...] = ()) -> Optional[MemoryLimit]:
    """This processor's official memory maximum with these modules, or None.

    Only what the table says, for that exact model and memory type. On AMD
    the figure depends on the modules' layout (`ranks`, each fitted module's
    ranks): without one matching the spec sheet there's no known maximum,
    and the caller still states nothing.
    """
    if not brand or not memory_type:
        return None
    model = normalize_cpu_model(brand)
    row = _load_memory_limits().get(model)
    if row is None or memory_type not in row["types"]:
        return None
    figure = row["types"][memory_type]
    if isinstance(figure, int):
        return MemoryLimit(model, figure, row["source"])
    layout = memory_layout(tuple(ranks))
    if layout is None or layout not in figure:
        return None
    return MemoryLimit(model, figure[layout], row["source"], layout)


# The Intel processors before Nehalem (2008) whose memory controller is in
# the board's chipset (the northbridge) and not the processor: the 64-bit
# Pentium 4 and Pentium D (family 15) and the family 6 Core 2: Merom and
# Conroe (0x0F), Merom-L (0x16), Penryn, Wolfdale and Yorkfield (0x17),
# Dunnington (0x1D). The Atoms of the time stay out: Diamondville has it in
# the chipset and Pineview already integrated, with models that cross.
_CONTROLLER_IN_CHIPSET = {0x0F, 0x16, 0x17, 0x1D}


def memory_controller_in_chipset(cpu_type) -> bool:
    """Whether this machine's memory is controlled by the chipset and not
    the processor.

    Then there's no «processor maximum» to speak of: the board decides how
    far memory goes.
    """
    # A virtual CPU's family and model are the hypervisor's: QEMU's is a
    # family 15 that has no chipset behind it.
    if getattr(cpu_type, "vendor", "") != "Intel" or getattr(cpu_type, "in_virtual_machine", False):
        return False
    family, model = cpu_type.disp_family, cpu_type.disp_model
    return family == 15 or (family == 6 and model in _CONTROLLER_IN_CHIPSET)
