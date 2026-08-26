"""Tabla de banderas de CPUID: qué bit de qué registro es qué instrucción.

Es puramente declarativo. Cada entrada es (hoja, subhoja, registro, bit, nombre).
Los nombres siguen la convención de /proc/cpuinfo cuando existe, para que sean
reconocibles y se puedan contrastar con lo que dice el kernel.
"""

from __future__ import annotations

EAX, EBX, ECX, EDX = 0, 1, 2, 3

# (hoja, subhoja, registro, bit, nombre)
FEATURE_BITS: tuple[tuple[int, int, int, int, str], ...] = (
    # --- hoja 1, EDX: lo clásico -------------------------------------------
    *((1, 0, EDX, bit, name) for bit, name in (
        (0, "fpu"), (4, "tsc"), (5, "msr"), (6, "pae"), (8, "cx8"), (9, "apic"),
        (11, "sep"), (12, "mtrr"), (15, "cmov"), (19, "clfsh"), (23, "mmx"),
        (24, "fxsr"), (25, "sse"), (26, "sse2"), (28, "htt"),
    )),
    # --- hoja 1, ECX -------------------------------------------------------
    *((1, 0, ECX, bit, name) for bit, name in (
        (0, "sse3"), (1, "pclmulqdq"), (3, "monitor"), (5, "vmx"), (7, "est"),
        (9, "ssse3"), (12, "fma3"), (13, "cx16"), (19, "sse4_1"), (20, "sse4_2"),
        (22, "movbe"), (23, "popcnt"), (25, "aes"), (26, "xsave"), (28, "avx"),
        (29, "f16c"), (30, "rdrand"), (31, "hypervisor"),
    )),
    # --- hoja 7 subhoja 0, EBX --------------------------------------------
    *((7, 0, EBX, bit, name) for bit, name in (
        (0, "fsgsbase"), (2, "sgx"), (3, "bmi1"), (4, "hle"), (5, "avx2"),
        (7, "smep"), (8, "bmi2"), (9, "erms"), (10, "invpcid"), (11, "rtm"),
        (14, "mpx"), (16, "avx512f"), (17, "avx512dq"), (18, "rdseed"),
        (19, "adx"), (20, "smap"), (21, "avx512ifma"), (23, "clflushopt"),
        (24, "clwb"), (26, "avx512pf"), (27, "avx512er"), (28, "avx512cd"),
        (29, "sha"), (30, "avx512bw"), (31, "avx512vl"),
    )),
    # --- hoja 7 subhoja 0, ECX --------------------------------------------
    *((7, 0, ECX, bit, name) for bit, name in (
        (1, "avx512vbmi"), (2, "umip"), (3, "pku"), (5, "waitpkg"),
        (6, "avx512vbmi2"), (8, "gfni"), (9, "vaes"), (10, "vpclmulqdq"),
        (11, "avx512vnni"), (12, "avx512bitalg"), (14, "avx512vpopcntdq"),
        (22, "rdpid"), (25, "cldemote"), (27, "movdiri"), (28, "movdir64b"),
    )),
    # --- hoja 7 subhoja 0, EDX --------------------------------------------
    *((7, 0, EDX, bit, name) for bit, name in (
        (4, "fsrm"), (8, "avx512vp2intersect"), (14, "serialize"),
        (20, "cet_ibt"), (22, "amx_bf16"), (23, "avx512fp16"),
        (24, "amx_tile"), (25, "amx_int8"),
    )),
    # --- hoja 7 subhoja 1, EAX --------------------------------------------
    *((7, 1, EAX, bit, name) for bit, name in (
        (4, "avx_vnni"), (5, "avx512bf16"), (23, "avx_ifma"),
    )),
    # --- hoja 0x80000001 ---------------------------------------------------
    *((0x8000_0001, 0, EDX, bit, name) for bit, name in (
        (11, "syscall"), (20, "nx"), (22, "mmxext"), (26, "pdpe1gb"),
        (27, "rdtscp"), (29, "lm"), (30, "3dnowext"), (31, "3dnow"),
    )),
    *((0x8000_0001, 0, ECX, bit, name) for bit, name in (
        (0, "lahf_lm"), (2, "svm"), (5, "abm"), (6, "sse4a"),
        (8, "3dnowprefetch"), (11, "xop"), (16, "fma4"), (21, "tbm"),
        (22, "topoext"),
    )),
)

# Lo que se enseña en primera línea, en el orden en que se quiere leer.
# El resto queda disponible pero no compite por el espacio de la pantalla.
HIGHLIGHTS: tuple[str, ...] = (
    "mmx", "sse", "sse2", "sse3", "ssse3", "sse4_1", "sse4_2", "sse4a",
    "avx", "avx2", "avx512f", "avx_vnni", "amx_tile",
    "fma3", "fma4", "aes", "sha", "pclmulqdq", "vaes",
    "bmi1", "bmi2", "adx", "rdrand", "rdseed", "vmx", "svm",
)

# Nombres bonitos para lo que se enseña destacado.
PRETTY: dict[str, str] = {
    "mmx": "MMX", "sse": "SSE", "sse2": "SSE2", "sse3": "SSE3",
    "ssse3": "SSSE3", "sse4_1": "SSE4.1", "sse4_2": "SSE4.2", "sse4a": "SSE4A",
    "avx": "AVX", "avx2": "AVX2", "avx512f": "AVX-512", "avx_vnni": "AVX-VNNI",
    "amx_tile": "AMX", "fma3": "FMA3", "fma4": "FMA4", "aes": "AES-NI",
    "sha": "SHA", "pclmulqdq": "CLMUL", "vaes": "VAES", "bmi1": "BMI1",
    "bmi2": "BMI2", "adx": "ADX", "rdrand": "RDRAND", "rdseed": "RDSEED",
    "vmx": "VT-x", "svm": "AMD-V", "nx": "NX", "lm": "x86-64",
    "htt": "HTT", "est": "SpeedStep",
}


def decode(reader) -> tuple[str, ...]:
    """Lee todas las banderas soportadas, agrupando por hoja para no repetir.

    `reader` es cualquier cosa invocable como `reader(hoja, subhoja)` que
    devuelva la tupla (eax, ebx, ecx, edx), es decir, un `CpuidReader`.
    """
    cache: dict[tuple[int, int], tuple[int, int, int, int]] = {}
    found: list[str] = []

    for leaf, subleaf, reg, bit, name in FEATURE_BITS:
        if not reader.supports(leaf):
            continue
        key = (leaf, subleaf)
        if key not in cache:
            cache[key] = reader(leaf, subleaf)
        if cache[key][reg] >> bit & 1:
            found.append(name)

    return tuple(found)


def pretty(name: str) -> str:
    return PRETTY.get(name, name.upper().replace("_", "-"))
