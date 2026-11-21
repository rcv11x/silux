"""Run CPUID from Python, without root and without compiling anything.

The 20 bytes of a function that executes `cpuid` go into an anonymous page,
the page is flipped from writable to executable (W^X), and ctypes calls it
like any C function.

CPUID reports on the core it runs on, so reading a given core means pinning
the thread to it first. On Linux `sched_setaffinity(0, …)` pins the calling
thread, not the process, which is why `pinned()` is only safe from the
worker thread and never from the UI thread.
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
    """Map `code` into an executable page and return (mmap, address).

    Keep the mmap alive while the function is in use: once it is collected
    the address dangles and the next call takes the process down. `membench`
    uses this too, for its pointer-chasing kernel.
    """
    mm = mmap.mmap(-1, mmap.PAGESIZE, prot=mmap.PROT_READ | mmap.PROT_WRITE)
    mm.write(code)

    # The process already has libc loaded. `find_library` would run
    # `ldconfig -p` to find it: a fork and exec in the sampling thread, and a
    # failure on systems without ldconfig.
    libc = ctypes.CDLL(None, use_errno=True)
    # Don't keep the buffer view: an exported mmap can never be closed. The
    # address stays valid as long as `mm` does.
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
    """CPUID is not usable on this machine or in this environment."""


# Part of the key for recorded answers: on a hybrid CPU, leaf 4 differs
# between P and E cores.
_pinned_cpu: Optional[int] = None


def machine() -> str:
    """`platform.machine()`, or the dumped machine's."""
    return sysroot.recorded("plataforma", "machine", platform.machine) or ""


def is_supported() -> bool:
    return machine() in ("x86_64", "AMD64")


@contextlib.contextmanager
def pinned(cpu_index: int) -> Iterator[None]:
    """Pin the current thread to one logical CPU, restoring its mask on exit.

    With a dump mounted the affinity is left alone: its CPUs may not exist
    here, and the answers are already recorded per CPU.
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
    except OSError as exc:                      # offline CPU, restrictive cgroup…
        raise CpuidError(f"could not pin the thread to CPU {cpu_index}: {exc}") from exc
    before, _pinned_cpu = _pinned_cpu, cpu_index
    try:
        yield
    finally:
        _pinned_cpu = before
        os.sched_setaffinity(0, previous)


class CpuidReader:
    """Reads CPUID leaves. Create one and reuse it."""

    def __init__(self) -> None:
        if not is_supported():
            raise CpuidError(f"CPUID is only implemented for x86-64, not {machine()}")

        self._mm, address = executable_page(_CODE_X86_64, CpuidError)

        prototype = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32, ctypes.c_uint32)
        self._call = prototype(address)
        self._regs = (ctypes.c_uint32 * 4)()

        # Leaf 0 always returns a printable vendor string; anything else means
        # the call itself is broken.
        try:
            self.max_leaf, ebx, ecx, edx = self(0)
            self.vendor_id = struct.pack("<III", ebx, edx, ecx).decode("ascii")
        except Exception as exc:
            self.close()
            raise CpuidError(f"CPUID returned garbage: {exc}") from exc

        self.max_extended_leaf = self(0x8000_0000)[0]

    def __call__(self, leaf: int, subleaf: int = 0) -> tuple[int, int, int, int]:
        """(eax, ebx, ecx, edx) for a leaf and subleaf.

        Goes through `sysroot.recorded`: dumping a machine records the
        answer, and a mounted dump replays it without running the instruction.
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
        """The brand string, from leaves 0x80000002 to 0x80000004."""
        if not self.supports(0x8000_0004):
            return ""
        raw = b"".join(struct.pack("<IIII", *self(leaf)) for leaf in (0x8000_0002, 0x8000_0003, 0x8000_0004))
        return " ".join(raw.split(b"\x00")[0].decode("ascii", "replace").split())

    def hypervisor_id(self) -> str:
        """The 12-byte hypervisor signature from leaf 0x40000000.

        Don't gate this on `supports`: the leaf is past the range leaf 0
        reports, and CPUID answers an unknown leaf with the highest one's
        contents, which looks plausible. The caller checks the hypervisor bit
        of leaf 1 first.
        """
        _eax, ebx, ecx, edx = self(0x4000_0000)
        # EBX-ECX-EDX here, unlike leaf 0's EBX-EDX-ECX.
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
