"""The raw data at the end of the full report: this machine's dump, as text.

The report says what Silux shows; the annex, what it read to show it. It is
the dump `tools/volcar_equipo.py` writes for the test suite (`volcado.py`),
through the same privacy pass, written as text someone can read before
sending it. `tools/importar_informe.py` turns it back into a dump folder, so
a report from someone else's machine becomes a test.

The block, folder by folder:

    silux-annex 1
    in /proc
    file cpuinfo
    | processor\t: 0
    link mounts -> self/mounts
    dir 1
    in /sys/devices/system/cpu/cpu0/cpufreq
    file scaling_cur_freq = 3400000
    in /sys/class/drm/card1-DP-1
    binary edid
    | 00000000  00 ff ff ff ff ff ff 00 1e 6d 7f 5b 00 00 00 00  |.........m.[....|

A content line is `| ` and the line as it is, or `|"` and the line as a JSON
string when it would not survive an editor (trailing blanks, control
characters). `file-no-eol` is a file without the final line break, and `dir`
an empty folder.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Optional

MARK = "silux-annex"
VERSION = 1
FENCE = "```"
# How long the dump may take in its own process: here it takes two seconds.
TIMEOUT_S = 90
# What says what the rest is, first.
FIRST = ("manifiesto.json", "grabado.json")
_PLAIN = re.compile(r"[^\x00-\x08\x0a-\x1f\x7f]*")
_FILES = ("file", "file-no-eol", "binary")
_HEADER = re.compile(re.escape(MARK) + r" \S+")


class AnnexError(ValueError):
    """A block this version cannot read, or a path it will not write."""


# -- writing ---------------------------------------------------------------------

def _plain(line: str) -> bool:
    """Survives as it is: no blank at the end, which an editor may trim, and
    no control character but the tab, which a terminal showing the report
    would run."""
    return bool(_PLAIN.fullmatch(line)) and line == line.rstrip(" \t")


def _content_line(line: str) -> str:
    return f"| {line}" if _plain(line) else "|" + json.dumps(line, ensure_ascii=False)


def _hexdump(data: bytes) -> list[str]:
    lines = []
    for offset in range(0, len(data), 16):
        chunk = data[offset:offset + 16]
        shown = "".join(chr(b) if 0x20 <= b < 0x7f else "." for b in chunk)
        lines.append(f"| {offset:08x}  {' '.join(f'{b:02x}' for b in chunk):<47}  |{shown}|")
    return lines


def _as_text(data: bytes) -> Optional[str]:
    if b"\x00" in data or b"\r" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _checked(name: str) -> str:
    if not name or not _plain(name) or "\t" in name or " -> " in name:
        raise AnnexError(f"a name the annex cannot write: {name!r}")
    return name


def _entry(path: pathlib.Path) -> list[str]:
    name = _checked(path.name)
    if path.is_symlink():
        return [f"link {name} -> {_checked(os.readlink(path))}"]
    if path.is_dir():
        return [f"dir {name}"] if not any(path.iterdir()) else []
    data = path.read_bytes()
    text = _as_text(data)
    if text is None:
        return [f"binary {name}"] + _hexdump(data)
    body, eol = (text[:-1], True) if text.endswith("\n") else (text, False)
    lines = body.split("\n") if text else []
    if eol and len(lines) == 1 and lines[0] and _plain(lines[0]) and " = " not in name:
        return [f"file {name} = {lines[0]}"]
    return [f"{'file' if eol else 'file-no-eol'} {name}"] + [_content_line(l) for l in lines]


def to_text(folder: pathlib.Path) -> str:
    """A dump folder as the annex block, without the fences."""
    folder = pathlib.Path(folder)

    def order(path: pathlib.Path) -> tuple:
        relative = path.relative_to(folder)
        return (relative.parent.as_posix() != "." or relative.name not in FIRST,
                relative.parent.as_posix(), relative.name)

    lines = [f"{MARK} {VERSION}"]
    current = None
    for path in sorted(folder.rglob("*"), key=order):
        entry = _entry(path)
        if not entry:
            continue
        parent = "/" + path.parent.relative_to(folder).as_posix().lstrip(".")
        if parent != current:
            lines.append(f"in {_checked(parent)}")
            current = parent
        lines += entry
    return "\n".join(lines) + "\n"


# -- reading ---------------------------------------------------------------------

def _inside(folder: pathlib.Path, current: Optional[str], name: str) -> pathlib.Path:
    """Where an entry goes, refusing what would leave the folder."""
    if current is None:
        raise AnnexError(f"{name!r} before any «in»")
    parts = [p for p in current.split("/")[1:] if p] + [name]
    if not current.startswith("/") or any(p in ("..", ".", "") or "/" in p for p in parts):
        raise AnnexError(f"a path outside the dump: {current}/{name}")
    return folder.joinpath(*parts)


def _unhex(lines: list[str], name: str) -> bytes:
    data = bytearray()
    for line in lines:
        offset, _sp, rest = line[2:].partition("  ")
        try:
            if int(offset, 16) != len(data):
                raise ValueError
            data += bytes.fromhex(rest.split("  |", 1)[0])
        except ValueError:
            raise AnnexError(f"a broken hex dump in {name}") from None
    return bytes(data)


def _line_of(content: str, name: str) -> str:
    if content == "|":
        return ""                     # «| » with its blank trimmed
    if content.startswith("| "):
        return content[2:]
    if content.startswith('|"'):
        try:
            return json.loads(content[1:])
        except json.JSONDecodeError:
            raise AnnexError(f"a broken line in {name}") from None
    raise AnnexError(f"a line that belongs to no file, in {name}")


def _entries(text: str):
    """(kind, rest of the header, content lines, folder it is in)."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or not lines[0].startswith(MARK + " "):
        raise AnnexError("no annex here")
    version = lines[0][len(MARK) + 1:].strip()
    if version != str(VERSION):
        raise AnnexError(f"an annex of version {version}; this one reads {VERSION}")
    current = None
    i = 1
    while i < len(lines):
        header = lines[i]
        i += 1
        content = []
        while i < len(lines) and lines[i].startswith("|"):
            content.append(lines[i])
            i += 1
        kind, _sp, rest = header.partition(" ")
        if kind == "in":
            current = rest
            continue
        yield kind, rest, content, current


def _file(kind: str, rest: str, content: list[str]) -> tuple[str, bytes]:
    """The name and the bytes of a `file`, `file-no-eol` or `binary` entry."""
    if kind == "binary":
        return rest, _unhex(content, rest)
    name, sep, value = rest.partition(" = ")
    if sep and kind == "file" and not content:
        return name, (value + "\n").encode("utf-8")
    body = "\n".join(_line_of(c, rest) for c in content) + ("\n" if kind == "file" else "")
    return rest, body.encode("utf-8")


def to_folder(text: str, folder: pathlib.Path) -> None:
    """Writes the dump an annex block describes into `folder`, which must not
    exist. Links go last, and none may lead out of the folder."""
    folder = pathlib.Path(folder)
    folder.mkdir(parents=True)
    links = []
    for kind, rest, content, current in _entries(text):
        if kind == "link":
            name, sep, target = rest.partition(" -> ")
            if not sep or target.startswith("/"):
                raise AnnexError(f"a link the annex does not write: {rest!r}")
            links.append((_inside(folder, current, name), target))
        elif kind == "dir":
            _inside(folder, current, rest).mkdir(parents=True, exist_ok=True)
        elif kind in _FILES:
            name, data = _file(kind, rest, content)
            path = _inside(folder, current, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        else:
            raise AnnexError(f"an entry this version does not know: {kind!r}")
    real = folder.resolve()
    for path, target in links:
        path.parent.mkdir(parents=True, exist_ok=True)
        where = pathlib.Path(os.path.normpath(path.parent.resolve() / target))
        if where != real and real not in where.parents:
            raise AnnexError(f"a link that leaves the dump: {path.name} -> {target}")
        os.symlink(target, path)


def find(report: str) -> str:
    """The annex block of a report, without its fences."""
    lines = report.split("\n")
    for start, line in enumerate(lines):
        if _HEADER.fullmatch(line) and start and lines[start - 1].startswith(FENCE):
            break
    else:
        raise AnnexError("this report has no annex")
    end = start
    while end < len(lines) and not lines[end].startswith(FENCE):
        end += 1
    return "\n".join(lines[start:end]) + "\n"


def size_of(block: str) -> tuple[int, int]:
    """How many files the block holds, and how many bytes they were."""
    files = size = 0
    for kind, rest, content, _current in _entries(block):
        if kind in _FILES:
            files += 1
            size += len(_file(kind, rest, content)[1])
    return files, size


# -- this machine ------------------------------------------------------------------

def of_this_machine() -> tuple[Optional[str], Optional[str]]:
    """This machine's annex block, made in another process, or why not.

    In another process because the dump learns what the Collector reads by
    patching `open` for the whole process, and the window's sampler keeps
    reading meanwhile.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([root] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    try:
        done = subprocess.run([sys.executable, "-m", "silux.annex"], capture_output=True,
                              text=True, timeout=TIMEOUT_S, env=env, check=False)
    except subprocess.TimeoutExpired:
        return None, f"took more than {TIMEOUT_S} s"
    except OSError as error:
        return None, str(error)
    if done.returncode != 0 or not done.stdout.startswith(MARK + " "):
        reason = done.stderr.strip().splitlines()
        return None, reason[-1] if reason else f"exit code {done.returncode}"
    return done.stdout, None


def main() -> int:
    from . import volcado

    with tempfile.TemporaryDirectory(prefix="silux-anexo-") as tmp:
        try:
            block = to_text(volcado.volcar("equipo", pathlib.Path(tmp)))
        except (SystemExit, AnnexError, OSError) as error:
            print(str(error).strip().replace("\n", " "), file=sys.stderr)
            return 1
    sys.stdout.write(block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
