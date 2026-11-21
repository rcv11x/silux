"""Proveedores de datos. Cada uno lee una fuente y no sabe nada de los demás."""

from .base import Draft, Provider
from .cppc import CppcClocks
from .armcpu import ArmIdentity
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
from .battery import Batteries
from .msr_voltage import MsrVoltage
from .msr_pstate import AmdPstateClocks
from .imc import ImcTraffic
from .rapl import RaplPower, PowerLimits
from .spd_modules import SpdModules
from .storage import Disks
from .sysfs_cpu import SysfsClocks, SysfsTopology
from .cpuidle import CpuIdle
from .thermal_throttle import ThermalThrottleCounts
from .devices import ConnectedDevices
from .pci import PciDevices, PlatformInfo
from .system import SystemIdentity, SystemSecurity, SystemState
from .system_deps import SystemDependencies
from .turbo import TurboState

__all__ = [
    "Draft", "Provider",
    "SysfsTopology", "CpuidIdentity", "ArmIdentity", "CppcClocks", "DmiBoard", "TurboState",
    "SysfsClocks", "CpuUsage", "HwmonSensors", "MsrVoltage", "AmdPstateClocks",
    "RaplPower", "ImcTraffic", "DerivedSensors",
    "Batteries",
    "DrmGpus", "GpuState", "GpuApis", "NvidiaGpus", "NetworkInterfaces",
    "ConnectedDevices", "CpuIdle", "ThermalThrottleCounts", "PowerLimits", "PciDevices", "PlatformInfo",
    "SystemIdentity", "SystemSecurity", "SystemState", "SystemDependencies", "PrivilegedMemory", "SpdModules", "Disks",
]
