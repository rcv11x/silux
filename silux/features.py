"""CPUID feature flags: which bit of which register is which instruction.

Each entry is (leaf, subleaf, register, bit, name). Names follow
/proc/cpuinfo where it has one, so they can be checked against the kernel.
"""

from __future__ import annotations

from typing import Optional

EAX, EBX, ECX, EDX = 0, 1, 2, 3

# (leaf, subleaf, register, bit, name)
FEATURE_BITS: tuple[tuple[int, int, int, int, str], ...] = (
    # --- leaf 1, EDX: the classics -----------------------------------------
    *((1, 0, EDX, bit, name) for bit, name in (
        (0, "fpu"), (4, "tsc"), (5, "msr"), (6, "pae"), (8, "cx8"), (9, "apic"),
        (11, "sep"), (12, "mtrr"), (15, "cmov"), (19, "clfsh"), (23, "mmx"),
        (24, "fxsr"), (25, "sse"), (26, "sse2"), (28, "htt"),
    )),
    # --- leaf 1, ECX -------------------------------------------------------
    *((1, 0, ECX, bit, name) for bit, name in (
        (0, "sse3"), (1, "pclmulqdq"), (3, "monitor"), (5, "vmx"), (7, "est"),
        (9, "ssse3"), (12, "fma3"), (13, "cx16"), (19, "sse4_1"), (20, "sse4_2"),
        (22, "movbe"), (23, "popcnt"), (25, "aes"), (26, "xsave"), (28, "avx"),
        (29, "f16c"), (30, "rdrand"), (31, "hypervisor"),
    )),
    # --- leaf 7 subleaf 0, EBX ---------------------------------------------
    *((7, 0, EBX, bit, name) for bit, name in (
        (0, "fsgsbase"), (2, "sgx"), (3, "bmi1"), (4, "hle"), (5, "avx2"),
        (7, "smep"), (8, "bmi2"), (9, "erms"), (10, "invpcid"), (11, "rtm"),
        (14, "mpx"), (16, "avx512f"), (17, "avx512dq"), (18, "rdseed"),
        (19, "adx"), (20, "smap"), (21, "avx512ifma"), (23, "clflushopt"),
        (24, "clwb"), (26, "avx512pf"), (27, "avx512er"), (28, "avx512cd"),
        (29, "sha"), (30, "avx512bw"), (31, "avx512vl"),
    )),
    # --- leaf 7 subleaf 0, ECX ---------------------------------------------
    *((7, 0, ECX, bit, name) for bit, name in (
        (1, "avx512vbmi"), (2, "umip"), (3, "pku"), (5, "waitpkg"),
        (6, "avx512vbmi2"), (8, "gfni"), (9, "vaes"), (10, "vpclmulqdq"),
        (11, "avx512vnni"), (12, "avx512bitalg"), (14, "avx512vpopcntdq"),
        (22, "rdpid"), (25, "cldemote"), (27, "movdiri"), (28, "movdir64b"),
    )),
    # --- leaf 7 subleaf 0, EDX ---------------------------------------------
    *((7, 0, EDX, bit, name) for bit, name in (
        (4, "fsrm"), (8, "avx512vp2intersect"), (14, "serialize"),
        (20, "cet_ibt"), (22, "amx_bf16"), (23, "avx512fp16"),
        (24, "amx_tile"), (25, "amx_int8"),
    )),
    # --- leaf 7 subleaf 1, EAX ---------------------------------------------
    *((7, 1, EAX, bit, name) for bit, name in (
        (4, "avx_vnni"), (5, "avx512bf16"), (23, "avx_ifma"),
    )),
    # --- leaf 0x80000001 ---------------------------------------------------
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

# Shown first, in reading order; the rest stays available below.
HIGHLIGHTS: tuple[str, ...] = (
    "mmx", "sse", "sse2", "sse3", "ssse3", "sse4_1", "sse4_2", "sse4a",
    "avx", "avx2", "avx512f", "avx_vnni", "amx_tile",
    "fma3", "fma4", "aes", "sha", "pclmulqdq", "vaes",
    "bmi1", "bmi2", "adx", "rdrand", "rdseed", "vmx", "svm",
)

# ARM gets its own list: some flag names exist on both architectures and mean
# different things. An aarch64's «aes» is ARMv8's crypto extension, and
# calling it AES-NI would credit the chip with an Intel instruction.
HIGHLIGHTS_ARM: tuple[str, ...] = (
    "asimd", "sve", "sve2", "sme", "aes", "pmull", "sha1", "sha2", "sha3",
    "sha512", "crc32", "atomics", "fphp", "asimdhp", "asimddp", "asimdrdm",
    "i8mm", "bf16", "jscvt", "fcma", "lrcpc", "dcpop", "flagm", "rng",
    "sm3", "sm4",
)

PRETTY_ARM: dict[str, str] = {
    "asimd": "NEON", "sve": "SVE", "sve2": "SVE2", "sme": "SME",
    "aes": "AES", "pmull": "PMULL", "sha1": "SHA1", "sha2": "SHA2",
    "sha3": "SHA3", "sha512": "SHA512", "crc32": "CRC32",
    "atomics": "LSE", "fphp": "FP16", "asimdhp": "NEON-FP16",
    "asimddp": "DotProd", "asimdrdm": "RDM", "i8mm": "I8MM", "bf16": "BF16",
    "jscvt": "JSCVT", "fcma": "FCMA", "lrcpc": "LRCPC", "dcpop": "DCPOP",
    "flagm": "FlagM", "rng": "RNG", "sm3": "SM3", "sm4": "SM4",
}

# Display names for the highlighted flags.
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
    """Read every known flag, querying each leaf only once.

    `reader(leaf, subleaf)` returns (eax, ebx, ecx, edx), like a
    `CpuidReader`.
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


def for_architecture(architecture: Optional[str]):
    """The highlighted flags and their names for this CPU's architecture."""
    is_arm = (architecture or "").lower().startswith(("aarch64", "arm"))
    return (HIGHLIGHTS_ARM, PRETTY_ARM) if is_arm else (HIGHLIGHTS, PRETTY)
