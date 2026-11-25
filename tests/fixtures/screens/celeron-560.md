## Inicio

Dell Vostro A840
Linux Mint 22.3 · Linux 6.14.0-37-generic · XFCE · x11 · encendido 5 min
silux-pc

### Procesador

Intel Celeron 560
1 núcleo · 1 hilo
1.63 GHz 70.0 °C

### Gráfica

Mobile GM965/GL960 Integrated Graphics
integrada
El uso, con permisos.

### Memoria

1.0 GiB de 1.9 GiB
55 % ocupada
Aplicaciones 918.1 MiB · Caché 936.6 MiB · Buffers 2.7 MiB · Libre 98.2 MiB

### Almacenamiento

408 GB en 3 unidades
1 × SSD · 1 × HDD · 1 × Memoria flash
109 GB libres
Ocupado 92.0 GB · Libre 109 GB · Reservado 15.3 GB · Sin montar 192 GB

### Temperaturas

Procesador 70.0 °C
lo más caliente ahora
Esta gráfica no tiene sensor de temperatura propio.

### Red

Sin conexión
Ninguna interfaz tiene salida a la red.

### Placa base

BIOS heredada
BIOS A03 · 2008-09-18

> **Faltan 3 datos que este equipo sí tiene**
> Detalle de los módulos de memoria
> Uso de la gráfica
> Salud de los discos

## CPU

Intel Celeron 560
1 núcleo · 1 hilo · 1 socket
x86_64
- Frecuencia: 1.63 GHz
- Uso: —
- Temperatura: 70 °C

### Núcleos lógicos

- CPU 0: 1.63 GHz  70°

### Potencia y reposo

- Frenos por temperatura: ninguno desde el arranque

### Procesador

- Fabricante: Intel
- Especificación: Intel(R) Celeron(R) CPU 560 @ 2.13GHz
- Arquitectura: x86_64
- Núcleos: 1
- Hilos: 1
- Virtualización: no soportada

#### Identificación (CPUID)

- Familia: 6 (0x6)
- Modelo: 22 (0x16)
- Stepping: 1
- Firma CPUID: 0x00010661
- Microcódigo: 0x33

### Relojes

- Frecuencia: 1.63 GHz
- Base: 2.13 GHz

Sin driver de frecuencia no hay gobernador, preferencia de energía, ni mínima o máxima del kernel. La de cada hilo es la efectiva que mide el propio procesador (APERF/MPERF) mientras trabaja; un hilo en reposo da la nominal. Este procesador no tiene turbo: su frecuencia más alta es la base.

### Jerarquía de caché

- L1 datos: 32 KiB, 8 vías línea 64 B · 1 hilo
- L1 instr.: 32 KiB, 8 vías línea 64 B · 1 hilo
- L2: 1 MiB, 4 vías línea 64 B · 1 hilo

### Juego de instrucciones

MMX · SSE · SSE2 · SSE3 · SSSE3
22 banderas detectadas por CPUID · 17 no destacadas

> **Esta versión no lo conoce todavía**
> Este procesador (Intel(R) Celeron(R) CPU 560 @ 2.13GHz) no está en la tabla de esta versión de Silux, que es de donde salen su nombre en clave, su nodo y su encapsulado.
> Todo lo demás lo da el propio procesador y sale entero. Si mandas el informe (en Ajustes, o con --report), entra en la próxima versión.

> **Este equipo no lo expone**
> Este equipo no publica su reloj de referencia (BCLK).
> Solo lo dan CPUID 0x16 en Intel moderno o los registros MSR del procesador. Deducirlo del reloj base únicamente es fiable en plataformas con ACPI CPPC, donde son 100 MHz.

> **Este equipo no lo expone**
> Este procesador no tiene driver de frecuencia (cpufreq).
> Pasa cuando el firmware no le da al sistema los estados de frecuencia —en algunas placas, con Cool'n'Quiet o SpeedStep desactivados en la BIOS— o cuando su driver no ha cargado; desde aquí no se distingue cuál de las dos. Sin él, el sistema no cambia la frecuencia del procesador.

> **Este equipo no lo expone**
> Esta CPU no expone contadores de energía RAPL.
> Llegó con los Intel de 2011 (Sandy Bridge) y con los AMD Zen: los anteriores, los ARM y las máquinas virtuales no lo tienen.

> **Este equipo no lo expone**
> Este procesador no publica el voltaje del núcleo.
> Intel lo pone en el registro que se lee a partir de los Core de segunda generación (Sandy Bridge); en uno anterior no está, con permisos o sin ellos.

## Cachés

1.1 MiB de caché en total
3 cachés distintas sobre 1 núcleo y 1 hilo
L1 datos 32 KiB · L1 instr. 32 KiB · L2 1 MiB

### Quién comparte qué

Cada bloque es una instancia física de caché; su anchura son las CPUs lógicas que la comparten.

### Detalle por nivel

| NIVEL | TAMAÑO | Nº | TOTAL | VÍAS | LÍNEA | CONJUNTOS | COMPARTEN |
|---|---|---|---|---|---|---|---|
| L1 datos | 32 KiB | 1 | 32 KiB | 8 | 64 B | 64 | 1 hilo |
| L1 instr. | 32 KiB | 1 | 32 KiB | 8 | 64 B | 64 | 1 hilo |
| L2 | 1 MiB | 1 | 1 MiB | 4 | 64 B | 4096 | 1 hilo |

### Vías y conjuntos

Una caché de N vías guarda cada dirección en uno de N sitios posibles. Más vías reducen los choques entre datos que compiten por el mismo conjunto, a costa de una búsqueda más cara.

### Línea

La unidad mínima que viaja entre memoria y caché. Leer un solo byte trae la línea entera, y por eso recorrer datos contiguos es mucho más rápido que saltar por la memoria.

## Placa base

Dell Vostro A840
Portátil
BIOS heredada

### Placa base

- Fabricante: Dell
- Modelo: 0G216H
- Chasis: Portátil
- Fabricante del chasis: Dell

El firmware de esta placa no dice su revisión.

### Firmware

- Tipo: BIOS heredada
- Fabricante: Dell
- Versión: A03
- Fecha: 2008-09-18
- Revisión de la BIOS: 0.3
- TPM: no detectado

Con BIOS heredada no hay arranque seguro: es cosa de UEFI.

### Chipset

- Identificación PCI: 82801HM (ICH8M) LPC Interface Controller
- Controlador de memoria: Mobile PM965/GM965/GL960 Memory Controller Hub

Su identificación PCI da el nombre en clave del chipset, no un modelo comercial.

### Equipo

- Fabricante: Dell
- Modelo: Vostro A840

### Plataforma

- IOMMU: sin activar
- Códec de sonido: Conexant CX20561 (Hermosa)

### Dispositivos PCIe

| TIPO | DISPOSITIVO | ENLACE | MÁXIMO | DRIVER |
|---|---|---|---|---|
| Gráfica | Mobile GM965/GL960 Integrated Graphics | en el chipset |  | i915 |
| Gráfica | Mobile GM965/GL960 Integrated Graphics Controller (secondary) | en el chipset |  | — |
| Ethernet | Realtek RTL810xE PCI Express Fast Ethernet controller | PCIe 1.0 × 1 | PCIe 1.0 × 1 | r8169 |
| Ethernet | Qualcomm Atheros AR242x / AR542x Wireless Network Adapter (PCI-Express) | PCIe 1.0 × 1 | PCIe 1.0 × 1 | ath5k |
| USB | 82801H (ICH8 Family) USB UHCI Controller #4 | en la placa |  | uhci_hcd |
| USB | 82801H (ICH8 Family) USB UHCI Controller #5 | en la placa |  | uhci_hcd |
| USB | 82801H (ICH8 Family) USB2 EHCI Controller #2 | en la placa |  | ehci-pci |
| USB | 82801H (ICH8 Family) USB UHCI Controller #1 | en la placa |  | uhci_hcd |
| USB | 82801H (ICH8 Family) USB UHCI Controller #2 | en la placa |  | uhci_hcd |
| USB | 82801H (ICH8 Family) USB UHCI Controller #3 | en la placa |  | uhci_hcd |
| USB | 82801H (ICH8 Family) USB2 EHCI Controller #1 | en la placa |  | ehci-pci |
| Sonido | 82801H (ICH8 Family) HD Audio Controller | en la placa |  | snd_hda_intel |

El nombre de cada ranura («PCIEX16», «M2A_CPU») está en la tabla del firmware y sale al dar permisos.

## Memoria

1.9 GiB utilizables
1 módulo leído de su chip SPD, catalogado a 667 MT/s · el resto no se ha podido leer; se sabe con permisos
DDR2 · 667 MT/s
Aplicaciones 918.1 MiB · Caché 936.6 MiB · Buffers 2.7 MiB · Libre 98.2 MiB
Disponible 884.3 MiB · sin intercambio

#### Desglose del uso

- Total: 1.9 GiB
- Usada: 1.0 GiB (55 %)
- Disponible: 884.3 MiB
- Aplicaciones: 918.1 MiB
- Caché: 936.6 MiB
- Buffers: 2.7 MiB
- Compartida: 169.7 MiB
- Libre: 98.2 MiB
- Intercambio: sin swap

En este equipo la memoria la controla el chipset de la placa, no el procesador: hasta qué velocidad llega lo decide la placa.

### Módulo 1

- Zócalo: (necesita permisos)
- Fabricante: Samsung
- Referencia: M4 70T2953EZ3-CE6
- Tipo: DDR2
- Capacidad: 1 GiB
- Catalogado a: 667 MT/s
- Funcionando a: (necesita permisos)
- Rangos: 2
- Voltaje: 1.80 V · nominal del SPD
- Formato: SODIMM
- Fabricado: semana 14 de 2008
- Banco: (necesita permisos)

El SPD de una DDR2 no tiene campo para el fabricante de los chips.

### Perfiles y temporizaciones

| PERFIL | VELOCIDAD | CL | LATENCIA | TRCD | TRP | TRAS | TRC | VOLTAJE |
|---|---|---|---|---|---|---|---|---|
| Módulo 1 · JEDEC | 667 MT/s | 5 | 15 ns | 5 | 5 | 15 | 20 | 1.80 V |

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

### Mobile GM965/GL960 Integrated Graphics

Dell · en el chipset
i915 · Mesa 25.0.7 · integrada · principal
- Uso: (necesita permisos)
- Frecuencia: —
- Consumo: (necesita permisos)

> **Requiere permisos**
> El uso de la gráfica solo se lee con permisos de administrador.
> Con permisos aparece el uso de cada motor. Las frecuencias, los monitores y lo que declaran Vulkan y OpenGL salen sin pedir nada.

> **Este equipo no lo expone**
> Esta gráfica va dentro del procesador y no tiene sensor de temperatura propio.

#### Ahora mismo

- Render / 3D: (necesita permisos)

Esta gráfica no publica cuánto se usa su motor de video.

#### Tarjeta

- Fabricante: Intel
- Ensamblada por: Dell
- Driver: i915
- Versión del driver: Mesa 25.0.7

i915 no cuenta ROPs ni motores de sombreado: el recuento de Intel son las unidades de ejecución. Una integrada de Intel no tiene BIOS de video propia: va dentro del firmware del equipo. Ni su driver (i915) ni la base de datos de dispositivos PCI dan nombre en clave ni unidades de proceso de esta tarjeta.

##### Identificadores

- Identificador: 8086:2A02
- Subsistema: 1028:0298
- Ranura PCI: 0000:00:02.0
- Nodo DRM: card0

#### Memoria de video

Una integrada no tiene memoria propia: usa la del sistema, así que no hay tipo, bus, ancho de banda, tasa de datos ni Resizable BAR que contar. i915 no publica memoria del sistema (GTT) de esta tarjeta.

#### Relojes y enlace

Sin memoria de video propia no hay reloj de memoria que enseñar. No tiene reloj de SoC ni perfil de rendimiento, y va dentro del procesador: no cuelga de un enlace PCIe. i915 no publica núcleo ni núcleo (máximo) de esta tarjeta.
Una integrada no tiene reguladores de voltaje, ventilador, SoC aparte ni memoria propia. Esta no publica su temperatura, su voltaje ni si se está frenando.

#### Motores gráficos

- En reposo: —

| MOTOR | FUNCIÓN | USO | SABE HACER |
|---|---|---|---|
| rcs0 | render | (necesita permisos) |  |

#### Bibliotecas gráficas

| API | VERSIÓN | DRIVER | DETALLE |
|---|---|---|---|
| OpenGL | 2.1 | 25.0.7-0ubuntu0.24.04.2 | GLSL 1.20 |

#### Monitores y salidas de video

| SALIDA | MONITOR | RESOLUCIÓN | REFRESCO | TAMAÑO | COLOR Y HDR | FABRICADO |
|---|---|---|---|---|---|---|
| LVDS-1 | Seiko Epson | 1280 × 800 | 60 Hz | 14.1" | — | 2008 |

1 salida libre: VGA-1

## Almacenamiento

408 GB en 3 unidades
92.0 GB ocupados en 1 partición montada
1 × SSD · 1 × HDD · 1 × Memoria flash
Ocupado 92.0 GB · Libre 109 GB · Reservado 15.3 GB · Sin montar 192 GB
- Leyendo: 0 B/s (suma de 3 unidades)
- Escribiendo: 0 B/s (suma de 3 unidades)
- Espacio libre: 109 GB (en 1 partición)
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
| sdc | SSD PLUS 240 GB | SSD | 240 GB | 92.0 GB | — | 0 B/s | 0 B/s |
| sda | ST9160827AS | HDD | 160 GB | — | — | 0 B/s | 0 B/s |
| sdb | Cruzer U | Memoria flash | 8.0 GB | — | — | 0 B/s | 0 B/s |

### Particiones montadas

| PARTICIÓN | SISTEMA | MONTADA EN | TAMAÑO | USADO | LIBRE |
|---|---|---|---|---|---|
| sdc1 | ext4 | /media/unidad1 | 216 GB | 92.0 GB (43 %) | 109 GB |

### sdc

Ocupado 92.0 GB · Libre 109 GB · Reservado 15.3 GB · Sin montar 24.0 GB
- Modelo: SSD PLUS 240 GB
- Fabricante: SanDisk
- Tipo: SSD
- Conexión: USB
- Enlace: USB 480 Mb/s
- Capacidad: 240 GB
- Temperatura: (necesita permisos)
- Horas encendido: (necesita permisos)
- Escrito en total: (necesita permisos)
- Vida restante: (necesita permisos)

#### Firmware y sectores

- Firmware: 1.02
- Sector lógico: 512 B
- Sector físico: 512 B
- Planificador: mq-deadline

### sda

- Modelo: ST9160827AS
- Tipo: HDD
- Conexión: SATA
- Capacidad: 160 GB
- Temperatura: (necesita permisos)
- Horas encendido: (necesita permisos)
- Escrito en total: (necesita permisos)

El disco no dice su fabricante, ni en su modelo ni en lo que publica el kernel. Un disco de platos no tiene «vida restante»: es el desgaste de las celdas de un SSD.

#### Firmware y sectores

- Firmware: B
- Sector lógico: 512 B
- Sector físico: 512 B
- Planificador: mq-deadline

### sdb

- Modelo: Cruzer U
- Fabricante: SanDisk
- Tipo: Memoria flash
- Conexión: USB
- Enlace: USB 480 Mb/s
- Capacidad: 8.0 GB
- Temperatura: (necesita permisos)
- Horas encendido: (necesita permisos)
- Escrito en total: (necesita permisos)
- Vida restante: (necesita permisos)

#### Firmware y sectores

- Firmware: 1.27
- Sector lógico: 512 B
- Sector físico: 512 B
- Planificador: mq-deadline

## Red

Sin conexión
Ninguna interfaz tiene salida a la red.
0 de 2 activas

### Tráfico por interfaz

1 MB/s son 8 Mb/s: los tests de velocidad usan bits.

| INTERFAZ | BAJANDO | SUBIENDO | RECIBIDO | ENVIADO | PAQUETES | DESCARTADOS |
|---|---|---|---|---|---|---|
| enp9s0 | 0 B/s | 0 B/s | 0 B | 0 B | 0 | 0 |
| wlp12s0 | 0 B/s | 0 B/s | 0 B | 0 B | 0 | 0 |

### enp9s0

- Estado: sin cable
- Tipo: Ethernet
- Dirección física: 00:00:5e:00:53:af
- MTU: 1500
- Driver: r8169
- Modelo: Realtek RTL810xE PCI Express Fast Ethernet controller
- Ranura PCI: 0000:09:00.0

### wlp12s0

- Estado: sin señal
- Tipo: Wi-Fi
- Dirección física: 00:00:5e:00:53:af
- MTU: 1500
- Driver: ath5k
- Modelo: Qualcomm Atheros AR242x / AR542x Wireless Network Adapter (PCI-Express)
- Ranura PCI: 0000:0c:00.0

### Interfaces virtuales

| INTERFAZ | BAJANDO | SUBIENDO | RECIBIDO | ENVIADO | PAQUETES | DESCARTADOS |
|---|---|---|---|---|---|---|
| lo | 0 B/s | 0 B/s | 111 kB | 111 kB | 3 088 | 0 |

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

2 dispositivos USB
1 tarjeta de sonido · 0 cámaras · sin Bluetooth

### USB

*DISPOSITIVO · VELOCIDAD*
- Almacenamiento · Alta velocidad · 480 Mb/s
- Almacenamiento · Alta velocidad · 480 Mb/s

Cada cosa cuelga del concentrador al que está enchufada. El número de serie no se lee.

### Sonido

| TARJETA | DÓNDE |
|---|---|
| Placa base · Conexant CX20561 (Hermosa) | en la placa |

### Cámaras

Este equipo no tiene ninguna cámara.

### Bluetooth

Este equipo no tiene adaptador Bluetooth.

## Batería

Batería sin datos
El firmware declara una batería, pero no da su capacidad ni su carga, y la tensión que da, 20.48 V, es imposible en una de 14.80 V nominales.

## Sistema

Linux Mint 22.3
silux-pc · encendido 5 min
Linux 6.14.0-37-generic · XFCE · x11

### Sistema operativo

- Distribución: Linux Mint 22.3
- Versión: 22.3
- Identificador: linuxmint
- Nombre del equipo: silux-pc

Esta distribución no declara variante.

### Kernel y entorno

- Kernel: Linux 6.14.0-37-generic
- Arquitectura: x86_64
- Compilación: #37~24.04.1-Ubuntu SMP PREEMPT_DYNAMIC Thu Nov 20 10:25:38 UTC 2 · gcc 13.3.0
- Init: systemd
- Escritorio: XFCE
- Sesión: x11
- Shell: bash
- Gráficos: Mesa 25.0.7
- Kernel contaminado: no

### Actividad

- Encendido desde: (hora de arranque)
- Tiempo encendido: 5 min
- Procesos: 183
- Hilos: 441
- Archivos abiertos: 1 952

### Vulnerabilidades del procesador

- Conocidas por este kernel: 18
- No afectan a este procesador: 10
- Mitigadas: 5
- Sin mitigar: 2
- Sin saber (el kernel no lo sabe): 1

#### Las que afectan a este procesador, como las describe el kernel

- itlb_multihit: KVM: Mitigation: VMX unsupported
- l1tf: Mitigation: PTE Inversion
- mds: Vulnerable: Clear CPU buffers attempted, no microcode; SMT disabled
- meltdown: Mitigation: PTI
- mmio_stale_data: Unknown: No mitigations
- spec_store_bypass: Vulnerable
- spectre_v1: Mitigation: usercopy/swapgs barriers and __user pointer sanitization
- spectre_v2: Mitigation: Retpolines; STIBP: disabled; RSB filling; PBRSB-eIBRS: Not affected; BHI: Not affected

### Intercambio

- Intercambio: no hay

### Arranque

- Kernel: 32.1 s
- Espacio de usuario: 290.3 s
- Línea de arranque: BOOT_IMAGE=/casper/vmlinuz boot=casper initrd=/casper/initrd.lz uuid=… username=mint hostname=… quiet splash --

Falta cuánto tardan el firmware y el cargador: ni el gestor de arranque ni el firmware lo publican.

## Rendimiento

Prueba de rendimiento
Mide el procesador con cinco cargas distintas, primero en un solo hilo y después en todos. Lo interesante no es solo la cifra: es que cada carga escala de una forma, y ahí se ve qué aprovecha los hilos y qué se queda esperando a la memoria. Mientras dura, el equipo irá al máximo.
Cada medida: 15 s · sostenida · la medida de referencia · la prueba entera, 2 min

## Sensores

SENSORES · 10 en 5 dispositivos
*Sensor · Actual · Mín · Máx · Media*
- Intel Celeron 560
  - Temperaturas
    - Núcleo 0 · 70.0 °C · 70.0 · 70.0 · 70.0
  - Relojes
    - CPU 0 · 1630.1 MHz · 1630.1 · 1630.1 · 1630.1
- Dell Vostro A840
  - Temperaturas
    - Temperatura 1 · 70.5 °C · 70.5 · 70.5 · 70.5
- dell_smm
  - Temperaturas
    - CPU (dell_smm) · 70.0 °C · 70.0 · 70.0 · 70.0
    - CPU (dell_smm) · 63.0 °C · 63.0 · 63.0 · 63.0
    - Other (dell_smm) · 43.0 °C · 43.0 · 43.0 · 43.0
  - Ventiladores
    - Processor Fan · 4699 RPM · 4699 · 4699 · 4699
- Memoria
  - Uso
    - RAM usada · 54.8 % · 54.8 · 54.8 · 54.8
- Batería
  - Voltajes
    - Tensión · 20.481 V · 20.481 · 20.481 · 20.481
  - Corrientes
    - Corriente · 0.00 A · 0.00 · 0.00 · 0.00

Mobile GM965/GL960 Integrated Graphics: no tiene sensor de temperatura propio.

> **Falta un driver del kernel**
> Cargando drivetemp tendrías la temperatura de los discos SATA. «Cargar ahora» lo carga hasta que se apague el equipo, con la contraseña de administrador.
> Para que se cargue siempre:
> echo drivetemp | sudo tee /etc/modules-load.d/drivetemp.conf

## Diagnóstico

**Módulos del kernel que ampliarían lo que se ve:**

- `drivetemp`: la temperatura de los discos SATA
  `sudo modprobe drivetemp`

**Datos que faltan:**

- `cpu.codename` (esta versión no lo conoce todavía): Este procesador (Intel(R) Celeron(R) CPU 560 @ 2.13GHz) no está en la tabla de esta versión de Silux, que es de donde salen su nombre en clave, su nodo y su encapsulado.
- `cpu.clocks.bus_hz` (este equipo no lo expone): Este equipo no publica su reloj de referencia (BCLK).
- `modules` (requiere permisos de administrador): Los módulos de memoria están en la tabla SMBIOS, que el kernel reserva al administrador.
- `cpu.clocks.driver` (este equipo no lo expone): Este procesador no tiene driver de frecuencia (cpufreq).
- `gpus.0` (requiere permisos de administrador): El uso de la gráfica solo se lee con permisos de administrador.
- `disks.health` (requiere permisos de administrador): El diagnóstico de los discos lo guarda cada unidad en sus propios contadores.
- `cpu.power` (este equipo no lo expone): Esta CPU no expone contadores de energía RAPL.
- `memory.traffic` (este equipo no lo expone): Este equipo no publica cuánto tráfico mueve el controlador de memoria.
- `cpu.voltage_v` (este equipo no lo expone): Este procesador no publica el voltaje del núcleo.
- `gpus.0.temp_c` (este equipo no lo expone): Esta gráfica va dentro del procesador y no tiene sensor de temperatura propio. (i915 y xe solo registran hwmon en las gráficas dedicadas, y no hay sensor del paquete.)
