# Propuesta: apoyarse en benchmarks conocidos

Solo propuesta: nada de esto está escrito en la aplicación. Lo que lleva cifra
se ejecutó el 17 de noviembre de 2026 en el i5-10400 de la oficina (Fedora 44)
o se buscó ese día en la fuente que se cita. Lo que no se pudo comprobar está
marcado como tal, y al final hay una lista con las dos cosas separadas.

## La recomendación, en corto

**Añadir `7z b` como la cifra que se compara entre equipos, y dejar el
benchmark propio para lo que hace bien: comparar este equipo consigo mismo y
decir en qué condiciones midió.** El detalle, la alternativa descartada y las
fases están en el apartado 9. Antes de escribir nada hay una fase de medida
que puede tumbar la propuesta: la misma que tumbó la escala v5.

## 1. Lo que hay hoy

| | Dónde | Qué hace |
|---|---|---|
| Mide | `benchmark.CARGAS`, `_medir` | cinco cargas de la biblioteca estándar (`zlib`, `sha512`, `bz2`, `pbkdf2_hmac`, `crc32`), a un hilo y a todos, por tiempo y no por trabajo fijo |
| Vigila | `benchmark._Vigilante`, `Conditions`, `_avisos` | frecuencia, temperatura y lo que se lleva otro programa, cada 0,25 s; de ahí los avisos |
| Puntúa | `score.puntuar`, `db/scores.json` | cada carga contra el patrón (un 5800X3D, 1000 puntos); desde la v6 dos de las cinco (`PUNTUABLES`), y solo se compara la prueba de 15 s (`comparable`) |
| Guarda | `history.py` | hasta 60 entradas en `~/.local/share/silux/benchmarks.json`, con `score_version`, condiciones y la zlib y la OpenSSL con que midió |

La vigilancia es lo que el programa tiene y los demás no.

**Lo que ha costado**, sacado de `docs/lecciones.md` y de los comentarios:

| Escala | Qué cambió | Por qué |
|---|---|---|
| v4 | LZMA por bzip2 | LZMA saltaba entre dos velocidades un 26 % y dispersaba la puntuación un 4,7 % |
| v5 | la verificación, en bytes por segundo | el bloque se dimensiona con la caché: un 42,8 % de regalo a quien tiene poca |
| v6 | puntúan dos cargas de cinco | la zlib de cada distribución: ×9,7 en el CRC en la misma pieza, 716 puntos contra 504 |

Y lo que sigue abierto después de la v6:

- **La cifra comparable descansa en dos cargas**, y con ellas el SMT sale a
  +9,5 % donde con las cinco salía a +0,2 % (`benchmark.py`, «QUÉ SE
  PERDIÓ»). La salida prevista, un kernel en ensamblador, no está escrita.
- **La tabla con la que comparar está vacía**: `score.comparar` devuelve
  `None` «casi siempre», porque `piezas` solo se llena con los informes que
  alguien mande a `tools/anadir_puntuacion.py`.
- **Nadie de fuera sabe qué son 1000 puntos de silux.** Es el problema de
  fondo: una escala propia solo vale con muchas medidas publicadas, y ese
  trabajo ya lo han hecho otros.

## 2. Los candidatos

### `7z b`, para el procesador

**Qué mide.** Comprime y descomprime con LZMA datos que genera él mismo, en
memoria, con diccionarios de 4 a 32 MB (las líneas `22:` a `25:`). La
compresión es latencia de memoria y caché; la descompresión es enteros y
saltos mal predichos. Da cada una en KiB/s y en **MIPS**, una cifra
normalizada contra un Core 2 con un hilo, de modo que a un hilo queda cerca
de los MHz reales del procesador (ayuda de 7-Zip, orden `b`).

**Cómo se lanza.** `7z b` usa todos los hilos; `7z b -mmt1`, uno; `-mmtN`,
los que se pidan; `-md25` fija el diccionario más grande; un número detrás de
la `b` son las pasadas. No hay opción de duración: hace un trabajo fijo.

**Cómo es la salida.** Texto en columnas, sin formato para máquinas; la forma
real está en el apartado 3. De memoria y sin comprobar aquí, las columnas son
las mismas desde p7zip 16.02 y lo que cambia es la cabecera. Un lector que
busque las líneas `NN:`, `Avr:` y `Tot:` aguantaría las dos.

**Cómo de estable es la cifra entre versiones: poco.** La propia tabla de
7-cpu.com lo avisa: las versiones nuevas para x64 y arm64 llevan el
descompresor en ensamblador y «the rating results can be 1.7 times larger
that with previous version», y la mayoría de sus filas son de versiones
anteriores. p7zip se quedó en la 16.02 (de memoria); el 7-Zip oficial para
Linux va por la **26.06, del 6 de noviembre de 2026** (7-zip.org).

**Binarios y paquetes**, que es donde más ha cambiado:

| Distribución | Paquete | Binarios | Comprobado |
|---|---|---|---|
| Fedora 44 | `7zip` 26.04 | `/usr/bin/7z`; `7za` en `7zip-standalone` | aquí, con `rpm -ql` |
| Fedora 44 | `7zip-reduced`, `7zip-standalone-all` | se supone `7zr` y `7zz` | existen en el repositorio; los nombres de binario, no |
| Arch | `7zip` 26.06-1, sustituye a `p7zip` | `7z`, `7za`, `7zr` | lista de archivos de archlinux.org |
| CachyOS | el de Arch | — | no comprobado |
| Debian 13 | `7zip` 25.01, sustituye a `p7zip-full` | `7z`, `7za`, `7zr` | lista de archivos de packages.debian.org |
| Ubuntu 24.04 | `p7zip-full` es ya de transición | — | por el nombre de la versión, `16.02+transitional.1` |
| Ubuntu 22.04 | `7zip` 21.07, en `universe` | se supone `7zz` | la versión sí; el binario no |
| Oficial | `7z2606-linux-x64.tar.xz` | `7zz` | la descarga sí; no se bajó |

O sea: `p7zip` 16.02 de verdad solo queda en distribuciones viejas, y el
nombre del binario depende de quién empaquete. Hay que buscar los cuatro, en
el orden `7zz`, `7z`, `7za`, `7zr`.

**Licencia.** LGPL-2.1 o posterior, con partes BSD y la restricción de unRAR
para el código de RAR (campo `License` del paquete de Fedora y de Arch).
`7zr` es la variante reducida, sin RAR; que acepte la orden `b` no se ha
comprobado porque aquí no está instalado.

### Otros para el procesador

| Candidato | Libre | Qué mide | Sirve | Por qué |
|---|---|---|---|---|
| `openssl speed` | sí | primitivas criptográficas, en bytes/s por tamaño de bloque | como diagnóstico, no como cifra | mide instrucciones especializadas (`sha_ni`, AES-NI): es justo lo que `benchmark.py` evita al usar SHA-512. Y cambia con la versión: la derivación se movía ×1,38 entre OpenSSL 3.0 y 3.5 |
| `zstd -b` | sí | compresión y descompresión en MB/s | no | cada versión de zstd cambia la velocidad a propósito, no hay tabla publicada, y `-T` solo reparte la compresión |
| `xz` | sí | — | no | no tiene modo de prueba: `xz --long-help` no lo lista |
| `sysbench cpu` | sí | primos hasta un límite, en eventos/s | no | es una división entera en bucle; la serie 0.4 y la 1.0 no dan cifras comparables (de memoria, no comprobado). Fedora 44 lo trae en la 1.0.20 |
| `stress-ng --metrics` | sí | «bogo ops» por estresor | no | su manual dice que esas cifras no son un benchmark (de memoria, no comprobado). Sirve para cargar, no para medir |
| Phoronix Test Suite | sí (GPL) | lanza perfiles, entre ellos el de 7-Zip | no para lanzarlo | pide PHP y descarga y compila cada prueba. Lo que sí vale es su base, OpenBenchmarking (apartado 6) |
| Blender Benchmark | sí | Cycles, en muestras por minuto, CPU o GPU | no para lanzarlo | descarga Blender y las escenas y tarda minutos. Tiene base pública, opendata.blender.org. El tamaño no se pudo comprobar |
| Geekbench | no | cifra única de CPU | no | privativo: no se puede empaquetar ni depender de él. Es el más conocido, y eso no lo arregla nada libre |
| y-cruncher | no | decimales de pi | no | cerrado y con redistribución restringida (de memoria, no comprobado) |

Ninguno mejora a `7z b` en lo que se busca: libre, instalable con una orden
en todas las distribuciones, corto, con cifra a un hilo y a todos, y con una
tabla publicada. `openssl speed` queda como posible diagnóstico, fuera de
este plan.

### `glmark2` y `vkmark`, para la gráfica

| | `glmark2` | `vkmark` |
|---|---|---|
| API | OpenGL 2.0 y OpenGL ES 2.0 | Vulkan |
| Qué hace | unas decenas de escenas cortas; FPS de cada una | lo mismo, con menos escenas |
| Cifra | `glmark2 Score: N`, la media de los FPS | `vkmark Score: N`, igual |
| Tamaño por defecto | ventana de 800×600 | ventana de 800×600 |
| Sin ventana | `--off-screen` | no tiene: `--winsys` es `xcb`, `wayland` o `kms` |
| Sincronía | `--swap-mode`; solo la variante DRM admite todos los modos | `--present-mode`, por defecto `mailbox` |
| Salida a archivo | `--results-file` en CSV o XML | no |
| Última versión | 2023.01; Fedora empaqueta un corte de febrero de 2025 | 2025.01 |
| Licencia | GPL-3 | LGPL-2.1 |
| Fedora 44 | `glmark2`, 5,8 MB instalado | `vkmark`, 2,7 MB |
| Arch | `glmark2` 2023.01-2 en `extra`, 13,3 MB | `vkmark` 2025.01 en `extra` |
| Debian y Ubuntu | `glmark2-wayland`, `glmark2-es2-wayland` y las de X11 | `vkmark` 2025.01; fuera de Debian *testing* desde enero de 2026 |

Las opciones salen de las páginas de manual de Arch y los tamaños de
`dnf repoquery` y archlinux.org. La línea de la puntuación y el número de
escenas van de memoria: aquí no está instalado ninguno y no se ejecutaron.

Dos cosas que pesan en la decisión:

- **Miden poco la gráfica en un equipo moderno.** Son escenas sencillas a
  800×600: en una tarjeta dedicada salen miles de FPS y el límite lo ponen
  un hilo del procesador y el driver. No está medido aquí; se comprueba en
  la RX 9070 XT.
- **Dependen de por dónde se presenta.** Hay informes de un 20 % entre
  `glmark2` por XWayland y `glmark2-wayland` en el mismo equipo.
  `--off-screen` quita el compositor de en medio en `glmark2`; en `vkmark`
  no hay forma desde una sesión gráfica, porque `kms` exige que no lo haya.

## 3. Lo que hay en esta máquina

Fedora 44, i5-10400, sesión Wayland. Sin instalar nada, **están** `7z` y
`7za` (7-Zip 26.04), `openssl` (3.5.9), `zstd` (1.5.7), `xz` (5.8.2) y
`stress-ng` (0.22.01). **No están** `7zz`, `7zr`, `sysbench`, `glmark2` ni
`vkmark`, ni las variantes `-wayland` y `-es2`.

`7z b -mmt1`, una vez, **29,1 s**:

```
7-Zip 26.04 (x64) : Copyright (c) 1999-2026 Igor Pavlov : 2026-10-05
 64-bit locale=es_ES.UTF-8 Threads:12 OPEN_MAX:1048576

 mt1
Compiler:  ver:16.2.1 20260819 (Red Hat 16.2.1-2) GCC 16.2.1 : SSE2
Linux : 7.3.3-200.fc44.x86_64 : #1 SMP PREEMPT_DYNAMIC … : x86_64
PageSize:4KB HPS:2MB THPS:2MB THP:madvise hwcap:2 hwcap2:2
Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz
(A0653)  (LP)

1T CPU Freq (MHz):  4023  4041  4004  4042  4077  4065  4123

RAM size:   15798 MB (LP),  # CPU hardware threads:  12
RAM usage:    437 MB (LP),  # Benchmark threads:      1

                       Compressing  |                  Decompressing
Dict     Speed Usage    R/U Rating  |      Speed Usage    R/U Rating
         KiB/s     %   MIPS   MIPS  |      KiB/s     %   MIPS   MIPS

22:       6492   100   6323   6316  |      50390    99   4327   4302
23:       5598    99   5762   5705  |      50070   100   4342   4334
24:       5394   100   5817   5800  |      48936   100   4316   4296
25:       5168    99   5931   5901  |      48734   100   4349   4338
----------------------------------  | ------------------------------
Avr:      5663   100   5958   5930  |      49532   100   4333   4318
Tot:             100   5146   5124
```

`7z b`, una vez, **38,1 s**. Lo que cambia respecto de la anterior, con las
líneas `22:` a `24:` y las vacías quitadas:

```
6T CPU Freq (MHz): 568% 3702   571% 3709
12T CPU Freq (MHz): 891% 2782   848% 2657
RAM usage:   2669 MB (LP),  # Benchmark threads:     12
25:      38437  1007   4358  43886  |     362748  1058   3051  32275
----------------------------------  | ------------------------------
Avr:     39996   978   4291  41993  |     370098  1056   3053  32235
Tot:            1017   3672  37114
```

De aquí salen cuatro hechos para el diseño:

- **La prueba entera son 67 s** en este equipo, y no se elige: el trabajo es
  fijo y en un equipo lento serán más.
- **La salida ya dice la versión y con qué se compiló** (`GCC 16.2.1 : SSE2`),
  que es lo que hay que guardar con cada medida.
- **Un indicio que hay que aclarar.** La descompresión a un hilo da 4338 MIPS
  a 4,0 GHz. La tabla de 7-cpu.com da 4640 a un i7-6700 a los mismos 4,0 GHz
  con la versión 9.22, que es de las antiguas, y dice que las nuevas dan
  hasta ×1,7. Que el de Fedora salga por debajo en un núcleo de la misma
  familia hace sospechar que **está compilado sin el descompresor en
  ensamblador**. No está comprobado: el `.spec` de Fedora no se dejó leer.
  Si es así, el mismo 7-Zip 26.04 da dos cifras según quién lo compile, que
  es la zlib otra vez.
- **Los 2,7 GB son del hijo**, no de silux, pero un equipo con 4 GB no los
  tiene, y qué hace `7z b` entonces no se ha comprobado.

`openssl speed -seconds 1 sha256`, **6,0 s**, y `zstd -b3 -i1`, **3,2 s**. Lo
último que escribe cada uno:

```
type             16 bytes     64 bytes    256 bytes   1024 bytes   8192 bytes  16384 bytes
sha256           66147.62k   165499.58k   347508.48k   470062.08k   497868.80k   529153.55k

 3#Lorem ipsum       :  10000000 ->   2983345 (x3.352),  226.1 MB/s, 1031.4 MB/s
```

`openssl` vuelca antes la línea entera de compilación del paquete y tiene
`-mr`, salida para máquinas. `zstd` reescribe su línea con retornos de carro.

## 4. Comparación con el benchmark propio

| | Propio (`benchmark.py` + `score.py`) | Externos lanzados por silux |
|---|---|---|
| La cifra la conoce alguien | no: 1000 es un 5800X3D y hay que explicarlo | sí: los MIPS de 7-Zip se buscan y salen |
| Con qué compararla | `piezas` de `scores.json`, vacía | 7-cpu.com, OpenBenchmarking, cualquier foro |
| Mantener la escala | tres versiones (v4, v5, v6), y cada una deja el historial sin cifra | ninguna: la escala es de 7-Zip |
| Carga | bucles de biblioteca, 64 KB a 192 MB | un compresor de verdad con diccionarios de 4 a 32 MB |
| Depende de lo instalado | de la zlib y la OpenSSL: por eso puntúan dos | de la versión de 7-Zip y de cómo se compiló |
| Funciona sin instalar nada | sí, siempre | no, salvo que el binario vaya dentro del AppImage |
| Igual dentro del AppImage | sí, con la zlib de Ubuntu 22.04 | solo si se limpia el entorno al lanzar (apartado 8) |
| Duración | de 1 s a 30 min por medida (`MAXIMO_SEGUNDOS`) | fija; alargar es repetir pasadas |
| Cancelar | al acabar la medida en curso | al momento: se mata el proceso |
| Condiciones | `_Vigilante`, dentro del proceso | el mismo vigilante, mirando a un hijo |
| Prueba de aguante (2 y 5 min) | sí | no es su papel |
| Memoria y cachés | `membench.py`, propio | no lo cubre ninguno: `membench` se queda como está |
| Una sola cifra | sí, a un hilo y a todos | cuatro: compresión y descompresión, a uno y a todos, más `Tot` |
| Gráfica | no hay nada | `vkmark` y `glmark2`, con sus límites |
| Código que mantener | cargas, escala, tabla, dos herramientas | detección, lanzamiento y un lector por herramienta |

Los riesgos, con lo que los acota:

- **Versiones distintas, cifras distintas**, hasta ×1,7 en descompresión. Se
  guardan la versión y la línea `Compiler`, y dos medidas de versión distinta
  no se comparan, igual que hoy con `score_version`.
- **Leer texto pensado para personas.** Un lector por herramienta, probado
  contra salidas reales guardadas en `tests/fixtures/`. Si no reconoce la
  salida no enseña cifra y lo dice: es preferible a una mal leída.
- **La gráfica depende del compositor.** `--off-screen` donde lo hay, y la
  sesión (`XDG_SESSION_TYPE`) guardada con la medida.

## 5. Si no están instalados

La regla 5 decide la forma: cuando falta un dato se explica. Un benchmark
que no está instalado tiene arreglo, así que su tarjeta sale, dice qué falta
y da la orden en el mismo campo con botón «Copiar» que ya usa el diálogo de
permisos (`ca91750`).

| Distribución | Procesador | Gráfica |
|---|---|---|
| Fedora | `sudo dnf install 7zip` | `sudo dnf install vkmark glmark2` |
| Arch, CachyOS | `sudo pacman -S 7zip` | `sudo pacman -S vkmark glmark2` |
| Debian, Ubuntu | `sudo apt install 7zip` | `sudo apt install vkmark glmark2-wayland` |

La distribución se lee de `/etc/os-release`; si no se reconoce, se nombra el
programa y no se inventa una orden.

**Empaquetarlos o no** es la decisión que más cambia el resultado:

| | 7-Zip | `glmark2` y `vkmark` |
|---|---|---|
| Tamaño | 1,2 MB (`7zip-reduced`) a 2,8 MB (`7zip-standalone-all`), sobre un AppImage de 43 MB | 2,7 a 13 MB, con modelos y texturas |
| Licencia | LGPL-2.1+: un ejecutable aparte dentro de un programa GPL-3 es agregación; hay que llevar su licencia y decir de dónde sale el código | GPL-3 y LGPL-2.1: se podría |
| Depende del equipo | de nada, si es el estático | del driver, de Mesa y del compositor del equipo |
| Qué se gana | la misma versión y la misma compilación en todos los equipos | nada: la cifra seguiría dependiendo de lo de fuera |
| Propuesta | **sí, en el AppImage, una versión fijada** | **no** |

Llevar un 7-Zip fijado dentro es lo que `docs/lecciones.md` pide para la
carga que falta: «código que no cambia de una máquina a otra porque viaja
dentro del programa». Solo que ya está escrito, y lo conoce todo el mundo.
En un paquete de distribución se usa el del sistema, con su versión a la
vista. **El benchmark propio se conserva**, y no solo como respaldo: es lo
que funciona siempre, lo que se alarga y lo que tiene historial.

## 6. Comparar con lo publicado

Se puede, con cautelas que van en la pantalla y no en la documentación:

- **7-cpu.com** es la tabla de referencia de `7z b`. Usa la línea `25:`
  (diccionario de 32 MB) y no `Tot:`, así que el lector tiene que guardarla.
  La mayoría de sus filas son de versiones antiguas y está desfasada: su
  Zen 3 es un 5600G, y no tiene ni el i5-10400 ni el 5800X3D. Sirve de orden
  de magnitud y como enlace, no como tabla que meter en `db/`.
- **OpenBenchmarking** tiene un perfil de 7-Zip con muchos resultados. Su
  página devolvió un 403 y no se pudo leer; de memoria, el perfil compila su
  propia versión fijada de 7-Zip, y por eso sus cifras se comparan entre sí.
  Con las de un `7z` de distribución, solo si coincide la versión.
- **Lo que se busca en un foro** casi nunca dice la versión.
- **`glmark2` y `vkmark`**: no. Sin resolución, modo de presentar y sesión,
  dos puntuaciones no dicen nada, y casi nadie los publica.

Lo que silux añade es lo de siempre: decir **en qué condiciones** salió la
cifra, con su versión de 7-Zip al lado. Y no se propone enviar nada a ningún
sitio: el historial sigue en el disco de quien mide, como dice `history.py`.

## 7. El historial guardado

`benchmarks.json` no se toca y no se migra:

- **No hay conversión posible** de operaciones de `bz2` a MIPS de LZMA.
- **Las entradas de hoy siguen valiendo para lo que valían**: comparar este
  equipo consigo mismo (`Entry.comparable_con`, `history.comparar`,
  `deriva_termica`). Nada de eso depende de otras máquinas.
- **Mezclar las dos cosas en el mismo archivo rompe hacia atrás.** `load`
  tira los campos que no conoce y `save` reescribe el archivo entero con un
  tope de 60: una versión anterior de silux que abra un archivo con medidas
  de 7-Zip las guardaría sin su versión de binario, y las externas echarían
  a las propias por el tope.

Así que las medidas externas van a **un archivo aparte**, por ejemplo
`~/.local/share/silux/external.json`, con su propio esquema: herramienta,
versión, línea de compilación, origen del binario (del sistema o del
AppImage), hilos, las cifras como números, y las mismas condiciones que hoy.
Dos entradas se comparan si coinciden procesador, hilos, herramienta, versión
y origen. Cuando la distribución actualice 7-Zip la serie se corta, y se
dice; con el binario del AppImage solo se corta cuando silux lo cambie.

En este equipo hay cuatro entradas guardadas: dos de la escala v4 y dos sin
`score_version`, ninguna de la v6. «Borrar las de otra escala»
(`history.remove_other_scales`) ya cubre ese caso.

**La escala v6 se congela.** Sin v7, `VERSION` y `scores.json` no se vuelven
a tocar y el historial propio deja de quedarse sin cifra con cada arreglo.

## 8. Cómo encajaría

- **`silux/extbench.py`**, nuevo. Tres cosas separadas: buscar el binario
  (`shutil.which` sobre una lista fija de nombres, nunca una ruta que venga
  de fuera), lanzarlo y leer su salida. Los lectores son funciones puras de
  texto a `dataclass` con números (`mips: int`, `kib_s: int`), que es la
  regla 1: el formateo sigue en `render.py`.
- **Otro proceso, por definición.** Es la regla 8 sin esfuerzo: los 2,7 GB de
  `7z b` y el contexto de OpenGL de `glmark2` viven y mueren en el hijo, como
  ya hacen `membench.consultar` y `gpuapi.consultar`. Lo lanza un hilo de la
  página con `subprocess.Popen`, como el de `_start` hoy; cancelar es
  `terminate()`, con un tope de tiempo.
- **El entorno hay que limpiarlo, y hoy nadie lo hace.** El `AppRun` exporta
  `LD_LIBRARY_PATH` y `PYTHONHOME` (`tools/build_appimage.py`, líneas 210 y
  214). Un `7z` o un `glmark2` del sistema lanzado con ese entorno cargaría
  las bibliotecas del AppImage. Los dos hijos de hoy son Python del propio
  paquete y por eso no ha hecho falta. Es lo primero que hay que probar
  dentro del AppImage.
- **El vigilante se comparte.** `_Vigilante` sale de `benchmark.py` a un
  sitio común en un commit que solo mueve código. Necesita un cambio:
  `_jiffies` resta lo que consume `os.getpid()`, y con un hijo el trabajo
  está en otro PID. Sin eso, la prueba entera saldría como «carga ajena del
  100 %».
- **El hilo de muestreo sigue a lo suyo.** `ui/sampler.py` ya toma fotos cada
  segundo mientras la prueba corre. `PerformancePage.apply` hoy solo se queda
  con el nombre del procesador; durante una prueba externa guardaría de cada
  foto el uso, la temperatura, el consumo y los relojes de la gráfica. Es la
  regla 4: nada se lee en el hilo de la interfaz.
- **`tracking.Tracker` y `throttling.SeguidorDeRecortes` ya hacen lo que
  falta** para la gráfica: máximos durante la prueba y cuánto tiempo estuvo
  recortando y por qué. Es lo que silux aporta a un `glmark2`: «la gráfica
  estuvo al 35 %; esta cifra la limitó el procesador».
- **Tests**: los lectores, contra salidas reales guardadas. Ninguno exige
  que `7z` esté instalado, porque en el CI no está. La tarjeta se monta de
  verdad con y sin binario.

Nada de esto toca privilegios.

## 9. Recomendación y plan

**Lo que se recomienda: convivencia, con los papeles cambiados.**

- `7z b` pasa a ser **la cifra para comparar con otros equipos**, a un hilo y
  a todos, con su versión y sus condiciones al lado.
- El benchmark propio se queda como **la prueba de este equipo**: historial,
  deriva térmica, duraciones largas, diagnóstico por carga con su biblioteca.
  Su puntuación se sigue calculando, porque `Entry.total` la usa, y deja de
  anunciarse como comparable entre máquinas.
- `score.comparar`, `piezas` y `tools/anadir_puntuacion.py` se retiran en su
  fase: es una tabla que no se ha llenado. El kernel en ensamblador deja de
  ser requisito; si se escribe será por el perfil de SMT.
- `vkmark` y `glmark2`, al final, detectados y nunca empaquetados, con la
  palabra «orientativa» y con el uso de la gráfica al lado de la cifra.

**Por qué.** El problema que ha dado guerra no era medir, era **sostener una
escala propia**: cada arreglo (LZMA, el bloque, la zlib) obligó a rehacerla y
dejó el historial sin cifra. `7z b` no elimina la dependencia de una
biblioteca, la cambia por una mejor: un solo origen, la versión y el
compilador escritos en la salida, y la posibilidad de fijarla llevándola
dentro. Con la zlib hay dos orígenes, y saber la versión no bastaba porque
`libz.so.1` elige ruta mirando el CPUID.

**La alternativa descartada: sustituir el benchmark propio por los
externos.** Borraría más código y es la tentación después de tres escalas.
Se descarta porque:

- un AppImage recién descargado en un equipo sin `7z` no mediría nada, y la
  página de Rendimiento empezaría pidiendo instalar un paquete;
- se perderían las duraciones largas (`bench.dur.endurance`,
  `bench.dur.stability`), que ningún externo ofrece;
- el historial de quien ya ha medido se quedaría sin continuidad;
- y la versión de 7-Zip pasaría a decidirlo todo sin nada con que
  contrastarla. Con los dos, una cifra de 7-Zip rara se mira contra el
  resumen criptográfico, que da lo mismo en todas partes (±0,1 %).

Y seguir como hasta ahora y escribir el kernel en ensamblador arregla la
comparabilidad técnica, no el fondo: sería una cifra que solo existe en silux.

**Fases.** Una rama por fase, como siempre.

| Fase | Qué | Qué se valida en el i5-10400 (UHD 630) | Qué se valida en el 5800X3D (RX 9070 XT) |
|---|---|---|---|
| 0. Medir | Sin código en la aplicación. Dispersión de `7z b` en diez repeticiones. La misma pieza con el `7z` de Fedora, el `7zz` oficial y lo que traen Ubuntu 22.04, Debian y Arch en contenedor: el experimento que tumbó la v5. Si `7zr` acepta `b`. Qué pasa con poca RAM (`systemd-run -p MemoryMax=`) | todo lo anterior; es la máquina donde se midió la zlib | dispersión y el `7z` de CachyOS; si la L3 de 96 MB hace algo raro con el diccionario de 32 MB |
| 1. 7-Zip del sistema | `extbench.py`, el lector, el vigilante compartido, una tarjeta en Rendimiento, `external.json`, la explicación cuando falta | con `7z` y quitándolo del `PATH`; dentro del AppImage, con el entorno limpio | lo mismo en CachyOS; gobernador y carga de fondo en los avisos |
| 2. 7-Zip dentro | El binario fijado en el AppImage con su licencia; origen guardado en cada medida; retirar `comparar` y `piezas`; `docs/benchmark.md` | AppImage normal y `compat`; que la cifra coincida con la de la fase 0 para ese binario | que los dos equipos den con el binario de dentro lo que dieron con el oficial |
| 3. Gráfica | Detección de `vkmark` y `glmark2`, lanzamiento, lo que vieron los sensores durante la prueba | UHD 630 con Mesa: Vulkan y OpenGL, Wayland; se espera la gráfica al 100 % y cifra baja. | RADV: se espera cifra limitada por el procesador, que es el aviso que hay que ver salir; consumo y motivos de recorte por `gpumetrics` |

**El criterio de la fase 0**, escrito antes de medir para no acomodarlo
después: si la misma versión de 7-Zip compilada por dos distribuciones se
separa más del 3 % (lo que hoy se mueve la compresión pesada), la cifra
comparable es **solo la del binario de dentro**, y la del sistema se enseña
como hoy las tres cargas con asterisco. Si ni el binario oficial repite
dentro del 3 % entre repeticiones, la propuesta entera se cae y se dice. La
fase 3 no depende de la 2 y se puede dejar sin hacer.

## Lo comprobado y lo que no

**Ejecutado aquí:** qué binarios hay; `7z b -mmt1` y `7z b` con 7-Zip 26.04,
una pasada cada uno; `openssl speed`; `zstd -b3 -i1`; que `xz` no tiene modo
de prueba; los paquetes de Fedora 44 con `rpm` y `dnf repoquery`; las cuatro
entradas del historial. Lo buscado lleva su fuente donde se cita.

**No comprobado:** que el `7z` de Fedora vaya sin ensamblador; la salida de
p7zip 16.02; los binarios de `7zip-reduced`, de `7zip-standalone-all` y del
`7zip` de Ubuntu 22.04; que `7zr` tenga la orden `b`; qué hace `7z b` con
poca RAM; la dispersión entre repeticiones; OpenBenchmarking (403); la salida
de `glmark2` y `vkmark` y cuánto los limita el compositor o el procesador en
estos dos equipos; los paquetes de CachyOS; el tamaño de Blender Benchmark;
lo que se dice de `sysbench`, `stress-ng` e `y-cruncher`.
