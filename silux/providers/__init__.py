"""Proveedores de datos. Cada uno lee una fuente y no sabe nada de los demás."""

from .base import Draft, Provider
from .cppc import CppcClocks
from .cpuid_x86 import CpuidIdentity
from .derived import DerivedSensors
from .dmi import DmiBoard
from .drm import DrmGpus, GpuState
from .gpu_apis import GpuApis
from .network import NetworkInterfaces
from .nvidia import NvidiaGpus
from .hwmon import HwmonSensors
from .privileged_memory import PrivilegedMemory
from .procfs import CpuUsage
from .rapl import RaplPower
from .spd_modules import SpdModules
from .storage import Disks
from .sysfs_cpu import SysfsClocks, SysfsTopology
from .system import SystemIdentity, SystemState
from .turbo import TurboState

__all__ = [
    "Draft", "Provider",
    "SysfsTopology", "CpuidIdentity", "CppcClocks", "DmiBoard", "TurboState",
    "SysfsClocks", "CpuUsage", "HwmonSensors", "RaplPower", "DerivedSensors",
    "DrmGpus", "GpuState", "GpuApis", "NvidiaGpus", "NetworkInterfaces",
    "SystemIdentity", "SystemState", "PrivilegedMemory", "SpdModules", "Disks",
]
