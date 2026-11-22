# Qué se ha probado contra qué hardware

Lo que sale de cada fuente, qué se ha validado con una pieza delante y qué
se escribió a ciegas, y lo que queda pendiente por plataforma.

## Equipos volcados

En `tests/fixtures/equipos/`, cada uno con su `manifiesto.json`. La suite
monta el Collector contra todos (`tests/test_equipos.py`).

Los volcados nuevos llevan una segunda lectura de sus contadores, un segundo
después de copiarlos (`segunda_lectura` en `grabado.json`, solo los archivos
de `sysroot.COUNTER_FILES`): montado, la segunda foto del Collector la
encuentra, y el uso, los ritmos y el reposo salen como en el equipo. Los de
antes no la tienen y esas cifras salen «Calculando…» o con guion.

Lo ocupado de cada partición montada: los volcados nuevos guardan los campos
de `statvfs` tal cual (`statfs` en `grabado.json`). Los anteriores guardaban
la pareja ocupado y libre ya calculada, y los hechos antes del 20 de
noviembre de 2026 cuentan como ocupado el 5 % que ext4 reserva para root: su
«Reservado» es solo las tablas del sistema de archivos.

| Volcado | Procesador | Gráfica | Notas |
|---|---|---|---|
| `i5-10400` | Intel Core i5-10400 (Comet Lake-S) | UHD Graphics 630 | Fedora 44, kernel 7.3; en reposo, con el turbo apagado por el gestor de energía (los 12 hilos a 2,9 GHz). Lleva `scaling_cur_freq` y el nombre de la gráfica grabado. De los puentes de Docker queda uno; una interfaz con nombre puesto a mano sale como `interfaz1`. Rehecho el 18 de noviembre con los datos nuevos (reposo, USB, sonido, vulnerabilidades, intercambio, arranque, PCIe); el volcado en reposo enciende a veces el turbo él solo, así que se repite hasta que dentro diga `no_turbo` 1 |
| `i5-10400-turbo` | el mismo | el mismo | con once hilos ocupados y el turbo ya encendido por `auto-cpufreq` (techo 4,3 GHz, los 12 hilos a 4,0). Cuánto tarda en encenderlo no es fijo: se espera a ver `no_turbo` a 0 y se comprueba dentro del volcado. Rehecho el 18 de noviembre, a la vez que el de reposo, y otra vez el 20, con la máquina cargada y el turbo encendido: trae la ventana de PL1 y PL2, los frenos por temperatura y el kernel contaminado. El de reposo sigue siendo el del 18 |
| `qemu-kvm` | «QEMU Virtual CPU version 2.5+» (`qemu64` con el vendedor Intel y las banderas de x86-64-v2-AES de Proxmox) | VGA estándar de QEMU (bochs-drm) | Debian 13, kernel 6.12, dentro de una máquina QEMU/KVM `pc-i440fx` con SeaBIOS, hecha el 20 de noviembre de 2026 para reproducir la de un probador: AHCI con descartes, e1000, tableta USB y el OpenGL de Mesa (llvmpipe). Sin cpufreq, sin sensores y sin zonas térmicas |
| `5800x3d` | AMD Ryzen 7 5800X3D (Zen 3, AM4) | Radeon RX 9070 XT | CachyOS, kernel 7.3; placa X570, dos monitores, cinco discos (dos montados fuera del sistema). De las interfaces de Docker queda una de cada. **Rehecho el 23 de noviembre de 2026**, sin permisos, con el volcado de la prueba11: la segunda lectura de los contadores (uso, ritmos y consumo de la gráfica en el volcado), el modo que tiene puesto cada monitor, los campos de statfs (el ocupado y el libre como `df`) y lo enchufado por USB con su vendor:product |

| `i5-1135g7` | Intel Core i5-1135G7 (Tiger Lake-UP3) | Iris Xe | El ThinkPad T14 Gen 2i del autor, importado del anexo de su informe de la prueba4 (`tools/importar_informe.py`), el 21 de noviembre de 2026. CachyOS, kernel 7.3; 8 GB soldados y un SODIMM Kingston (el único SPD del bus), Wi-Fi, un túnel de WireGuard (sale como `interfaz1`), batería, `thinkpad_acpi` y una zona `acpitz` que mide de verdad. RAPL solo para root: es el único volcado con el candado del consumo |
| `i7-10700f` | Intel Core i7-10700F (Comet Lake-S) | GeForce RTX 4060 (nvidia 595) | Un sobremesa, importado del anexo de un informe de la prueba5, el 21 de noviembre de 2026 (antes, del de la prueba4). Gentoo con OpenRC, kernel 6.18, con carga en un hilo; MSI H410M-A PRO, dos TEAMGROUP-UD4-3200 con XMP 2.0 (el primer SPD con XMP de la suite), NVML grabada (sin el consumo, que su driver no dio), sin el cargador de OpenCL (el único volcado con un paquete del sistema que falta), estados de reposo de la tabla ACPI y `acpitz` de relleno |
| `i5-12450h` | Intel Core i5-12450H (Alder Lake-H, híbrido) | UHD Graphics + GeForce RTX 4050 Laptop (nvidia 550) | Un portátil Lenovo LOQ 15IRH8, importado del anexo de un informe de la prueba5 el 21 de noviembre de 2026 y **rehecho con el de la prueba8** el 22. Debian 13, kernel 6.12; dos SODIMM DDR5 con `spd5118` cargado pero sin el SPD legible y su sensor de temperatura, los contadores del controlador de memoria, de dos campos, que el ayudante aún no abre, la página 0 del SPD que su dueño leyó con `dd` (las demás dan ENXIO), Vulkan con la UHD (Mesa 25.0.7) y OpenGL de la NVIDIA, y NVML grabada. Lo que su prueba5 grababa de Vulkan (sin la Intel) va en `tests/test_loq_prueba5.py` |
| `celeron-n4000` | Intel Celeron N4000 (Gemini Lake) | UHD Graphics 600 | Un portátil Lenovo V130-15IGM, importado del anexo de un informe de la prueba5, el 21 de noviembre de 2026. Debian 13, kernel 7.1; un SODIMM DDR4 con su SMBus y ningún chip SPD registrado, buses i2c del touchpad, una memoria USB y el informe hecho con permisos |
| `athlon-3000g` | AMD Athlon 3000G (Picasso) | Radeon Vega 3 (integrada) | Un sobremesa MSI A320M-A PRO, importado del anexo de un informe de la prueba5, el 21 de noviembre de 2026. Arch, kernel 7.3; sin driver de frecuencia y sin CPPC, la bandera `cpb` sin turbo de verdad, una memoria USB y el informe hecho con permisos |
| `ryzen3-4100` | AMD Ryzen 3 4100 (Renoir) | Radeon RX 550 (Polaris 12, amdgpu) | Un sobremesa Gigabyte B450M DS3H V2, importado del anexo de un informe de la prueba6, el 21 de noviembre de 2026. Fedora 44, kernel 7.2; la primera Radeon dedicada sin telemetría del firmware de la suite, su enlace a x4 de x8 a toda velocidad, el SMBus reservado y el informe hecho con permisos |
| `i5-3330` | Intel Core i5-3330 (Ivy Bridge) | HD Graphics 2500 | Un sobremesa con chipset H61, importado del anexo de un informe de la prueba6, el 22 de noviembre de 2026. Arch, kernel 7.3; dos DDR3 catalogadas a velocidades distintas, con su SPD |
| `i5-5200u` | Intel Core i5-5200U (Broadwell-U) | HD Graphics 5500 | Un portátil Acer, importado del anexo de un informe de la prueba7, el 22 de noviembre de 2026. Ubuntu 24.04, kernel 7.0; DDR3L con su SPD y una partición de intercambio |
| `core2-p8400` | Intel Core 2 Duo P8400 (Penryn) | Quadro NVS 160M (nouveau) | Un Dell Latitude E6400, importado del anexo de un informe de la prueba7, el 22 de noviembre de 2026. antiX (base Debian 13) con runit y sin logind, BIOS heredada, sin RAPL y sin voltaje en su MSR; el kernel no registra el chip SPD |
| `i5-8350u` | Intel Core i5-8350U (Kaby Lake-R) | UHD Graphics 620 | Un ThinkPad T480s, importado del anexo de un informe de la prueba7, el 22 de noviembre de 2026. Ubuntu 24.04, kernel 7.0; batería con umbrales de carga, CPPC y su SPD |
| `celeron-560` | Intel Celeron 560 (Merom-L, un núcleo) | GM965 (i915) | Un Dell Vostro A840, importado del anexo de un informe de la prueba7, el 22 de noviembre de 2026. Linux Mint 22.3 desde una unidad USB, kernel 6.14; el primer DDR2 de la suite, leído de su SPD, una BIOS que declara DDR para él, una batería sin nada dentro y sin conexión de red |
| `i7-4710hq` | Intel Core i7-4710HQ (Haswell) | HD Graphics 4600 + GeForce GTX 850M (nouveau, dormida) | Un ASUS X550JK con Optimus, importado del anexo de un informe de la prueba7, el 22 de noviembre de 2026. El mismo Linux Mint por USB; un SSD SATA por USB, sin conexión de red, y un anexo sin `uname` (sin versión del kernel ni nombre del equipo) |
| `celeron-g3900` | Intel Celeron G3900 (Skylake, sin turbo) | HD Graphics 510 | Un sobremesa con una ASUS H110M-D, importado del anexo de un informe de la prueba8, el 22 de noviembre de 2026. Linux Mint 22.3, kernel 6.8; un módulo DDR4-2133 leído de su SPD, un SSD SATA y un HDD sin montar, una Wi-Fi USB con `rtl8192eu` (que cuenta mal los paquetes) y la Ethernet sin cable, ZFS cargado, y una tele por HDMI cuyo EDID no entró en el anexo (llevaba su número de serie) |

Todos son sin permisos. Lo que se arregle en lo que lee el procesador o la
gráfica se comprueba contra un volcado de Intel y contra el de AMD.

Lo que en AMD se escribió sin la pieza delante: un `k10temp` que publique
Tdie además de Tctl (los Ryzen con desplazamiento: 1700X, 1800X y los
Threadripper de las dos primeras generaciones). Se enseña Tdie, por lo que
dice la documentación del kernel; el 5800X3D solo tiene Tctl.

## Lo que ha llegado de la gente

Una línea por equipo del que ha llegado un informe, sin quién lo mandó. Los
informes y el detalle de cada fallo están en las notas privadas del autor;
lo que se arregla, en el CHANGELOG. «A ciegas»: arreglado con lo que dice el
informe, sin haberlo visto todavía en ese equipo.

| Equipo | Procesador | Placa | Memoria | Gráfica | Sistema | Versión | Permisos | Lo que salió mal | Estado |
|---|---|---|---|---|---|---|---|---|---|
| Sobremesa | Intel Core i7-10700F | MSI H410M-A PRO | DDR4 Team Group, con XMP | GeForce RTX 4060 (nvidia 595) | Gentoo, OpenRC | 0.4-prueba1, 0.4-prueba2, 0.4-prueba4, 0.4-prueba5 | sí | XMP mal leído; consumo de la NVIDIA «—»; 8,2 GB de VRAM; versión del driver sin un cero; «Escrito en total» del Kingston A400; OpenRC como «init»; los C-states; en la prueba2, «?» en Sistema con OpenRC | En la prueba4 el anexo salió entero y Sistema bien; con él, el XMP, los C-states y la NVIDIA en Sensores, arreglados. En la prueba5 (el volcado `i7-10700f`) se ven en su equipo el XMP, la NVIDIA en Sensores y RAPL con núcleos y DRAM; el consumo de la NVIDIA sigue sin salir, y desde la prueba6 dice qué contestó NVML |
| Portátil Lenovo LOQ 15IRH8 | Intel Core i5-12450H | Lenovo | DDR5-4800 | UHD + GeForce RTX 4050 Laptop | Debian 13 | 0.4-prueba1 (normal y compat), 0.4-prueba2, 0.4-prueba5, 0.4-prueba8 | sí | Sin tiempos de arranque con el compat; la L3 contada dos veces; la dedicada dormida «sin driver»; nombres en bruto; el anexo de la prueba2 no salió (NVIDIA) | Arreglados en la prueba2 y la prueba3. En la prueba5 el anexo salió entero (es el volcado `i5-12450h`): comprobados el ventilador y las rayas de la NVIDIA, el aviso de la UHD y el espacio reservado; siguen el SPD de la DDR5, las bibliotecas de la UHD y el tráfico de memoria. La prueba8 rehízo el volcado: el SPD de la DDR5 sigue sin leerse, su sensor de temperatura sin módulo, el tráfico de memoria como un fallo, la versión de Mesa de la UHD sin «Mesa», el paquete de `pnp.ids` en Debian y los núcleos P y E sin distinguir en Sensores |
| Máquina virtual (QEMU/KVM en Proxmox) | QEMU Virtual CPU | — | — | VGA de QEMU | Debian | 0.4-prueba1 (compat) | sí | El procesador como un Xeon; el disco como HDD y SMR; permisos para lo que no tiene; rayas | Arreglados en la prueba2, comprobados con el volcado `qemu-kvm` |
| Sobremesa | AMD Athlon 3000G | MSI A320M-A PRO | 4 GB DDR4-2400, un módulo | Radeon Vega 3 integrada | Arch | 0.3.0, 0.4-prueba1 | sí | Sin frecuencia (no hay cpufreq); «Turbo —»; la tabla PCI de una APU; rayas en Gráficos; un pendrive como HDD; «Memoria prestada al sistema»; sin aviso de errores de cable | Frecuencia y turbo hechos, para la siguiente; lo demás, pendiente o a falta de su volcado |
| Portátil Lenovo V130-15IGM | Intel Celeron N4000 | Lenovo | 8 GB | UHD 600 | Debian 13, XFCE | 0.4-prueba2 | no | El anexo no salió (la puerta de enlace y un pendrive) | Arreglado en la prueba3 |
| Portátil ThinkPad T14 Gen 2i | Intel Core i5-1135G7 | Lenovo | 16 GB DDR4-3200 (8 soldados y un SODIMM) | Iris Xe | CachyOS | 0.4-prueba2, 0.4-prueba4 | sí | En la prueba2, el anexo no salió (el equipo se llama como su marca), los puertos USB-C y la nota pegada en Sensores. En la prueba4 el anexo salió entero (es el volcado `i5-1135g7`), y con él: el SPD de la ranura pegado a lo soldado, el Kingston sin fabricante y el candado del consumo, que no hacía nada | Los de la prueba2, comprobados en la prueba4; los de la prueba4, arreglados y comprobados con su volcado |
| Sobremesa | Intel Celeron G3900 | ASUS H110M-D | 4 GB DDR4-2133, un módulo | HD Graphics 510 | Linux Mint 22.3 | 0.4-prueba8 | sí | «Turbo desactivado» en un procesador sin turbo; los paquetes de la Wi-Fi USB (`rtl8192eu`) imposibles para su MTU; la Wi-Fi sin modelo y con «Ranura PCI»; ZFS como «módulo propietario»; «Rev X.0x» como revisión; la tele a 1360×768 y 72" cuando iba a 1920×1080 y es de 32"; «0 W» en Gráficos; DIMM y UDIMM; la zona PP1 de RAPL como «Uncore» | Volcado `celeron-g3900`; en la prueba10 |

## Por plataforma

De Gráficos sale todo lo que publica el nodo DRM (identidad, VRAM, tabla DPM,
enlace PCIe, sensores propios) más lo que solo da el ioctl de amdgpu (tipo de
memoria, anchura del bus, ancho de banda, unidades de cómputo y ROP), las tres
APIs y el EDID de cada monitor. De las Intel, el uso por motor y los vatios
salen del PMU de perf leído por el ayudante privilegiado (`gpu_pmu`); el
reposo (RC6) y los motores con sus capacidades, de sysfs sin permisos; y los
códecs que acelera, de VA-API atada a su nodo de render. Su temperatura no
existe por ningún camino. Queda pendiente:

- **Las versiones de `gpu_metrics` de la 1.4 en adelante**, que reordenaron los
  campos, y las 2.x de las APU a partir de la 2.1. Se reconocen y se dejan
  pasar en vez de interpretarlas mal, y ahora se dice cuál es y sale en el
  informe: con eso y el modelo se puede escribir su tabla sin tener la pieza.
  La 2.1 ya se lee, y salió así: la trajo la captura de un usuario con una
  Radeon 740M donde el punto caliente y los recortes salían a guiones. **Y ya
  está validada contra hardware**: el 30 de agosto de 2026 esa misma 740M
  enseñó punto caliente 31.4 °C y voltaje 0.755 V donde antes había guiones.
  Aquí sigue habiendo solo una v1.3, así que de la 1.4 en adelante y del resto
  de las 2.x no hay pieza a la que preguntar.

**Los motores de la RX 9070 XT, validados el 18 de noviembre de 2026**
(docs/motores-de-graficas.md): «Render / 3D» coincide con la ficha «Uso» y,
desde ese día, con MangoHud (80-86 %), porque es la media del intervalo y no
una lectura suelta. Una sola barra de video, «Video (codificar y
decodificar)»: en el VCN 5.0 decodificar también va por la cola de codificar
(lo dice el `fdinfo` de mpv decodificando por VA-API), y la cifra de la
tarjeta es una. Con Big Buck Bunny de YouTube en AV1 4K, 18 %; grabando la
pantalla con gpu-screen-recorder (HEVC), 76 %; con las dos cosas, 100 %. La
`gpu_metrics` 1.3 de esta tarjeta casa con hwmon (borde, unión y memoria, y
el consumo a 4 W). NVENC y NVDEC, escritos sin una NVIDIA delante.

**El contador del IMC ya está**, que era la otra mitad de esa línea: cuánto
tráfico mueve la memoria ahora mismo, en la ficha, en el árbol de sensores y en
el informe. Sale del PMU del uncore por el ayudante privilegiado (los
contadores de perf piden CAP_PERFMON y `perf_event_paranoid` viene a 2 en
cualquier distribución), y el nombre del PMU cambia con la generación:
`uncore_imc` hasta Comet Lake, `uncore_imc_free_running_N` de Ice Lake en
adelante y `uncore_imc_N` en los de servidor, que además llaman a sus eventos
por el comando de la DRAM. Va en bytes por segundo para compartir con
`membench` el porcentaje del teórico, que si no serían dos cifras de la misma
página que no se pueden comparar. Se validó contra tráfico de tamaño conocido
en el i5-10400: diez GiB leídos a propósito con `memchr` y diez escritos con
`memset`, y el contador vio 9,95 y 10,30 descontando el fondo. En el árbol de
sensores estrena la rama «Tráfico» y el aparato «Memoria», cuyo hueco llevaba
reservado en `_device_order` desde que se escribió el orden, vacío.

**Y es de Intel a propósito, no por falta de ganas.** De Zen 4 en adelante
existe `amd_umc_N`, pero el kernel le registra `format` y no `events/`: los
nombres viven en el JSON de la herramienta `perf` y no en sysfs, así que
habría que escribir el número de evento a mano (`event=0x05` con su
`rdwrmask`) y afirmar lo que significa sin ninguna pieza donde comprobarlo. De
Zen 3 para atrás no hay ni eso: `amd_df` existe y sus eventos de DRAM no están
documentados. Escribir ese camino sería dejarlo estrenándose en la máquina de
otro, que es la forma exacta del `NameError` de `_identidad`. Así que en AMD
sale el aviso gris de que este equipo no lo publica, y cuando aparezca un Zen 4
al que preguntarle, lo que falta es una tabla de posiciones más.

La ficha ya está: los zócalos vacíos van juntos en una línea como las salidas
de vídeo libres, y el título de cada uno sale de `render.slot_labels`, que
compone el mínimo que lo distingue («Canal A», y el controlador o el DIMM solo
cuando sin ellos dos se llamarían igual), así que se acabaron los dos «DIMM 0».
Sin SMBIOS no hay zócalo que dar y se numeran «Módulo 1», «Módulo 2»: el `slot`
del SPD es la dirección en el bus i2c y no la posición en la placa.

**ARM se identifica, sin dejar de ser un programa de x86.** Donde no hay
CPUID, `providers/armcpu.py` lee el MIDR de `/proc/cpuinfo` (quién hizo el
núcleo, cuál es y en qué revisión va) y lo cruza con `db.identify_arm`, que
ya estaba escrita y sin usar. Sale «ARM Cortex-A76 r0p0», nombre en clave
«Enyo» y 10-7 nm, en vez de una interrogación. Un big.LITTLE se reparte en tipos de núcleo por el mismo
sitio por el que se reparte un Intel híbrido, que para eso `cpu.types` es una
lista. Lo atado a x86 no se finge: CPUID, DMI, RAPL y el SPD por i2c salen
como «no aplica». El resto (sysfs, hwmon, red, discos) funciona igual porque
sysfs es igual en toda arquitectura.

**NVIDIA ya está probada contra hardware.** Se escribió a ciegas siguiendo la
API documentada, porque en esta máquina no hay ninguna GeForce, y el 26 de
agosto de 2026 llegaron las capturas de dos equipos ajenos: una GTX 1660 Ti
(TU116) y una RTX 3050 Mobile (GA107M). Acertó en casi todo lo comprobable
(anchura de bus, identificadores, UUID, el enlace bajado a PCIe 1.0 en reposo
con su máximo bien leído, los motivos de recorte) así que `nvml.py` y
`providers/nvidia.py` ya no son código de fe. En lo que no acertaba era en los
núcleos CUDA, y se tardó en verlo porque el arreglo estaba escrito: la 3050
seguía diciendo 16 y una RTX 4080 Laptop, 58. Están abajo, en las lecciones. Lo que sigue sin salir en NVIDIA
es el tipo de memoria y las unidades de rasterizado: NVML no los publica.

⚠ **ARM no se ha ejecutado contra hardware.** Está probado contra
`/proc/cpuinfo` de máquinas reales guardados en `tests/fixtures/arm/`, pero en
esta máquina no hay ningún aarch64. Quien lo pruebe en uno, que contraste con
`lscpu`.

## Lo que trajo el ThinkCentre M80q

Capturas del 1 de septiembre de 2026, de la misma persona que mandó la máquina
virtual del día anterior y esta vez desde su equipo: un Lenovo ThinkCentre M80q
(i5-10500T, UHD 630, 31 GB en dos SODIMM, Manjaro con XFCE) y con los permisos
ya dados, así que es el equipo ajeno más completo que ha pasado por aquí: 45
sensores y catorce fuentes activas, `msr`, `smbios`, `spd` y `rapl` incluidos.
Tres fallos confirmados leyendo el código, los tres ya arreglados, y dos que
necesitan su informe:

- **El titular era el código de placa OEM y no el nombre del equipo**: salía
  «Lenovo 316C» donde eso es un ThinkCentre M80q. **Hecho**, y la solución no
  fue la que parecía: ampliar la lista de chasis no habría cerrado nada, porque
  los sobremesas de marca suelen declararse «Desktop» a secas. Ver la lección
  de abajo.
- **El ⚠ «por debajo de su velocidad» salta por un redondeo**: un SK Hynix
  catalogado a 2667 y funcionando a 2666 es el mismo grado JEDEC (DDR4-2666 son
  1333,33 MHz, o sea 2666,67 MT/s, que unos redondean arriba y otros abajo) y
  `MemoryModule.underclocked` comparaba `actual < rated` a pelo. **Hecho**:
  margen del 1 %, que no puede confundir dos grados (los contiguos están a 133
  MT/s en DDR4 y a 400 en DDR5) y absorbe el redondeo, que es de un MT/s.
- **Y el consejo manda a la BIOS a por algo imposible**: con un módulo de 3200
  y otro de 2667, la frase «va a 2666 de los 3200 que declara admitir, suele ser
  el perfil rápido sin activar» es falsa, porque el conjunto va al ritmo del más
  lento y ese equipo no verá 3200 active lo que active. `_apply_avisos` toma
  `lentos[0]` y usaba su velocidad catalogada, así que el diagnóstico salía
  del módulo rápido e ignoraba al que manda. **Hecho**: el techo es el mínimo
  de los catalogados y hay tres respuestas donde había dos (hay margen, no hay
  margen pero uno declara más, o no hay nada que decir), en
  `render.memory_speed_warning`.
- **Por confirmar**: la insignia del hostname dice `none`, resaltada como si
  fuera la identidad del equipo. El kernel usa `(none)` cuando nadie lo
  configuró, y si es eso, es un «sin configurar» pintado como un nombre. Y en
  «Perfiles y temporizaciones» solo sale el módulo A, aunque del B se leyó el
  SPD entero.

Lo que hay que pedirle, por orden: el informe con permisos; los sensores; y el
almacenamiento, que sería el primer SMART ajeno.

**El voltaje en Intel ya no hace falta pedirlo: está validado.** El 1 de
septiembre de 2026, en el i5-10400 donde se escribió el contador del IMC:
`IA32_PERF_STATUS` devolvió `0x00001bb800001d00`, cuyos bits 47:32 son 7096, y
7096 ÷ 8192 = 0,8662 V, que es lo que enseña la ficha. Ese camino se había
escrito a la vez que el de AMD y solo se había comprobado en el 5800X3D, así
que era la mitad no probada de la misma función.
