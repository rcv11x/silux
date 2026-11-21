"""Run the CPUID instruction from Python, without root or compiling anything.

The trick: a few anonymous pages are reserved with `mmap`, the 20 bytes of
machine code of a function that runs `cpuid` are written in them, write
permission is removed and execute permission given (W^X), and the result is
called with `ctypes` like any other C function.

CPUID answers for the core it runs on, so reading a given core's data means
pinning the thread to it. On Linux `sched_setaffinity(0, …)` affects the
calling *thread*, not the whole process: `pinned()` is safe as long as it is
used in the worker thread and never in the interface's.
"""

from __future__ import annotations

import contextlib
import ctypes
import mmap
import os
import platform
import struct
from typing import Iterator, Optional

from . import sysroot

__all__ = ["CpuidError", "CpuidReader", "pinned", "is_supported",
           "executable_page"]

# System V AMD64: rdi = output pointer, esi = leaf, edx = subleaf.
_CODE_X86_64 = bytes(
    (
        0x53,                    # push rbx        (rbx is callee-saved)
        0x89, 0xF0,              # mov  eax, esi   -> leaf
        0x89, 0xD1,              # mov  ecx, edx   -> subleaf
        0x0F, 0xA2,              # cpuid
        0x89, 0x07,              # mov  [rdi+0],  eax
        0x89, 0x5F, 0x04,        # mov  [rdi+4],  ebx
        0x89, 0x4F, 0x08,        # mov  [rdi+8],  ecx
        0x89, 0x57, 0x0C,        # mov  [rdi+12], edx
        0x5B,                    # pop  rbx
        0xC3,                    # ret
    )
)

_PROT_READ_EXEC = 0x1 | 0x4


def executable_page(code: bytes, error=RuntimeError):
    """A page with `code` inside, ready to be called with ctypes.

    Returns the `mmap` and the address. The `mmap` must be kept while the
    function is used: if collected, the address stops being valid and the
    next call takes the process down.

    It lives here because this module needed it first, for CPUID; `membench`'s
    pointer-chasing kernel uses it too. Its details were learnt once and must
    not live in two places to drift apart.
    """
    mm = mmap.mmap(-1, mmap.PAGESIZE, prot=mmap.PROT_READ | mmap.PROT_WRITE)
    mm.write(code)

    # `CDLL(None)` is the process itself, which already has libc loaded, as the
    # other two modules that need it do. `find_library` finds it no better and
    # runs `ldconfig -p` for something already open: a fork and an exec in
    # the sampling thread, and a failure where there is no ldconfig.
    libc = ctypes.CDLL(None, use_errno=True)
    # The view is created and dropped in the same expression: kept, the mmap
    # would be «exported» and could never be closed. The address stays valid
    # while `mm` lives.
    address = ctypes.addressof(ctypes.c_char.from_buffer(mm))

    if libc.mprotect(ctypes.c_void_p(address), mmap.PAGESIZE, _PROT_READ_EXEC) != 0:
        errno = ctypes.get_errno()
        mm.close()
        raise error(
            f"mprotect failed (errno {errno}): executing anonymous memory is not "
            "allowed here, usually by a strict SELinux policy or a sandbox"
        )
    return mm, address


class CpuidError(RuntimeError):
    """CPUID cannot be used on this machine or in this environment."""


# The CPU the thread is pinned to, for the key of what is recorded: on a
# hybrid, a P core's leaf 4 and an E core's do not answer the same.
_pinned_cpu: Optional[int] = None


def machine() -> str:
    """`platform.machine()`, or the dumped machine's."""
    return sysroot.recorded("plataforma", "machine", platform.machine) or ""


def is_supported() -> bool:
    return machine() in ("x86_64", "AMD64")


@contextlib.contextmanager
def pinned(cpu_index: int) -> Iterator[None]:
    """Pin the current thread to a logical CPU and restore the mask on exit.

    With a dumped machine the affinity is not touched: its CPUs need not exist
    here, and what is asked is already recorded CPU by CPU.
    """
    global _pinned_cpu
    if sysroot.active():
        before, _pinned_cpu = _pinned_cpu, cpu_index
        try:
            yield
        finally:
            _pinned_cpu = before
        return
    previous = os.sched_getaffinity(0)
    try:
        os.sched_setaffinity(0, {cpu_index})
    except OSError as exc:                      # cpu apagada, cgroup restrictivo…
        raise CpuidError(f"could not pin the thread to CPU {cpu_index}: {exc}") from exc
    before, _pinned_cpu = _pinned_cpu, cpu_index
    try:
        yield
    finally:
        _pinned_cpu = before
        os.sched_setaffinity(0, previous)


class CpuidReader:
    """A CPUID leaf reader. Build it once and reuse it."""

    def __init__(self) -> None:
        if not is_supported():
            raise CpuidError(f"CPUID is only implemented for x86-64, not {machine()}")

        self._mm, address = executable_page(_CODE_X86_64, CpuidError)

        prototype = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32, ctypes.c_uint32)
        self._call = prototype(address)
        self._regs = (ctypes.c_uint32 * 4)()

        # Sanity check: leaf 0 always returns a vendor id of printable
        # characters.
        try:
            self.max_leaf, ebx, ecx, edx = self(0)
            self.vendor_id = struct.pack("<III", ebx, edx, ecx).decode("ascii")
        except Exception as exc:
            self.close()
            raise CpuidError(f"CPUID returned garbage: {exc}") from exc

        self.max_extended_leaf = self(0x8000_0000)[0]

    def __call__(self, leaf: int, subleaf: int = 0) -> tuple[int, int, int, int]:
        """(eax, ebx, ecx, edx) for a leaf and subleaf.

        Through `sysroot.recorded`: dumping a machine records it, and reading
        a dumped one replays it without running the instruction.
        """
        cpu = "*" if _pinned_cpu is None else _pinned_cpu
        return sysroot.recorded("cpuid", f"{cpu}:{leaf}:{subleaf}",
                                self._ask, leaf, subleaf) or (0, 0, 0, 0)

    def _ask(self, leaf: int, subleaf: int) -> tuple[int, int, int, int]:
        self._call(self._regs, leaf, subleaf)
        return tuple(self._regs)  # type: ignore[return-value]

    def supports(self, leaf: int) -> bool:
        if leaf >= 0x8000_0000:
            return leaf <= self.max_extended_leaf
        return leaf <= self.max_leaf

    def brand_string(self) -> str:
        """The vendor's brand string, in leaves 0x80000002-4."""
        if not self.supports(0x8000_0004):
            return ""
        raw = b"".join(struct.pack("<IIII", *self(leaf)) for leaf in (0x8000_0002, 0x8000_0003, 0x8000_0004))
        return " ".join(raw.split(b"\x00")[0].decode("ascii", "replace").split())

    def hypervisor_id(self) -> str:
        """The twelve-byte signature the hypervisor publishes in leaf 0x40000000.

        `supports` cannot be asked: this leaf is outside the range leaf 0
        announces, and CPUID answers what it does not know with its highest
        leaf's contents, believable garbage. The «hypervisor» bit of leaf 1
        authorizes this question, and checking it is the caller's job.
        """
        _eax, ebx, ecx, edx = self(0x4000_0000)
        # Here the order is EBX-ECX-EDX, not leaf 0's EBX-EDX-ECX: two strings
        # written by two different people.
        raw = struct.pack("<III", ebx, ecx, edx).split(b"\x00")[0]
        if not raw or any(b < 0x20 or b > 0x7E for b in raw):
            return ""
        return raw.decode("ascii")

    def close(self) -> None:
        self._call = None  # type: ignore[assignment]
        mm = getattr(self, "_mm", None)
        if mm is not None and not mm.closed:
            mm.close()

    def __enter__(self) -> "CpuidReader":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.close()
