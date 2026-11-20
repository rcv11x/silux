## Inicio

QEMU Standard PC (i440FX + PIIX, 1996)
Debian GNU/Linux 13 (trixie) · Linux 6.12.117+deb13-amd64 · encendido 11 min
silux-pc · Máquina virtual · KVM

### Procesador

QEMU Virtual version 2.5+
4 núcleos · 4 hilos

### Gráfica

QEMU Standard VGA

### Memoria

427.5 MB de 3.8 GB
11 % ocupada
Aplicaciones 206.2 MB · Caché 773.5 MB · Buffers 34.6 MB · Libre 2.8 GB

### Almacenamiento

32 GB en 1 unidad
1 × Virtual
28.8 GB libres
Ocupado 2.6 GB · Libre 28.8 GB · Reservado 593.6 MB

### Temperaturas

Sin sensores de temperatura

### Red

ens4 · 192.168.1.120
Intel 82540EM Gigabit Ethernet Controller · 1 Gb/s · dúplex completo
↓ 0 B/s ↑ 0 B/s

### Placa base

BIOS Arch Linux 1.17.0-2-2 · 2014-04-01
BIOS heredada

## CPU

QEMU Virtual version 2.5+
4 núcleos · 4 hilos · 1 socket
Máquina virtual · KVM · x86_64
- Frecuencia: —
- Uso: —
- Temperatura: —
- Consumo: —

### Núcleos lógicos

- CPU 0: 
- CPU 1: 
- CPU 2: 
- CPU 3: 

### Procesador

- Fabricante: Intel
- Especificación: QEMU Virtual CPU version 2.5+
- Arquitectura: x86_64
- Núcleos: 4
- Hilos: 4
- Virtualización: dentro de una máquina virtual
Es un procesador virtual: lo que declara lo decide el hipervisor, así que no se busca en la tabla de procesadores, que es de donde salen el nombre en clave, la tecnología y el encapsulado.

#### Identificación (CPUID)

- Familia: 15 (0xF)
- Modelo: 107 (0x6B)
- Stepping: 1
- Firma CPUID: 0x00060FB1

### Jerarquía de caché

- L1 datos: 4 × 32 KB, 8 vías línea 64 B · 1 hilos
- L1 instr.: 4 × 32 KB, 8 vías línea 64 B · 1 hilos
- L2: 4 × 4 MB, 16 vías línea 64 B · 1 hilos
- L3: 16 MB, 16 vías línea 64 B · 4 hilos

### Juego de instrucciones

MMX · SSE · SSE2 · SSE3 · SSSE3 · SSE4.1 · SSE4.2 · AES-NI
27 banderas detectadas por CPUID · 19 no destacadas

> **Este equipo no lo expone**
> El hipervisor no expone la frecuencia del procesador.
> Quien gobierna el reloj es el anfitrión: dentro de una máquina virtual no hay cpufreq que leer.

> **Este equipo no lo expone**
> Esta CPU no expone contadores de energía RAPL.
> Es normal en AMD antiguos, en ARM y en máquinas virtuales.

## Cachés

32.2 MB de caché en total
4 cachés distintas sobre 4 núcleos y 4 hilos
L1 datos 128 KB · L1 instr. 128 KB · L2 16 MB · L3 16 MB
Las declara el hipervisor: no tienen por qué ser las del procesador de verdad.

### Quién comparte qué

Cada bloque es una instancia física de caché; su anchura son las CPUs lógicas que la comparten.

### Detalle por nivel

| NIVEL | TAMAÑO | Nº | TOTAL | VÍAS | LÍNEA | CONJUNTOS | COMPARTEN |
|---|---|---|---|---|---|---|---|
| L1 datos | 32 KB | 4 | 128 KB | 8 | 64 B | 64 | 1 hilo |
| L1 instr. | 32 KB | 4 | 128 KB | 8 | 64 B | 64 | 1 hilo |
| L2 | 4 MB | 4 | 16 MB | 16 | 64 B | 4096 | 1 hilo |
| L3 | 16 MB | 1 | 16 MB | 16 | 64 B | 16384 | 4 hilos |

### Vías y conjuntos

Una caché de N vías guarda cada dirección en uno de N sitios posibles. Más vías reducen los choques entre datos que compiten por el mismo conjunto, a costa de una búsqueda más cara.

### Línea

La unidad mínima que viaja entre memoria y caché. Leer un solo byte trae la línea entera, y por eso recorrer datos contiguos es mucho más rápido que saltar por la memoria.

## Placa base

QEMU Standard PC (i440FX + PIIX, 1996)
BIOS heredada · Otro
BIOS heredada

### Placa base

- Chasis: Otro
- Fabricante del chasis: QEMU
Es una máquina virtual: no tiene placa base, y lo que se ve es lo que declara el hipervisor.

### Firmware

- Tipo: BIOS heredada
- Fabricante: SeaBIOS
- Versión: Arch Linux 1.17.0-2-2
- Fecha: 2014-04-01
- Revisión SMBIOS: 0.0
- TPM: no detectado
Con BIOS heredada no hay arranque seguro: es cosa de UEFI.

### Chipset

- Chipset: —
- Identificación PCI: 82371SB PIIX3 ISA [Natoma/Triton II]
- Controlador de memoria: 440FX - 82441FX PMC [Natoma]

### Equipo

- Fabricante: QEMU
- Modelo: Standard PC (i440FX + PIIX, 1996)
- Versión: pc-i440fx-11.1

### Plataforma

- IOMMU: sin activar

### Dispositivos PCIe

| TIPO | DISPOSITIVO | ENLACE | MÁXIMO | DRIVER |
|---|---|---|---|---|
| Gráfica | QEMU Standard VGA | emulado |  | bochs-drm |
| Ethernet | Intel 82540EM Gigabit Ethernet Controller | emulado |  | e1000 |
| SATA | 82801IR/IO/IH (ICH9R/DO/DH) 6 port SATA Controller [AHCI mode] | emulado |  | ahci |
| USB | 82371SB PIIX3 USB [Natoma/Triton II] | emulado |  | uhci_hcd |

## Memoria

3.8 GB utilizables
Memoria de una máquina virtual: no hay módulos que leer
Aplicaciones 206.2 MB · Caché 773.5 MB · Buffers 34.6 MB · Libre 2.8 GB
Disponible 3.4 GB · sin intercambio

#### Desglose del uso

- Total: 3.8 GB
- Usada: 427.5 MB (11 %)
- Disponible: 3.4 GB
- Aplicaciones: 206.2 MB
- Caché: 773.5 MB
- Buffers: 34.6 MB
- Compartida: 572 KB
- Libre: 2.8 GB
- Intercambio: sin swap

### Ancho de banda y latencia

Mide cuánto se mueve la memoria de verdad, leyendo un bloque más grande que la caché. Tarda una décima de segundo.

### Lo que falta necesita permisos

El detalle de los módulos está en la tabla SMBIOS, que el kernel reserva al administrador porque junto a esos campos van los números de serie del equipo.
El ayudante que se lanza solo sabe leer esa tabla y unos registros del procesador: no ejecuta órdenes ni escribe nada.

## Gráficos

QEMU Standard VGA
Red Hat
bochs-drm · principal

### Ahora mismo

Esta gráfica no publica cuánto se usa su motor gráfico ni su motor de video.

### Tarjeta

- Fabricante: QEMU
- Ensamblada por: Red Hat
- Driver: bochs-drm
Es una gráfica emulada por el hipervisor: no tiene nombre en clave ni unidades de proceso que contar.

#### Identificadores

- Identificador: 1234:1111
- Subsistema: 1AF4:1100
- Ranura PCI: 0000:00:02.0
- Nodo DRM: card0
- BIOS de video: —

### Memoria de video

No tiene memoria de video propia.

### Relojes y enlace

No tiene relojes ni enlace PCIe: no hay silicio debajo.

### Consumo y temperaturas

Tampoco temperaturas, voltajes, ventilador ni consumo.

### Bibliotecas gráficas

| API | VERSIÓN | DRIVER | DETALLE |
|---|---|---|---|
| Sin bibliotecas gráficas | — | — | — |

### Monitores y salidas de video

| SALIDA | MONITOR | RESOLUCIÓN | REFRESCO | TAMAÑO | COLOR Y HDR | FABRICADO |
|---|---|---|---|---|---|---|
| Virtual-1 | Red Hat QEMU Monitor | 1280 × 800 | 50–125 Hz |  | — |  |

## Almacenamiento

32 GB en 1 unidad
2.6 GB ocupados en 2 particiones montadas
1 × Virtual
Ocupado 2.6 GB · Libre 28.8 GB · Reservado 593.6 MB
- Leyendo: 0 B/s (suma de 1 unidad)
- Escribiendo: 0 B/s (suma de 1 unidad)
- Espacio libre: 28.8 GB (en 2 particiones)
- Más caliente: — (ningún disco publica su temperatura)

### Unidades

| UNIDAD | MODELO | TIPO | CAPACIDAD | OCUPADO | TEMPERATURA | LEYENDO | ESCRIBIENDO |
|---|---|---|---|---|---|---|---|
| sda | QEMU HARDDISK | Virtual | 32 GB | 2.6 GB | — | 0 B/s | 0 B/s |

### Particiones montadas

| PARTICIÓN | SISTEMA | MONTADA EN | TAMAÑO | USADO | LIBRE |
|---|---|---|---|---|---|
| sda1 | ext4 | / | 31.9 GB | 2.6 GB (8 %) | 28.7 GB |
| sda15 | vfat | /boot/efi | 124 MB | 8.9 MB (7 %) | 114.8 MB |

### sda

Ocupado 2.6 GB · Libre 28.8 GB · Reservado 593.6 MB
- Modelo: QEMU HARDDISK
- Fabricante: —
- Tipo: Virtual
- Conexión: SATA
- Capacidad: 32 GB
Es un disco virtual: no tiene temperatura, horas, lo escrito ni desgaste propios, y lo que contestaría a un diagnóstico se lo inventa el hipervisor.

#### Firmware y sectores

- Firmware: 2.5+
- Sector lógico: 512 B
- Sector físico: 512 B
- Planificador: mq-deadline
- TRIM: lo admite · montado con discard · fstrim.timer activado

## Red

ens4 · 192.168.1.120
Intel 82540EM Gigabit Ethernet Controller · 1 Gb/s · dúplex completo
puerta 192.168.1.1 · 1 de 1 activas
- Bajando: 0 B/s (sin pérdidas)
- Subiendo: 0 B/s
- Recibido: 109.8 MB (79 087 paquetes)
- Enviado: 881.5 KB (6 177 paquetes)

### Tráfico por interfaz

Los mismos datos son 116 MB/s o 931 Mb/s: los tests de velocidad usan bits.

| INTERFAZ | BAJANDO | SUBIENDO | RECIBIDO | ENVIADO | PAQUETES | PERDIDOS |
|---|---|---|---|---|---|---|
| ens4 | 0 B/s | 0 B/s | 109.8 MB | 881.5 KB | 85 264 | 0 |

### ens4

- Estado: activa
- Tipo: Ethernet
- Dirección IPv4: 192.168.1.120
- Máscara: 255.255.255.0
- Puerta de enlace: 192.168.1.1
- Dirección IPv6: 2001:db8::11
- Dirección física: 00:00:5e:00:53:af
- Velocidad del enlace: 1 Gb/s · dúplex completo
- MTU: 1500
- Driver: e1000
- Modelo: Intel 82540EM Gigabit Ethernet Controller
- Ranura PCI: 0000:00:04.0

## Dispositivos

1 dispositivo USB
0 tarjetas de sonido · 0 cámaras · sin Bluetooth

### USB

*DISPOSITIVO · VELOCIDAD*
- Mando o dispositivo de entrada · Velocidad completa · 12 Mb/s
Cada cosa cuelga del concentrador al que está enchufada. El número de serie no se lee.

### Cámaras

Este equipo no tiene ninguna cámara.

### Bluetooth

Este equipo no tiene adaptador Bluetooth.

## Sistema

Debian GNU/Linux 13 (trixie)
silux-pc · encendido 11 min
Linux 6.12.117+deb13-amd64

### Sistema operativo

- Distribución: Debian GNU/Linux 13 (trixie)
- Versión: 13
- Identificador: debian
- Nombre del equipo: silux-pc
Esta distribución no declara variante.

### Kernel y entorno

- Kernel: Linux 6.12.117+deb13-amd64
- Arquitectura: x86_64
- Compilación: #1 SMP PREEMPT_DYNAMIC Debian 6.12.117-1 (2026-11-12) · gcc 14.2.0
- Init: systemd
- Escritorio: —
- Sesión: tty
- Shell: bash
- Kernel contaminado: no

### Actividad

- Encendido desde: (hora de arranque)
- Tiempo encendido: 11 min
- Procesos: 121
- Hilos: 122
- Archivos abiertos: 736

### Vulnerabilidades del procesador

- Conocidas por este kernel: 17
- No afectan a este procesador: 8
- Mitigadas: 6
- Sin mitigar: 2

#### Las mitigadas, como las describe el kernel

- indirect_target_selection: Mitigation: Aligned branch/return thunks
- itlb_multihit: KVM: Mitigation: VMX unsupported
- l1tf: Mitigation: PTE Inversion
- mds: Vulnerable: Clear CPU buffers attempted, no microcode; SMT Host state unknown
- meltdown: Mitigation: PTI
- mmio_stale_data: Unknown: No mitigations
- spec_store_bypass: Vulnerable
- spectre_v1: Mitigation: usercopy/swapgs barriers and __user pointer sanitization
- spectre_v2: Mitigation: Retpolines; STIBP: disabled; RSB filling; PBRSB-eIBRS: Not affected; BHI: Retpoline

### Intercambio

- Intercambio: no hay

### Arranque

- Kernel: 2.4 s
- Espacio de usuario: 4.4 s
- Línea de arranque: BOOT_IMAGE=/boot/vmlinuz-6.12.117+deb13-amd64 root=… ro console=tty0 console=ttyS0,115200 earlyprintk=ttyS0,115200 consoleblank=0
Falta cuánto tardan el firmware y el cargador: Gestor de arranque no lo publica, y el firmware tampoco.

## Rendimiento

Prueba de rendimiento
Mide el procesador con cinco cargas distintas, primero en un solo hilo y después en todos. Lo interesante no es solo la cifra: es que cada carga escala de una forma, y ahí se ve qué aprovecha los hilos y qué se queda esperando a la memoria. Mientras dura, el equipo irá al máximo.
Cada medida: 15 s · sostenida  · la medida de referencia · la prueba entera, 2 min

## Sensores

SENSORES · 5 en 2 dispositivos
*Sensor · Actual · Mín · Máx · Media*
- Memoria
  - Uso
    - RAM usada · 10.9 % · 10.9 · 10.9 · 10.9
- Red (ens4)
  - Ocupación
    - Recibido · 110.0 MB · 110.0 · 110.0 · 110.0
    - Enviado · 1.0 MB · 1.0 · 1.0 · 1.0
  - Tráfico
    - Bajada · 0.0 KB/s · 0.0 · 0.0 · 0.0
    - Subida · 0.0 KB/s · 0.0 · 0.0 · 0.0

## Diagnóstico

**Datos que faltan:**

- `cpu.clocks.current_hz` (este equipo no lo expone): El hipervisor no expone la frecuencia del procesador.
- `cpu.power` (este equipo no lo expone): Esta CPU no expone contadores de energía RAPL.
