"""A GPU spec sheet's figures worked out from what the driver reads.

Shading and texture units, FP32 TFLOPS and fill rates come from the
compute units, the ROPs and the core's top clock, by each architecture's
own formula. An architecture with no formula here gives none: no figure
beats a wrong one. Only AMD for now: NVIDIA's cores and Intel's units
take a table per architecture.

Each is a calculation, and the page says so with what it used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# GCN (gfx6 to 9) and RDNA (gfx10 to 12): 64 stream processors and 4 texture
# units per compute unit. RDNA 3 and 4 issue two FP32 operations per clock
# (dual issue), which AMD counts in its TFLOPS.
AMD_SHADERS_PER_CU = 64
AMD_TMUS_PER_CU = 4
AMD_KNOWN = range(6, 13)
AMD_DUAL_ISSUE = (11, 12)


@dataclass(frozen=True)
class Figures:
    shading_units: int
    texture_units: int
    clock_hz: int
    # Operations per unit and clock: 2 for a fused multiply-add, times 2 more
    # with dual issue.
    operations: int
    rops: Optional[int] = None

    @property
    def tflops(self) -> float:
        return self.shading_units * self.operations * self.clock_hz / 1e12

    @property
    def gigapixels(self) -> Optional[float]:
        return self.rops * self.clock_hz / 1e9 if self.rops else None

    @property
    def gigatexels(self) -> float:
        return self.texture_units * self.clock_hz / 1e9


def _amd_generation(isa: Optional[str]) -> Optional[int]:
    """«gfx1201» -> 12, «gfx906» -> 9, «gfx90a» -> 9."""
    if not isa or not isa.startswith("gfx") or len(isa) < 6:
        return None
    try:
        return int(isa[3:-2])
    except ValueError:
        return None


def amd(compute_units: Optional[int], rops: Optional[int], isa: Optional[str],
        clock_hz: Optional[int]) -> Optional[Figures]:
    generation = _amd_generation(isa)
    if not compute_units or not clock_hz or generation not in AMD_KNOWN:
        return None
    return Figures(shading_units=compute_units * AMD_SHADERS_PER_CU,
                   texture_units=compute_units * AMD_TMUS_PER_CU,
                   clock_hz=clock_hz,
                   operations=4 if generation in AMD_DUAL_ISSUE else 2,
                   rops=rops)


def of(gpu) -> Optional[Figures]:
    """A card's figures, with the top clock it reports; None where there is
    no formula for it."""
    if gpu.driver == "amdgpu":
        return amd(gpu.compute_units, gpu.rops, gpu.isa, gpu.clocks.core_max_hz)
    return None
