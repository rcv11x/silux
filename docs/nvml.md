# Desde qué driver de NVIDIA existe cada dato

Lo que Silux pide a NVML (`silux/nvml.py`) para una NVIDIA con el driver
propietario: la primera rama del driver que exporta cada función y en qué
tarjetas contesta. Una función que la biblioteca no trae, o que contesta con
un error, deja su dato vacío y no rompe los demás; donde hay otra forma de
pedirlo, se prueba la otra, en el orden de la tabla. Lo que contestó cada una
va al informe.

## La tabla

| Dato | Función | Desde | Tarjetas | Fuente |
|---|---|---|---|---|
| Abrir NVML | `nvmlInit_v2`; si no, `nvmlInit` | R319; 270 | | SYM, CL |
| Contar y abrir las tarjetas | `nvmlDeviceGetCount_v2`, `nvmlDeviceGetHandleByIndex_v2`; si no, sin `_v2` | R319; 270 | todas | SYM, CL, DQ |
| Ranura PCI | `nvmlDeviceGetPciInfo_v3`; si no, `_v2` o sin versión | R384; R285; 270 | todas | SYM, H, DQ |
| Nombre, UUID, versión del driver | `nvmlDeviceGetName`, `nvmlDeviceGetUUID`, `nvmlSystemGetDriverVersion` | 270 | todas | SYM, DQ |
| BIOS de video | `nvmlDeviceGetVbiosVersion` | R285 | todas | SYM, CL, DQ |
| Memoria total y usada | `nvmlDeviceGetMemoryInfo` | 270 | todas menos las integradas de los SoC | SYM, DQ |
| Uso de la GPU y de la memoria | `nvmlDeviceGetUtilizationRates` | 270 | Fermi o posterior | SYM, DQ |
| Uso de NVENC y NVDEC | `nvmlDeviceGetEncoderUtilization`, `nvmlDeviceGetDecoderUtilization` | R340 | Kepler o posterior | SYM, CL, DQ |
| Núcleos CUDA, ancho del bus | `nvmlDeviceGetNumGpuCores`, `nvmlDeviceGetMemoryBusWidth` | R510 | no lo dice; puede contestar `NOT_SUPPORTED` | SYM, CL, DQ |
| Temperatura | `nvmlDeviceGetTemperatureV`; si no, `nvmlDeviceGetTemperature` | R570; 270 | todas | H, DEP |
| Ventilador | `nvmlDeviceGetFanSpeed` | 270 | las dedicadas con ventilador propio | SYM, DQ |
| Consumo | `nvmlDeviceGetPowerUsage` | 270 | Fermi o posterior, con gestión de energía | SYM, DQ |
| | si no, los campos 185 y 186 con `nvmlDeviceGetFieldValues` | campos R535 (la función, R384) | 185: Ampere o posterior, menos GA100; 186: todas | H, CL |
| Límite de potencia actual | `nvmlDeviceGetEnforcedPowerLimit` | R331 | Kepler o posterior | SYM, CL, DQ |
| Límite de fábrica y rango | `nvmlDeviceGetPowerManagementDefaultLimit`, `nvmlDeviceGetPowerManagementLimitConstraints` | R304 | Kepler o posterior | SYM, CL, DQ |
| Relojes actuales y máximos | `nvmlDeviceGetClockInfo`, `nvmlDeviceGetMaxClockInfo` | 270; R285 (el de video, R361) | Fermi o posterior | SYM, CL, DQ |
| Enlace PCIe | `nvmlDeviceGetCurrPcieLinkGeneration`/`Width`, `nvmlDeviceGetMaxPcieLinkGeneration`/`Width` | R295 | Fermi o posterior | SYM, CL, DQ |
| Motivos de recorte | `nvmlDeviceGetCurrentClocksEventReasons`; si no, `nvmlDeviceGetCurrentClocksThrottleReasons` | R535; R304 | todas las que NVML admite del todo | SYM, H, CL, DQ |

El consumo es lo que `nvidia-smi` da como `power.draw`, `power.draw.average`
y `power.draw.instant`. Si las tres contestan que no, la tarjeta sale sin
consumo, con lo que contestó cada una en el informe: no se toma la media del
búfer de muestras (`nvmlDeviceGetSamples`, `NVML_TOTAL_POWER_SAMPLES`), que el
driver no da como consumo de la tarjeta, ni un límite.

Comprobado con `nvidia-smi` en dos RTX 4060 de sobremesa, una con el driver
595 y otra con el 620: las dos dan N/A en `power.draw`, `power.draw.average`
y `power.draw.instant`. Los 53 W que Silux enseñaba en las dos (desde la
0.4-prueba7) salían de ese búfer, y las dos quedan sin consumo con el mismo
arreglo.

La temperatura y los motivos de recorte se piden primero con la función
nueva: las antiguas están obsoletas desde CUDA 13.0 (R580) y se quitan en
CUDA 14, donde contestarán `NVML_ERROR_DEPRECATED`. Los bits de los motivos
son los mismos con los dos nombres.

## Fuentes

- **SYM**: el archivo de símbolos de Debian para `libnvidia-ml1`
  ([555.58.02-4](https://sources.debian.org/src/nvidia-graphics-drivers/555.58.02-4/debian/libnvidia-ml1.symbols/)),
  que da el driver mínimo que exporta cada símbolo. Lo mantiene Debian, no
  NVIDIA, y su valor más bajo, 270, es NVML 1.0.
- **CL**: el [registro de cambios de NVML](https://docs.nvidia.com/deploy/nvml-api/change-log.html).
  Se equivoca en `nvmlDeviceGetPciInfo_v3` (lo pone en R545; los símbolos y
  las cabeceras dicen R384) y llama `NVML_FI_GPU_POWER_*` a los campos que la
  cabecera llama `NVML_FI_DEV_POWER_*`.
- **DQ**: la [referencia de las consultas por tarjeta](https://docs.nvidia.com/deploy/nvml-api/api/group__nvmlDeviceQueries.html).
- **H**: `nvml.h` de cada versión de CUDA, en el historial de
  [NVIDIA/go-nvml](https://github.com/NVIDIA/go-nvml).
- **DEP**: los [avisos de obsolescencia](https://docs.nvidia.com/deploy/nvml-api/deprecations.html).

## Lo que no se ha confirmado

- Por qué esas dos 4060 dan N/A: si es cosa de los drivers recientes (una
  RTX 4050 de portátil con el 550 sí lo daba) o de esas tarjetas. Es una
  sospecha hasta que haya más casos: el volcado guarda ya qué llamada dio el
  consumo (`power_source`).
- Que «270» sea el driver de NVML 1.0 sale solo del archivo de Debian.
- Después de 555 no hay archivo de símbolos de Debian: que las funciones
  antiguas sigan exportándose sale de las cabeceras y de los avisos.
