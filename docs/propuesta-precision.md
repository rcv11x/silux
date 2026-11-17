# Propuesta: que los datos sean correctos en cualquier equipo

Solo propuesta: nada de esto está escrito en la aplicación ni en la suite. Lo
que sí está hecho es la medida: el 17 de noviembre de 2026, en el i5-10400 de
la oficina (Fedora 44, kernel 7.3.3), se ejecutaron las herramientas de
referencia que no piden permisos y se comparó su salida, campo a campo, con
`python3 -m silux.cli --json` y `--sensors`. El 5800X3D se revisó montando el
Collector contra su volcado. Lo que no se pudo comprobar se dice como tal.

El objetivo es el del encargo: que lo que enseña silux sea verdad en cualquier
CPU, placa, RAM y gráfica de Intel y AMD, y que cuando no se sepa si lo es, se
diga. Hoy la única prueba de que un dato está bien es que el autor lo miró en
una de sus dos máquinas.

## 1. Lo que se midió antes de proponer

### Las herramientas, en esta máquina

| Herramienta | Está | Versión | Sin permisos |
|---|---|---|---|
| `lscpu` | sí | util-linux 2.41.6 | completa. Con `LANG=es_ES` escribe `4300,0000`: hay que lanzarla con `LC_ALL=C` |
| `sensors -j` | sí | lm-sensors 3.6.0 | completa |
| `lspci -vv` | sí | pciutils 3.15.0 | **recortada**: en los trece dispositivos sale `Capabilities: <access denied>`. Faltan el enlace PCIe (`LnkCap`, `LnkSta`) y el número de serie del dispositivo |
| `inxi -Fxz` | sí | 3.3.41 | casi completa: el serie de la placa sale `<superuser required>` y no hay memoria por zócalo |
| `dmidecode` | sí | 3.7 | **nada**: `/sys/firmware/dmi/tables/smbios_entry_point: Permission denied`. No se ejecutó con privilegios |
| `decode-dimms` | **no** | — | en Fedora va en `i2c-tools-perl`. Lee `/sys/bus/i2c/devices/*/eeprom`, que aquí es legible sin root con el módulo `ee1004` cargado, pero no se pudo probar |
| `edid-decode` | **no** | — | sí está `di-edid-decode` (libdisplay-info), que escribe en el mismo formato; se usó esa |

También sirvieron `lsblk`, `df`, `udevadm`, `ethtool`, `xrandr`, `mokutil`,
`vulkaninfo` y `glxinfo`. `smartctl`, `nvme` y `turbostat` piden root.

### Lo que coincide en el i5-10400

Comprobado campo a campo, con el valor igual en los dos lados:

- **Procesador** (`lscpu`): cadena de marca, fabricante, familia 6, modelo 165,
  stepping 3, 6 núcleos y 12 hilos, 1 zócalo, VT-x, mínima 800 MHz, máxima
  4300 MHz, base 2900 MHz (`base_frequency`), microcódigo `0x100`
  (`/proc/cpuinfo`).
- **Cachés** (`lscpu -C`): las cuatro, en tamaño, instancias, vías, conjuntos
  y línea. L1d y L1i 6 × 32 KiB de 8 vías y 64 conjuntos; L2 6 × 256 KiB de 4
  vías y 1024; L3 12 MiB de 16 vías y 12288.
- **Banderas**: las 53 de `CpuType.features` están entre las 115 del kernel,
  salvo una (`sgx`, en la tabla de abajo) y cuatro que se llaman distinto
  (`clfsh`/`clflush`, `htt`/`ht`, `sse3`/`pni`, `fma3`/`fma`).
- **Sensores** (`sensors -j`): los siete de `coretemp` con sus límites (84 y
  100 °C), la `acpitz` a 27,8 °C (que silux marca como relleno) y `drivetemp`
  a 26 °C. Los valores se mueven un par de grados entre una orden y la
  siguiente; las etiquetas, los límites y el número de canales son idénticos.
- **Placa** (`/sys/class/dmi/id`, `inxi -M`, `lspci`): fabricante, modelo,
  versión, BIOS 1.80 del 06/08/2023, chipset H510 (el puente ISA `8086:4388`),
  puente raíz, arranque seguro apagado (`mokutil --sb-state`), TPM 2.0.
- **Gráfica** (`lspci -nn`, `vulkaninfo`, `glxinfo`): `8086:9bc8`, subsistema
  `1462:7d23`, revisión 3, driver `i915`, Vulkan 1.4.354 con instancia 1.4.341,
  OpenGL 4.6 y Mesa 26.2.6. El reloj a 0 MHz es lo que dice `gt_act_freq_mhz`
  con la gráfica en reposo.
- **Monitor** (`di-edid-decode`): fabricante `BNQ`, producto 30953, semana 17
  de 2021, EDID 1.3, rango 50–76 Hz, los diez modos de la extensión CTA.
- **Red** (`lspci`, `ethtool`): nombre y fabricante de la tarjeta, driver
  `r8169`, 1000 Mb/s, dúplex completo, ranura.
- **Disco** (`lsblk -b`): tamaño del disco y de las tres particiones al byte,
  sectores 512/512, no rotatorio, planificador, sistema de archivos, y el
  espacio **libre** de cada montaje (`df`, columna «Disp»).
- **Memoria**: `MemTotal` al byte; los dos módulos del SPD suman 16 GiB.

### Lo que ya sabemos que está mal o a medias

«Nuevo» es lo que salió de esta medida y no estaba apuntado en ningún sitio.
La columna de la razón dice quién la tiene, no qué hay que hacer.

| Equipo | Dato | Dice silux | Dice la referencia | Tiene razón | Estado |
|---|---|---|---|---|---|
| i5-10400 | Ocupado de `/boot` (ext4) | 526 778 368 B, 49,1 % | `df`: 456 314 880 B, 44,7 % | `df`. `_ocupacion` resta `f_bavail` y cuenta la reserva del administrador como ocupada; su comentario dice que así cuadra con las demás herramientas, y no cuadra | **nuevo** |
| i5-10400 | Ocupado de `/` (btrfs) | 124,69 GB | `df`: 116,33 GB | `df`, por lo mismo. El libre sí coincide | **nuevo** |
| los dos | Firmware de un disco SATA | «12.7» | `udevadm`, `lsblk`: `SBFA12.7` | la herramienta. `device/rev` son 4 caracteres. En el 5800X3D el MX500 sale «020» y es probable que sea el mismo corte (sin comprobar) | **nuevo** |
| los dos | Modelo de un disco SATA | «KIOXIA-EXCERIA S», «ST2000DM008-2FR1» | `lsblk`: «KIOXIA-EXCERIA SATA SSD» | la herramienta | en pendientes |
| i5-10400 | Aparato del disco en Sensores | «ATA KIOXIA-EXCERIA S» | — | nadie: «ATA» es el `vendor` de sysfs, no un fabricante, y la página de Almacenamiento dice «Kioxia» | **nuevo**, a medias |
| los dos | Diagonal del monitor | 21,7" (480 × 270 mm) | `di-edid-decode`, `xrandr`: 476 × 268 mm, o sea 21,5", lo que anuncia el fabricante | la herramienta. `edid.py` lee los bytes 21 y 22, que van en centímetros; el descriptor detallado lleva los milímetros. En el 5800X3D un 27" sale 26,6" (590 × 330) | **nuevo** |
| los dos | Resolución y refresco de una pantalla | la nativa del EDID | el modo que hay puesto | depende de qué se quiera decir. `_salidas` rellena `Display.width`, `height` y `refresh_hz` con el modo preferido, no con el activo: aquí la salida estaba `disabled` y seguía a 1920 × 1080 y 60 Hz; en el 5800X3D el AORUS de 240 Hz sale a 60. A cuánto va de verdad no lo sabe el modelo | **nuevo**, a medias |
| i5-10400 | Bandera `sgx` | presente | `lscpu`: ausente | los dos. CPUID la declara; el kernel la quita porque el firmware no la activa. Falta distinguir «la tiene» de «está activa» | **nuevo** |
| i5-10400 | Fabricante del monitor | `None` | `BNQ` es BenQ | la referencia. El `pnp.ids` de Fedora no trae `BNQ`; se salva porque el nombre del modelo ya dice «BenQ» | **nuevo**, bajo |
| los dos | Frecuencia de un hilo dormido | 4300,0 MHz clavados en 8 de 12 hilos con el turbo encendido, varios al 0 % de uso | `/proc/cpuinfo`: 4000 MHz en todos; una lectura directa dio `cpuinfo_avg_freq` 4300000 y `scaling_cur_freq` 4076156 en el mismo hilo | sin decidir. En el volcado del 5800X3D cinco de dieciséis hilos dan 1 755 355 kHz idénticos en las dos fuentes. Parece el valor que devuelve el kernel cuando no hay muestra reciente, no una medida. Con el turbo apagado no se repitió (0 de 240 lecturas) | **nuevo**, falta medirlo bien |
| los dos | Bytes de red en Sensores | «869.0 MB», categoría `cat.memory` | 911 089 631 B son 911 MB | la cuenta decimal, que es la de la página de Red | en pendientes (`derived.py`) |
| 5800X3D | Clave de sensor repetida | dos sensores `nvme/temp1`, uno por disco | — | es el fallo de `hwmon.py` de pendientes, y en este equipo ocurre: mín/máx y CSV se mezclan | en pendientes, ahora con caso |
| 5800X3D | Voltajes de `it8688` | «Tensión 1: 1,968 V», «Tensión 2: 2,028 V», con límites 0,0 y 3,06 | — | a medias. Son la tensión en la patilla del chip, antes del divisor de la placa, y 3,06 V es el fondo de escala del registro, no un umbral. Qué raíl es cada una no se puede saber sin la pieza | **nuevo** |
| 5800X3D | Sondas de la placa por duplicado | seis de `it8688` y seis de `gigabyte_wmi`, doce filas sin nombre | — | a medias: son casi con seguridad las mismas seis sondas (42/42, 35/35, 38/37…) | **nuevo**, sin la pieza |
| 5800X3D | Ventiladores 3, 4 y 5 | 0 RPM | — | a medias: una cabecera sin ventilador se enseña como un ventilador parado | **nuevo** |
| 5800X3D | Particiones sin montar | sin sistema de archivos (`sda1`, `sdc1`) | `lsblk -f` lo sabría | la herramienta: silux solo lo lee de `/proc/mounts` | **nuevo**, a medias |
| 5800X3D | Niveles de reloj de la gráfica | dos niveles, ninguno activo, y el reloj (454 MHz) por debajo del más bajo (500) | — | sin contrastar | **nuevo**, sin la pieza |
| 5800X3D | BCLK | 100 029 412 Hz | — | es una división (3401 MHz entre 34), no una lectura; se enseña con la misma seguridad que un dato medido | a medias, pide procedencia |
| 5800X3D | Memoria sin permisos | ni módulos ni SPD: el firmware se reserva el SMBus | — | correcto, pero la página se queda en el total | conocido |
| 5800X3D | Memoria con permisos | «DDR4-…» en vez de «Desconocido» | `sudo dmidecode -t 17` | arreglado con una tabla de prueba; **no visto en la pieza** | en curso |
| 5800X3D | Chipset | «AMD X570», del nombre de la placa | — | arreglado; la lista `_CHIPSETS_AMD` es cerrada y solo se ha visto con esta placa | en pendientes |
| 5800X3D | Techo del silicio con `acpi-cpufreq` | sin dato y con aviso | — | **sin comprobar**: falta el arranque con `amd_pstate=disable` | en curso |
| 5800X3D | `acpitz` a 16,8 °C | apagadas y marcadas | — | arreglado; falta ver en la pieza que no se mueven nunca | en curso |
| 5800X3D | Temperatura de los SATA | «—» con explicación | `smartctl -A` | falta `drivetemp` o permisos; con permisos no se ha visto | en curso |
| i5-10400 | XMP de DDR4 | sin perfiles | — | correcto aquí (los módulos no lo traen); F-A2 sigue sin un volcado con XMP | en pendientes |
| los dos | Proceso de fabricación | «14++ nm» en Intel, «TSMC N7FF» en AMD | — | dos formatos para el mismo campo | **nuevo**, bajo |

Dos cosas de la comparación que no son fallos pero que harán fallar un test
escrito con prisa:

- `CpuType.model` es el modelo base de CPUID (5); lo que `lscpu` llama
  «Model» es `disp_model` (165). Lo mismo con `family` y `disp_family` en AMD
  (15 y 25).
- `inxi` dice «cpu: 38.0 C» donde `sensors` da 47 °C de paquete: coge un
  núcleo. Y abrevia el fabricante de la BIOS. Aquí la que se equivoca es la
  herramienta, y por eso hace falta la lista de excepciones del apartado 3.

Tres datos del volcado parecen fallos y son artefactos de volcar:
`system.processes` vale 1, el consumo no sale (un contador leído una vez) y
todas las interfaces comparten dirección. Las invariantes los tienen que
conocer.

## 2. Las salidas de las herramientas, dentro del volcado

`volcar_equipo.py` guardaría, en una carpeta `herramientas/` del volcado, lo
que dice cada herramienta en el mismo momento en que el Collector lee. Cinco
decisiones, cada una por algo que se midió:

1. **El volcado no depende de ninguna.** Si `shutil.which` no la encuentra, se
   apunta en `manifiesto.json` (`"herramientas": {"edid-decode": null}`) y se
   sigue. Aquí faltan dos de siete; en un equipo ajeno faltarán otras.
2. **Se guarda la versión de cada una** (`lscpu --version`, `sensors -v`…).
   El formato de `lscpu -J` y los campos de `inxi` cambian entre versiones, y
   un test que deja de casar tiene que poder decir por qué.
3. **Siempre con `LC_ALL=C`.** Con el idioma del autor `lscpu` escribe comas
   decimales y `df` traduce las cabeceras.
4. **En el formato más estable que tenga**: `lscpu -J`, `lscpu -B -C -J` (las
   cachés en bytes exactos, sin «1,5M»), `sensors -j`, `lspci -vv -nn`,
   `lsblk -b -J`. `inxi` solo tiene texto: es la menos fiable para comparar y
   la más útil para que un humano lea el equipo de un vistazo.
5. **Las que leen un archivo se ejecutan contra el archivo ya anonimizado.**
   `edid-decode` vuelca el EDID en hexadecimal además de decodificarlo, serie
   incluido; si se le da el `edid` del volcado, que ya pasó por
   `_edid_sin_serie`, no hay nada que tapar. `decode-dimms` admite volcados
   hexadecimales con `-x` (sin comprobar aquí: no está instalada) y podría
   hacerse igual con la `eeprom` limpia.

### Qué hay que tapar en cada una

Regla dura del proyecto: nada que identifique a la máquina se publica. Todas
las salidas pasan por `_Anonimizador._cambiar_texto` y por la búsqueda final
byte a byte de `comprobar()`, que ya recorre cada archivo del volcado. Pero
esa búsqueda solo encuentra lo que sabe buscar (F-M30), así que además:

| Salida | Pide root | Lleva | Qué se hace |
|---|---|---|---|
| `lscpu -J` | no | nada que identifique | tal cual |
| `sensors -j` | no | nombres de chip con su dirección; ningún serie | tal cual |
| `lspci -vv -nn` | no, recortada | sin root no hay `Capabilities`, y por tanto no sale `Device Serial Number`, que en una tarjeta de red **se deriva de la MAC** | se guarda la recortada. De la completa se borraría esa línea |
| `inxi` | no | `-z` tapa MAC, IP y series, pero **no los nombres de interfaz**: aquí dejó en claro una interfaz que lleva el nombre del equipo. Lista además todos los puentes de Docker, los puntos de montaje, el intérprete y el número de paquetes | solo las secciones de hardware (`inxi -c0 -z -x -M -C -G -N -D -s`), sin `-i`, `-p`, `-l`, `-u`, `-S` ni `-I`; los nombres de interfaz, por `privacidad.de_sistema` |
| `edid-decode` | no | `Serial Number`, `Display Product Serial Number` y el volcado hexadecimal | contra el EDID limpio, punto 5 |
| `lsblk -b -J` | no | con `-o` por defecto, nada; con `SERIAL`, `WWN`, `UUID`, `LABEL` o `MOUNTPOINT`, sí | lista de columnas fija: `NAME,MODEL,SIZE,ROTA,TRAN,PHY-SEC,LOG-SEC,REV,FSTYPE` |
| `dmidecode` | **sí** | `Serial Number` (sistema, placa, chasis, procesador, cada módulo, batería), `UUID`, `Asset Tag`, `SKU Number` | no entra en un volcado sin permisos |
| `decode-dimms` | módulo `ee1004` o `spd5118`; a veces root | `Assembly Serial Number` | contra la `eeprom` limpia, o no entra |
| `lspci -vv` completa, `smartctl -x`, `nvme id-ctrl` | **sí** | series, WWN, `Device Serial Number` | no entran |

**Las que piden root no entran en un volcado «sin permisos»**, que es lo que
dice hoy el manifiesto y lo que abre la mayoría de la gente. Si el dueño las
quiere aportar, las genera él con `sudo` y las adjunta
(`--adjuntar dmidecode=ARCHIVO`): la herramienta no eleva nada, las filtra por
lista blanca de tipos (`dmidecode -t 0,2,4,16,17`, nunca el tipo 1, que lleva
el UUID), borra las líneas de serie, UUID y etiqueta de inventario, y las deja
en `herramientas/con-permisos/`, con el manifiesto diciendo quién las aportó.
Que el ayudante privilegiado grabe lo que lee es otra cosa y va en la fase F.

Como al añadir esto hay que volver a volcar los tres equipos, se aprovecha
para numerar las direcciones físicas (pendiente de la tercera tanda).

## 3. La comparación campo a campo

Un test nuevo, `tests/test_contraste.py`, recorre cada volcado que tenga
`herramientas/` y compara. Los analizadores de cada formato viven en `tests/`,
y la tabla de correspondencias es un dato, no cuarenta tests a mano.

| Campo de `silux/model.py` | Referencia | Tolerancia |
|---|---|---|
| `CpuType.brand` | `lscpu -J` «Model name» | exacto |
| `CpuType.vendor_id` | «Vendor ID» | exacto |
| `CpuType.disp_family`, `disp_model`, `stepping` | «CPU family», «Model», «Stepping» | exacto |
| `CpuInfo.sockets`, `total_cores`, `total_threads` | «Socket(s)», «Core(s) per socket» × zócalos, «CPU(s)» | exacto. En un híbrido «Core(s) per socket» no distingue P de E: se compara la suma |
| `CpuType.smt` | «Thread(s) per core» > 1 | exacto |
| `Clocks.min_hz`, `max_hz` | «CPU min MHz», «CPU max MHz» | ±1 MHz |
| `CpuType.virtualization` | «Virtualization» | exacto |
| `CpuType.features` | «Flags», con una tabla de alias | cada bandera de silux está en el kernel, salvo las de la lista de excepciones; al revés no (el kernel inventa banderas) |
| `Cache.size_bytes`, `instances` | `lscpu -B -C -J`: `one-size`, `all-size` ÷ `one-size` | exacto |
| `Cache.ways`, `sets`, `line_bytes` | `ways`, `sets`, `coherency-size` | exacto |
| `LogicalCpu.core_id`, `package_id` | `lscpu -e=CPU,CORE,SOCKET -J` | exacto |
| `Sensor.value` (temperatura) | `sensors -j`: `tempN_input` del mismo chip y canal | ±5 °C: son dos lecturas con un segundo de por medio |
| `Sensor.high`, `critical`, `low` | `tempN_max`, `tempN_crit`, `tempN_min` | exacto, si `estimated_limits` es falso; si es verdadero, la referencia no debe traerlo |
| `Sensor.label` | la clave del canal en `sensors -j` | exacto si `unnamed` es falso |
| número de sensores por chip y tipo | número de canales `*_input` del chip | exacto |
| `Sensor.value` (ventilador, voltaje) | `fanN_input`, `inN_input` | ±10 %, ±0,05 V |
| `Gpu.vendor_id`, `device_id`, `subsystem_*_id`, `revision` | `lspci -nn -vv`: `[vvvv:dddd]`, `Subsystem`, `(rev xx)` | exacto |
| `Gpu.driver` | «Kernel driver in use» | exacto |
| `Gpu.name`, `codename` | el nombre de `lspci` | contenido: `lspci` escribe «CometLake-S GT2 [UHD Graphics 630]» y silux lo parte en dos campos |
| `NetworkInterface.model`, `vendor`, `driver` | `lspci -vv` de su `pci_slot` | exacto |
| `PcieLink.*` (gráfica y NVMe) | `LnkCap`, `LnkSta` | exacto, **solo con la `lspci` completa** |
| `Board.chipset_full`, `host_bridge` | el puente ISA (clase 0601) y el `00:00.0` | exacto |
| `Board.vendor`, `name`, `bios_version`, `bios_date` | `dmidecode -t 0,2` | exacto, solo con permisos |
| `MemoryModule.size_bytes`, `type`, `speed_mts`, `configured_mts`, `manufacturer`, `part_number`, `locator` | `dmidecode -t 17`: «Size», «Type», «Speed», «Configured Memory Speed», «Manufacturer», «Part Number», «Locator» | exacto; la velocidad, ±1 MT/s (2666 y 2667 son el mismo grado) |
| `MemoryArray.slots`, `max_capacity_bytes` | `dmidecode -t 16` | exacto |
| `SpdInfo.capacity_bytes`, `ranks`, `part_number`, `jedec.cl`/`trcd`/`trp`/`tras` | `decode-dimms`: «Size», «Ranks», «Part Number», «tCL-tRCD-tRP-tRAS» | exacto |
| `SpdInfo.rated_mts`, perfiles XMP | «Maximum module speed», «XMP Profile» | exacto: es la comprobación que le falta a F-A2 |
| `Edid.manufacturer_id`, `product_code`, `week`, `year`, `version` | `edid-decode`: «Manufacturer», «Model», «Made in», «EDID Structure Version» | exacto |
| `Edid.model` | «Display Product Name» | exacto |
| `Edid.width_mm`, `height_mm` | los milímetros del primer DTD | ±5 mm: hoy falla por 4 y 2 mm, y la diagonal se va 0,2" |
| `Edid.refresh_min_hz`, `refresh_max_hz` | «Monitor ranges» | exacto |
| `Edid.modes` | los modos de «Video Data Block» y los DTD | el mismo conjunto de (ancho, alto, Hz redondeado a 0,01) |
| `Disk.size_bytes`, `rotational`, `transport`, `logical_sector`, `physical_sector` | `lsblk -b -J` | exacto |
| `Disk.model`, `firmware` | `MODEL`, `REV` | exacto: hoy falla en los SATA |
| `Partition.size_bytes`, `filesystem` | `lsblk -b -J` | exacto |

`inxi` no entra en la tabla como juez: se guarda para leer, y de ella solo se
compara lo que no tiene otra fuente sin permisos.

### Cuando la que se equivoca es la herramienta

Un archivo `tests/fixtures/equipos/excepciones.json`, con una entrada por
desacuerdo aceptado:

```json
{"campo": "cpu.types.0.features", "valor": "sgx", "herramienta": "lscpu",
 "equipos": ["i5-10400", "i5-10400-turbo"],
 "motivo": "CPUID 7.EBX[2] la declara; el kernel la retira si el firmware no la activa",
 "razon": "las dos"}
```

Tres reglas para que no se convierta en un cubo donde tirar lo que molesta:

- **Nunca silenciosa**: el test imprime al terminar cuántas excepciones aplicó
  y a qué equipos; y una excepción que ya no hace falta (el desacuerdo
  desapareció) hace fallar el test, para que se borre.
- **Por equipo y por valor**, no por campo: «`sgx` en el i5-10400», no «las
  banderas no se comparan».
- **Con motivo y con quién tiene razón** (`silux`, `herramienta`, `las dos`).
  Si la razón es de la herramienta, no es una excepción: es un fallo, y va a
  `docs/pendientes.md` con su test marcado como fallo esperado.

## 4. Invariantes para todos los volcados

`test_equipos` solo comprueba lo que vale para cualquier equipo, y eso son
estas. Cada una dice qué fallo real habría cazado. Las que ya existen están
marcadas; el resto se ve fallar antes de darla por buena, contra el commit
anterior al arreglo que cita.

**Se pueden escribir ya contra los tres volcados:**

| # | Invariante | Fallo que caza |
|---|---|---|
| 1 | `min_hz ≤ max_hz`, `base_hz ≤ max_turbo_hz`, cada hilo ≤ techo × 1,02 (existe) | la gráfica de frecuencia con muestras por encima del eje (`3f6c1a6`) |
| 2 | relojes en rango físico: `min_hz` ≥ 100 MHz, `max_turbo_hz` ≤ 7 GHz, `bus_hz` a ±2 % de 100 MHz o vacío | el techo de 4,96 GHz que salía del ranking de núcleos (`35756d1`) solo en parte: dentro del rango no lo ve |
| 3 | ninguna temperatura fuera de −30…125 °C (existe) | un canal sin sonda a −128 o 127 °C |
| 4 | una temperatura cuyo valor está en `VALORES_DE_RELLENO`, o repetida al decimal en tres canales del mismo chip sin límites, lleva `placeholder` | las tres `acpitz` a 16,8 °C (`f310582`) |
| 5 | las claves de `snapshot.sensors` son únicas | dos discos iguales que se pisan. **Hoy falla en `5800x3d`**: `nvme/temp1` sale dos veces |
| 6 | cada caché cumple `size_bytes == ways × sets × line_bytes`, y L1 ≤ L2 ≤ L3 | una hoja de CPUID mal decodificada (4 en Intel, 0x8000001D en AMD). Los tres volcados la cumplen |
| 7 | los `cpus` de `cpu.types` reparten los hilos sin solaparse ni dejar ninguno; la suma de núcleos y de hilos da los totales (en parte existe) | un híbrido mal repartido entre P y E |
| 8 | `Board.chipset` no es el nombre de un dispositivo PCI: no casa con `Bridge`, `Controller`, `Root Complex`, `SMBus` ni `Device xxxx` | «FCH LPC Bridge» como chipset (`013c098`) |
| 9 | ningún `Gpu.name`, `NetworkInterface.model` ni `Disk.model` es «Device xxxx», un nombre de fabricante a secas o una clase PCI; dos gráficas con distinto `device_id` no comparten nombre | una Navi 33 llamada «Radeon 780M» (F-M17); el nombre del `pci.ids` de quien ejecuta |
| 10 | ningún texto del modelo es un relleno del firmware («Unknown», «Default string», «To be filled by O.E.M.», «Not Specified», una ristra de ceros) | «31.3 GB · Desconocido» (`3e36f9b`), pero en el modelo y no solo en pantalla, que es lo que ven el informe y el CLI |
| 11 | un zócalo vacío no tiene tipo, velocidad ni fabricante; uno ocupado tiene tamaño | el mismo «Desconocido», por su causa |
| 12 | la memoria instalada (módulos, o SPD si no hay módulos) es ≥ `MemTotal` y lo supera en menos de un 10 % | módulos cruzados o contados dos veces (F-M16). Medido aquí: 16 GiB frente a 15,43, un 3,6 % |
| 13 | `package_w` nunca es 0,0 y sin dos lecturas no hay vatios (existe) | los 0 W de un contador parado (`3bf54ea`) |
| 14 | en un AMD, `Power.core_w` está vacío | «núcleos 3,7 W» con el paquete a 64 W (`7ee762b`) |
| 15 | un límite de sensor no es el fondo de escala de su registro (`low` 0,0 con `high` 3,06 o 6,12 V; mínimo y máximo iguales a 127 °C) | umbrales de `it8688` y de `nct6798` que no son umbrales. **Hoy falla en `5800x3d`** |
| 16 | `low < high ≤ critical` cuando están; ventilador 0 o entre 150 y 20 000 RPM; uso entre 0 y 100; voltaje entre 0 y 20 V | un driver que escala mal |
| 17 | pantalla: `enabled` implica `connected`; diagonal entre 5 y 100"; `refresh_hz` dentro del rango del EDID; suma de control (existe) | un EDID a medio leer |
| 18 | disco: particiones ≤ disco (existe); sectores potencia de dos y lógico ≤ físico; `rotational` implica `kind` HDD y `percentage_used` vacío; un NVMe tiene `link` | la vida al 200 % de un disco mecánico (F-M18) |
| 19 | red: `speed_mbps` positivo o vacío; `duplex` es `full`, `half` o vacío; una interfaz con `pci_slot` tiene `model` y `driver` | «-1 Mb/s» sin cable. **Hoy falla en los tres**: `duplex` vale `unknown` en las interfaces caídas (no llega a la pantalla) |
| 20 | el mismo dato en dos sitios de la foto: `cpu.temperature_c` y su sensor, `Gpu.temp_c` y `amdgpu/temp1`, `Disk.temp_c` y su `hwmon` (±0,1), cada hilo y su `clock/cpuN` (existe) | Inicio y CPU con temperaturas distintas (`6c83db3`) |
| 21 | cada `Note.path` señala un campo que de verdad está vacío, y cada campo que falta por permisos tiene su nota | un aviso que sigue pidiendo permisos después de darlos; un hueco sin explicación (regla 5) |
| 22 | `bios_date` es una fecha entre 1990 y hoy; el chipset es del mismo fabricante que el procesador | una búsqueda cruzada en la tabla de chipsets |

**Piden un dato que el volcado no guarda:**

| # | Invariante | Qué falta |
|---|---|---|
| 23 | temperaturas no clavadas: entre dos lecturas separadas, un sensor que no es de relleno cambia o lo hacen sus vecinos | una segunda lectura de cada `*_input`, unos segundos después (`muestras/`). Con ella `VALORES_DE_RELLENO` deja de ser una lista cerrada de tres números |
| 24 | `core_w ≤ package_w`, y el paquete por debajo del doble de `limit_short_w` | dos lecturas de `energy_uj` con su intervalo: hoy el volcado no da vatios |
| 25 | la frecuencia de un hilo es una medida: un hilo al 0 % de uso no está al techo exacto | el uso de cada hilo (dos lecturas de `/proc/stat`). Es la fila «hilo dormido» de la tabla |
| 26 | `system.processes > 0` | el número grabado: hoy sale 1 por cómo se copia `/proc` |
| 27 | batería: porcentaje entre 0 y 100, `full_wh ≤ design_wh × 1,1`, voltaje entre 2 y 25 V | un volcado de portátil: no hay ninguno |

La segunda lectura sería de unos pocos archivos dentro del mismo volcado
(`*_input` de `hwmon`, `energy_uj` y `/proc/stat`), no un segundo volcado.

## 5. Un informe de referencia por equipo

Las invariantes dicen que un dato es posible; el contraste, que coincide con
otra herramienta. Ninguna de las dos dice que sea verdad: `lscpu` y silux
pueden leer el mismo archivo equivocado. Eso solo lo dice el dueño con la
pieza delante.

- En cada volcado, `referencia.json`: la foto que da el Collector, pasada por
  `dataclasses.asdict`, sin lo que depende del momento de montarla
  (`monotonic_ns`, `boot_time`). Y `referencia.md`, el informe de
  `report.build(foto, anonymous=True)`, que es lo que se lee.
- Un test compara la foto de hoy con `referencia.json`. Si un cambio de código
  mueve un dato, el test lo enseña campo a campo: quien hace el cambio decide
  si es un arreglo (y regenera) o una regresión.
- **La revisión se apunta por contenido, no por fecha**: el manifiesto guarda
  `"revisado": {"por": …, "fecha": …, "con": "BIOS, etiqueta de los módulos,
  caja de la gráfica", "suma": <sha256 de referencia.json>}`. Si la referencia
  cambia, la suma deja de casar y el equipo pasa de «revisado» a «volcado»
  hasta que su dueño mire lo que cambió (`tools/revisar_referencia.py
  NOMBRE` le enseñaría solo la diferencia). Es la regla del proyecto: lo que
  depende de que alguien se acuerde de subir un número no es una comprobación.
  Lo que el dueño no puede confirmar va en `"sin_confirmar"`.

**Esto necesita al autor una vez por equipo**: leer `referencia.md` del
i5-10400 y del 5800X3D con la máquina delante, contra la BIOS y las etiquetas,
y apuntar lo que no cuadre. La tabla del apartado 1 dice por dónde empezar.

## 6. Procedencia visible

Cada dato dice de dónde sale: la ruta o la fuente, y el driver. Sirve a quien
desconfía y, sobre todo, a quien arregla: «BCLK 100,03 MHz» y «Tctl 47,6 °C»
se enseñan hoy igual, y uno es una división y el otro una lectura.

### Tres formas de hacerlo

**A. Un campo de procedencia junto a cada campo del modelo.** Duplica las
dataclasses y engorda cada foto, que se crea una vez por segundo. Descartada.

**B. Una tabla aparte en la foto, por ruta de campo.** `Snapshot.sources`, una
tupla de `Source(path, kind, where, driver, provider)`:

- `path` usa la misma gramática que `Note.path` (`cpu.clocks.bus_hz`,
  `gpus.0.temp_c`), con comodín para lo que se repite
  (`cpu.logical.*.freq_hz` es una entrada, no dieciséis);
- `kind` es un enumerado: `SYSFS`, `PROCFS`, `CPUID`, `IOCTL`, `MSR`, `SMBIOS`,
  `SPD`, `EDID`, `DATABASE` (sale de `db/`), `DERIVED` (se calcula de otros) y
  `ESTIMATED`;
- `where` es la ruta o el registro, sin formatear (`cpufreq/cpuinfo_avg_freq`,
  `0x16`, `0x198`), y `driver` el módulo del kernel si lo hay.

La rellena el proveedor con `draft.source(...)`, igual que hoy `draft.note`,
porque es el único que sabe qué fuente eligió. La tabla es casi estática: se
construye una vez y la misma tupla se reutiliza entre fotos mientras no cambie
una elección.

**C. Una tabla declarativa fuera de la foto** (`db/sources.json`), escrita a
mano, de la que saldría también `docs/comprobar.md`. Es la más barata y miente
justo donde la procedencia importa: cuando un proveedor cae a su segunda
fuente (`cpuinfo_avg_freq` → `scaling_cur_freq`; CPUID 0x16 → CPPC → la cadena
de marca; Tdie o Tctl; el EDID o `modes`).

**Se recomienda B**, con `docs/comprobar.md` como su versión para personas y
un test que vigila que no se separen: cada `where` que aparece en la foto de
un volcado tiene su fila en la página.

### Cómo respeta las reglas

- **Regla 1**: `Source` guarda símbolos y rutas, no frases. El texto lo
  compone `render.source(source)` al pintar: «Leído de
  `/sys/…/cpufreq/cpuinfo_avg_freq` · driver intel_pstate», «Calculado: base
  ÷ multiplicador», «Estimado: el chip no declara límites».
- **Los sensores no necesitan entrada propia**: `Sensor.chip` y `Sensor.key`
  ya son su procedencia si la clave incluye el nodo `hwmon`, que es además el
  arreglo del pendiente de las claves repetidas.
- **Memoria y F-M9**: no se añade ningún widget ni se llama a `setToolTip` en
  las 1299 etiquetas en cada repintado. Cada etiqueta de valor lleva su ruta
  de campo como propiedad, puesta una vez al construirse (regla 6), y el texto
  se compone cuando llega el evento `QEvent.ToolTip`, para esa etiqueta sola.
  El coste es una cadena corta por etiqueta: se mide antes y después, y si
  pasa de 1 MB no se hace así.
- **Sin llenar la pantalla**: la procedencia es la última línea del tooltip
  que ya exista (la explicación o el candado van primero), en texto plano.
- **Privacidad**: una ruta puede llevar el nombre de una interfaz o un punto
  de montaje. `privacidad.anonimizar` tiene que pasar por `sources`, y lo que
  viene de un volcado, por `sysroot.fuera`.

### En el informe

Una sección al final de `report.build`, «Procedencia de los datos», con una
fila por entrada (unas cuarenta gracias a los comodines): campo, fuente,
driver. No va dato a dato para que el informe se siga leyendo. Ojo: en
`report.py` ya hay una `_procedencia()` que dice si se ejecuta desde un
AppImage; hay que renombrar una de las dos.

## 7. «Contribuir mi equipo»

### El botón

En Ajustes, y al final del aviso del apartado 8. Hace tres cosas y ninguna
sale de la máquina sin que el usuario lo haga a mano:

1. Vuelca el equipo, sin permisos, en un `.tar.gz` en la carpeta que elija. El
   volcado parchea `builtins.open` para apuntar lo que lee el Collector: no
   puede correr en el proceso de la interfaz. Va en un hijo
   (`python3 -m silux.cli --dump DESTINO`), como las APIs de la gráfica
   (regla 8), y la espera, fuera del hilo de la interfaz (regla 4).
2. Enseña qué lleva y qué se tapó, con las dos comprobaciones de privacidad
   pasadas; si alguna falla, no deja nada escrito, como hoy.
3. Abre el navegador en la plantilla de issue. Adjuntar el archivo es cosa del
   usuario. silux no sube nada ni abre ninguna conexión.

Para esto el núcleo de `tools/volcar_equipo.py` tiene que vivir en el paquete
(`silux/dump.py`), con la herramienta como envoltorio: el AppImage no lleva
`tools/`. Los volcados pesan entre 3,1 y 5,4 MB sin comprimir. Uno ajeno no
entra en `tests/fixtures/equipos/` tal cual: el autor lo monta y le pasa las
comprobaciones de privacidad y las invariantes de hoy, porque la herramienta
de quien lo manda puede ser más vieja que la última regla de privacidad.

### La plantilla de issue

Para `.github/ISSUE_TEMPLATE/contribuir-equipo.yml`:

```yaml
name: Contribuir mi equipo
description: Mandar el volcado de un equipo para que silux se compruebe contra él
title: "Equipo: <procesador> · <placa> · <gráfica>"
labels: ["equipo"]
body:
  - type: markdown
    attributes:
      value: |
        Un volcado es una copia de lo que silux lee de `/sys`, `/proc` y `/etc`, sin
        permisos de administrador y con lo que identifica a tu máquina sustituido:
        nombre del equipo, direcciones MAC e IP, números de serie, UUID, interfaces
        con nombre propio y puntos de montaje. Se genera con el botón «Contribuir mi
        equipo» de Ajustes, o con `python3 -m silux.cli --dump mi-equipo.tar.gz`.
  - type: input
    id: version
    attributes:
      label: Versión de silux (`python3 -m silux.cli --version`)
    validations:
      required: true
  - type: input
    id: cpu
    attributes:
      label: Procesador
    validations:
      required: true
  - type: input
    id: placa
    attributes:
      label: Placa base o modelo del portátil
    validations:
      required: true
  - type: input
    id: memoria
    attributes:
      label: Memoria
      description: Cuántos módulos, de cuánto, y si XMP o EXPO está activado en la BIOS.
    validations:
      required: true
  - type: input
    id: grafica
    attributes:
      label: Gráfica y driver
    validations:
      required: true
  - type: input
    id: sistema
    attributes:
      label: Distribución y kernel
    validations:
      required: true
  - type: textarea
    id: volcado
    attributes:
      label: El volcado
      description: Arrastra aquí el archivo `.tar.gz`. Se hace sin dar permisos a silux.
    validations:
      required: true
  - type: textarea
    id: desacuerdos
    attributes:
      label: Lo que silux dice mal o no dice
      description: |
        Una línea por dato: qué enseña silux, qué es de verdad y cómo lo sabes
        (la BIOS, la etiqueta de la pieza, otra herramienta). Los comandos para
        comprobar cada dato están en docs/comprobar.md. Si todo cuadra, dilo:
        también es un resultado.
      placeholder: "Memoria: silux dice DDR4-3200 y la BIOS, con XMP, 3600."
  - type: textarea
    id: con-permisos
    attributes:
      label: Salidas que piden administrador (opcional)
      description: |
        Solo si quieres. Antes de pegarlas, borra las líneas `Serial Number`,
        `UUID` y `Asset Tag`.
        `sudo dmidecode -t 0,2,4,16,17` · `sudo decode-dimms` · `sudo lspci -vv`
      render: text
  - type: checkboxes
    id: acuerdos
    attributes:
      label: Antes de enviar
      options:
        - label: He abierto el archivo y no he visto nada mío que no quiera publicar.
          required: true
        - label: Acepto que el volcado se añada al repositorio, que es público, bajo su licencia (GPL-3.0).
          required: true
```

### El hardware que más falta

Hoy hay dos equipos volcados, los dos sobremesas con DDR4. De lo demás hay
capturas ajenas (GTX 1660 Ti, RTX 3050 Mobile, Radeon 740M, ThinkCentre
M80q), que la suite no puede montar. Por orden de cuánto código estrenan:

1. **Intel híbrido** (12.ª a 14.ª generación, Core Ultra). `cpu.types` es una
   lista por ellos y ninguno ha pasado por aquí: núcleos P y E, cachés y
   relojes distintos, `/sys/devices/cpu_core` y `cpu_atom`.
2. **AM5 con DDR5** (Ryzen 7000 y 9000). El SPD de DDR5 por `spd5118`, EXPO,
   la integrada de un Ryzen de sobremesa junto a una dedicada (F-M17) y
   `amd_umc`, que está sin escribir a propósito por falta de pieza.
3. **Un portátil, de Intel y de AMD.** No hay ningún volcado con batería: la
   página entera y la invariante 27 están sin contrastar. Además, `acpitz` de
   verdad, el controlador embebido y dos gráficas.
4. **NVIDIA con el driver propietario.** Está validada con capturas, pero NVML
   no se graba en los volcados (lo dice el manifiesto): antes hay que pasarla
   por `sysroot.a_traves`.
5. **Intel Arc y el driver `xe`** (DG2, Battlemage, la integrada de Lunar
   Lake). Lo de Intel solo se ha visto en una UHD 630 con `i915`.
6. **Una APU de AMD** (5600G, 780M, 890M): `gpu_metrics` 2.x, de la que solo
   se ha visto la 2.1 en una captura.
7. **Placas con `nct67xx`** (ASUS, ASRock, MSI) y con `asus-ec-sensors`. El
   único chip de placa volcado es un `it8688` de Gigabyte; la MSI de la
   oficina no tiene driver cargado. Es donde se decide si los voltajes y las
   sondas sin nombre tienen arreglo.
8. **Ryzen con Tdie y Tctl** (1700X, 1800X, Threadripper de 1.ª y 2.ª
   generación): `60e354e` se escribió por la documentación del kernel.
9. **DDR4 con XMP activado y el SPD legible**: es lo que pide F-A2.
10. **Dos discos iguales, un mecánico de WD, dos gráficas del mismo
    fabricante**: las claves repetidas y F-M18.
11. **Intel anterior a Skylake y AMD anterior a Zen** (sin CPUID 0x16 ni
    CPPC), **dos zócalos, ECC y un ARM**, que nunca se ha ejecutado en uno.

Y uno del autor: el 5800X3D arrancado con `amd_pstate=disable`.

## 8. El aviso de familia sin volcado validado

**Qué es una familia.** Tres, independientes, y cada una con la granularidad
a la que cambia el código que la lee:

| Familia | Clave | Ejemplos |
|---|---|---|
| procesador | fabricante y microarquitectura, la que ya resuelve `db/families.json` | `intel/comet-lake`, `amd/zen3` |
| chip de sensores | el nombre del chip sin su dirección (`render.chip_name`), solo los de placa | `it8688`, `nct6798`; `coretemp` y `k10temp` van con el procesador |
| gráfica | driver y generación | `i915/gen9.5`, `amdgpu/navi4x`, `nvidia`, `xe` |

**Dónde vive la lista.** En `silux/db/validated.json`, **generada**
(`tools/gen_validated.py`) a partir de los manifiestos de
`tests/fixtures/equipos/`, como `cpu_ids.json`. Un test compara el archivo con
lo que saldría de generarlo: no depende de que alguien se acuerde de apuntar
un equipo. Cada familia tiene dos grados: `volcado` (hay un equipo en la
suite) y `revisado` (además su referencia tiene la suma vigente, apartado 5).

**Qué dice y dónde.** Una línea gris al pie de la página afectada (CPU,
Sensores o Gráficos), con las demás notas de la página; no en Inicio, no en
ámbar, sin icono de alerta:

> Ningún equipo con este chip de sensores (nct6798) se ha comprobado todavía
> con silux. Los datos pueden estar bien. Si ves algo que no cuadra, o si
> cuadra todo, nos ayuda saberlo: **Contribuir mi equipo**.

**Cómo no convertirlo en ruido:**

- no es una `Note` con `Need`: no cuenta en «Faltan N datos» ni en el aviso de
  permisos, que es para lo que tiene arreglo en el momento;
- una línea por página como mucho, y otra en el diagnóstico del informe;
- se cierra para siempre, por familia (`validation_notice_dismissed` en
  `settings.json`), y no vuelve salvo que cambie el hardware;
- la lista viaja con el programa: un equipo validado ayer no lo sabe el
  AppImage de hace un mes, y silux no consulta nada por red;
- no sale en un volcado montado con `SILUX_SYSROOT` ni con `--anonimo`.

Hoy saldría en casi cualquier equipo: por eso mismo no puede molestar.

## 9. Por fases

Una rama por fase; cada paso, un commit con su test visto fallar.

| Fase | Qué | Toca privilegios | Necesita al autor |
|---|---|---|---|
| A | Las invariantes 1 a 22 en `test_equipos`. Las tres que hoy fallan (5, 15 y 19) entran con su arreglo o como fallo esperado con su línea en pendientes | no | decidir qué se arregla ya |
| B | `volcar_equipo.py` guarda las herramientas sin root, sus versiones y la segunda lectura; se vuelven a volcar los tres equipos (y de paso las MAC numeradas); `test_contraste.py` y `excepciones.json` | no | volcar el 5800X3D en casa |
| C | `referencia.json` y `referencia.md` de cada equipo, el test y la suma de revisión | no | **leer el informe de cada equipo con la pieza delante, una vez** |
| D | Procedencia: `Source` en el modelo, los proveedores, el tooltip, la sección del informe; `docs/comprobar.md` enlazada desde el README y vigilada por un test | no | aprobar el texto del tooltip en capturas |
| E | El volcado dentro del paquete, `--dump`, el botón, la plantilla de issue, `validated.json` y el aviso de familia | no: el volcado es sin permisos | aprobar el texto del aviso; crear la etiqueta `equipo` en GitHub |
| F | Las salidas que piden root | **sí** | **propuesta aparte, antes de escribir nada** |

La fase F tiene dos caminos y solo el segundo toca el ayudante:

- **el dueño aporta las salidas** que generó él con `sudo` (`--adjuntar`,
  apartado 2). silux no eleva nada; lo que hay que proponer es el filtrado,
  porque un fallo ahí publica un número de serie;
- **el volcado «con permisos»**: grabar por `sysroot.a_traves` lo que contesta
  el ayudante (la tabla SMBIOS, el SMART, los MSR). No cambia qué lee, pero
  saca del equipo datos que hoy no salen, y la tabla SMBIOS es binaria y lleva
  series y el UUID: hay que anonimizarla por estructura, como el EDID y el
  SPD. Medido: en esta máquina `energy_uj` y las `eeprom` del SPD se leen sin
  root, así que parte de lo «privilegiado» depende de la distribución.

Aparte quedan los fallos nuevos de la tabla del apartado 1: cada uno, un
commit con su test. El ocupado de las particiones, el firmware de los SATA y
los milímetros del monitor los habría cazado el contraste de la fase B.
