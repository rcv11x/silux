"""El contrato entre el programa y su ayudante privilegiado.

Vive en un módulo aparte porque lo comparten los dos lados, y porque tener el
contrato escrito en un solo sitio es lo que permite auditarlo de un vistazo:
estas son *todas* las cosas que el proceso con privilegios sabe hacer.
"""

from __future__ import annotations

PROTOCOL_VERSION = 1

# Acciones admitidas. Cualquier otra cosa se rechaza sin mirarla.
ACTION_PING = "ping"
ACTION_SMBIOS = "smbios"
ACTION_MSR = "msr"
ACTION_SMART = "smart"
ACTION_GPU_PMU = "gpu_pmu"
ACTION_RAPL = "rapl"
ACTIONS = frozenset({ACTION_PING, ACTION_SMBIOS, ACTION_MSR, ACTION_SMART,
                     ACTION_GPU_PMU, ACTION_RAPL})

# Rutas que el ayudante puede abrir. No hay ninguna forma de pedirle otra.
DMI_TABLE = "/sys/firmware/dmi/tables/DMI"
DMI_ENTRY_POINT = "/sys/firmware/dmi/tables/smbios_entry_point"
MSR_DEVICE = "/dev/cpu/{cpu}/msr"

# Los nombres de disco que el ayudante acepta abrir. El patrón es estricto a
# propósito: sin él, un nombre como «../../etc/shadow» le haría abrir
# cualquier cosa. Aquí solo caben nvme0, nvme0n1, sda y parecidos.
DISK_NAME = r"^(nvme\d+n\d+|nvme\d+|sd[a-z]{1,2}|hd[a-z])$"
DISK_DEVICE = "/dev/{name}"

# El ayudante solo pide los registros de diagnóstico, que son de lectura. No
# hay forma de pedirle un comando de escritura ni de borrado.
NVME_GET_LOG_PAGE = 0x02          # opcode de administración
NVME_LOG_SMART = 0x02             # el registro de salud
ATA_SMART_READ_DATA = 0xD0        # función de SMART READ DATA
SMART_DATA_BYTES = 512            # lo que ocupa la respuesta de los dos

# Registros MSR permitidos, con lo que significan. La lista blanca existe
# porque un MSR arbitrario puede exponer información sensible o depender de
# efectos secundarios; estos son de solo lectura y bien documentados.
MSR_ALLOWED: dict[int, str] = {
    0x0198: "IA32_PERF_STATUS",          # voltaje y ratio actuales
    0x0199: "IA32_PERF_CTL",             # ratio solicitado
    0x019C: "IA32_THERM_STATUS",         # margen hasta el límite térmico
    0x01A2: "MSR_TEMPERATURE_TARGET",    # TjMax
    0x01AD: "MSR_TURBO_RATIO_LIMIT",     # multiplicadores turbo por nº de núcleos
    0x00CE: "MSR_PLATFORM_INFO",         # ratio base, mínimo y máximo eficiente
    0x0610: "MSR_PKG_POWER_LIMIT",       # PL1 y PL2 configurados
    0x0606: "MSR_RAPL_POWER_UNIT",       # unidades para interpretar los de arriba
    0xC0010293: "AMD_MSR_CORE_ENERGY",   # energía por núcleo en AMD
    0xC0010299: "AMD_MSR_RAPL_UNIT",
}

# El PMU de las gráficas Intel. Es la única acción que no lleva parámetros: el
# ayudante enumera él mismo los PMU y los eventos, y solo abre los que encajan
# en estos dos patrones. El cliente no manda nombres ni números de evento.
#
# Los contadores de ocupación son agregados de la máquina entera y no llevan
# periodo de muestreo, así que cuentan nanosegundos de motor ocupado y nada
# más: ni pilas de llamadas, ni direcciones, ni actividad de ningún proceso.
PMU_ROOT = "/sys/bus/event_source/devices"
PMU_GPU = r"^(i915|xe_[0-9a-f]{4}_[0-9a-f]{2}_[0-9a-f]{2}\.[0-9a-f])$"
PMU_EVENT = r"^(rcs|bcs|vcs|vecs|ccs)\d+-busy$"

# Tamaño máximo de un mensaje, en bytes. Evita que un lado pueda hacer que el
# otro reserve memoria sin límite.
MAX_MESSAGE = 4 * 1024 * 1024


class ProtocolError(RuntimeError):
    """El otro lado ha dicho algo que no encaja con el contrato."""
