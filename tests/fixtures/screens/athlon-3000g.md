## Inicio

MSI A320M-A PRO (MS-7C51)
Arch Linux · Linux 7.3.5-arch1-1 · KDE · wayland · encendido 5 min
silux-pc

### Procesador

AMD Athlon 3000G with Radeon Vega Graphics
2 núcleos · 4 hilos · Athlon (Picasso)
5.9 % 2.91 GHz 27.8 °C

### Gráfica

AMD Radeon Vega 3 Graphics
integrada · DDR4 · 3 unidades de cómputo
0.0 % 27.0 °C

### Memoria

1.6 GiB de 3.3 GiB
50 % ocupada
Aplicaciones 1.4 GiB · Caché 1.6 GiB · Buffers 66.2 MiB · Libre 203.6 MiB

### Almacenamiento

624 GB en 2 unidades
1 × HDD · 1 × Memoria flash
518 GB libres
Ocupado 71.9 GB · Libre 518 GB · Reservado 34.0 GB

### Temperaturas

Procesador 27.8 °C
lo más caliente ahora
Gráfica (compartida con la CPU) 27.0 °C

### Red

enp37s0 · 192.168.1.120
Realtek RTL8111/8168/8211/8411 PCI Express Gigabit Ethernet Controller · 1 Gb/s · dúplex completo
↓ 0 B/s ↑ 0 B/s

### Placa base

AMD A320
BIOS 1.30 · 2019-11-08
UEFI (64 bits)

> **Faltan 5 datos que este equipo sí tiene**
> Reloj base del procesador
> Detalle de los módulos de memoria
> Salud de los discos
> Consumo del procesador
> Voltaje del procesador

## CPU

AMD Athlon 3000G with Radeon Vega Graphics
2 núcleos · 4 hilos · 1 socket
Athlon (Picasso) · AM4 · GF 12LP · x86_64
- Frecuencia: 2.91 GHz
- Uso: 6 % (carga 1.39)
- Temperatura: 28 °C
- Consumo: (necesita permisos)

### Núcleos lógicos

- CPU 0: 3.49 GHz · 17.8 %
- CPU 1: 2.33 GHz · 1.0 %
- CPU 2: 3.48 GHz · 1.0 %
- CPU 3: 2.33 GHz · 4.0 %

### Procesador

- Fabricante: AMD
- Especificación: AMD Athlon 3000G with Radeon Vega Graphics
- Nombre en clave: Athlon (Picasso)
- Tecnología: GF 12LP
- Encapsulado: AM4
- Arquitectura: x86_64
- Núcleos: 2
- Hilos: 4 (SMT activo)
- Virtualización: AMD-V (soportada)
- Voltaje: (necesita permisos)

#### Identificación (CPUID)

- Familia: 23 (0x17)
- Modelo: 24 (0x18)
- Stepping: 1
- Firma CPUID: 0x00810F81
- Microcódigo: 0x8108109

### Relojes

- Frecuencia: 2.91 GHz
- Base: (necesita permisos)

Sin driver de frecuencia no hay gobernador, preferencia de energía, ni mínima o máxima del kernel. La de cada hilo es la efectiva que mide el propio procesador (APERF/MPERF) mientras trabaja; un hilo en reposo da la nominal. Este procesador no tiene turbo: su frecuencia más alta es la base.

### Jerarquía de caché

- L1 datos: 2 × 32 KiB, 8 vías línea 64 B · 2 hilos
- L1 instr.: 2 × 64 KiB, 4 vías línea 64 B · 2 hilos
- L2: 2 × 512 KiB, 8 vías línea 64 B · 2 hilos
- L3: 4 MiB, 16 vías línea 64 B · 4 hilos

### Juego de instrucciones

SMT · MMX · SSE · SSE2 · SSE3 · SSSE3 · SSE4.1 · SSE4.2 · SSE4A · AVX · AVX2 · FMA3 · AES-NI · SHA · CLMUL · BMI1 · BMI2 · ADX · RDRAND · RDSEED · AMD-V
52 banderas detectadas por CPUID · 31 no destacadas

> **Hace falta elevar permisos**
> El reloj base lo dice el propio procesador, y leerlo pide permisos.
> Es su P-state 0, en un registro MSR que solo lee el administrador. Ni CPUID ni ACPI CPPC lo publican en este equipo.

> **Este equipo no lo expone**
> Este equipo no publica su reloj de referencia (BCLK).
> Solo lo dan CPUID 0x16 en Intel moderno o los registros MSR del procesador. Deducirlo del reloj base únicamente es fiable en plataformas con ACPI CPPC, donde son 100 MHz.

> **Este equipo no lo expone**
> Este procesador no tiene driver de frecuencia (cpufreq).
> Pasa cuando el firmware no le da al sistema los estados de frecuencia —en algunas placas, con Cool'n'Quiet o SpeedStep desactivados en la BIOS— o cuando su driver no ha cargado; desde aquí no se distingue cuál de las dos. Sin él, el sistema no cambia la frecuencia del procesador.

> **Hace falta elevar permisos**
> El contador de energía RAPL existe pero no se puede leer.
> Muchas distribuciones lo restringen a root desde CVE-2020-8694.

> **Hace falta elevar permisos**
> El voltaje del núcleo lo tiene el procesador, no un sensor de la placa.
> Se lee de un registro del propio procesador, y eso lo reserva el kernel al administrador.

## Cachés

5.2 MiB de caché en total
4 cachés distintas sobre 2 núcleos y 4 hilos
L1 datos 64 KiB · L1 instr. 128 KiB · L2 1 MiB · L3 4 MiB

### Quién comparte qué

Cada bloque es una instancia física de caché; su anchura son las CPUs lógicas que la comparten.

### Detalle por nivel

| NIVEL | TAMAÑO | Nº | TOTAL | VÍAS | LÍNEA | CONJUNTOS | COMPARTEN |
|---|---|---|---|---|---|---|---|
| L1 datos | 32 KiB | 2 | 64 KiB | 8 | 64 B | 64 | 2 hilos |
| L1 instr. | 64 KiB | 2 | 128 KiB | 4 | 64 B | 256 | 2 hilos |
| L2 | 512 KiB | 2 | 1 MiB | 8 | 64 B | 1024 | 2 hilos |
| L3 | 4 MiB | 1 | 4 MiB | 16 | 64 B | 4096 | 4 hilos |

### Vías y conjuntos

Una caché de N vías guarda cada dirección en uno de N sitios posibles. Más vías reducen los choques entre datos que compiten por el mismo conjunto, a costa de una búsqueda más cara.

### Línea

La unidad mínima que viaja entre memoria y caché. Leer un solo byte trae la línea entera, y por eso recorrer datos contiguos es mucho más rápido que saltar por la memoria.

## Placa base

MSI A320M-A PRO (MS-7C51)
Sobremesa
AMD A320 · UEFI (64 bits)

### Placa base

- Fabricante: MSI
- Modelo: A320M-A PRO (MS-7C51)
- Revisión: 1.0
- Chasis: Sobremesa
- Fabricante del chasis: MSI

Es una placa suelta: el firmware no describe un equipo de marca.

### Firmware

- Tipo: UEFI (64 bits)
- Fabricante: AMI
- Versión: 1.30
- Fecha: 2019-11-08
- Revisión de la BIOS: 5.14
- Arranque seguro: desactivado
- TPM: no detectado

### Chipset

- Chipset: AMD A320
- Identificación PCI: FCH LPC Bridge
- Controlador de memoria: Raven/Raven2 Root Complex

### Plataforma

- IOMMU: activa · 11 grupos
- Códec de sonido: Realtek ALC892

### Dispositivos PCIe

| TIPO | DISPOSITIVO | ENLACE | MÁXIMO | DRIVER |
|---|---|---|---|---|
| Gráfica | AMD Radeon Vega 3 Graphics | en el procesador |  | amdgpu |
| Ethernet | Realtek RTL8111/8168/8211/8411 PCI Express Gigabit Ethernet Controller | PCIe 1.0 × 1 | PCIe 1.0 × 1 | r8169 |
| SATA | A320 Chipset SATA Controller [AHCI mode] | en la placa |  | ahci |
| SATA | FCH SATA Controller [AHCI mode] | en la placa |  | ahci |
| USB | A320 USB 3.1 XHCI Host Controller | en la placa |  | xhci_hcd |
| USB | Raven2 USB 3.1 | en el procesador |  | xhci_hcd |
| Sonido | Raven/Raven2/Fenghuang HDMI/DP Audio Controller | en el procesador |  | snd_hda_intel |
| Sonido | Ryzen HD Audio Controller | en el procesador |  | snd_hda_intel |

El nombre de cada ranura («PCIEX16», «M2A_CPU») está en la tabla del firmware y sale al dar permisos.

## Memoria

4 GiB instalados · 3.3 GiB utilizables
1 módulo leído de su chip SPD, catalogado a 2400 MT/s · el zócalo y a cuánto va, con permisos
DDR4 · 2400 MT/s
Aplicaciones 1.4 GiB · Caché 1.6 GiB · Buffers 66.2 MiB · Libre 203.6 MiB
Disponible 1.6 GiB · sin intercambio

#### Desglose del uso

- Total: 3.3 GiB
- Usada: 1.6 GiB (50 %)
- Disponible: 1.6 GiB
- Aplicaciones: 1.4 GiB
- Caché: 1.6 GiB
- Buffers: 66.2 MiB
- Compartida: 53.3 MiB
- Libre: 203.6 MiB
- Intercambio: sin swap

### Módulo 1

- Zócalo: (necesita permisos)
- Fabricante: Ramaxel Technology
- Chips: Micron
- Referencia: RMUA5120MB86H9F2400
- Tipo: DDR4
- Capacidad: 4 GiB
- Catalogado a: 2400 MT/s
- Funcionando a: (necesita permisos)
- Rangos: 1
- Voltaje: 1.20 V · nominal del SPD
- Formato: UDIMM
- Fabricado: semana 38 de 2016
- Banco: (necesita permisos)

### Perfiles y temporizaciones

| PERFIL | VELOCIDAD | CL | LATENCIA | TRCD | TRP | TRAS | TRC | VOLTAJE |
|---|---|---|---|---|---|---|---|---|
| Módulo 1 · JEDEC | 2400 MT/s | 17 | 13.75 ns | 17 | 17 | 39 | 55 | 1.20 V |

Lo que cada módulo declara en su chip SPD; a cuánto va de verdad lo decide la BIOS.

### Última prueba de memoria

Sin medir todavía.

### Lo que falta necesita permisos

El módulo de arriba sale de su propio chip SPD, que se lee sin permisos. En qué zócalo va, cuántos quedan libres y a qué velocidad lo ha puesto la BIOS están en la tabla SMBIOS, que el kernel reserva al administrador.
El ayudante que se lanza solo sabe leer esa tabla y unos registros del procesador: no ejecuta órdenes ni escribe nada.

> **Este equipo no lo expone**
> Este equipo no publica cuánto tráfico mueve el controlador de memoria.
> Solo lo publican los procesadores Intel. En AMD el kernel no le pone nombre a esos contadores, y una cifra deducida a ciegas sería peor que ninguna.

## Gráficos

### AMD Radeon Vega 3 Graphics

MSI · Picasso/Raven 2 · en el procesador
amdgpu · Mesa 26.3.1 · 512 MiB · 3 CU · integrada · principal
- Uso: 0 %
- Frecuencia: 400 MHz (memoria 933 MHz)
- Temperatura: 27 °C (compartida con la CPU)

#### Ahora mismo

- Memoria de video: 372.4 MiB de 512 MiB · 73 %
- Render / 3D: 0 %

Esta gráfica no publica cuánto se usa su motor de video.

#### Tarjeta

- Fabricante: AMD
- Ensamblada por: MSI
- Nombre en clave: Picasso/Raven 2
- Driver: amdgpu
- Versión del driver: Mesa 26.3.1
- Unidades de proceso: 3 unidades de cómputo
- ROPs (unidades de salida de render): 4
- Motores de sombreado: 1

##### Identificadores

- Identificador: 1002:15D8
- Subsistema: 1462:7C51
- Ranura PCI: 0000:29:00.0
- Nodo DRM: card1
- BIOS de video: 113-RAVEN2-115
- Versión de la BIOS de video: 016.002.000.010.000000 · 2019-04-25

#### Memoria de video

- Total: 512 MiB
- Tipo: DDR4
- Bus: 64 bits
- Ancho de banda: 19 GB/s
- Tasa de datos: 2.4 Gbps
- Visible por la CPU: 512 MiB
- Memoria del sistema (GTT): 139.8 MiB de 1.6 GiB

Una integrada no tiene Resizable BAR: el procesador ya ve toda su memoria. amdgpu no publica chips de esta tarjeta.

#### Relojes y enlace

- Núcleo: 400 MHz
- Núcleo (máximo): 1.10 GHz
- Memoria: 933 MHz
- Memoria (máximo): 1.20 GHz
- Perfil de rendimiento: auto

Va dentro del procesador: el enlace PCIe que publica el kernel es interno, no el de una ranura. amdgpu no publica SoC de esta tarjeta.

##### Para expertos

- Escalones del núcleo: 200 · ▸400 · 1100 MHz
- Escalones de la memoria: 400 · ▸933 · 1067 · 1200 MHz
- Perfil de energía: por defecto (BOOTUP_DEFAULT)
- OverDrive: activado: el driver deja cambiar relojes y voltajes

▸ marca el escalón en uso.

#### Consumo y temperaturas

Los reguladores de voltaje y el ventilador son de una tarjeta aparte: esta se alimenta y se refrigera con el resto del equipo. En una APU, el consumo que da el driver es el del procesador entero y su segunda temperatura es la del SoC: ninguna de las dos es de la gráfica. amdgpu no publica estado, chips de memoria, voltaje ni otros 3 datos de esta tarjeta.

#### Códecs de video por hardware

| CÓDEC | DECODIFICA | CODIFICA | PROFUNDIDAD | PERFILES |
|---|---|---|---|---|
| HEVC | ✓ | ✓ | 10 bits | Main, Main 10 |
| H.264 | ✓ | ✓ | 8 bits | Constrained Baseline, Main, High |
| VP9 | ✓ | ✗ | 10 bits | Profile 0, Profile 2 |
| MPEG-2 | ✓ | ✗ | 8 bits | Simple, Main |
| VC-1 | ✓ | ✗ | 8 bits | Simple, Main, Advanced |
| JPEG | ✓ | ✗ | 8 bits | Baseline |

#### Bibliotecas gráficas

| API | VERSIÓN | DRIVER | DETALLE |
|---|---|---|---|
| Vulkan | 1.4.363 | radv (Mesa 26.3.1) | — |
| OpenGL | 4.6 | radeonsi (Mesa 26.3.1) | GLSL 4.60 |

#### Monitores y salidas de video

| SALIDA | MONITOR | RESOLUCIÓN | REFRESCO | TAMAÑO | COLOR Y HDR | FABRICADO |
|---|---|---|---|---|---|---|
| HDMI-A-1 | BLUSENS TV | 1920 × 1080 | 24–85 Hz | ≈ 46" | — | semana 6 de 2012 |

2 salidas libres: DP-1, DVI-D-1

## Almacenamiento

624 GB en 2 unidades
71.9 GB ocupados en 3 particiones montadas
1 × HDD · 1 × Memoria flash
Ocupado 71.9 GB · Libre 518 GB · Reservado 34.0 GB
Unidad Todas las unidades
- Leyendo: 0 B/s (suma de 2 unidades)
- Escribiendo: 8.4 MB/s (suma de 2 unidades)
- Espacio libre: 518 GB (en 3 particiones)
- Más caliente: — (ningún disco publica su temperatura)

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
| sda | WDC WD5000LPVX-0 | HDD | 500 GB | 8.3 GB | — | 0 B/s | 8.4 MB/s |
| sdb | DataTraveler 3.0 | Memoria flash | 124 GB | 63.6 GB | — | 0 B/s | 0 B/s |

### Particiones montadas

| PARTICIÓN | SISTEMA | MONTADA EN | TAMAÑO | USADO | LIBRE |
|---|---|---|---|---|---|
| sda1 | vfat | /boot | 1.1 GB | 84.2 MB (8 %) | 987 MB |
| sda2 | ext4 | / | 499 GB | 8.2 GB (2 %) | 457 GB |
| sdb1 | exfat | /media/unidad1 | 124 GB | 63.6 GB (51 %) | 60.1 GB |

### sda · WDC WD5000LPVX-0

● Con permisos
La salud la guarda cada disco y solo la lee el administrador.
Ocupado 8.3 GB · Libre 458 GB · Reservado 34.0 GB
- Modelo: WDC WD5000LPVX-0
- Fabricante: Western Digital
- Tipo: HDD
- Conexión: SATA
- Capacidad: 500 GB
- Temperatura: (necesita permisos)
- Horas encendido: (necesita permisos)
- Escrito en total: (necesita permisos)

Un disco de platos no tiene «vida restante»: es el desgaste de las celdas de un SSD.

#### Firmware y sectores

- Firmware: 1A01
- Sector lógico: 512 B
- Sector físico: 4096 B
- Planificador: mq-deadline

### sdb · DataTraveler 3.0

● Con permisos
La salud la guarda cada disco y solo la lee el administrador.
Ocupado 63.6 GB · Libre 60.1 GB
- Modelo: DataTraveler 3.0
- Fabricante: Kingston
- Tipo: Memoria flash
- Conexión: USB
- Enlace: USB 480 Mb/s
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

enp37s0 · 192.168.1.120
Realtek RTL8111/8168/8211/8411 PCI Express Gigabit Ethernet Controller · 1 Gb/s · dúplex completo
puerta 192.168.1.1 · 1 de 1 activa
- Bajando: 0 B/s (7 paquetes descartados)
- Subiendo: 0 B/s
- Recibido: 231 kB (621 paquetes)
- Enviado: 74.0 kB (454 paquetes)

### Tráfico por interfaz

1 MB/s son 8 Mb/s: los tests de velocidad usan bits.

| INTERFAZ | BAJANDO | SUBIENDO | RECIBIDO | ENVIADO | PAQUETES | DESCARTADOS |
|---|---|---|---|---|---|---|
| enp37s0 | 0 B/s | 0 B/s | 231 kB | 74.0 kB | 1 075 | 7 |

### enp37s0

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
- Ranura PCI: 0000:25:00.0

### Interfaces virtuales

| INTERFAZ | BAJANDO | SUBIENDO | RECIBIDO | ENVIADO | PAQUETES | DESCARTADOS |
|---|---|---|---|---|---|---|
| lo | 0 B/s | 0 B/s | 3.6 kB | 3.6 kB | 64 | 0 |

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
2 tarjetas de sonido · 0 cámaras · sin Bluetooth

### USB

*DISPOSITIVO · VELOCIDAD*
- Almacenamiento · Alta velocidad · 480 Mb/s
- Teclado y ratón · Velocidad completa · 12 Mb/s
- Teclado · Baja velocidad · 1.5 Mb/s

Cada cosa cuelga del concentrador al que está enchufada. El número de serie no se lee.

### Sonido

| TARJETA | DÓNDE |
|---|---|
| HDMI de la gráfica | en la gráfica |
| Placa base · Realtek ALC892 | en la placa |

### Cámaras

Este equipo no tiene ninguna cámara.

### Bluetooth

Este equipo no tiene adaptador Bluetooth.

## Sistema

Arch Linux
silux-pc · encendido 5 min
Linux 7.3.5-arch1-1 · KDE · wayland

### Sistema operativo

- Distribución: Arch Linux
- Identificador: arch
- Nombre del equipo: silux-pc

Esta distribución no declara versión ni variante.

### Kernel y entorno

- Kernel: Linux 7.3.5-arch1-1
- Arquitectura: x86_64
- Compilación: #1 SMP PREEMPT_DYNAMIC Tue, 17 Nov 2026 22:28:33 +0000 · gcc 16.2.1
- Init: systemd
- Escritorio: KDE
- Sesión: wayland
- Shell: bash
- Gráficos: Mesa 26.3.1
- Kernel contaminado: no

### Actividad

- Encendido desde: (hora de arranque)
- Tiempo encendido: 5 min
- Procesos: 244
- Hilos: 515
- Archivos abiertos: 6 790

### Vulnerabilidades del procesador

- Conocidas por este kernel: 19
- No afectan a este procesador: 13
- Mitigadas: 6
- Sin mitigar: ninguna

#### Las que afectan a este procesador, como las describe el kernel

- retbleed: Mitigation: untrained return thunk; SMT vulnerable
- spec_rstack_overflow: Mitigation: Safe RET
- spec_store_bypass: Mitigation: Speculative Store Bypass disabled via prctl
- spectre_v1: Mitigation: usercopy/swapgs barriers and __user pointer sanitization
- spectre_v2: Mitigation: Retpolines; IBPB: conditional; STIBP: disabled; RSB filling; PBRSB-eIBRS: Not affected; BHI: Not affected
- vmscape: Mitigation: IBPB before exit to userspace

### Intercambio

- Intercambio: no hay

### Arranque

- Gestor de arranque: systemd-boot 262.2-1-arch
- Entrada elegida: arch-linux.efi
- Firmware: 13.2 s
- Cargador: 7.0 s
- Kernel: 8.5 s
- Espacio de usuario: 14.5 s
- Total: 43.2 s
- Línea de arranque: root=… rw rootfstype=ext4

## Rendimiento

Prueba de rendimiento
Mide el procesador con cinco cargas distintas, primero en un solo hilo y después en todos. Lo interesante no es solo la cifra: es que cada carga escala de una forma, y ahí se ve qué aprovecha los hilos y qué se queda esperando a la memoria. Mientras dura, el equipo irá al máximo.
Cada medida: 15 s · sostenida · la medida de referencia · la prueba entera, 2 min

## Sensores

SENSORES · 21 en 4 dispositivos
*Sensor · Actual · Mín · Máx · Media*
- AMD Athlon 3000G with Radeon Vega Graphics
  - Temperaturas
    - Tctl · 27.8 °C · 27.8 · 27.8 · 27.8
  - Uso
    - Total · 5.9 % · 5.9 · 5.9 · 5.9
    - CPU 0 · 17.8 % · 17.8 · 17.8 · 17.8
    - CPU 1 · 1.0 % · 1.0 · 1.0 · 1.0
    - CPU 2 · 1.0 % · 1.0 · 1.0 · 1.0
    - CPU 3 · 4.0 % · 4.0 · 4.0 · 4.0
  - Relojes
    - CPU 0 · 3491.0 MHz · 3491.0 · 3491.0 · 3491.0
    - CPU 1 · 2332.5 MHz · 2332.5 · 2332.5 · 2332.5
    - CPU 2 · 3481.7 MHz · 3481.7 · 3481.7 · 3481.7
    - CPU 3 · 2333.3 MHz · 2333.3 · 2333.3 · 2333.3
- Memoria
  - Uso
    - RAM usada · 49.7 % · 49.7 · 49.7 · 49.7
- AMD Radeon Vega 3 Graphics
  - Temperaturas
    - Borde · 27.0 °C · 27.0 · 27.0 · 27.0
  - Uso
    - Uso del núcleo · 0.0 % · 0.0 · 0.0 · 0.0
    - Memoria de video · 72.7 % · 72.7 · 72.7 · 72.7
  - Relojes
    - Núcleo · 400.0 MHz · 400.0 · 400.0 · 400.0
  - Ocupación
    - Memoria de video · 372.0 MiB · 372.0 · 372.0 · 372.0
    - Memoria prestada al sistema · 140.0 MiB · 140.0 · 140.0 · 140.0
- Red (enp37s0)
  - Tráfico
    - Bajada · 0.0 kB/s · 0.0 · 0.0 · 0.0
    - Subida · 0.0 kB/s · 0.0 · 0.0 · 0.0
    - Recibido · 0.0 MB · 0.0 · 0.0 · 0.0
    - Enviado · 0.0 MB · 0.0 · 0.0 · 0.0

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

- `cpu.clocks.base_hz` (requiere permisos de administrador): El reloj base lo dice el propio procesador, y leerlo pide permisos.
- `cpu.clocks.bus_hz` (este equipo no lo expone): Este equipo no publica su reloj de referencia (BCLK).
- `modules` (requiere permisos de administrador): Los módulos de memoria están en la tabla SMBIOS, que el kernel reserva al administrador.
- `cpu.clocks.driver` (este equipo no lo expone): Este procesador no tiene driver de frecuencia (cpufreq).
- `disks.health` (requiere permisos de administrador): El diagnóstico de los discos lo guarda cada unidad en sus propios contadores.
- `cpu.power` (requiere permisos de administrador): El contador de energía RAPL existe pero no se puede leer.
- `memory.traffic` (este equipo no lo expone): Este equipo no publica cuánto tráfico mueve el controlador de memoria.
- `cpu.voltage_v` (requiere permisos de administrador): El voltaje del núcleo lo tiene el procesador, no un sensor de la placa.
