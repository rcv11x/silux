## Inicio

Lenovo V130-15IGM
Debian GNU/Linux 13 (trixie) · Linux 7.1.8+deb13-amd64 · XFCE · x11 · encendido 1 min
silux-pc

### Procesador

Intel Celeron N4000
2 núcleos · 2 hilos · Celeron (Gemini Lake)
2.54 GHz 41.0 °C

### Gráfica

UHD Graphics 600
integrada · 12 unidades de ejecución
100 MHz de 650 MHz
El uso y el consumo, con permisos.

### Memoria

1.2 GiB de 7.6 GiB
16 % ocupada
Aplicaciones 1000.9 MiB · Caché 1.1 GiB · Buffers 72.8 MiB · Libre 5.4 GiB

### Almacenamiento

380 GB en 2 unidades
1 × SSD · 1 × Memoria flash
67.4 GB libres
Ocupado 35.4 GB · Libre 67.4 GB · Reservado 131 GB · Intercambio 4.9 GB · Sin montar 141 GB

### Temperaturas

Procesador 41.0 °C
lo más caliente ahora
Esta gráfica no tiene sensor de temperatura propio.

### Red

wlp2s0 · 192.168.1.120
Intel Dual Band Wireless-AC 3165 Plus Bluetooth
↓ 0 B/s ↑ 0 B/s

### Placa base

BIOS 6VCN43WW · 2021-11-26
UEFI (64 bits) · TPM 2.0 · Arranque seguro

> **Faltan 5 datos que este equipo sí tiene**
> Detalle de los módulos de memoria
> Uso y consumo de la gráfica
> Salud de los discos
> Consumo del procesador
> Voltaje del procesador

## CPU

Intel Celeron N4000
2 núcleos · 2 hilos · 1 socket
Celeron (Gemini Lake) · BGA 1090 · 14 nm · x86_64
- Frecuencia: 2.54 GHz (800 MHz – 2.60 GHz)
- Uso: —
- Temperatura: 41 °C (núcleos 40 °C)
- Consumo: (necesita permisos) (con permisos)

### Núcleos lógicos

- CPU 0: 2.49 GHz  41°
- CPU 1: 2.59 GHz  40°

### Potencia y reposo

- Límite sostenido (PL1): 9.0 W · ventana de 28.0 s
- Límite de pico (PL2): 15 W · ventana de 976 µs

### Procesador

- Fabricante: Intel
- Especificación: Intel(R) Celeron(R) N4000 CPU @ 1.10GHz
- Nombre en clave: Celeron (Gemini Lake)
- Tecnología: 14 nm
- Encapsulado: BGA 1090
- Arquitectura: x86_64
- Núcleos: 2
- Hilos: 2
- Virtualización: VT-x (soportada)
- Voltaje: (necesita permisos)

#### Identificación (CPUID)

- Familia: 6 (0x6)
- Modelo: 122 (0x7A)
- Stepping: 1
- Firma CPUID: 0x000706A1
- Microcódigo: 0x42

### Relojes

- Frecuencia: 2.54 GHz
- Base: 1.10 GHz
- Mínima: 800 MHz
- Máxima (kernel): 2.60 GHz
- Turbo: activado
- Driver: intel_cpufreq
- Gobernador: schedutil

intel_cpufreq no ofrece preferencia de energía: la dan intel_pstate en modo activo con HWP y amd-pstate en modo activo.

### Jerarquía de caché

- L1 datos: 2 × 24 KiB, 6 vías línea 64 B · 1 hilo
- L1 instr.: 2 × 32 KiB, 8 vías línea 64 B · 1 hilo
- L2: 4 MiB, 16 vías línea 64 B · 2 hilos

### Juego de instrucciones

MMX · SSE · SSE2 · SSE3 · SSSE3 · SSE4.1 · SSE4.2 · AES-NI · SHA · CLMUL · RDRAND · RDSEED · VT-x
47 banderas detectadas por CPUID · 34 no destacadas

> **Este equipo no lo expone**
> Este equipo no publica su reloj de referencia (BCLK).
> Solo lo dan CPUID 0x16 en Intel moderno o los registros MSR del procesador. Deducirlo del reloj base únicamente es fiable en plataformas con ACPI CPPC, donde son 100 MHz.

> **Este equipo no lo expone**
> Este procesador no publica su frecuencia máxima de fábrica.
> La dan CPUID 0x16, en los Intel desde la sexta generación, y ACPI CPPC; este no tiene ninguno de los dos. La máxima que aplica el kernel sí está, en su fila.

> **Hace falta elevar permisos**
> El contador de energía RAPL existe pero no se puede leer.
> Muchas distribuciones lo restringen a root desde CVE-2020-8694.

> **Hace falta elevar permisos**
> El voltaje del núcleo lo tiene el procesador, no un sensor de la placa.
> Se lee de un registro del propio procesador, y eso lo reserva el kernel al administrador.

## Cachés

4.1 MiB de caché en total
3 cachés distintas sobre 2 núcleos y 2 hilos
L1 datos 48 KiB · L1 instr. 64 KiB · L2 4 MiB

### Quién comparte qué

Cada bloque es una instancia física de caché; su anchura son las CPUs lógicas que la comparten.

### Detalle por nivel

| NIVEL | TAMAÑO | Nº | TOTAL | VÍAS | LÍNEA | CONJUNTOS | COMPARTEN |
|---|---|---|---|---|---|---|---|
| L1 datos | 24 KiB | 2 | 48 KiB | 6 | 64 B | 64 | 1 hilo |
| L1 instr. | 32 KiB | 2 | 64 KiB | 8 | 64 B | 64 | 1 hilo |
| L2 | 4 MiB | 1 | 4 MiB | 16 | 64 B | 4096 | 2 hilos |

### Vías y conjuntos

Una caché de N vías guarda cada dirección en uno de N sitios posibles. Más vías reducen los choques entre datos que compiten por el mismo conjunto, a costa de una búsqueda más cara.

### Línea

La unidad mínima que viaja entre memoria y caché. Leer un solo byte trae la línea entera, y por eso recorrer datos contiguos es mucho más rápido que saltar por la memoria.

## Placa base

Lenovo V130-15IGM
Portátil
UEFI (64 bits) · TPM 2.0 · Arranque seguro

### Placa base

- Fabricante: Lenovo
- Modelo: LNVNB161216
- Revisión: SDK0J40700 WIN
- Chasis: Portátil
- Fabricante del chasis: Lenovo

### Firmware

- Tipo: UEFI (64 bits)
- Fabricante: Lenovo
- Versión: 6VCN43WW
- Fecha: 2021-11-26
- Revisión de la BIOS: 1.43
- Arranque seguro: activado
- TPM: TPM 2.0

### Chipset

- Identificación PCI: Celeron/Pentium Silver Processor LPC Controller
- Controlador de memoria: Gemini Lake Host Bridge

Su identificación PCI da el nombre en clave del chipset, no un modelo comercial.

### Equipo

- Fabricante: Lenovo
- Modelo: 81HL
- Versión: Lenovo V130-15IGM
- Familia: V130-15IGM
- SKU: LENOVO_MT_81HL_BU_idea_FM_V130-15IGM

### Plataforma

- IOMMU: activa · 16 grupos
- Virtualización: activa (VT-x), en uso por KVM
- Códec de sonido: Conexant CX20751/2

### Dispositivos PCIe

| TIPO | DISPOSITIVO | ENLACE | MÁXIMO | DRIVER |
|---|---|---|---|---|
| Gráfica | UHD Graphics 600 | en el procesador |  | i915 |
| Ethernet | Realtek RTL8111/8168/8211/8411 PCI Express Gigabit Ethernet Controller | en la placa |  | r8169 |
| Wifi | Intel Dual Band Wireless-AC 3165 Plus Bluetooth | PCIe 1.0 × 1 | PCIe 1.0 × 1 | iwlwifi |
| SATA | Celeron/Pentium Silver Processor SATA Controller | en la placa |  | ahci |
| USB | Celeron/Pentium Silver Processor USB 3.0 xHCI Controller | en la placa |  | xhci_hcd |
| Sonido | Celeron/Pentium Silver Processor High Definition Audio | en la placa |  | snd_hda_intel |

El nombre de cada ranura («PCIEX16», «M2A_CPU») está en la tabla del firmware y sale al dar permisos.

## Memoria

7.6 GiB utilizables
El detalle por módulo necesita permisos de administrador
Aplicaciones 1000.9 MiB · Caché 1.1 GiB · Buffers 72.8 MiB · Libre 5.4 GiB
Disponible 6.4 GiB · intercambio 0 B de 8.3 GiB

#### Desglose del uso

- Total: 7.6 GiB
- Usada: 1.2 GiB (16 %)
- Disponible: 6.4 GiB
- Aplicaciones: 1000.9 MiB
- Caché: 1.1 GiB
- Buffers: 72.8 MiB
- Compartida: 103.5 MiB
- Libre: 5.4 GiB
- Intercambio: 8.3 GiB
- Intercambio usado: 0 B (0 %)

### Ancho de banda y latencia

Mide cuánto se mueve la memoria de verdad, leyendo un bloque más grande que la caché. Tarda una décima de segundo.

### Lo que falta necesita permisos

El detalle de los módulos está en la tabla SMBIOS, que el kernel reserva al administrador porque junto a esos campos van los números de serie del equipo.
El ayudante que se lanza solo sabe leer esa tabla y unos registros del procesador: no ejecuta órdenes ni escribe nada.

> **Este equipo no lo expone**
> El bus de la memoria está, pero el kernel no ha registrado ningún chip SPD en él.
> Sin un chip registrado no hay driver que cargar: cargar ee1004 o spd5118 no cambiaría nada.

> **Este equipo no lo expone**
> Este equipo no publica cuánto tráfico mueve el controlador de memoria.
> Solo lo publican los procesadores Intel. En AMD el kernel no le pone nombre a esos contadores, y una cifra deducida a ciegas sería peor que ninguna.

## Gráficos

UHD Graphics 600
Lenovo · GeminiLake
i915 · Mesa 25.2.6 · 12 EU · integrada · principal
- Uso: (necesita permisos) (con permisos)
- Frecuencia: 100 MHz
- Temperatura del paquete: 41 °C (compartida con la CPU)
- Consumo: (necesita permisos) (con permisos)

> **Requiere permisos**
> El uso y el consumo de la gráfica solo se leen con permisos de administrador.
> Con permisos aparecen el uso de cada motor y, en las integradas, el consumo. Las frecuencias, los monitores y lo que declaran Vulkan y OpenGL salen sin pedir nada.

> **Este equipo no lo expone**
> Esta gráfica va dentro del procesador y no tiene sensor de temperatura propio: se muestra la del paquete, que comparte con la CPU.

### Ahora mismo

- Render / 3D: (necesita permisos)
- Video (codificar y decodificar): (necesita permisos)
- Mejora de video: (necesita permisos)
- Copia: (necesita permisos)

### Tarjeta

- Fabricante: Intel
- Ensamblada por: Lenovo
- Nombre en clave: GeminiLake
- Driver: i915
- Versión del driver: Mesa 25.2.6
- Unidades de proceso: 12 unidades de ejecución

i915 no cuenta unidades de rasterizado ni motores de sombreado: el recuento de Intel son las unidades de ejecución. Una integrada de Intel no tiene BIOS de video propia: va dentro del firmware del equipo.

#### Identificadores

- Identificador: 8086:3185
- Subsistema: 17AA:3805
- Ranura PCI: 0000:00:02.0
- Nodo DRM: card0

### Memoria de video

- Memoria del sistema (GTT): hasta 5.7 GiB

Una integrada no tiene memoria propia: usa la del sistema, así que no hay tipo, bus, ancho de banda, tasa de datos ni Resizable BAR que contar.

### Relojes y enlace

- Núcleo: 100 MHz
- Máxima (silicio): 650 MHz
- Eficiente: 200 MHz
- Mínima (silicio): 100 MHz

Sin memoria de video propia no hay reloj de memoria que enseñar. No tiene reloj de SoC ni perfil de rendimiento, y va dentro del procesador: no cuelga de un enlace PCIe.
Una integrada no tiene reguladores de voltaje, ventilador, SoC aparte ni memoria propia. Esta no publica su temperatura, su voltaje ni si se está frenando.

### Motores gráficos

- En reposo: 0.0 %

| MOTOR | FUNCIÓN | USO | SABE HACER |
|---|---|---|---|
| bcs0 | copia | (necesita permisos) |  |
| rcs0 | render | (necesita permisos) |  |
| vcs0 | video | (necesita permisos) | hevc, sfc |
| vecs0 | mejora de video | (necesita permisos) |  |

### Códecs de video por hardware

| CÓDEC | DECODIFICA | CODIFICA | PROFUNDIDAD | PERFILES |
|---|---|---|---|---|
| HEVC | ✓ | ✓ | 10 bits | Main, Main 10 |
| H.264 | ✓ | ✓ | 8 bits | Main, High, Constrained Baseline |
| VP9 | ✓ | ✗ | 10 bits | Profile 0, Profile 2 |
| VP8 | ✓ | ✓ | 8 bits | Version 0.3 |
| MPEG-2 | ✓ | ✗ | 8 bits | Simple, Main |
| VC-1 | ✓ | ✗ | 8 bits | Simple, Main, Advanced |
| JPEG | ✓ | ✓ | 8 bits | Baseline |

### Bibliotecas gráficas

| API | VERSIÓN | DRIVER | DETALLE |
|---|---|---|---|
| Vulkan | 1.4.348 | 26.1.2 | — |
| OpenGL | 4.6 | 25.2.6-1 | GLSL 4.60 |

### Monitores y salidas de video

| SALIDA | MONITOR | RESOLUCIÓN | REFRESCO | TAMAÑO | COLOR Y HDR | FABRICADO |
|---|---|---|---|---|---|---|
| eDP-1 | Chimei Innolux | 1366 × 768 | 60 Hz | 15.5" | — | semana 45 de 2015 |

3 salidas libres: DP-1, HDMI-A-1, HDMI-A-2

> **Falta un paquete del sistema**
> Falta pnp.ids: el fabricante de cada monitor sale con su código de tres letras y no con su nombre.
> Viene en el paquete hwdata.

## Almacenamiento

380 GB en 2 unidades
35.4 GB ocupados en 3 particiones montadas
1 × SSD · 1 × Memoria flash
Ocupado 35.4 GB · Libre 67.4 GB · Reservado 131 GB · Intercambio 4.9 GB · Sin montar 141 GB
- Leyendo: 0 B/s (suma de 2 unidades)
- Escribiendo: 0 B/s (suma de 2 unidades)
- Espacio libre: 67.4 GB (en 2 particiones)
- Más caliente: — (ningún disco publica su temperatura)

### Estado de los discos

Las horas de encendido, los terabytes escritos y el desgaste los guarda cada disco en sus propios contadores de diagnóstico. El kernel reserva esos comandos al administrador porque son los mismos que sirven para borrar un disco.
El ayudante que se lanza solo sabe pedir diagnóstico y leer unas tablas del sistema: no ejecuta órdenes ni escribe nada.

### Unidades

| UNIDAD | MODELO | TIPO | CAPACIDAD | OCUPADO | TEMPERATURA | LEYENDO | ESCRIBIENDO |
|---|---|---|---|---|---|---|---|
| sda | SAMSUNG MZ7LN256 | SSD | 256 GB | 35.4 GB | — | 0 B/s | 0 B/s |
| sdb | DataTraveler 3.0 | Memoria flash | 124 GB | — | — | 0 B/s | 0 B/s |

### Particiones montadas

| PARTICIÓN | SISTEMA | MONTADA EN | TAMAÑO | USADO | LIBRE |
|---|---|---|---|---|---|
| sda4 | ext4 | / | 100.0 GB | 35.4 GB (35 %) | 57.4 GB |
| sda6 | vfat | /boot/efi | 10.0 GB | 9.5 MB (0 %) | 10.0 GB |
| sdb1 | exfat | /media/unidad1 | 124 GB | — | — |

### sda

Ocupado 35.4 GB · Libre 67.4 GB · Reservado 7.2 GB · Intercambio 4.9 GB · Sin montar 141 GB
- Modelo: SAMSUNG MZ7LN256
- Fabricante: Samsung
- Tipo: SSD
- Conexión: SATA
- Capacidad: 256 GB
- Temperatura: (necesita permisos)
- Horas encendido: (necesita permisos)
- Escrito en total: (necesita permisos)
- Vida restante: (necesita permisos)

#### Firmware y sectores

- Firmware: 4L0Q
- Sector lógico: 512 B
- Sector físico: 4096 B
- Planificador: mq-deadline
- TRIM: lo admite · fstrim.timer activado

### sdb

- Modelo: DataTraveler 3.0
- Fabricante: Kingston
- Tipo: Memoria flash
- Conexión: USB
- Capacidad: 124 GB
- Temperatura: (necesita permisos)
- Horas encendido: (necesita permisos)
- Escrito en total: (necesita permisos)
- Vida restante: (necesita permisos)

#### Firmware y sectores

- Firmware: —
- Sector lógico: 512 B
- Sector físico: 512 B
- Planificador: mq-deadline

## Red

wlp2s0 · 192.168.1.120
Intel Dual Band Wireless-AC 3165 Plus Bluetooth
puerta 192.168.1.1 · 1 de 2 activas
- Bajando: 0 B/s (3 paquetes descartados)
- Subiendo: 0 B/s
- Recibido: 8.5 kB (105 paquetes)
- Enviado: 8.5 kB (66 paquetes)

### Tráfico por interfaz

1 MB/s son 8 Mb/s: los tests de velocidad usan bits.

| INTERFAZ | BAJANDO | SUBIENDO | RECIBIDO | ENVIADO | PAQUETES | DESCARTADOS |
|---|---|---|---|---|---|---|
| wlp2s0 | 0 B/s | 0 B/s | 8.5 kB | 8.5 kB | 171 | 3 |
| enp3s0 | 0 B/s | 0 B/s | 0 B | 0 B | 0 | 0 |

### wlp2s0

- Estado: activa
- Tipo: Wi-Fi
- Dirección IPv4: 192.168.1.120
- Máscara: 255.255.255.0
- Puerta de enlace: 192.168.1.1
- Dirección IPv6: 2001:db8::11
- Dirección física: 00:00:5e:00:53:af
- MTU: 1500
- Driver: iwlwifi
- Modelo: Intel Dual Band Wireless-AC 3165 Plus Bluetooth
- Ranura PCI: 0000:02:00.0

### enp3s0

- Estado: sin cable
- Tipo: Ethernet
- Dirección física: 00:00:5e:00:53:af
- MTU: 1500
- Driver: r8169
- Modelo: Realtek RTL8111/8168/8211/8411 PCI Express Gigabit Ethernet Controller
- Ranura PCI: 0000:03:00.0

### Interfaces virtuales

| INTERFAZ | BAJANDO | SUBIENDO | RECIBIDO | ENVIADO | PAQUETES | DESCARTADOS |
|---|---|---|---|---|---|---|
| lo | 0 B/s | 0 B/s | 8.7 kB | 8.7 kB | 198 | 0 |

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
1 tarjeta de sonido · 1 cámara · 1 adaptador Bluetooth

### USB

*DISPOSITIVO · VELOCIDAD*
- Video · Alta velocidad · 480 Mb/s
- Inalámbrico · Velocidad completa · 12 Mb/s
- Almacenamiento · SuperSpeed · 5 Gb/s

Cada cosa cuelga del concentrador al que está enchufada. El número de serie no se lee.

### Sonido

| TARJETA | DÓNDE |
|---|---|
| Placa base · Conexant CX20751/2 | en la placa |

### Cámaras

| CÁMARA | TIPO |
|---|---|
| Cámara | conectada |

### Bluetooth

- hci0: Adaptador · por USB · encendido

Solo el adaptador. Lo emparejado no se enseña: es de otros.

## Batería

L17M2PB3
SMP · Descargando
Li-poly · 30.0 Wh
- Salud: 82 % (24.6 Wh de 30.0 Wh originales)
- Carga: 76 % (18.8 Wh)
- Potencia: 6.6 W (Descargando)
- Autonomía: 2 h 51 min (a 6.6 W de ahora)

### La celda

- Fabricante: SMP
- Modelo: L17M2PB3
- Tecnología: Li-poly
- Tensión: 7.48 V
- Tensión nominal: 7.50 V
- Capacidad: 24.6 Wh
- Capacidad de diseño: 30.0 Wh

## Sistema

Debian GNU/Linux 13 (trixie)
silux-pc · encendido 1 min
Linux 7.1.8+deb13-amd64 · XFCE · x11

### Sistema operativo

- Distribución: Debian GNU/Linux 13 (trixie)
- Versión: 13
- Identificador: debian
- Nombre del equipo: silux-pc

Esta distribución no declara variante.

### Kernel y entorno

- Kernel: Linux 7.1.8+deb13-amd64
- Arquitectura: x86_64
- Compilación: #1 SMP PREEMPT_DYNAMIC Debian 7.1.8-1~bpo13+1 (2026-08-16) · gcc 14.2.0
- Init: systemd
- Escritorio: XFCE
- Sesión: x11
- Shell: bash
- Gráficos: Mesa 25.2.6
- Kernel contaminado: no

### Actividad

- Encendido desde: (hora de arranque)
- Tiempo encendido: 1 min
- Procesos: 195
- Hilos: 455
- Archivos abiertos: 7 635

### Vulnerabilidades del procesador

- Conocidas por este kernel: 19
- No afectan a este procesador: 14
- Mitigadas: 5
- Sin mitigar: ninguna

#### Las que afectan a este procesador, como las describe el kernel

- meltdown: Mitigation: PTI
- reg_file_data_sampling: Mitigation: Clear Register File
- spec_store_bypass: Mitigation: Speculative Store Bypass disabled via prctl
- spectre_v1: Mitigation: usercopy/swapgs barriers and __user pointer sanitization
- spectre_v2: Mitigation: Enhanced / Automatic IBRS; IBPB: conditional; PBRSB-eIBRS: Not affected; BHI: SW loop, KVM: SW loop

### Intercambio

- /dev/sda7 (partición): 0 B de 4.5 GiB · prioridad -1
- zram0 (en memoria): 0 B de 3.8 GiB · lz4 · comprime 64.0 a 1 · prioridad 100

### Arranque

- Kernel: 6.5 s
- Espacio de usuario: 12.5 s
- Línea de arranque: BOOT_IMAGE=/boot/vmlinuz-7.1.8+deb13-amd64 root=… ro quiet

Falta cuánto tardan el firmware y el cargador: ni el gestor de arranque ni el firmware lo publican.

## Rendimiento

Prueba de rendimiento
Mide el procesador con cinco cargas distintas, primero en un solo hilo y después en todos. Lo interesante no es solo la cifra: es que cada carga escala de una forma, y ahí se ve qué aprovecha los hilos y qué se queda esperando a la memoria. Mientras dura, el equipo irá al máximo.
Cada medida: 15 s · sostenida · la medida de referencia · la prueba entera, 2 min

## Sensores

SENSORES · 16 en 6 dispositivos
*Sensor · Actual · Mín · Máx · Media*
- Intel Celeron N4000
  - Temperaturas
    - Paquete · 41.0 °C · 41.0 · 41.0 · 41.0
    - Núcleo 0 · 41.0 °C · 41.0 · 41.0 · 41.0
    - Núcleo 1 · 40.0 °C · 40.0 · 40.0 · 40.0
  - Relojes
    - CPU 0 · 2487.3 MHz · 2487.3 · 2487.3 · 2487.3
    - CPU 1 · 2585.5 MHz · 2585.5 · 2585.5 · 2585.5
- Lenovo V130-15IGM
  - Temperaturas
    - Temperatura 1 (acpitz_0) · 42.0 °C · 42.0 · 42.0 · 42.0
    - Temperatura 1 (acpitz_1) · 25.0 °C · 25.0 · 25.0 · 25.0
- Memoria
  - Uso
    - RAM usada · 16.0 % · 16.0 · 16.0 · 16.0
    - Intercambio usado · 0.0 % · 0.0 · 0.0 · 0.0
- Red (Wi-Fi)
  - Temperaturas
    - Temperatura 1 · 24.0 °C · 24.0 · 24.0 · 24.0
- Red (wlp2s0)
  - Tráfico
    - Bajada · 0.0 kB/s · 0.0 · 0.0 · 0.0
    - Subida · 0.0 kB/s · 0.0 · 0.0 · 0.0
    - Recibido · 0.0 MB · 0.0 · 0.0 · 0.0
    - Enviado · 0.0 MB · 0.0 · 0.0 · 0.0
- Batería
  - Potencias
    - Potencia · 6.6 W · 6.6 · 6.6 · 6.6
  - Voltajes
    - Tensión · 7.477 V · 7.477 · 7.477 · 7.477

UHD Graphics 600: no tiene sensor de temperatura propio.

> **Falta un driver de sensores**
> Cargando drivetemp tendrías la temperatura de los discos SATA.
> sudo modprobe drivetemp

## Diagnóstico

**Módulos del kernel que ampliarían lo que se ve:**

- `drivetemp`: la temperatura de los discos SATA
  `sudo modprobe drivetemp`

**Datos que faltan:**

- `cpu.clocks.bus_hz` (este equipo no lo expone): Este equipo no publica su reloj de referencia (BCLK).
- `cpu.clocks.max_turbo_hz` (este equipo no lo expone): Este procesador no publica su frecuencia máxima de fábrica.
- `gpus.packages.pnpids` (falta un paquete del sistema): Falta pnp.ids: el fabricante de cada monitor sale con su código de tres letras y no con su nombre. Viene en el paquete hwdata.
- `modules` (requiere permisos de administrador): Los módulos de memoria están en la tabla SMBIOS, que el kernel reserva al administrador.
- `spd` (este equipo no lo expone): El bus de la memoria está, pero el kernel no ha registrado ningún chip SPD en él.
- `gpus.0` (requiere permisos de administrador): El uso y el consumo de la gráfica solo se leen con permisos de administrador.
- `disks.health` (requiere permisos de administrador): El diagnóstico de los discos lo guarda cada unidad en sus propios contadores.
- `cpu.power` (requiere permisos de administrador): El contador de energía RAPL existe pero no se puede leer.
- `memory.traffic` (este equipo no lo expone): Este equipo no publica cuánto tráfico mueve el controlador de memoria.
- `cpu.voltage_v` (requiere permisos de administrador): El voltaje del núcleo lo tiene el procesador, no un sensor de la placa.
- `gpus.0.temp_c` (este equipo no lo expone): Esta gráfica va dentro del procesador y no tiene sensor de temperatura propio: se muestra la del paquete, que comparte con la CPU. (i915 y xe solo registran hwmon en las gráficas dedicadas; la temperatura es la del sensor del paquete (coretemp).)
