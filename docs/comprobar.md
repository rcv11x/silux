# Comprobar a mano lo que dice silux

Para no tener que fiarse. Cada tabla dice, de un dato que enseña silux, de
dónde lo lee y con qué orden se comprueba sin silux. Si una orden y silux no
coinciden, es un fallo de alguien y merece un issue: lo que se sabe que no
coincide está al final.

Cómo leer las tablas:

- La segunda columna sale del código de `silux/providers/`. `cpuN` es cada
  hilo, `hwmonN` cada chip de sensores, `cardN` cada gráfica.
- Las órdenes se ejecutaron el 17 de noviembre de 2026 en un i5-10400 con
  Fedora 44. Las que llevan un asterisco no: piden root, o la herramienta no
  estaba instalada.
- Con el sistema en español algunas herramientas escriben comas decimales o
  traducen las cabeceras. Para comparar, delante de la orden: `LC_ALL=C`.
- `silux --json` no tapa nada (series, direcciones). Para compartir, el
  informe: `python3 -m silux.cli --report archivo.md`.

## Procesador

| Dato | De dónde lo lee silux | Para comprobarlo | Root |
|---|---|---|---|
| Nombre («Especificación») | la instrucción CPUID, hojas 0x80000002 a 4 | `lscpu \| grep 'Model name'` | no |
| Fabricante, familia, modelo, stepping | CPUID, hoja 1. El modelo que se enseña es el extendido | `lscpu \| grep -E 'Vendor\|family\|Model:\|Stepping'` | no |
| Núcleos e hilos | `/sys/devices/system/cpu/cpuN/topology/core_id` y `physical_package_id` | `lscpu -e=CPU,CORE,SOCKET` | no |
| Tipos de núcleo (P y E) | `/sys/devices/cpu_core/cpus` y `/sys/devices/cpu_atom/cpus` | `cat /sys/devices/cpu_core/cpus` * | no |
| Instrucciones | CPUID, por la tabla de `silux/features.py` | `grep -m1 flags /proc/cpuinfo`. Cuatro cambian de nombre: `pni` es SSE3, `fma` es FMA3, `ht` y `clflush` | no |
| Virtualización | CPUID (VT-x o AMD-V) | `lscpu \| grep Virtualization` | no |
| Microcódigo | `/sys/devices/system/cpu/cpu0/microcode/version` | `grep -m1 microcode /proc/cpuinfo` | no |
| Frecuencia de cada hilo | `cpuN/cpufreq/cpuinfo_avg_freq`; si no existe, `scaling_cur_freq`; si no, `cpuinfo_cur_freq` | `cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_avg_freq` (kHz). `lscpu -e=CPU,MHZ` lee otra fuente y puede no coincidir | no |
| Mínima | `cpuN/cpufreq/cpuinfo_min_freq` | `lscpu \| grep 'min MHz'` | no |
| Máxima (kernel) | `cpuN/cpufreq/cpuinfo_max_freq`, releída en cada muestreo | `lscpu \| grep 'max MHz'` | no |
| Base | `cpuN/cpufreq/base_frequency`; si no, CPUID hoja 0x16; en AMD, `cpuN/acpi_cppc/` | `cat /sys/devices/system/cpu/cpu0/cpufreq/base_frequency` | no |
| Máxima (silicio) | CPUID hoja 0x16 en Intel; `cpuN/cpufreq/amd_pstate_max_freq` en AMD | `cat /sys/devices/system/cpu/cpu0/cpufreq/amd_pstate_max_freq` * | no |
| Bus (BCLK) | CPUID hoja 0x16; en AMD se calcula: base entre multiplicador | no hay orden: en AMD no es una lectura | — |
| Turbo | `/sys/devices/system/cpu/intel_pstate/no_turbo`, o `cpufreq/boost` | `cat /sys/devices/system/cpu/intel_pstate/no_turbo` (1 es apagado) | no |
| Driver, gobernador, preferencia | `cpuN/cpufreq/scaling_driver`, `scaling_governor`, `energy_performance_preference` | `cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor` | no |
| Orden de preferencia de los núcleos (AMD) | `cpuN/cpufreq/amd_pstate_prefcore_ranking` | `grep . /sys/devices/system/cpu/cpu*/cpufreq/amd_pstate_prefcore_ranking` * | no |
| Uso | dos lecturas de `/proc/stat` | `top`, o `mpstat -P ALL 1` * | no |
| Carga media | `/proc/loadavg` | `uptime` | no |
| Temperatura | el sensor de paquete de `coretemp`, o Tdie o Tctl de `k10temp` (ver Sensores) | `sensors coretemp-isa-0000` | no |
| Consumo | dos lecturas de `/sys/class/powercap/intel-rapl:0/energy_uj` | `sudo turbostat --Summary --show PkgWatt -i 1` * | depende: aquí el contador se lee sin root, en otras distribuciones no |
| Límites de potencia | `/sys/class/powercap/intel-rapl:0/constraint_*_power_limit_uw` | `grep . /sys/class/powercap/intel-rapl:0/constraint_*_power_limit_uw` | no |
| Voltaje | el registro `0x198` del procesador (`/dev/cpu/N/msr`), por el ayudante | `sudo rdmsr -p 0 0x198` *: los bits 47 a 32, entre 8192, son voltios (Intel) | sí |

## Cachés

| Dato | De dónde lo lee silux | Para comprobarlo | Root |
|---|---|---|---|
| Nivel, tipo y tamaño | `cpuN/cache/indexM/level`, `type` y `size` | `lscpu -C` | no |
| Tamaño exacto en bytes | lo mismo | `LC_ALL=C lscpu -B -C=NAME,ONE-SIZE,ALL-SIZE` | no |
| Vías, conjuntos, línea | `ways_of_associativity`, `number_of_sets`, `coherency_line_size` | `lscpu -C=NAME,WAYS,SETS,COHERENCY-SIZE` | no |
| Cuántas hay y quién las comparte | `cpuN/cache/indexM/shared_cpu_list` | `grep . /sys/devices/system/cpu/cpu0/cache/index*/shared_cpu_list` | no |

El tamaño tiene que ser vías × conjuntos × línea: 8 × 64 × 64 son los 32 KiB
de una L1.

## Placa base

| Dato | De dónde lo lee silux | Para comprobarlo | Root |
|---|---|---|---|
| Fabricante, modelo, versión | `/sys/class/dmi/id/board_vendor`, `board_name`, `board_version` | `grep . /sys/class/dmi/id/board_{vendor,name,version}` | no |
| BIOS: fabricante, versión, fecha | `/sys/class/dmi/id/bios_vendor`, `bios_version`, `bios_date`, `bios_release` | `grep . /sys/class/dmi/id/bios_*`, o `sudo dmidecode -t 0` * | no |
| Equipo (marca, nombre, familia) | `/sys/class/dmi/id/sys_vendor`, `product_name`, `product_family` | `grep . /sys/class/dmi/id/product_*` (los series piden root y no se leen) | no |
| Tipo de chasis | `/sys/class/dmi/id/chassis_type` | `cat /sys/class/dmi/id/chassis_type` (3 es sobremesa, 10 portátil) | no |
| Chipset | Intel: el puente ISA (clase PCI 0601) de `/sys/bus/pci/devices`, por `pci.ids`. AMD: el que nombra el modelo de la placa | `lspci -nn \| grep -i 'ISA bridge'` | no |
| Puente raíz | el dispositivo `0000:00:00.0` | `lspci -s 00:00.0` | no |
| UEFI o BIOS heredada | si existe `/sys/firmware/efi`, y `fw_platform_size` | `ls /sys/firmware/efi` | no |
| Arranque seguro | la variable `SecureBoot-8be4df61-…` de `/sys/firmware/efi/efivars` | `mokutil --sb-state` | no |
| Tiempos de arranque: firmware y cargador | las variables `LoaderTimeInitUSec` y `LoaderTimeExecUSec` del gestor (systemd-boot, Limine) y, si no están, la tabla FPDT: `/sys/firmware/acpi/fpdt/boot/bootloader_launch_ns` y `exitbootservice_end_ns` | `systemd-analyze` (lo saca de los mismos sitios) | no |
| Tiempos de arranque: kernel, initrd y espacio de usuario | `systemctl show -p InitRDTimestampMonotonic -p UserspaceTimestampMonotonic -p FinishTimestampMonotonic` | `systemd-analyze` | no |
| TPM | `/sys/class/tpm/tpm0/tpm_version_major` | `cat /sys/class/tpm/tpm0/tpm_version_major` | no |

## Memoria

| Dato | De dónde lo lee silux | Para comprobarlo | Root |
|---|---|---|---|
| Total, disponible, caché, intercambio | `/proc/meminfo` | `free -b`, o `grep -E 'MemTotal\|MemAvailable' /proc/meminfo` | no |
| Módulos: zócalo, tamaño, tipo, velocidad, fabricante, referencia | la tabla SMBIOS (`/sys/firmware/dmi/tables/DMI`), por el ayudante | `sudo dmidecode -t 17` * | sí |
| Zócalos y capacidad máxima | la misma tabla | `sudo dmidecode -t 16` * | sí |
| Velocidad catalogada, latencias, perfiles XMP | el chip SPD de cada módulo: `/sys/bus/i2c/devices/*/eeprom` (drivers `ee1004` en DDR4, `spd5118` en DDR5) | `decode-dimms` * (paquete `i2c-tools`) | depende: aquí se lee sin root; si el módulo no está cargado, `sudo modprobe ee1004` |
| Fabricante y semana del módulo | el mismo SPD | `decode-dimms \| grep -E 'Manufacturer\|Manufacturing Date'` * | igual |
| Tráfico de la memoria (Intel) | el contador `uncore_imc` de `/sys/bus/event_source/devices`, por el ayudante | `sudo perf stat -a -e uncore_imc/data_reads/,uncore_imc/data_writes/ sleep 1` * | sí |

`MemTotal` es siempre algo menos que lo instalado: aquí, 15,43 GiB con dos
módulos de 8. Lo que falta se lo quedan el firmware y la gráfica integrada.

## Gráficos

| Dato | De dónde lo lee silux | Para comprobarlo | Root |
|---|---|---|---|
| Nombre y nombre en clave | los identificadores de `/sys/class/drm/cardN/device/vendor` y `device`, por `pci.ids` | `lspci -nn \| grep -E 'VGA\|3D\|Display'` | no |
| Identificador, subsistema, revisión | `device/vendor`, `device`, `subsystem_vendor`, `subsystem_device`, `revision` | `lspci -nn -v -s 00:02.0` (con la ranura de la tarjeta) | no |
| Driver | el enlace `device/driver` | `lspci -k -s 00:02.0` | no |
| Enlace PCIe | `device/current_link_speed`, `current_link_width`, `max_link_*` | `cat /sys/class/drm/card*/device/current_link_speed`, o `sudo lspci -vv` * (`LnkSta`): sin root no lo enseña | no por sysfs |
| VRAM total y usada (AMD) | `device/mem_info_vram_total`, `mem_info_vram_used` | `cat /sys/class/drm/card*/device/mem_info_vram_total` * | no |
| Tipo y fabricante de la VRAM (AMD) | un ioctl de `amdgpu` sobre `/dev/dri/renderD*`, y `mem_info_vram_vendor` | sin orden equivalente sencilla | no |
| Reloj del núcleo y de la memoria (AMD) | `device/pp_dpm_sclk`, `pp_dpm_mclk` y `hwmon/freq1_input` | `cat /sys/class/drm/card*/device/pp_dpm_sclk` * | no |
| Reloj (Intel) | `/sys/class/drm/cardN/gt_act_freq_mhz` y `gt_max_freq_mhz` | `cat /sys/class/drm/card*/gt_act_freq_mhz` (0 es en reposo) | no |
| Uso (AMD) | `device/gpu_busy_percent`, `mem_busy_percent` | `cat /sys/class/drm/card*/device/gpu_busy_percent` * | no |
| Uso por motor y vatios (Intel) | el PMU `i915` de perf, por el ayudante | `sudo intel_gpu_top` * | sí |
| En reposo (Intel) | `gt/gt0/rc6_residency_ms` | `cat /sys/class/drm/card*/gt/gt0/rc6_residency_ms` | no |
| Temperatura, ventilador, consumo | el `hwmon` de la tarjeta: `temp1_input`, `fan1_input`, `power1_average` | `sensors amdgpu-pci-*` * | no |
| BIOS de video (AMD) | `device/vbios_version` | `cat /sys/class/drm/card*/device/vbios_version` * | no |
| NVIDIA propietaria | la biblioteca NVML del driver | `nvidia-smi -q` * | no |
| Vulkan | se pregunta a la biblioteca en otro proceso | `vulkaninfo --summary` | no |
| OpenGL | igual | `glxinfo -B` | no |
| Códecs de video | VA-API sobre el nodo de render de la tarjeta | `vainfo` | no |
| Salidas y cuál está conectada | `/sys/class/drm/cardN-*/status` y `enabled` | `grep . /sys/class/drm/card*-*/status` | no |
| Monitor: nombre, tamaño, fecha, rango, modos | el EDID: `/sys/class/drm/cardN-*/edid` | `edid-decode /sys/class/drm/card1-HDMI-A-1/edid` *, o `di-edid-decode` con la misma ruta | no |
| Fabricante del monitor | las tres letras del EDID, por `pnp.ids` | `grep ^GSM /usr/share/hwdata/pnp.ids` | no |

La resolución que enseña silux es la nativa del monitor, no el modo que hay
puesto. El modo activo lo dicen `xrandr` o `kscreen-doctor -o`.

## Almacenamiento

| Dato | De dónde lo lee silux | Para comprobarlo | Root |
|---|---|---|---|
| Modelo | `/sys/block/DISCO/device/model` | `lsblk -d -o NAME,MODEL` | no |
| Firmware | `device/firmware_rev` (NVMe) o `device/rev` (SATA) | `lsblk -d -o NAME,REV` | no |
| Tamaño | `/sys/block/DISCO/size`, en sectores de 512 | `lsblk -b -d -o NAME,SIZE` | no |
| SSD o mecánico | `queue/rotational` | `lsblk -d -o NAME,ROTA` | no |
| Bus | el camino del dispositivo en sysfs | `lsblk -d -o NAME,TRAN` | no |
| Sectores y planificador | `queue/logical_block_size`, `physical_block_size`, `scheduler` | `lsblk -d -o NAME,LOG-SEC,PHY-SEC,SCHED` | no |
| Enlace PCIe de un NVMe | `current_link_speed` y `current_link_width` de su dispositivo PCI | `cat /sys/class/nvme/nvme0/device/current_link_speed` * | no |
| Particiones y sistema de archivos | `/sys/block/DISCO/PARTICIÓN/size` y `/proc/mounts` | `lsblk -b -o NAME,SIZE,FSTYPE,MOUNTPOINT` | no |
| Ocupado y libre | `statvfs` de cada punto de montaje | `df -B1 --output=source,size,used,avail,target` | no |
| Lectura y escritura | dos lecturas de `/sys/block/DISCO/stat` | `iostat -d 1` * | no |
| Temperatura | el `hwmon` del disco: `nvme`, o `drivetemp` en los SATA | `sensors 'drivetemp-*' 'nvme-*'`; sin el módulo, `sudo modprobe drivetemp` | no |
| Horas, escrito, vida, errores | el diagnóstico del disco (SMART), por el ayudante | `sudo smartctl -a /dev/sda` *, `sudo nvme smart-log /dev/nvme0` * | sí |

## Red

| Dato | De dónde lo lee silux | Para comprobarlo | Root |
|---|---|---|---|
| Interfaces y estado | `/sys/class/net/*/operstate` y `carrier` | `ip -br link` | no |
| Dirección física | `/sys/class/net/IF/address` | `ip -br link` | no |
| Velocidad y dúplex | `/sys/class/net/IF/speed` y `duplex` | `ethtool IF \| grep -E 'Speed\|Duplex'` | no |
| MTU | `/sys/class/net/IF/mtu` | `ip link show IF` | no |
| IPv4 y máscara | un ioctl sobre la interfaz | `ip -4 -br addr` | no |
| IPv6 | `/proc/net/if_inet6` | `ip -6 -br addr` | no |
| Puerta de enlace | `/proc/net/route` | `ip route show default` | no |
| Modelo y fabricante de la tarjeta | `/sys/class/net/IF/device/vendor` y `device`, por `pci.ids` | `lspci -nn \| grep -iE 'ethernet\|network'` | no |
| Driver | el enlace `/sys/class/net/IF/device/driver` | `ethtool -i IF` | no |
| Tráfico y errores | `/sys/class/net/IF/statistics/` | `ip -s link show IF` | no |
| Wifi o cable | si existen `wireless` o `phy80211` en la interfaz | `iw dev` * | no |

## Batería

No hay ningún equipo con batería entre los comprobados: esta tabla sale del
código y ninguna orden se ha ejecutado.

| Dato | De dónde lo lee silux | Para comprobarlo | Root |
|---|---|---|---|
| Estado y porcentaje | `/sys/class/power_supply/BAT*/status` y `capacity` | `upower -i $(upower -e \| grep BAT)` * | no |
| Capacidad de diseño, actual y ahora | `energy_full_design`, `energy_full`, `energy_now` (o `charge_*` por el voltaje) | `grep . /sys/class/power_supply/BAT0/energy_*` * | no |
| Voltaje y potencia | `voltage_now`, `voltage_min_design`, `power_now` (o `current_now`) | `upower -i …` *: «voltage», «energy-rate» | no |
| Ciclos | `cycle_count` | `cat /sys/class/power_supply/BAT0/cycle_count` * | no |
| Fabricante, modelo, tecnología | `manufacturer`, `model_name`, `technology` | `upower -i …` * | no |
| Umbrales de carga | `charge_control_start_threshold` y `charge_control_end_threshold` | `grep . /sys/class/power_supply/BAT0/charge_control_*` * | no |

## Sistema

| Dato | De dónde lo lee silux | Para comprobarlo | Root |
|---|---|---|---|
| Distribución y versión | `/etc/os-release` | `cat /etc/os-release` | no |
| Kernel | `/proc/version` | `uname -r`, `cat /proc/version` | no |
| Nombre del equipo | `/proc/sys/kernel/hostname` | `hostname` | no |
| Sistema de inicio | `/proc/1/comm` | `cat /proc/1/comm` | no |
| Escritorio, sesión, intérprete | las variables `XDG_CURRENT_DESKTOP`, `XDG_SESSION_TYPE` y `SHELL` | `echo $XDG_CURRENT_DESKTOP $XDG_SESSION_TYPE $SHELL` | no |
| Tiempo encendido | `/proc/uptime` | `uptime` | no |
| Procesos e hilos | los directorios numéricos de `/proc` y sus `task` | `ps -e --no-headers \| wc -l`, `ps -eL --no-headers \| wc -l` | no |
| Archivos abiertos | `/proc/sys/fs/file-nr` | `cat /proc/sys/fs/file-nr` | no |

## Sensores

| Dato | De dónde lo lee silux | Para comprobarlo | Root |
|---|---|---|---|
| Todos los de un chip | `/sys/class/hwmon/hwmonN/name` y cada `*_input` | `sensors`, o `sensors -j` para compararlo con `silux --json` | no |
| Nombre de cada canal | `tempN_label`, `fanN_label`, `inN_label`. Si el chip no lo da, silux numera («Temperatura 1») y lo dice al pie | `grep . /sys/class/hwmon/hwmon*/*_label` | no |
| Límites | `tempN_max`, `tempN_crit`, `tempN_min`. Si el chip no los da, silux los estima y lo marca | `sensors -j`: si no trae `_max` ni `_crit`, el de silux es estimado | no |
| Temperatura por núcleo (Intel) | el chip `coretemp` | `sensors coretemp-isa-0000` | no |
| Temperatura del procesador (AMD) | el chip `k10temp`: Tdie si existe, y si no Tctl | `sensors k10temp-pci-00c3` * | no |
| Ventiladores y voltajes de la placa | el chip de la placa (`it87`, `nct6775`…), si su driver está cargado | `sensors`; si no sale ninguno, `sudo sensors-detect` * | no para leer |
| Zonas `acpitz` | `hwmon` de ACPI. 16,8, 27,8 y 29,8 °C fijos son un relleno del firmware, y silux los apaga | `sensors acpitz-acpi-0` | no |
| Relojes de cada hilo | los mismos de Procesador | — | no |
| Tráfico de red | `/sys/class/net/IF/statistics/`, dos lecturas | `ip -s link` | no |

## Lo que hoy no coincide

Medido el mismo día. El detalle y lo que se propone, en
[pendientes.md](pendientes.md).

| Dato | silux | La orden | Quién tiene razón |
|---|---|---|---|
| Ocupado de una partición | cuenta como ocupado lo reservado al administrador | `df` no | `df`. El libre sí coincide |
| Firmware de un disco SATA | los 4 últimos caracteres («12.7») | `lsblk -o REV`: «SBFA12.7» | `lsblk` |
| Modelo de un disco SATA | 16 caracteres | `lsblk -o MODEL`: entero | `lsblk` |
| Tamaño del monitor | 480 × 270 mm, 21,7" | `di-edid-decode`: 476 × 268 mm, 21,5" | la orden |
| Bandera `sgx` | sale | `/proc/cpuinfo` no la trae | los dos: el procesador la tiene y el firmware no la activa |
| Bytes de red en Sensores | en potencias de 1024 con la etiqueta «MB» | `ip -s link` da bytes | la página de Red, que va en decimal |
| Frecuencia de un hilo dormido | a veces el techo exacto | `/proc/cpuinfo` dice otra cosa | sin decidir |
