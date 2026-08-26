"""Proveedores de datos. Cada uno lee una fuente y no sabe nada de los demás."""

from .base import Draft, Provider
from .cpuid_x86 import CpuidIdentity
from .derived import DerivedSensors
from .dmi import DmiBoard
from .hwmon import HwmonSensors
from .privileged_memory import PrivilegedMemory
from .procfs import CpuUsage
from .rapl import RaplPower
from .spd_modules import SpdModules
from .sysfs_cpu import SysfsClocks, SysfsTopology
from .system import SystemIdentity, SystemState
from .turbo import TurboState

__all__ = [
    "Draft", "Provider",
    "SysfsTopology", "CpuidIdentity", "DmiBoard", "TurboState",
    "SysfsClocks", "CpuUsage", "HwmonSensors", "RaplPower", "DerivedSensors",
    "SystemIdentity", "SystemState", "PrivilegedMemory", "SpdModules",
]
