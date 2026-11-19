#!/usr/bin/env python3
"""Las CPU de referencia: los volcados reales de los tests de libcpuid, en corto.

    python3 tools/gen_referencias_cpu.py --libcpuid ~/.cache/silux/sources/libcpuid

libcpuid trae en `tests/` cientos de volcados de CPUID de procesadores de
verdad, cada uno con lo que tiene que salir. De cada uno se guarda lo que
hace falta para identificarlo —fabricante, firma, marca, núcleos y cachés— y
lo que libcpuid espera: el nombre en clave y el nodo. Lo lee
`tests/test_referencias_cpu.py`, que pasa cada uno por la tabla de Silux.

La firma y la marca salen de las hojas de CPUID en crudo (la 1, y de la
0x80000002 a la 0x80000004 de la primera CPU lógica); los núcleos y las
cachés, de lo esperado, que es como los cuenta libcpuid al elegir fila.

Son datos de libcpuid (BSD-2): su aviso está en
`silux/db/THIRD_PARTY_NOTICES.md`. Fuente: el fork `rcv11x/libcpuid`.
"""

from __future__ import annotations

import argparse
import json
import lzma
import pathlib
import re
import struct

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "tests" / "fixtures" / "referencias_cpu.json"
SEPARADOR = "-" * 80
# El orden de la salida esperada, como lo escribe `tests/run_tests.py` de libcpuid.
CAMPOS_X86 = ("architecture", "feature-level", "purpose", "family", "model", "stepping",
              "extfamily", "extmodel", "cores", "logical",
              "l1d-cache", "l1i-cache", "l2-cache", "l3-cache", "l4-cache",
              "l1d-assoc", "l1i-assoc", "l2-assoc", "l3-assoc", "l4-assoc",
              "l1d-cacheline", "l1i-cacheline", "l2-cacheline", "l3-cacheline", "l4-cacheline",
              "l1d-instances", "l1i-instances", "l2-instances", "l3-instances", "l4-instances",
              "sse-size", "codename", "technology", "flags")


LFS = b"version https://git-lfs.github.com/spec/"


def _texto(archivo: pathlib.Path) -> str:
    # Los `.test.xz` van en Git LFS: un clon sin `git lfs` trae el puntero, no
    # el volcado. Se saltan y se cuentan.
    if archivo.read_bytes()[:len(LFS)] == LFS:
        raise FileNotFoundError(f"{archivo.name} es un puntero de Git LFS")
    if archivo.suffix == ".xz":
        with lzma.open(archivo, "rt", encoding="utf-8", errors="replace") as f:
            return f.read()
    return archivo.read_text(encoding="utf-8", errors="replace")


_HOJA = re.compile(r"^CPUID ([0-9A-Fa-f]{8}): ([0-9A-Fa-f]{8})-([0-9A-Fa-f]{8})-"
                   r"([0-9A-Fa-f]{8})-([0-9A-Fa-f]{8})")
# El formato antiguo de los volcados: `basic_cpuid[1]=00030661 …`.
_HOJA_ANTIGUA = re.compile(r"^(basic|ext)_cpuid\[(\d+)\]=([0-9a-fA-F]{8}) ([0-9a-fA-F]{8}) "
                           r"([0-9a-fA-F]{8}) ([0-9a-fA-F]{8})")
_CPU_LOGICA = re.compile(r"Logical CPU #(\d+)")


def _hojas(entrada: list[str]) -> dict[int, tuple[int, int, int, int]]:
    """Las hojas de la primera CPU lógica; de cada una, su primera subhoja.

    Tres formatos: `CPUID 00000001: A-B-C-D`, el mismo con notas al final
    (`[SL 00] [L1D: 32 KB]`), y el antiguo, `basic_cpuid[1]=A B C D`.
    """
    hojas: dict[int, tuple[int, int, int, int]] = {}
    for linea in entrada:
        if (cpu := _CPU_LOGICA.search(linea)) and int(cpu.group(1)) > 0:
            break
        if encaje := _HOJA.match(linea):
            hoja, *valores = encaje.groups()
            hoja = int(hoja, 16)
        elif encaje := _HOJA_ANTIGUA.match(linea):
            grupo, indice, *valores = encaje.groups()
            hoja = int(indice) + (0x80000000 if grupo == "ext" else 0)
        else:
            continue
        hojas.setdefault(hoja, tuple(int(v, 16) for v in valores))
    return hojas


def _cadena(*registros: int) -> str:
    return b"".join(struct.pack("<I", r) for r in registros).split(b"\0")[0].decode(
        "ascii", errors="replace")


def leer(archivo: pathlib.Path) -> dict | None:
    """Un volcado x86, o None si no lo es o le falta algo."""
    texto = _texto(archivo)
    if SEPARADOR not in texto:
        return None
    entrada, salida = texto.split(SEPARADOR, 1)
    hojas = _hojas(entrada.splitlines())
    esperado = [l for l in salida.strip().splitlines()]
    if not hojas.get(0) or not hojas.get(1) or len(esperado) < len(CAMPOS_X86):
        return None
    campos = dict(zip(CAMPOS_X86, esperado[:len(CAMPOS_X86)]))
    if campos["architecture"] != "x86":
        return None
    _maximo, ebx, ecx, edx = hojas[0]
    eax1 = hojas[1][0]
    familia_base = (eax1 >> 8) & 0xF
    modelo_base = (eax1 >> 4) & 0xF
    familia = familia_base + ((eax1 >> 20) & 0xFF if familia_base == 0xF else 0)
    modelo = modelo_base + (((eax1 >> 16) & 0xF) << 4 if familia_base in (6, 0xF) else 0)
    # Las tres hojas van seguidas: la cadena cruza de una a otra.
    marca = _cadena(*(r for h in (0x80000002, 0x80000003, 0x80000004)
                      for r in hojas.get(h, (0, 0, 0, 0))))
    return {
        "source": archivo.as_posix().split("/tests/", 1)[-1],
        "vendor": _cadena(ebx, edx, ecx),
        "signature": eax1,
        "family": familia_base, "model": modelo_base, "stepping": eax1 & 0xF,
        "ext_family": familia, "ext_model": modelo,
        "brand": " ".join(marca.split()),
        "cores": int(campos["cores"]),
        "l2_kb": int(campos["l2-cache"]), "l3_kb": int(campos["l3-cache"]),
        "codename": campos["codename"],
        "technology": campos["technology"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--libcpuid", type=pathlib.Path, required=True,
                        help="un clon de libcpuid (el fork rcv11x/libcpuid)")
    args = parser.parse_args()
    filas, sin_lfs = [], []
    for archivo in sorted((args.libcpuid / "tests").rglob("*.test*")):
        try:
            fila = leer(archivo)
        except FileNotFoundError:
            sin_lfs.append(archivo.name)
            continue
        if fila is not None:
            filas.append(fila)
    if sin_lfs:
        print(f"{len(sin_lfs)} volcados en Git LFS sin bajar: hace falta `git lfs pull` en el clon")
    DESTINO.write_text(json.dumps({
        "_": "Generado por tools/gen_referencias_cpu.py de los tests de libcpuid "
             "(BSD-2, aviso en silux/db/THIRD_PARTY_NOTICES.md). No se edita a mano.",
        "cpus": filas,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(filas)} procesadores en {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
