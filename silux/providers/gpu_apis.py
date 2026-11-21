"""What the graphics APIs say of each card.

Asking is costly (the three drivers add up to 118 MB resident), so
`silux.gpuapi` does it in a separate process and only the result arrives.

The kernel says what is installed; OpenGL, Vulkan and OpenCL say what can be
done with it: API versions, not registers.

It also settles what sysfs cannot: `pci.ids` may give one name for three
models («Radeon RX 9070/9070 XT/9070 GRE»), and the driver knows which. A
name with slashes is replaced by Vulkan's; otherwise the database's stays,
which is usually fuller, with whoever built the card.
"""

from __future__ import annotations

import dataclasses
import os
import re
from typing import Optional

from .. import amdgpu, gpuapi, sysroot
from ..i18n import _
from ..model import GpuApi, GpuMemory, Need, VideoCodec
from .base import Draft, Provider

# «AMD Radeon RX 9070 XT (RADV GFX1201)» → the parenthesis is the driver's,
# not the card's name.
_DRIVER_SUFFIX = re.compile(r"\s*\((?:RADV|LLVM|ACO|radeonsi|llvmpipe)[^)]*\)\s*$",
                              re.IGNORECASE)
# «4.6 (Compatibility Profile) Mesa 26.2.1-arch3.1» → 26.2.1-arch3.1
_MESA_VERSION = re.compile(r"Mesa\s+([\w.\-]+)")
_NVIDIA_VERSION = re.compile(r"NVIDIA\s+(\d+\.\d+(?:\.\d+)?)")


class GpuApis(Provider):
    """OpenGL, Vulkan and OpenCL, asked once."""

    name = "gpu-apis"
    provides = "gpus.apis"
    # API versions do not change while the program runs, and creating an
    # OpenGL context on every sample would be absurd.
    static = True

    def available(self) -> bool:
        return True

    def collect(self, draft: Draft) -> None:
        if not draft.gpus:
            return
        if any(gpu.get("suspended") for gpu in draft.gpus):
            # Vulkan and OpenCL open every card to list them, and opening a
            # suspended card's node wakes it. Asked when it wakes: the static
            # data is read again then.
            draft.note("gpus.apis", Need.HARDWARE,
                       _("prov.apis.asleep"), _("prov.apis.asleep.hint"))
            return

        # A single call: inside, it starts a process that loads the drivers,
        # answers and dies. Why, in `silux.gpuapi`.
        data = sysroot.recorded("gpuapi", "consultar", _without_crashing, gpuapi.consultar) or {}
        vulkan = data.get("vulkan") or []
        opencl = data.get("opencl") or []
        opengl = data.get("opengl")
        vaapi = data.get("vaapi") or []
        rejected = data.get("vulkan_rejected") or []
        icds = data.get("vulkan_icds") or []

        if not (vulkan or opencl or opengl or vaapi):
            draft.note(
                "gpus.apis", Need.DRIVER,
                _("prov.apis.none"), _("prov.apis.none.hint"),
            )
            return

        draft.capabilities.add("gpu-apis")
        primary = _primary_index(draft.gpus)

        for index, gpu in enumerate(draft.gpus):
            gpu["codecs"] = _codecs_of(gpu, vaapi)
            apis: list[GpuApi] = []
            not_the_cards_driver: set[int] = set()

            if device := _vulkan_of(gpu, vulkan):
                apis.append(GpuApi(
                    name="Vulkan",
                    version=device["api_version"],
                    device=device["name"],
                    driver=_driver_version(device),
                    extra=_("gpu.api.instance").format(version=device["instance_version"]),
                ))
                _refine_name(gpu, device["name"])
                _vulkan_memory(gpu, device)

            # OpenGL and OpenCL do not publish the PCI node, but say who
            # answers. On a hybrid laptop the card the kernel marks as primary
            # is the integrated one while the dedicated one answers: matched to
            # the primary, a Radeon's card ended with «GLSL 4.60 NVIDIA».
            if opengl and opengl.get("version") and _answers_for(
                    f"{opengl.get('renderer') or ''} {opengl.get('vendor') or ''}",
                    gpu, draft.gpus, primary, index):
                # llvmpipe is the processor drawing: in a virtual machine
                # Mesa's version showed as that of its emulated VGA.
                by_software = _vendor_of(opengl.get("renderer") or "") == "software"
                extra = " · ".join(p for p in (
                    f"GLSL {opengl['glsl']}" if opengl.get("glsl") else None,
                    _("gpu.api.software") if by_software else None) if p)
                apis.append(GpuApi(
                    name="OpenGL",
                    version=_version_only(opengl["version"]),
                    device=opengl.get("renderer"),
                    driver=_mesa(opengl["version"]),
                    extra=extra or None,
                ))
                if by_software:
                    not_the_cards_driver.add(len(apis) - 1)
            for device in opencl:
                if not _answers_for(f"{device.get('name') or ''} "
                              f"{device.get('vendor') or ''}",
                              gpu, draft.gpus, primary, index):
                    continue
                apis.append(GpuApi(
                    name="OpenCL",
                    version=_version_only(device.get("version") or ""),
                    device=device.get("name"),
                    driver=device.get("driver_version"),
                    extra=_units(device),
                ))
                # What OpenCL counts does NOT go to `compute_units`, even
                # when that field is empty. Its «compute units» are those of
                # its programming model, not of the silicon: an Intel's
                # subslices (5 on an 80 EU Iris Xe), an NVIDIA's
                # multiprocessors (16 on a 2048-core RTX 3050). There they
                # carried the maker's label («5 EU», «16 CUDA cores»), false in
                # the unit, and they arrived before NVML and i915's ioctl, which
                # then could not set the right one. OpenCL's figure stays in its
                # row of the libraries table, where it is understood.

            if not apis:
                gpu["api_rejections"] = _rejections(gpu, draft.gpus, primary, index,
                                                    rejected, icds, bool(vulkan))
            if apis:
                gpu["apis"] = tuple(apis)
                gpu["driver_version"] = gpu.get("driver_version") or next(
                    (a.driver for i, a in enumerate(apis)
                     if a.driver and i not in not_the_cards_driver), None
                )


# The maker a Vulkan driver library is for, by its file name.
_ICD_VENDORS = (("intel", "Intel"), ("radeon", "AMD"), ("amd", "AMD"), ("nvidia", "NVIDIA"))


def _rejections(gpu: dict, gpus: list[dict], primary: int, index: int,
                rejected: list[dict], icds: list[str], vulkan_works: bool) -> tuple:
    """Why no Vulkan driver took this card, when one is installed for it.

    The driver's own words when it said them on stderr; otherwise, with
    Vulkan working for other cards and this maker's driver installed, an
    empty reason: it is there and does not accept the card.
    """
    for item in rejected:
        if _answers_for(item.get("device") or "", gpu, gpus, primary, index):
            return (("Vulkan", item.get("reason") or ""),)
    vendor = gpu.get("vendor") or ""
    installed = {maker for library in icds for word, maker in _ICD_VENDORS
                 if word in library.lower()}
    if vulkan_works and vendor in installed:
        return (("Vulkan", ""),)
    return ()


def _vulkan_memory(gpu: dict, device: dict) -> None:
    """The VRAM the driver does not publish, if Vulkan knows it.

    amdgpu writes it in sysfs and NVML gives it for NVIDIA's own driver.
    With nouveau there is neither, and a GeForce's card had no memory data.
    Vulkan lists the card's memory heaps, and it is there. It never
    overwrites what was known: the driver measures its own chip, and Vulkan
    reports what it can share out, which need not be the same.
    """
    bytes_ = device.get("device_memory_bytes")
    if not bytes_:
        return
    memory = gpu.get("memory") or GpuMemory()
    if memory.total_bytes:
        return
    # On an integrated card that heap is NOT the card's memory: it is system
    # RAM the driver lets it take (11.5 GB on a machine with 15.3 GB). As the
    # video memory's «Total» it read like a card with 11.5 GB of VRAM. The
    # model has its own field for it. When it could not be decided whether
    # it is integrated, `integrated` is None and the usual happens: guessing
    # the other way would take a dedicated card's VRAM away.
    if gpu.get("integrated"):
        if memory.gtt_total_bytes:
            return
        gpu["memory"] = dataclasses.replace(memory, gtt_total_bytes=bytes_)
        return
    gpu["memory"] = dataclasses.replace(memory, total_bytes=bytes_)


# -- matching and cleaning ---------------------------------------------------

def _without_crashing(function):
    """A broken API must not take the other two down."""
    try:
        return function()
    except Exception:                                  # noqa: BLE001
        return None


def _primary_index(gpus: list[dict]) -> int:
    """The card the system uses by default, the one it booted with."""
    for index, gpu in enumerate(gpus):
        if gpu.get("primary"):
            return index
    return 0


# The words that tell each maker in the text OpenGL and OpenCL return, a
# loose string and not a list of fields: «NVIDIA GeForce RTX 3050 Laptop
# GPU/PCIe/SSE2», «AMD Radeon 740M (RADV PHOENIX)», «Mesa Intel(R) Graphics
# (RPL-P)».
_VENDOR_WORDS = {
    "NVIDIA": ("nvidia", "geforce", "quadro", "tesla", "rtx ", "gtx "),
    "AMD": ("amd", "radeon", "radv", "amdgpu", "gfx1", "gfx9", "advanced micro"),
    "Intel": ("intel", "iris", "arc ", " uhd", " hd graphics", "anv"),
}
# Software rasterizers: they answer when no driver does, and are none of the
# installed cards.
_SOFTWARE_RASTERIZERS = ("llvmpipe", "softpipe", "swrast", "zink", "lavapipe")


def _vendor_of(text: str) -> Optional[str]:
    """Which maker an API's text sounds like, if any."""
    lower = text.lower()
    if any(word in lower for word in _SOFTWARE_RASTERIZERS):
        return "software"
    for name, words in _VENDOR_WORDS.items():
        if any(word in lower for word in words):
            return name
    return None


def _answers_for(text: str, gpu: dict, gpus: list[dict],
           primary: int, index: int) -> bool:
    """Whether this card answers this API and not another installed one.

    With one card there is nothing to decide. With several, who it says it is
    decides: OpenGL and OpenCL publish nothing else, not the PCI node. When
    the text cannot decide, the primary card is taken, without its compute
    units.
    """
    if len(gpus) <= 1:
        return index == primary
    who = _vendor_of(text)
    if who == "software":
        return False                      # none of the installed ones
    if who is None:
        return index == primary        # no clue: as before
    candidates = [i for i, g in enumerate(gpus) if (g.get("vendor") or "") == who]
    if not candidates:
        return index == primary
    if len(candidates) == 1:
        return index == candidates[0]
    # Several from the same maker: the model breaks the tie if it shows whole.
    lower = text.lower()
    for i in candidates:
        name = (gpus[i].get("name") or "").lower()
        if name and name in lower:
            return index == i
    return index == (primary if primary in candidates else candidates[0])


def _vulkan_of(gpu: dict, devices: list[dict]) -> Optional[dict]:
    """Vulkan does publish the PCI id, so nothing is guessed here."""
    for device in devices:
        if (device.get("vendor_id") == gpu.get("vendor_id")
                and device.get("device_id") == gpu.get("device_id")):
            return device
    return None


def _refine_name(gpu: dict, name: Optional[str]) -> None:
    """Replace a name that fits several models with the driver's."""
    if not name:
        return
    current = gpu.get("name")
    # A slash in the name is pci.ids's mark for «one of these».
    if current and "/" not in current:
        return
    gpu["name"] = _DRIVER_SUFFIX.sub("", name).strip() or current


def _version_only(text: str) -> Optional[str]:
    """«OpenCL 3.1» and «4.6 (Compatibility Profile) Mesa…» → «3.1» and «4.6»."""
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", text)
    return match.group(1) if match else (text.strip() or None)


def _mesa(text: str) -> Optional[str]:
    """The driver version in OpenGL's: Mesa's, or NVIDIA's («4.6.0 NVIDIA
    595.104.02»)."""
    match = _MESA_VERSION.search(text) or _NVIDIA_VERSION.search(text)
    return match.group(1) if match else None


def _units(device: dict) -> Optional[str]:
    units = device.get("compute_units")
    return (_("gpu.units.count").format(n=units)
            if units else None)


def _driver_version(device: dict) -> Optional[str]:
    """Vulkan gives the driver version in 32 bits, not packed the same by all.

    Almost all follow the API's own split (10, 10 and 12 bits), which gives
    Mesa as 26.2.1. NVIDIA uses its own, and read the standard way it gives a
    number that looks like nothing.
    """
    raw = device.get("driver_version")
    if not raw:
        return None
    if device.get("vendor_id") == 0x10DE:
        # Two digits in the last part, as NVIDIA writes it: 595.104.02.
        return f"{(raw >> 22) & 0x3FF}.{(raw >> 14) & 0xFF}.{(raw >> 6) & 0xFF:02d}"
    return f"{(raw >> 22) & 0x7F}.{(raw >> 12) & 0x3FF}.{raw & 0xFFF}"


def _codecs_of(gpu: dict, vaapi: list) -> tuple[VideoCodec, ...]:
    """The codecs of this card's render node, and only its own.

    Nothing to guess: VA-API opens on a given node, and the node hangs from
    the card's PCI device. The opposite of OpenGL, which does not say whom
    it speaks of.
    """
    slot = gpu.get("pci_slot")
    if not slot:
        return ()
    node = amdgpu.render_node(f"/sys/bus/pci/devices/{slot}")
    if not node:
        return ()
    name = os.path.basename(node)
    for entry in vaapi:
        if entry.get("node") != name:
            continue
        return tuple(
            VideoCodec(
                name=str(c.get("name")),
                decode=bool(c.get("decode")),
                encode=bool(c.get("encode")),
                max_bit_depth=c.get("bits"),
                profiles=tuple(c.get("profiles") or ()),
            )
            for c in entry.get("codecs") or []
        )
    return ()
