## Inicio

ASUS PRIME A520M-A II
CachyOS · Linux 7.3.5-2-cachyos · KDE · wayland · encendido 29 min
silux-pc

### Procesador

AMD Ryzen 5 5600G
6 núcleos · 12 hilos · Cezanne
3.51 GHz 49.2 °C

### Gráfica

GeForce RTX 4060
PCIe 3.0 × 8 · 3072 núcleos CUDA
0.0 % 48.0 °C 53 W

### Memoria

5.3 GiB de 31.1 GiB
17 % ocupada
Aplicaciones 5.4 GiB · Caché 14.8 GiB · Buffers 57.1 MiB · Libre 10.9 GiB

### Almacenamiento

2.0 TB en 2 unidades
1 × NVMe · 1 × HDD
1.8 TB libres
Ocupado 228 GB · Libre 1.8 TB

### Temperaturas

Procesador 49.2 °C
lo más caliente ahora
Gráfica 48.0 °C · Disco 33.9 °C

### Red

enp7s0 · 192.168.1.120
Realtek RTL8111/8168/8211/8411 PCI Express Gigabit Ethernet Controller · 1 Gb/s · dúplex completo
↓ 0 B/s ↑ 0 B/s

### Placa base

AMD A520
BIOS 3405 · 2023-12-13
UEFI (64 bits) · TPM 2.0

> **Faltan 4 datos que este equipo sí tiene**
> Detalle de los módulos de memoria
> Salud de los discos
> Consumo del procesador
> Voltaje del procesador

## CPU

AMD Ryzen 5 5600G
6 núcleos · 12 hilos · 1 socket
Cezanne · AM4 · TSMC 7nm FinFET · x86_64
- Frecuencia: 3.51 GHz (404 MHz – 4.47 GHz)
- Uso: —
- Temperatura: 49 °C
- Consumo: (necesita permisos)

### Núcleos lógicos

- CPU 0: 4.45 GHz
- CPU 1: 3.75 GHz
- CPU 2: 4.14 GHz
- CPU 3: 3.56 GHz
- CPU 4: 3.60 GHz
- CPU 5: 3.57 GHz
- CPU 6: 2.37 GHz
- CPU 7: 2.37 GHz
- CPU 8: 3.61 GHz
- CPU 9: 3.56 GHz
- CPU 10: 3.65 GHz
- CPU 11: 3.56 GHz

★ Núcleo 0 y núcleo 4 (CPU 0, CPU 4, CPU 6 y CPU 10, que son sus hilos): los mejores núcleos de este procesador.

### Procesador

- Fabricante: AMD
- Especificación: AMD Ryzen 5 5600G with Radeon Graphics
- Nombre en clave: Cezanne
- Tecnología: TSMC 7nm FinFET
- Encapsulado: AM4
- Arquitectura: x86_64
- Núcleos: 6
- Hilos: 12 (SMT activo)
- Virtualización: AMD-V (soportada)
- Voltaje: (necesita permisos)

#### Identificación (CPUID)

- Familia: 25 (0x19)
- Modelo: 80 (0x50)
- Stepping: 0
- Firma CPUID: 0x00A50F00
- Microcódigo: 0xa500012

### Relojes

- Frecuencia: 3.51 GHz
- Multiplicador: × 35.1
- Base: 3.90 GHz × 39.0
- Mínima: 404 MHz × 4.0
- Máxima (kernel): 4.47 GHz × 44.6
- Máxima (silicio): 4.47 GHz × 44.6
- Bus (BCLK): 100 MHz
- Turbo: activado
- Driver: amd-pstate-epp
- Gobernador: powersave
- Preferencia de energía: balance_performance

### Jerarquía de caché

- L1 datos: 6 × 32 KiB, 8 vías línea 64 B · 2 hilos
- L1 instr.: 6 × 32 KiB, 8 vías línea 64 B · 2 hilos
- L2: 6 × 512 KiB, 8 vías línea 64 B · 2 hilos
- L3: 16 MiB, 16 vías línea 64 B · 12 hilos

### Juego de instrucciones

SMT · MMX · SSE · SSE2 · SSE3 · SSSE3 · SSE4.1 · SSE4.2 · SSE4A · AVX · AVX2 · FMA3 · AES-NI · SHA · CLMUL · VAES · BMI1 · BMI2 · ADX · RDRAND · RDSEED · AMD-V
61 banderas detectadas por CPUID · 39 no destacadas

> **Hace falta elevar permisos**
> El contador de energía RAPL existe pero no se puede leer.
> Muchas distribuciones lo restringen a root desde CVE-2020-8694.

> **Hace falta elevar permisos**
> El voltaje del núcleo lo tiene el procesador, no un sensor de la placa.
> Se lee de un registro del propio procesador, y eso lo reserva el kernel al administrador.

## Cachés

19.4 MiB de caché en total
4 cachés distintas sobre 6 núcleos y 12 hilos
L1 datos 192 KiB · L1 instr. 192 KiB · L2 3 MiB · L3 16 MiB

### Quién comparte qué

Cada bloque es una instancia física de caché; su anchura son las CPUs lógicas que la comparten.

### Detalle por nivel

| NIVEL | TAMAÑO | Nº | TOTAL | VÍAS | LÍNEA | CONJUNTOS | COMPARTEN |
|---|---|---|---|---|---|---|---|
| L1 datos | 32 KiB | 6 | 192 KiB | 8 | 64 B | 64 | 2 hilos |
| L1 instr. | 32 KiB | 6 | 192 KiB | 8 | 64 B | 64 | 2 hilos |
| L2 | 512 KiB | 6 | 3 MiB | 8 | 64 B | 1024 | 2 hilos |
| L3 | 16 MiB | 1 | 16 MiB | 16 | 64 B | 16384 | 12 hilos |

### Vías y conjuntos

Una caché de N vías guarda cada dirección en uno de N sitios posibles. Más vías reducen los choques entre datos que compiten por el mismo conjunto, a costa de una búsqueda más cara.

### Línea

La unidad mínima que viaja entre memoria y caché. Leer un solo byte trae la línea entera, y por eso recorrer datos contiguos es mucho más rápido que saltar por la memoria.

## Placa base

ASUS PRIME A520M-A II
Sobremesa
AMD A520 · UEFI (64 bits) · TPM 2.0

### Placa base

- Fabricante: ASUS
- Modelo: PRIME A520M-A II
- Chasis: Sobremesa

El firmware de esta placa no dice su revisión ni el fabricante del chasis. Es una placa suelta: el firmware no describe un equipo de marca.

### Firmware

- Tipo: UEFI (64 bits)
- Fabricante: AMI
- Versión: 3405
- Fecha: 2023-12-13
- Revisión de la BIOS: 5.17
- Arranque seguro: desactivado
- TPM: TPM 2.0

### Chipset

- Chipset: AMD A520
- Identificación PCI: FCH LPC Bridge
- Controlador de memoria: Renoir/Cezanne Root Complex

### Plataforma

- IOMMU: activa · 18 grupos
- Virtualización: activa (AMD-V), en uso por KVM
- Chip de sensores: ASUS
- Códec de sonido: Realtek ALC897

### Dispositivos PCIe

| TIPO | DISPOSITIVO | ENLACE | MÁXIMO | DRIVER |
|---|---|---|---|---|
| Gráfica | GeForce RTX 4060 | PCIe 2.0 × 8 | PCIe 3.0 × 8 | nvidia |
| NVMe | KINGSTON SNV2S1000G | PCIe 3.0 × 4 | PCIe 3.0 × 4 | nvme |
| Ethernet | Realtek RTL8111/8168/8211/8411 PCI Express Gigabit Ethernet Controller | PCIe 1.0 × 1 | PCIe 1.0 × 1 | r8169 |
| SATA | 500 Series Chipset SATA Controller | en la placa |  | ahci |
| USB | A520 Series Chipset USB 3.1 XHCI Controller | en la placa |  | xhci_hcd |
| USB | Renoir/Cezanne USB 3.1 | en la placa |  | xhci_hcd |
| USB | Renoir/Cezanne USB 3.1 | en la placa |  | xhci_hcd |
| Sonido | AD107 High Definition Audio Controller | en la gráfica |  | snd_hda_intel |
| Sonido | Renoir/Cezanne HDMI/DP Audio Controller | en la placa |  | snd_hda_intel |
| Sonido | Ryzen HD Audio Controller | en la placa |  | snd_hda_intel |

El nombre de cada ranura («PCIEX16», «M2A_CPU») está en la tabla del firmware y sale al dar permisos.

## Memoria

32 GiB instalados · 31.1 GiB utilizables
4 módulos leídos de su chip SPD, catalogados a 3200 MT/s · el zócalo y a cuánto van, con permisos
DDR4 · 3200 MT/s
Aplicaciones 5.4 GiB · Caché 14.8 GiB · Buffers 57.1 MiB · Libre 10.9 GiB
Disponible 25.8 GiB · intercambio 1.4 MiB de 31.1 GiB

#### Desglose del uso

- Total: 31.1 GiB
- Usada: 5.3 GiB (17 %)
- Disponible: 25.8 GiB
- Aplicaciones: 5.4 GiB
- Caché: 14.8 GiB
- Buffers: 57.1 MiB
- Compartida: 181.5 MiB
- Libre: 10.9 GiB
- Intercambio: 31.1 GiB
- Intercambio usado: 1.4 MiB (0 %)

### Módulo 1

- Zócalo: (necesita permisos)
- Fabricante: Kingston
- Chips: Nanya
- Referencia: KF3200C16D4/8GX
- Tipo: DDR4
- Capacidad: 8 GiB
- Catalogado a: 3200 MT/s
- Funcionando a: (necesita permisos)
- Rangos: 1
- Voltaje: 1.20 V · nominal del SPD
- Formato: UDIMM
- Fabricado: semana 36 de 2024
- Banco: (necesita permisos)

### Módulo 2

- Zócalo: (necesita permisos)
- Fabricante: Kingston
- Chips: Nanya
- Referencia: KF3200C16D4/8GX
- Tipo: DDR4
- Capacidad: 8 GiB
- Catalogado a: 3200 MT/s
- Funcionando a: (necesita permisos)
- Rangos: 1
- Voltaje: 1.20 V · nominal del SPD
- Formato: UDIMM
- Fabricado: semana 36 de 2024
- Banco: (necesita permisos)

### Módulo 3

- Zócalo: (necesita permisos)
- Fabricante: Kingston
- Chips: Nanya
- Referencia: KF3200C16D4/8GX
- Tipo: DDR4
- Capacidad: 8 GiB
- Catalogado a: 3200 MT/s
- Funcionando a: (necesita permisos)
- Rangos: 1
- Voltaje: 1.20 V · nominal del SPD
- Formato: UDIMM
- Fabricado: semana 16 de 2023
- Banco: (necesita permisos)

### Módulo 4

- Zócalo: (necesita permisos)
- Fabricante: Kingston
- Chips: Nanya
- Referencia: KF3200C16D4/8GX
- Tipo: DDR4
- Capacidad: 8 GiB
- Catalogado a: 3200 MT/s
- Funcionando a: (necesita permisos)
- Rangos: 1
- Voltaje: 1.20 V · nominal del SPD
- Formato: UDIMM
- Fabricado: semana 16 de 2023
- Banco: (necesita permisos)

### Perfiles y temporizaciones

| PERFIL | VELOCIDAD | CL | LATENCIA | TRCD | TRP | TRAS | TRC | VOLTAJE |
|---|---|---|---|---|---|---|---|---|
| Módulo 1 · JEDEC | 2400 MT/s | 17 | 13.75 ns | 17 | 17 | 39 | 55 | 1.20 V |
| Módulo 1 · XMP 1 | 3200 MT/s | 16 | 10 ns | 18 | 18 | 36 | 74 | 1.35 V |
| Módulo 2 · JEDEC | 2400 MT/s | 17 | 13.75 ns | 17 | 17 | 39 | 55 | 1.20 V |
| Módulo 2 · XMP 1 | 3200 MT/s | 16 | 10 ns | 18 | 18 | 36 | 74 | 1.35 V |
| Módulo 3 · JEDEC | 2400 MT/s | 17 | 13.75 ns | 17 | 17 | 39 | 55 | 1.20 V |
| Módulo 3 · XMP 1 | 3200 MT/s | 16 | 10 ns | 18 | 18 | 36 | 74 | 1.35 V |
| Módulo 4 · JEDEC | 2400 MT/s | 17 | 13.75 ns | 17 | 17 | 39 | 55 | 1.20 V |
| Módulo 4 · XMP 1 | 3200 MT/s | 16 | 10 ns | 18 | 18 | 36 | 74 | 1.35 V |

Lo que cada módulo declara en su chip SPD; a cuánto va de verdad lo decide la BIOS.

### Ancho de banda y latencia

Mide cuánto se mueve la memoria de verdad, leyendo un bloque más grande que la caché. Tarda una décima de segundo.

### Lo que falta necesita permisos

Los 4 módulos de arriba salen de su propio chip SPD, que se lee sin permisos. En qué zócalo va cada uno, cuántos quedan libres y a qué velocidad los ha puesto la BIOS están en la tabla SMBIOS, que el kernel reserva al administrador.
El ayudante que se lanza solo sabe leer esa tabla y unos registros del procesador: no ejecuta órdenes ni escribe nada.

> **Este equipo no lo expone**
> Este equipo no publica cuánto tráfico mueve el controlador de memoria.
> Solo lo publican los procesadores Intel. En AMD el kernel no le pone nombre a esos contadores, y una cifra deducida a ciegas sería peor que ninguna.

## Gráficos

### GeForce RTX 4060

MSI · AD107 · PCIe 3.0 × 8
nvidia · 620.73.04 · 8.0 GiB · 3072 CUDA · principal
- Uso: 0 %
- Frecuencia: 1980 MHz (memoria 8.50 GHz)
- Temperatura: 48 °C
- Consumo: 53 W (de 115 W)

#### Ahora mismo

- Memoria de video: 866.5 MiB de 8.0 GiB · 11 %
- Consumo: 53 W de 115 W · 46 %
- Bus de memoria: 1 %
- Render / 3D: 0 %
- Decodificar video: 0 %
- Codificar video: 0 %

#### Tarjeta

- Fabricante: NVIDIA
- Ensamblada por: MSI
- Nombre en clave: AD107
- Driver: nvidia
- Versión del driver: 620.73.04
- Unidades de proceso: 3072 núcleos CUDA

NVML no cuenta ROPs ni motores de sombreado: el recuento de NVIDIA son los núcleos CUDA.

##### Identificadores

- Identificador: 10DE:2882
- Subsistema: 1462:5161
- Ranura PCI: 0000:01:00.0
- Nodo DRM: card1
- BIOS de video: 95.07.31.40.F2

#### Memoria de video

- Total: 8.0 GiB
- Bus: 128 bits

El driver de NVIDIA no publica el tipo de memoria, su ancho de banda, cuánta ve el procesador ni de quién son los chips.

#### Relojes y enlace

- Núcleo: 1.98 GHz
- Núcleo (máximo): 3.10 GHz
- Memoria: 8.50 GHz
- Memoria (máximo): 8.50 GHz
- Enlace: PCIe 2.0 × 8
- Enlace (máximo): PCIe 3.0 × 8
- Errores del enlace: ninguno desde el arranque

Una NVIDIA no tiene reloj de SoC ni perfil de rendimiento, y NVML no da la frecuencia efectiva de la memoria.

#### Consumo y temperaturas

- Estado: sin límites
- Límite de potencia: 115 W
- Ventilador: parado

NVML no publica el punto caliente, la temperatura de la memoria, los reguladores ni los voltajes de esta tarjeta; el uso del video está en «Ahora mismo».

#### Bibliotecas gráficas

| API | VERSIÓN | DRIVER | DETALLE |
|---|---|---|---|
| Vulkan | 1.4.357 | 620.73.04 | — |
| OpenGL | 4.6.0 | 620.73.04 | GLSL 4.60 NVIDIA |
| OpenCL | 3.0 | 620.73.04 | 24 unidades de cómputo |

#### Monitores y salidas de video

| SALIDA | MONITOR | RESOLUCIÓN | REFRESCO | TAMAÑO | COLOR Y HDR | FABRICADO |
|---|---|---|---|---|---|---|
| DP-3 | LG LG ULTRAGEAR | 1920 × 1080 | 48–180 Hz | 23.8" | HDR10 (PQ) · BT.2020 RGB | semana 4 de 2024 |

3 salidas libres: DP-1, DP-2, HDMI-A-1

## Almacenamiento

2.0 TB en 2 unidades
228 GB ocupados en 3 particiones montadas
1 × NVMe · 1 × HDD
Ocupado 228 GB · Libre 1.8 TB
- Leyendo: 0 B/s (suma de 2 unidades)
- Escribiendo: 0 B/s (suma de 2 unidades)
- Espacio libre: 1.8 TB (en 3 particiones)
- Más caliente: 34 °C (nvme0n1)

### Estado de los discos

Las horas de encendido, los terabytes escritos y el desgaste los guarda cada disco en sus propios contadores de diagnóstico. El kernel reserva esos comandos al administrador porque son los mismos que sirven para borrar un disco.
El ayudante que se lanza solo sabe pedir diagnóstico y leer unas tablas del sistema: no ejecuta órdenes ni escribe nada.

> **Falta un driver del kernel**
> Cargando drivetemp tendrías la temperatura de los discos SATA. «Cargar ahora» lo carga hasta que se apague el equipo, con la contraseña de administrador.
> Para que se cargue siempre:
> echo drivetemp | sudo tee /etc/modules-load.d/drivetemp.conf

### Unidades

| UNIDAD | MODELO | TIPO | CAPACIDAD | OCUPADO | TEMPERATURA | LEYENDO | ESCRIBIENDO |
|---|---|---|---|---|---|---|---|
| nvme0n1 | KINGSTON SNV2S1000G | NVMe | 1.0 TB | 214 GB | 33.9 °C | 0 B/s | 0 B/s |
| sda | WDC WD10JPCX-24U | HDD | 1.0 TB | 13.6 GB | — | 0 B/s | 0 B/s |

### Particiones montadas

| PARTICIÓN | SISTEMA | MONTADA EN | TAMAÑO | USADO | LIBRE |
|---|---|---|---|---|---|
| nvme0n1p1 | vfat | /boot | 4.3 GB | 392 MB (9 %) | 3.9 GB |
| nvme0n1p2 | btrfs | / | 996 GB | 214 GB (22 %) | 780 GB |
| sda2 | ntfs3 | /media/unidad1 | 1.0 TB | 13.6 GB (1 %) | 987 GB |

### nvme0n1

Ocupado 214 GB · Libre 784 GB
- Modelo: KINGSTON SNV2S1000G
- Fabricante: Kingston
- Tipo: NVMe
- Conexión: NVMe
- Enlace: PCIe 3.0 × 4
- Capacidad: 1.0 TB
- Temperatura: 33.9 °C
- Límites: aviso 83 °C · crítica 90 °C
- Horas encendido: (necesita permisos)
- Escrito en total: (necesita permisos)
- Vida restante: (necesita permisos)

#### Firmware y sectores

- Firmware: SBM02103
- Sector lógico: 512 B
- Sector físico: 512 B
- Planificador: kyber
- TRIM: lo admite · montado con discard · fstrim.timer activado

### sda

Ocupado 13.6 GB · Libre 987 GB
- Modelo: WDC WD10JPCX-24U
- Fabricante: Western Digital
- Tipo: HDD
- Conexión: SATA
- Capacidad: 1.0 TB
- Temperatura: (necesita permisos)
- Horas encendido: (necesita permisos)
- Escrito en total: (necesita permisos)

Un disco de platos no tiene «vida restante»: es el desgaste de las celdas de un SSD.

#### Firmware y sectores

- Firmware: 1A01
- Sector lógico: 512 B
- Sector físico: 4096 B
- Planificador: bfq

## Red

enp7s0 · 192.168.1.120
Realtek RTL8111/8168/8211/8411 PCI Express Gigabit Ethernet Controller · 1 Gb/s · dúplex completo
puerta 192.168.1.1 · 1 de 1 activa
- Bajando: 0 B/s (ninguno descartado)
- Subiendo: 0 B/s
- Recibido: 850 MB (608 640 paquetes)
- Enviado: 22.4 MB (168 359 paquetes)

### Tráfico por interfaz

1 MB/s son 8 Mb/s: los tests de velocidad usan bits.

| INTERFAZ | BAJANDO | SUBIENDO | RECIBIDO | ENVIADO | PAQUETES | DESCARTADOS |
|---|---|---|---|---|---|---|
| enp7s0 | 0 B/s | 0 B/s | 850 MB | 22.4 MB | 776 999 | 0 |

### enp7s0

- Estado: activa
- Tipo: Ethernet
- Dirección IPv4: 192.168.1.120
- Máscara: 255.255.255.0
- Puerta de enlace: 192.168.1.1
- Dirección IPv6: 2001:db8::11
- Dirección física: 00:00:5e:00:53:af
- Velocidad del enlace: 1 Gb/s · dúplex completo
- MTU: 1500
- Driver: r8169
- Modelo: Realtek RTL8111/8168/8211/8411 PCI Express Gigabit Ethernet Controller
- Ranura PCI: 0000:07:00.0

### Interfaces virtuales

| INTERFAZ | BAJANDO | SUBIENDO | RECIBIDO | ENVIADO | PAQUETES | DESCARTADOS |
|---|---|---|---|---|---|---|
| lo | 0 B/s | 0 B/s | 6.7 MB | 6.7 MB | 40 624 | 0 |

### lo

- Estado: activa
- Tipo: Bucle local
- Dirección IPv4: 127.0.0.1
- Máscara: 255.0.0.0
- Dirección IPv6: ::1
- Dirección física: 00:00:00:00:00:00
- MTU: 65536

No tiene driver, modelo ni ranura PCI: es una interfaz virtual, sin tarjeta detrás.

## Dispositivos

3 dispositivos USB
3 tarjetas de sonido · 0 cámaras · sin Bluetooth

### USB

*DISPOSITIVO · VELOCIDAD*
- Mando o dispositivo de entrada · Velocidad completa · 12 Mb/s
- Teclado · Velocidad completa · 12 Mb/s
- Ratón · Velocidad completa · 12 Mb/s

Cada cosa cuelga del concentrador al que está enchufada. El número de serie no se lee.

### Sonido

| TARJETA | DÓNDE |
|---|---|
| HDMI de la gráfica | en la gráfica |
| HDMI de la gráfica | en la gráfica |
| Placa base · Realtek ALC897 | en la placa |

### Cámaras

Este equipo no tiene ninguna cámara.

### Bluetooth

Este equipo no tiene adaptador Bluetooth.

## Sistema

CachyOS
silux-pc · encendido 29 min
Linux 7.3.5-2-cachyos · KDE · wayland

### Sistema operativo

- Distribución: CachyOS
- Identificador: cachyos
- Nombre del equipo: silux-pc

Esta distribución no declara versión ni variante.

### Kernel y entorno

- Kernel: Linux 7.3.5-2-cachyos
- Arquitectura: x86_64
- Compilación: #1 SMP PREEMPT_DYNAMIC Fri, 20 Nov 2026 19:34:15 +0000 · clang 23.1.5
- Init: systemd
- Escritorio: KDE
- Sesión: wayland
- Shell: fish
- Gráficos: NVIDIA 620.73.04
- Kernel contaminado: un módulo de fuera del kernel (nvidia, nvidia_drm, nvidia_modeset, nvidia_uvm)

### Actividad

- Encendido desde: (hora de arranque)
- Tiempo encendido: 29 min
- Procesos: 337
- Hilos: 1 130
- Archivos abiertos: 12 117

### Vulnerabilidades del procesador

- Conocidas por este kernel: 19
- No afectan a este procesador: 13
- Mitigadas: 6
- Sin mitigar: ninguna

#### Las que afectan a este procesador, como las describe el kernel

- spec_rstack_overflow: Mitigation: Safe RET
- spec_store_bypass: Mitigation: Speculative Store Bypass disabled via prctl
- spectre_v1: Mitigation: usercopy/swapgs barriers and __user pointer sanitization
- spectre_v2: Mitigation: Retpolines; IBPB: conditional; IBRS_FW; STIBP: always-on; RSB filling; PBRSB-eIBRS: Not affected; BHI: Not affected
- tsa: Mitigation: Clear CPU buffers
- vmscape: Mitigation: IBPB before exit to userspace

### Intercambio

- zram0 (en memoria): 1.4 MiB de 31.1 GiB · zstd · comprime 6.6 a 1 · prioridad 100

### Arranque

- Gestor de arranque: Limine 12.11.1
- Entrada elegida: CachyOS.linux-cachyos
- Firmware: 7.7 s
- Cargador: 5.3 s
- Kernel: 2.0 s
- Initrd: 1.9 s
- Espacio de usuario: 6.9 s
- Total: 23.8 s
- Línea de arranque: quiet nowatchdog splash rw rootflags=subvol=/@ root=…

## Rendimiento

Prueba de rendimiento
Mide el procesador con cinco cargas distintas, primero en un solo hilo y después en todos. Lo interesante no es solo la cifra: es que cada carga escala de una forma, y ahí se ve qué aprovecha los hilos y qué se queda esperando a la memoria. Mientras dura, el equipo irá al máximo.
Cada medida: 15 s · sostenida · la medida de referencia · la prueba entera, 2 min

## Sensores

SENSORES · 29 en 5 dispositivos
*Sensor · Actual · Mín · Máx · Media*
- AMD Ryzen 5 5600G with Radeon Graphics
  - Temperaturas
    - Tctl · 49.2 °C · 49.2 · 49.2 · 49.2
  - Relojes
    - CPU 0 · 4449.7 MHz · 4449.7 · 4449.7 · 4449.7
    - CPU 1 · 3746.8 MHz · 3746.8 · 3746.8 · 3746.8
    - CPU 2 · 4138.5 MHz · 4138.5 · 4138.5 · 4138.5
    - CPU 3 · 3555.5 MHz · 3555.5 · 3555.5 · 3555.5
    - CPU 4 · 3595.8 MHz · 3595.8 · 3595.8 · 3595.8
    - CPU 5 · 3567.1 MHz · 3567.1 · 3567.1 · 3567.1
    - CPU 6 · 2367.5 MHz · 2367.5 · 2367.5 · 2367.5
    - CPU 7 · 2367.5 MHz · 2367.5 · 2367.5 · 2367.5
    - CPU 8 · 3611.9 MHz · 3611.9 · 3611.9 · 3611.9
    - CPU 9 · 3556.8 MHz · 3556.8 · 3556.8 · 3556.8
    - CPU 10 · 3652.1 MHz · 3652.1 · 3652.1 · 3652.1
    - CPU 11 · 3559.7 MHz · 3559.7 · 3559.7 · 3559.7
- Memoria
  - Uso
    - RAM usada · 17.0 % · 17.0 · 17.0 · 17.0
    - Intercambio usado · 0.0 % · 0.0 · 0.0 · 0.0
- GeForce RTX 4060
  - Temperaturas
    - Núcleo · 48.0 °C · 48.0 · 48.0 · 48.0
  - Potencias
    - Potencia · 53.4 W · 53.4 · 53.4 · 53.4
  - Uso
    - Uso del núcleo · 0.0 % · 0.0 · 0.0 · 0.0
    - Uso de la memoria · 1.0 % · 1.0 · 1.0 · 1.0
    - Ventilador · 0.0 % · 0.0 · 0.0 · 0.0
    - Memoria de video · 10.6 % · 10.6 · 10.6 · 10.6
  - Relojes
    - Núcleo · 1980.0 MHz · 1980.0 · 1980.0 · 1980.0
    - Memoria · 8501.0 MHz · 8501.0 · 8501.0 · 8501.0
  - Ocupación
    - Memoria de video · 866.0 MiB · 866.0 · 866.0 · 866.0
- KINGSTON SNV2S1000G
  - Temperaturas
    - Del disco · 33.9 °C · 33.9 · 33.9 · 33.9
- Red (enp7s0)
  - Tráfico
    - Bajada · 0.0 kB/s · 0.0 · 0.0 · 0.0
    - Subida · 0.0 kB/s · 0.0 · 0.0 · 0.0
    - Recibido · 850.0 MB · 850.0 · 850.0 · 850.0
    - Enviado · 22.0 MB · 22.0 · 22.0 · 22.0

> **Falta un driver del kernel**
> Con el driver del chip Super I/O de la placa tendrías ventiladores, voltajes de la placa y temperaturas del chipset.
> No conviene adivinar el módulo: cada placa lleva un chip distinto y cargar el que no es puede leer basura. sensors-detect lo identifica y dice cuál cargar.
> sudo sensors-detect

> **Falta un driver del kernel**
> Cargando drivetemp tendrías la temperatura de los discos SATA. «Cargar ahora» lo carga hasta que se apague el equipo, con la contraseña de administrador.
> Para que se cargue siempre:
> echo drivetemp | sudo tee /etc/modules-load.d/drivetemp.conf

## Diagnóstico

**Módulos del kernel que ampliarían lo que se ve:**

- Super I/O: ventiladores, voltajes de la placa y temperaturas del chipset
  `sudo sensors-detect`
- `drivetemp`: la temperatura de los discos SATA
  `sudo modprobe drivetemp`

**Datos que faltan:**

- `modules` (requiere permisos de administrador): Los módulos de memoria están en la tabla SMBIOS, que el kernel reserva al administrador.
- `disks.health` (requiere permisos de administrador): El diagnóstico de los discos lo guarda cada unidad en sus propios contadores.
- `cpu.power` (requiere permisos de administrador): El contador de energía RAPL existe pero no se puede leer.
- `memory.traffic` (este equipo no lo expone): Este equipo no publica cuánto tráfico mueve el controlador de memoria.
- `cpu.voltage_v` (requiere permisos de administrador): El voltaje del núcleo lo tiene el procesador, no un sensor de la placa.

**Consumo de las gráficas: lo que contestó cada vía**

- GeForce RTX 4060 (0000:01:00.0)
  - runtime_status: active
