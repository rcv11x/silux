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
| Consumo estimado | `nvmlDeviceGetSamples` con `NVML_TOTAL_POWER_SAMPLES`; se enseña solo si ninguna de las de arriba contesta | R340 | Kepler o posterior | SYM, H |
| Energía gastada (solo al informe) | `nvmlDeviceGetTotalEnergyConsumption` | R384 | Volta o posterior | SYM, H |
| Límite de potencia actual | `nvmlDeviceGetEnforcedPowerLimit` | R331 | Kepler o posterior | SYM, CL, DQ |
| Límite de fábrica y rango | `nvmlDeviceGetPowerManagementDefaultLimit`, `nvmlDeviceGetPowerManagementLimitConstraints` | R304 | Kepler o posterior | SYM, CL, DQ |
| Relojes actuales y máximos | `nvmlDeviceGetClockInfo`, `nvmlDeviceGetMaxClockInfo` | 270; R285 (el de video, R361) | Fermi o posterior | SYM, CL, DQ |
| Enlace PCIe | `nvmlDeviceGetCurrPcieLinkGeneration`/`Width`, `nvmlDeviceGetMaxPcieLinkGeneration`/`Width` | R295 | Fermi o posterior | SYM, CL, DQ |
| Motivos de recorte | `nvmlDeviceGetCurrentClocksEventReasons`; si no, `nvmlDeviceGetCurrentClocksThrottleReasons` | R535; R304 | todas las que NVML admite del todo | SYM, H, CL, DQ |

El consumo es lo que `nvidia-smi` da como `power.draw`, `power.draw.average`
y `power.draw.instant`. Si las tres contestan que no y el búfer de muestras
sí, la tarjeta sale con el consumo estimado del driver, en su propio campo y
nunca como el consumo. Lo que contestó cada vía, el búfer y la energía
incluidos, va al informe. Qué vale cada cifra está abajo, en «El consumo, a
fondo».

La temperatura y los motivos de recorte se piden primero con la función
nueva: las antiguas están obsoletas desde CUDA 13.0 (R580) y se quitan en
CUDA 14, donde contestarán `NVML_ERROR_DEPRECATED`. Los bits de los motivos
son los mismos con los dos nombres.

## El consumo, a fondo

### Las vías que hay

| Vía | Qué da | Unidad | Tarjetas, según la cabecera |
|---|---|---|---|
| `nvmlDeviceGetPowerUsage` | El consumo de la tarjeta entera. La media de 1 s en Ampere y posteriores (menos GA100); la lectura instantánea en las anteriores y en GA100 | mW | Fermi o posterior, «solo si admite gestión de energía» |
| Campo 186, `NVML_FI_DEV_POWER_INSTANT` | La última lectura | mW | todas |
| Campo 185, `NVML_FI_DEV_POWER_AVERAGE` | La media de 1 s | mW | Ampere o posterior, menos GA100 |
| `nvmlDeviceGetSamples` con `NVML_TOTAL_POWER_SAMPLES` | El búfer circular de lecturas que mantiene el driver, cada una con su marca de tiempo | mW | Kepler o posterior |
| `nvmlDeviceGetTotalEnergyConsumption` (y los campos 83 y 191) | La energía gastada desde que se cargó el driver | mJ | Volta o posterior |

`nvidia-smi` enseña las tres primeras como `power.draw`,
`power.draw.instant` y `power.draw.average`, y el búfer aparte, en
`nvidia-smi -q -d POWER`, como «Power Samples» con su duración, su número de
muestras, el mínimo, el máximo y la media. Las dos consultas de campo
llegaron entre las ramas 525 y 530 (la primera publicada con ellas es la
535); desde la 575, `nvidia-smi -q` escribe siempre las dos líneas, «Average
Power Draw» e «Instantaneous Power Draw».

Los programas que se han leído (LACT, nvtop y MangoHud) piden solo
`nvmlDeviceGetPowerUsage`: si no contesta, salen sin consumo. Ninguno usa el
búfer, los campos ni el contador de energía.

El búfer son lecturas del monitor de potencia del driver
(`NV2080_CTRL_GPUMON_SAMPLE_TYPE_PWR_MONITOR_STATUS` en los módulos
abiertos), no un relleno: cambian de una muestra a otra. En las dos tarjetas
donde se ha mirado guardaba 119 muestras de los últimos 2,4 s.

### Las tarjetas sin sensor de consumo

Hay tarjetas que no llevan en la placa el circuito que mide lo que gastan, y
el driver calcula la cifra con un modelo. La RTX 4060 de sobremesa es una:
lo dice NVIDIA («the graphics card does not have a sensor to report power
consumption») y lo dicen las reseñas que la midieron en el cable. En reposo
gasta entre 11 y 14 W y la estimación del driver marca entre 51 y 53 W.

En Linux, esas tarjetas contestan así: `nvmlDeviceGetPowerUsage` y los campos
185 y 186, que no (N/A en `nvidia-smi`, con el driver propietario y con los
módulos abiertos, al menos desde la rama 565); el búfer de muestras, que sí,
con la estimación. Los 52 a 55 W del búfer de dos RTX 4060 en reposo, una con
el driver 595 y otra con el 620, son esa cifra.

De ahí la regla: **una cifra que solo sale del búfer es una estimación del
driver, no una medida**. Se puede enseñar con ese nombre; no es «el consumo».

Así la enseña Silux:

- En la página de la gráfica, una fila propia: «Consumo estimado: 53 W ·
  media de las muestras del driver, últimos 2.4 s». La ventana es la de las
  muestras nuevas desde la lectura anterior; en la primera, todo el búfer.
- Al pie, que el driver no mide el consumo de esa tarjeta: lo calcula, y en
  reposo puede marcar más de lo que gasta.
- En `--json`, `power_estimate_w`, `power_estimate_window_s` y
  `power_estimate_samples`. `power_w` se queda vacío.
- Ni en Sensores, ni en Inicio, ni en la ficha del consumo, ni en ninguna
  gráfica: no la toman por el consumo ni el máximo ni la media.

En una tarjeta con sensor el búfer también se pregunta, pero solo va al
informe. `power_source` dice qué vía dio `power_w`. No es lo que NVML llama
«power source» (`nvmlDeviceGetPowerSource`, corriente o batería).

### Por generación

Lo que dice la cabecera y lo que se ha visto. Donde pone «sin datos», no se
ha encontrado un caso ni una fuente.

| Generación | Última rama | `GetPowerUsage` | Campos 186 / 185 | Búfer | Energía |
|---|---|---|---|---|---|
| Maxwell (GTX 750, 900) | 580 | instantánea | sí / no | sí | no |
| Pascal (GTX 10) | 580 | instantánea | sí / no | sí | no |
| Volta (Titan V) | 580 | instantánea | sí / no | sí | sí |
| Turing (GTX 16, RTX 20) | actual | instantánea | sí / no | sí | sí |
| Ampere (RTX 30) | actual | media de 1 s | sí / sí | sí | sí |
| Ada (RTX 40) | actual | media de 1 s | sí / sí | sí | sí |
| Blackwell (RTX 50) | actual | media de 1 s | sí / sí | sí | sí |

Es lo que la cabecera promete para una tarjeta con sensor. Lo visto:

- **Sobremesa con sensor** (RTX 3060 con el 620): `GetPowerUsage` contesta.
- **Sobremesa sin sensor** (RTX 4060): arriba. De las que se alimentan solo
  por la ranura (GT 710, GT 1030, GTX 1050 y 1050 Ti, GTX 1650, RTX 3050 de
  6 GB), sin datos propios.
- **Portátil** (RTX 4050 con el 550): contesta cuando la tarjeta está
  despierta. En una RTX 3050 de portátil con el 570, la media daba N/A y la
  instantánea contestaba.
- **Maxwell, Pascal y Volta**, de sobremesa o de portátil: sin datos
  propios con el driver propietario.

### Las portátiles dormidas

En un portátil con Turing o posterior, el driver apaga la gráfica cuando no
se usa (Runtime D3; solo ahí: en sobremesa y en las anteriores no lo activa).
Preguntarle entonces tiene dos efectos:

- **La despierta.** Toda llamada de control al driver pide la tarjeta
  encendida, salvo las marcadas como que no la tocan. Por eso Silux cierra
  NVML mientras una NVIDIA está suspendida (`sleeping_nvidias`).
- **La primera lectura puede ser imposible.** Hay tres casos publicados, con
  las ramas 550 y 570: 588 y 593 W en una tarjeta de 145 W como mucho, 749 W
  en una de 45 y 752 W en una de 80. En los tres la tarjeta dormía o acababa
  de despertar, y la lectura siguiente era normal. El reloj y el estado de
  rendimiento que acompañan a esa lectura también son viejos.

Una lectura de 588,21 W seguida de 1,28 W unos segundos después, en una RTX
4050 de portátil con el 550, encaja con esto: la primera despertó la
tarjeta. La misma cifra, 588,21 W, sale en el caso publicado de otra tarjeta
con el mismo driver.

Por eso Silux descarta toda lectura por encima de 1,5 veces el mayor límite
que declara la tarjeta (el vigente, el de fábrica o el máximo), venga de la
vía que venga. No pasa a la vía siguiente: esa muestra sale sin consumo, con
una nota, y el informe dice la cifra, la vía y el techo. Si la tarjeta
estaba suspendida desde la lectura anterior, la nota lo da como causa
probable. El margen hace falta: una tarjeta a tope va pegada a su límite y
lo pasa por poco (una RTX 3060 tiene el máximo igual al de fábrica, 170 W).
Las imposibles vistas van de 4 a 16 veces el máximo. Sin ningún límite
declarado queda el techo general de 5000 W, y el informe lo dice. Del búfer
de muestras se apartan las que pasan el techo.

Los módulos abiertos enseñan de dónde puede salir una cifra vieja: el driver
copia la potencia cada 250 ms a una página de memoria compartida, con su
marca de tiempo, para que NVML la lea de ahí. Con la tarjeta dormida nadie
la actualiza. Que el 588 salga de ahí es una suposición: la biblioteca que
lo lee no es abierta.

### Con root y sin root

Ninguna fuente dice que leer el consumo pida root. La cabecera señala las
funciones que lo piden, y son las que cambian algo (el límite de potencia,
el modo de cómputo); las de lectura no. En los módulos abiertos el permiso
va por llamada de control, pero las del monitor de potencia no están en el
código publicado: corren en el firmware.

El único indicio en contra era aquel 588 W como usuario y 1,28 W con `sudo`
justo después, y lo explica la tarjeta dormida. Falta repetirlo con dos
lecturas seguidas como usuario.

### Módulos abiertos y propietarios

Desde Turing, el driver puede dejar la gestión de la tarjeta en el firmware
GSP; los módulos abiertos lo hacen siempre. Para el consumo cambia el camino
y no la cifra: con GSP, o desde Ampere sin él, el driver sondea la potencia a
la página compartida; en una tarjeta anterior sin GSP no hay sondeo. En una
RTX 4060 las tres consultas dan N/A con los dos juegos de módulos.

### nouveau y NVK

nouveau publica por hwmon lo que sabe leer de cada generación (kernel 6.18):

| Generación | Temperatura | Voltaje | Consumo (`power1_input`) |
|---|---|---|---|
| Fermi, Kepler, Maxwell | sí | sí | solo si la BIOS de video declara un sensor INA209, INA219 o INA3221 |
| Pascal | sí | no | no |
| Volta y Turing, sin GSP | sí | no | no |
| Volta y Turing, con GSP | no | no | no |
| Ampere, Ada, Blackwell | no | no | no |

El ventilador sale del mismo subsistema que la temperatura: donde no hay una,
no hay otro.

Con el firmware GSP, nouveau no registra hwmon: no crea ninguno de los tres
subsistemas de los que sale. En el kernel 6.18 lo usa por defecto si el
firmware está instalado; en Ada y posteriores no hay otra forma. NVK es el
driver de Vulkan de Mesa, encima de nouveau: no añade ningún sensor.

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

- **SMI**: el manual de `nvidia-smi` de la rama 620, con su registro de
  cambios por rama ([Arch Linux](https://man.archlinux.org/man/nvidia-smi.1)).
- **OGKM**: [NVIDIA/open-gpu-kernel-modules](https://github.com/NVIDIA/open-gpu-kernel-modules)
  en 620.73.04: `ctrl2080gpumon.h` (el búfer), `cl00de.h` y
  `gpu_user_shared_data.c` (la página compartida y su sondeo),
  `dynamic-power.c` (Runtime D3) y `rmapi/control.c` (cuándo una llamada
  pide la tarjeta encendida).
- **Los programas**: [LACT](https://github.com/ilya-zlobintsev/LACT)
  (`lact-daemon/src/server/gpu_controller/nvidia.rs`),
  [nvtop](https://github.com/Syllo/nvtop) (`src/extract_gpuinfo_nvidia.c`) y
  [MangoHud](https://github.com/flightlessmango/MangoHud) (`src/nvidia.cpp`).
- **nouveau**: el kernel 6.18, `drivers/gpu/drm/nouveau/nouveau_hwmon.c`,
  `nvkm/engine/device/base.c` (qué subsistemas tiene cada chip),
  `nvkm/subdev/iccsense/base.c` y `nvkm/subdev/therm/gp100.c`.
- **La RTX 4060 sin sensor**: la respuesta de NVIDIA en su foro de GeForce
  ([4060 idle power](https://www.nvidia.com/en-us/geforce/forums/geforce-graphics-cards/5/522968/4060-idle-power/)),
  las reseñas de TechPowerUp
  ([una de ellas](https://www.techpowerup.com/review/gigabyte-geforce-rtx-4060-gaming-oc/42.html))
  y, en Linux, [un caso con el 565](https://forum.endeavouros.com/t/issue-nvidia-rtx-4060-power-draw-metrics-show-as-n-a/67045).
- **Las lecturas imposibles de las portátiles**: tres hilos del foro de
  desarrolladores de NVIDIA:
  [588 y 593 W en Runtime D3](https://forums.developer.nvidia.com/t/rtx-5000-ada-laptop-gpu-reports-invalid-588-593-w-power-draw-while-runtime-d3-suspended/378866),
  [749 W](https://forums.developer.nvidia.com/t/linux-driver-570-124-06-reports-silly-power-draw-on-mobile-gpu/326477)
  y [752 W en la primera consulta](https://forums.developer.nvidia.com/t/nvidia-smi-driver-version-570-on-ubuntu-24-04-shows-wrong-power-consumption-when-running-for-the-first-time/326408).
- **Las ramas**: el [calendario de retirada](https://forums.developer.nvidia.com/t/unix-graphics-feature-deprecation-schedule/60588)
  de NVIDIA: la 580 es la última para Maxwell, Pascal y Volta.

## Lo que no se ha confirmado

- Lo de la RTX 4060 sin sensor y las reseñas que la midieron se ha leído en
  citas y resúmenes: las páginas de NVIDIA y de TechPowerUp no se dejaron
  abrir desde aquí.
- Qué marca el búfer de una RTX 4060 con carga, y si su contador de energía
  contesta. Y qué otras tarjetas no tienen sensor.
- Que una cifra que solo sale del búfer sea siempre una estimación: sale de
  dos tarjetas del mismo modelo.
- Si leer el consumo cambia con root: falta la prueba de dos lecturas
  seguidas como usuario en una portátil recién despertada.
- De dónde sale la lectura imposible de una portátil dormida.
- Maxwell, Pascal y Volta con el driver propietario, y Blackwell: ningún
  caso propio.
- Que «270» sea el driver de NVML 1.0 sale solo del archivo de Debian.
- Después de 555 no hay archivo de símbolos de Debian: que las funciones
  antiguas sigan exportándose sale de las cabeceras y de los avisos.
