# Propuesta: datos nuevos

Solo propuesta: nada de esto está escrito en la aplicación ni en la suite.
No es el estado del programa.

Lo que sí está hecho es mirar de dónde saldría cada dato. El 17 de noviembre
de 2026, en el 5800X3D de casa (Gigabyte X570, RX 9070 XT, CachyOS, kernel
7.3.4), se leyó cada fuente **sin permisos** y se apuntó qué devolvía. Del
i5-10400 solo hay su volcado, y un volcado guarda lo que el Collector lee
hoy: de casi todo lo de aquí no tiene nada. Por eso la columna «Intel» dice
casi siempre que no, y no es que falle: es que no se ha mirado.

Cómo leer las tablas:

- **Permisos**: «no» es que se lee con el usuario de siempre. «sí» es que
  hace falta el ayudante, y entonces el dato lleva candado mientras no se
  den (regla 5).
- **AMD / Intel**: «sí» es que se leyó en esa pieza y devolvió algo con
  sentido. «volcado» es que el dato está en el volcado de esa pieza. «no» es
  que no se ha comprobado. Nada se da por bueno en una pieza por haberlo
  visto en la otra (`docs/en-curso.md`, decisiones).
- **Fiable**: si el dato se puede afirmar. Lo que no se puede leer de forma
  fiable no se propone, y está al final con su porqué.

Las maquetas están en `~/Imágenes/silux-test/datos-nuevos/` (casa), con el
guion que las genera. No van al repositorio.

## Resumen

| Bloque | Entra sin permisos | Pide permisos | Se descarta |
|---|---|---|---|
| Placa base | enlaces PCIe, controladores USB/SATA/NVMe, audio, chip de sensores, IOMMU, virtualización, Above 4G | nombre de cada ranura (SMBIOS tipo 9) | temperatura del chipset y del VRM con nombre |
| Sistema | vulnerabilidades, Mesa, swap y zram, gestor de arranque, tiempo de firmware y cargador | — | tiempo de kernel y de servicios sin lanzar un proceso |
| CPU | residencia en C-states, PL1/PL2 de Intel, microcódigo | — | PPT/TDC/EDC de AMD |
| Cachés | la latencia ya medida, en su nivel | — | — |
| Memoria | perfiles XMP/EXPO y secundarias del SPD | — | temporizaciones en uso, FCLK/UCLK |
| Almacenamiento | TRIM, cifrado LUKS | tabla SMART completa | — |
| Red | adaptador Bluetooth; del wifi, la señal | — | banda, canal y estándar sin netlink (ver abajo) |
| Dispositivos | USB, audio, cámaras, Bluetooth | — | — |

## Placa base

| Dato | De dónde | Permisos | AMD | Intel | Fiable |
|---|---|---|---|---|---|
| Qué cuelga de cada enlace PCIe, con su velocidad y anchura actuales y máximas | `/sys/bus/pci/devices/*/{current,max}_link_{speed,width}` y `class`; el nombre, de `pci.ids` | no | sí: 30 dispositivos con enlace | volcado, parcial: solo la gráfica | sí |
| El nombre de la ranura («PCIEX16», «M2A_CPU») | SMBIOS tipo 9, `/sys/firmware/dmi/entries/9-*/raw` | **sí** | no: sin permisos da `PermissionError` | no | a medias: ver nota |
| Controladores USB (xHCI) | PCI clase `0x0c0330`, con su driver | no | sí: tres | no | sí |
| Controladores SATA y NVMe | PCI clases `0x010601` y `0x010802` | no | sí: dos y dos | no | sí |
| Audio: códec de la placa | `/proc/asound/card*/codec#*`, primera línea | no | sí: «Realtek ALCS1200A» | no | sí |
| Chip de sensores | el nombre del `hwmon` de placa, que `render.chip_name` ya limpia | no | sí: IT8688 | volcado | sí |
| IOMMU activa | `/sys/class/iommu/` no vacío y nº de `/sys/kernel/iommu_groups/*` | no | sí: `ivhd0`, 34 grupos | no | sí |
| Virtualización utilizable | bandera `svm` o `vmx` en `/proc/cpuinfo` y que exista `/dev/kvm` | no | sí | no | con matiz: ver nota |
| Decodificación por encima de 4 GB | alguna BAR con dirección ≥ 4 GB en `/sys/bus/pci/devices/*/resource` | no | sí: cuatro dispositivos | no | solo en positivo |
| Resizable BAR | ya está en Gráficos (`GpuMemory.resizable_bar`) | no | sí | — | sí |

**Las ranuras.** Hay dos cosas distintas y solo una es gratis. *Qué hay
enchufado y a qué velocidad negocia* sale de sysfs sin permisos, y es lo que
responde a «¿mi gráfica va a ×16?» y «¿este NVMe se ha quedado en PCIe 3.0?».
*Cómo se llama la ranura en la placa* solo está en la tabla del firmware, que
pide permisos, y los fabricantes la rellenan regular: ranuras que no existen,
ranuras con el nombre de otra. Propuesta: la tabla se monta con lo de sysfs
(dispositivo, enlace, puente del que cuelga) y, con permisos, se le añade el
nombre de la ranura **solo cuando la dirección PCI de la tabla casa con un
dispositivo que existe**. `/sys/bus/pci/slots` está vacío en esta placa: no
sirve de atajo.

**El enlace de una gráfica no se lee en su nodo PCI.** Se vio al hacer la
maqueta: la RX 9070 XT dice ahí «32 GT/s × 16», PCIe 5.0, en una placa de
PCIe 4.0. Es el enlace de dentro de la tarjeta, entre su puente y su chip.
El de la ranura está un puente más arriba, y `providers/drm.py` ya lo busca
ahí para la página de Gráficos («PCIe 4.0 × 16»). La tabla de ranuras tiene
que usar esa misma función para todo dispositivo que lleve un puente
propio, y no leer cada nodo por su cuenta.

Lo que se enseña son los dispositivos finales (gráfica, NVMe, red, USB), no
los puentes. Un enlace por debajo de su máximo se marca; no es un fallo,
puede ser ahorro de energía (ASPM) o una ranura eléctricamente más corta, y
el texto lo tiene que decir así.

**Virtualización.** La bandera en `/proc/cpuinfo` dice que el procesador la
tiene, no que la BIOS la haya dejado encendida. Lo que sí se puede afirmar
sin permisos: si `/dev/kvm` existe, está encendida y usable. Si la bandera
está y `/dev/kvm` no, no se sabe si es la BIOS o que falta el módulo `kvm`;
el registro que lo aclara (`IA32_FEATURE_CONTROL`, `VM_CR`) pide permisos y
el ayudante ya lee registros del procesador. Propuesta: tres estados,
«activa», «el procesador la tiene; no está en uso» y, con permisos,
«apagada en la BIOS».

**Above 4G.** Una BAR por encima de 4 GB demuestra que está activado. Que no
haya ninguna no demuestra lo contrario: puede no haber nada que lo necesite.
Se enseña «activo» o no se enseña.

**Descartado: temperatura del chipset y del VRM.** El chip de sensores las
mide, pero sin decir cuál es cuál: en esta placa son «Temperatura 1…6»
(`docs/lecciones.md`). Ponerles «Chipset» y «VRM» sería inventarlo, y por
placa haría falta una tabla que no hay de dónde sacar de forma fiable. Se
quedan en Sensores, numeradas, como están.

## Sistema

| Dato | De dónde | Permisos | AMD | Intel | Fiable |
|---|---|---|---|---|---|
| Vulnerabilidades del procesador y su mitigación | `/sys/devices/system/cpu/vulnerabilities/*` | no | sí: 19 entradas | no | sí |
| Versión de Mesa o del driver gráfico | ya se lee: la cadena de versión de OpenGL (`gpuapi`) | no | sí: «Mesa 26.2.6» | volcado | sí |
| Swap: dispositivos, tamaño y uso | `/proc/swaps` | no | sí | no | sí |
| zram: tamaño, algoritmo y cuánto comprime | `/sys/block/zram*/{disksize,comp_algorithm,mm_stat}` | no | sí: 31.3 GB, zstd | no | sí |
| Gestor de arranque | `LoaderInfo-4a67b082-…` en `/sys/firmware/efi/efivars` | no | sí: «Limine 12.10.0» | no | solo si el cargador lo publica |
| Tiempo de arranque del firmware y del cargador | `LoaderTimeInitUSec` y `LoaderTimeExecUSec`, mismo sitio | no | sí: 13.3 s y 18.6 s | no | solo si el cargador lo publica |

**Vulnerabilidades.** Cada archivo trae una de tres cosas: «Not affected»,
«Mitigation: …» o «Vulnerable». Propuesta: una línea de resumen («19
conocidas: 13 no afectan, 6 mitigadas, ninguna abierta») y la lista
plegada. El texto de la mitigación es del kernel y va tal cual, sin
traducir: es lo que se pega en un buscador. Solo «Vulnerable» lleva aviso.
En el volcado del 5800X3D la carpeta existe pero está vacía: el Collector no
la lee hoy.

**Arranque.** Las variables `Loader*` las escriben systemd-boot, Limine y
algún otro; GRUB no. Donde no estén, la fila no sale y se dice al pie. Los
tiempos son los del firmware y del cargador, que es lo que no depende del
sistema; van como «hasta el cargador» y «hasta el kernel».

**Descartado por ahora: el tiempo del kernel y de los servicios.** Lo da
`systemd-analyze`, que es lanzar un proceso y depender de systemd, o sus
propiedades por D-Bus. Se puede hacer, pero no es leer un archivo; si se
quiere, es una decisión aparte.

## CPU

| Dato | De dónde | Permisos | AMD | Intel | Fiable |
|---|---|---|---|---|---|
| Residencia en cada C-state, por núcleo | `/sys/devices/system/cpu/cpu*/cpuidle/state*/{name,time,usage}`, restando dos lecturas | no | sí: POLL, C1, C2 | no | sí |
| Límites de potencia PL1 y PL2 | `/sys/class/powercap/intel-rapl:0/constraint_{0,1}_power_limit_uw` | no | no existen: la carpeta no trae `constraint_*` | volcado: 65 W y 115 W | sí en Intel |
| Microcódigo | ya se lee; hoy va dentro de «Identificación CPUID», plegado | no | sí | volcado | sí |

**C-states.** Es un dato que sale de restar, como el uso por hilo: el
porcentaje del último intervalo que cada núcleo pasó en cada estado. Va como
una barra apilada por núcleo, con la primitiva que ya existe (`StackedBar`).
Los nombres cambian entre fabricantes («C2» en AMD por ACPI, «C6», «C10» en
Intel) y se enseñan como los da el kernel. Un volcado guarda una sola
lectura: los tests de esto necesitan dos, como los de RAPL.

**PL1/PL2.** En Intel están en el mismo sitio que la energía y se leen sin
permisos. Son los límites que el firmware programó, no los del catálogo: es
justo lo interesante («esta placa deja al i5 en 115 W»).

**Microcódigo.** No hay dato nuevo: propuesta de sacarlo de lo plegado a la
tarjeta de identificación. Lo que no se puede hacer es decir si está al día
sin una tabla de versiones por procesador, y esa tabla no existe aquí; el
kernel sí lo dice (`vulnerabilities/old_microcode`) y eso basta.

**Descartado: PPT, TDC y EDC de AMD.** No los publica ningún driver del
kernel. Solo salen con `ryzen_smu`, un módulo de fuera del kernel que habla
con el firmware por una interfaz sin documentar, distinta por generación. No
es una fuente fiable y no se propone.

## Cachés

| Dato | De dónde | Permisos | AMD | Intel | Fiable |
|---|---|---|---|---|---|
| Latencia medida de cada nivel | ya se mide: `membench.Resultado.latencias` (L1, L2, L3, RAM) | no | sí | sí | es una medida, con sus condiciones |

No se lee nada nuevo. Hoy la latencia se enseña en Memoria, al medir. La
propuesta es que, una vez medida, la tabla «Detalle por nivel» de Cachés
gane una columna «Latencia» con la cifra de cada nivel, y una fila para la
RAM debajo. Mientras no se haya medido, la columna no existe: nada de
guiones. Hace falta que el resultado de la medida llegue a la foto o a la
página de Cachés; hoy vive en la de Memoria.

## Memoria

| Dato | De dónde | Permisos | AMD | Intel | Fiable |
|---|---|---|---|---|---|
| Perfiles XMP y EXPO con sus temporizaciones | SPD: ya se decodifican (`spd.profiles`) | no, si el SPD se lee | no: esta placa no deja leer el SPD | volcado: sin perfiles en esos módulos | sí, con el fallo conocido F-A2 |
| Temporizaciones secundarias del SPD (tRFC, tRRD, tFAW, tWR) | los mismos bytes del SPD, que hoy no se decodifican | ídem | no | no | sí como «catalogadas» |

**Lo que el SPD dice es lo catalogado, no lo que está en uso.** Vale para
las primarias, que ya se enseñan así, y valdría para las secundarias. Antes
de añadir más temporizaciones hay que cerrar F-A2 (el XMP de DDR4 ignora la
corrección fina: un DDR4-3600 sale 3200), que sigue pidiendo un volcado real
con XMP.

**Descartado: las temporizaciones en uso, y FCLK/UCLK.** Lo que la placa ha
programado de verdad vive en registros del controlador de memoria. En Intel
hay camino con permisos para algunas generaciones; en AMD solo con
`ryzen_smu`, por lo mismo que PPT. No hay forma fiable y común: no se
propone.

## Almacenamiento

| Dato | De dónde | Permisos | AMD | Intel | Fiable |
|---|---|---|---|---|---|
| Tabla SMART completa | el ayudante ya pide el registro; hoy se enseñan cuatro campos | **sí** | con permisos (no se han pedido en esta sesión) | no | sí |
| TRIM: si la unidad lo admite | `/sys/block/X/queue/discard_max_bytes` distinto de 0 | no | sí | no | sí |
| TRIM: si se está haciendo | opción `discard` en `/proc/mounts`, o `fstrim.timer` activado | no | sí: las dos cosas | no | con matiz |
| Planificador de E/S | ya se lee y se enseña, plegado | no | sí | volcado | sí |
| Cifrado LUKS | `/sys/block/dm-*/dm/uuid` que empiece por `CRYPT-LUKS` y de qué partición cuelga (`slaves/`) | no | no: este equipo no cifra nada | no | sí en teoría; sin pieza |

**SMART.** El ayudante ya lee el registro entero; solo se decodifica una
parte. Propuesta: una tabla plegada por disco. En NVMe son campos con nombre
fijo por la especificación. En SATA los atributos son números y su nombre
depende del fabricante: se enseñan el número, el nombre habitual cuando es
de los comunes y el valor crudo, sin interpretar los que no se conocen.

**TRIM.** «Lo admite» es un hecho. «Se hace» es una inferencia: el
temporizador puede estar activado y no cubrir esa partición. Se dice lo que
se ve («montada con discard», «fstrim.timer activo») y no un «sí» a secas.
Curiosidad vista aquí: un HDD (`sda`) declara que admite descartes; es un
disco SMR. Se enseña lo que dice, sin llamarlo TRIM de SSD.

**LUKS.** Escrito a ciegas: en ninguna de las dos máquinas hay un volumen
cifrado. Necesita un volcado de un equipo que lo tenga antes de darlo por
bueno.

## Red

| Dato | De dónde | Permisos | AMD | Intel | Fiable |
|---|---|---|---|---|---|
| Adaptador Bluetooth: cuál es y si está encendido | `/sys/class/bluetooth/hci*`, su dispositivo y `rfkill*/state` | no | sí: un adaptador USB | no | sí |
| Wifi: nivel de señal | `/proc/net/wireless` | no | no: este equipo no tiene wifi | no | sí, sin pieza |
| Wifi: banda, canal y estándar | nl80211 (netlink genérico) | no | no | no | ver nota |

**Wifi.** No hay tarjeta wifi en ninguna de las dos máquinas, así que todo
esto está sin comprobar. La señal es un archivo. La banda, el canal y el
estándar (Wi-Fi 5, 6, 7) no están en sysfs: solo los da nl80211, que es
hablar con el kernel por un socket netlink. Se puede hacer desde Python sin
permisos y sin dependencias, pero es un proveedor nuevo de cierto tamaño y
hay que escribirlo con una pieza delante. Propuesta: aplazarlo hasta tener
un portátil que volcar, y entonces hacer las tres cosas a la vez.

## Sección nueva: Dispositivos

Lo que hay enchufado. No es hardware del equipo sino de alrededor, y por
eso va aparte de Placa base.

| Dato | De dónde | Permisos | AMD | Intel | Fiable |
|---|---|---|---|---|---|
| USB: qué hay, de quién, a qué velocidad y en qué puerto | `/sys/bus/usb/devices/*/{manufacturer,product,speed,idVendor,idProduct,bDeviceClass}` | no | sí: 17 dispositivos | no | sí |
| Audio: tarjetas de sonido | `/proc/asound/cards` | no | sí: cinco | no | sí |
| Cámaras | `/sys/class/video4linux/*/name` | no | sí | no | con matiz |
| Bluetooth: el adaptador | como en Red | no | sí | no | sí |

**USB.** La velocidad sale en Mb/s (12, 480, 5000, 10000). Es la velocidad
negociada, no la versión del dispositivo: un ratón USB 2.0 va a 12 Mb/s y
está bien. La maqueta pone «USB 1.1 · 12 Mb/s» y eso habría que escribirlo
mejor («velocidad completa · 12 Mb/s»). Lo útil es ver un dispositivo rápido
negociando despacio: un disco USB 3 a 480 Mb/s es un cable o un puerto. Los
concentradores raíz no se enseñan como dispositivos; los demás
concentradores, como rama de lo que cuelga de ellos. Cuando el dispositivo
no trae nombre, se busca en `usb.ids` como se hace con `pci.ids`, y ese
nombre se graba en el volcado por lo mismo que el de la gráfica.

**Privacidad.** Aquí hay cosas que identifican: el número de serie de cada
dispositivo USB (`serial`), y el propio inventario (una llave de seguridad,
un micrófono concreto). El serie no se lee nunca. Y `privacidad.py` tiene
que saber de esta sección antes de que exista: `--anonimo` y el informe
enseñan la clase y la velocidad, no el modelo, salvo que se pida. Los
dispositivos Bluetooth emparejados no se proponen: son de otros.

**Cámaras.** Un mismo aparato crea varios nodos (`video1` y `video2` para la
misma cámara) y las cámaras virtuales aparecen igual que las de verdad. Se
agrupa por dispositivo y se dice cuál es virtual cuando no cuelga de un bus.

## Lo que habría que añadir a `volcar_equipo.py`

El volcado guarda lo que el Collector lee, así que al escribir cada
proveedor nuevo sus archivos entran solos. Lo que no entra solo:

1. **Lo que hay que tapar.** `serial` de cada dispositivo USB; las
   direcciones de Bluetooth (`address`); `LoaderDevicePartUUID` y
   `LoaderSystemToken` de efivars; el UUID de la raíz en `/proc/cmdline` si
   se llegara a leer; los nombres de los dispositivos USB si el autor decide
   que identifican. Cada uno, además, entre lo que la comprobación final
   busca byte a byte.
2. **Lo que no es texto.** Las variables de efivars llevan cuatro bytes de
   atributos y van en UTF-16; hoy la herramienta copia `SecureBoot` y habría
   que comprobar que copia igual las `Loader*`. La tabla SMBIOS tipo 9 y el
   registro SMART entero son del ayudante: como todo lo suyo, no se graban
   (lo dice el `manifiesto.json`).
3. **Lo que sale de restar.** La residencia en C-states necesita dos
   lecturas, como RAPL y el uso por hilo. O el volcado guarda dos, o se
   apunta en `sin_grabar` y el test se hace con una foto fabricada por el
   proveedor a partir de dos lecturas reales.
4. **Lo que no es un archivo.** nl80211, si se hace: va por
   `sysroot.a_traves`, como CPUID y los ioctl, para que quede en
   `grabado.json`.
5. **Nombres de fuera.** `usb.ids`, igual que `pci.ids`: el nombre resuelto
   se graba en el volcado para que no dependa de quien ejecuta la suite.
6. **Carpetas vacías.** Varias de estas fuentes son carpetas cuya sola
   existencia es el dato (`/sys/class/iommu/ivhd0`, `/dev/kvm`). Ya se
   apuntan en `vacios`; `/dev/kvm` no es de `/sys` y habría que decidir cómo
   se graba que existe.

Y hacen falta volcados que hoy no hay: **un portátil con wifi y batería**,
**un equipo con LUKS** y **un Intel rehecho** cuando existan los
proveedores, porque el de ahora no trae nada de esto.

## Orden que propongo

Por lo que da frente a lo que cuesta, y dejando para el final lo que no
tiene pieza:

1. **Sistema**: vulnerabilidades, swap y zram, cargador. Son archivos de
   texto, sin permisos, y llenan una página que hoy ocupa un tercio.
2. **Placa base**: enlaces PCIe y controladores. Es lo que más se echa en
   falta frente a HWiNFO, y la mitad ya está en `pciids.py`.
3. **Dispositivos**, con su privacidad resuelta antes.
4. **CPU**: C-states y PL1/PL2.
5. **Cachés**: la latencia en su nivel. Pequeño, pero toca cómo viaja el
   resultado de la medida.
6. **Almacenamiento**: TRIM y, con permisos, la tabla SMART.
7. **Con pieza delante**: wifi, LUKS, secundarias del SPD.

## Lo que no se ha podido comprobar

- **Nada en Intel**, salvo lo que ya trae su volcado (PL1/PL2, el chip de
  sensores, Mesa, el planificador). Todo lo demás se leyó solo en el
  5800X3D.
- **Nada con permisos**: ni la tabla de ranuras ni el SMART entero. No se
  piden permisos desde la sesión de Claude.
- **Wifi y LUKS**: no hay pieza en ninguna de las dos máquinas.
- **Portátiles**: ninguno de los dos equipos lo es.
- Las maquetas del i5-10400 llevan, en lo nuevo, **valores de ejemplo
  marcados como tales**: su volcado no los tiene.
