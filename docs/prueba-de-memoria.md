# La prueba de memoria: cómo comprobarla tú mismo

La pestaña Memoria de Rendimiento da dos cosas: cuánto tarda la memoria en
contestar, nivel a nivel (L1, L2, L3 y RAM), y cuántos GB/s mueve leyendo,
escribiendo y copiando. Aquí está cómo se mide, qué acompaña a cada cifra
para que te puedas fiar de ella y las órdenes para repetirla con otras
herramientas.

Lo mide un módulo nativo en Rust (`native/silux_bench/`), en un proceso
aparte. Sin él (una instalación por pip sin el módulo) contesta una medida
sencilla, y la pestaña lo dice.

## Qué mide y cómo

**Latencia.** Una cadena de lecturas donde cada una da la dirección de la
siguiente, al azar por todo el bloque: el procesador no puede adelantar
ninguna, así que lo que se cronometra es lo que tarda una. Con bloques de
4 KiB a 1 GiB (dos por cada potencia de dos) sale una curva con un escalón
donde acaba cada caché.

- La latencia de cada nivel es la mediana de los bloques que caben en su
  caché con holgura (hasta la mitad de su tamaño).
- La de la RAM, siempre igual para poder comparar equipos: al azar sobre
  1 GiB con páginas grandes, o sobre cuatro veces la caché mayor si es más.
  Sin memoria libre para eso, el mayor bloque que quepa, y se dice.
- Cada punto son 7 muestras de al menos 10 ms; se enseña la mediana. Un punto
  disperso se repite solo, hasta dos veces.

**Ancho de banda.** Lectura, escritura y copia, con un hilo y con todos,
cada hilo fijado a su CPU. Un hilo recorre 1 GiB, u ocho veces la caché
mayor si es más; todos juntos, 1 GiB repartido (o esas ocho veces). Con
bloques más pequeños la L3 sirve una parte: con una de 96 MiB, un hilo leía
60 GB/s sobre 128 MiB (más que el máximo teórico de la memoria), 42–44 sobre
512 MiB y 41–44 sobre 1 o 2 GiB. La copia cuenta lo que lee más lo que
escribe, como STREAM. Las escrituras «sin pasar por la caché» son las no
temporales.

## Lo que acompaña a cada cifra

- **La frecuencia a la que se midió.** Una caché contesta en ciclos del
  núcleo: el mismo bloque tarda más nanosegundos con el reloj bajo. Cada
  punto lleva la frecuencia de sus muestras, contando los ciclos del propio
  hilo (o la que da el kernel, si el sistema no deja contar), y cada nivel
  sale también en ciclos, que no cambian con el reloj. Antes del primer
  punto se espera a que la frecuencia se quede quieta. Si aun así cambia
  durante la prueba, hay un aviso.
- **Si la curva cuadra con las cachés.** El escalón de cada nivel se compara
  con el tamaño que declara el procesador. Si cae lejos (más de un factor
  2), se dice dónde sube y qué declara.
- **El porcentaje del máximo teórico.** Canales ocupados × MT/s × 8 bytes es
  lo más que puede mover esa memoria. La lectura más rápida se enseña como
  porcentaje de eso. Por encima del 100 %, una de las dos cifras está mal, y
  se avisa. Sin saber los canales no hay porcentaje, y se dice por qué.
- **El método**, en una línea: el bloque de la RAM, cuánta parte tuvo
  páginas grandes de verdad (se mira después de medir), la CPU y cómo se
  midió la frecuencia.

## Cómo repetirlo con otras herramientas

Con el equipo en reposo y en la misma CPU que dice la línea del método (aquí,
la 1). Otro programa usando la caché compartida mueve los escalones. Y con
la frecuencia quieta: un programa que enciende y apaga el turbo según la
carga (auto-cpufreq, por ejemplo) lo cambia a mitad de una prueba, y las
referencias no dicen a qué frecuencia midieron. `perf stat -e cycles:u,task-clock`
delante de cada orden lo dice: ciclos entre milisegundos.

**multichase** (latencia, páginas grandes, al azar por todo el bloque):

```bash
git clone https://github.com/google/multichase && cd multichase && make
taskset -c 1 ./multichase -s 64 -m 1g -T 1g -H     # la RAM, sobre 1 GiB
taskset -c 1 ./multichase -s 64 -m 16m -T 16m -H   # dentro de una L3 grande
```

`-T` igual a `-m` es lo que hace el recorrido al azar por todo el bloque: por
defecto multichase salta en ventanas de 256 KiB y da cifras más bajas (50 ns
donde esto da 75).

**lmbench** (latencia con páginas de 4 KiB, y ancho de banda con un hilo):

```bash
git clone https://github.com/intel/lmbench && cd lmbench && make
taskset -c 1 ./bin/*/lat_mem_rd -t 1024       # la curva; -t es el recorrido al azar
taskset -c 1 ./bin/*/bw_mem -N 5 512m rd      # lectura
taskset -c 1 ./bin/*/bw_mem -N 5 512m wr      # escritura
taskset -c 1 ./bin/*/bw_mem -N 5 512m cp      # copia: cuenta lo copiado una vez, ×2 para comparar
```

En las distribuciones recientes, compilar lmbench pide las cabeceras de
`libtirpc`. `lat_mem_rd` usa páginas de 4 KiB: la TLB adelanta el escalón de una caché
grande (en una L3 de 96 MiB sube desde 32 MiB), y la RAM sale más lenta.

**STREAM** (ancho de banda con escrituras no temporales):

```bash
curl -LO https://www.cs.virginia.edu/stream/FTP/Code/stream.c
gcc -O3 -fopenmp -DSTREAM_ARRAY_SIZE=80000000 -DNTIMES=20 stream.c -o stream
OMP_NUM_THREADS=1 taskset -c 1 ./stream                            # un hilo
OMP_PROC_BIND=spread OMP_PLACES=cores ./stream                     # todos
```

Su «Copy» se compara con la «copia sin pasar por la caché»: gcc cambia ese
bucle por una llamada a `memcpy`, y la de la glibc, con bloques tan grandes,
escribe sin pasar por la caché y recorre cuatro páginas a la vez. Es la
mejor copia que sabe hacer la glibc, no un bucle sencillo.

**Intel MLC** (latencia y ancho de banda; la referencia en Intel). Es un
binario de Intel con su propia licencia: se descarga de
<https://www.intel.com/content/www/us/en/download/736633/intel-memory-latency-checker-intel-mlc.html>.
Sin root no puede apagar los prefetchers ni usar páginas grandes (pide
reservarlas antes en `vm.nr_hugepages`), así que se le dice que no los toque
(`-e`) y que salte al azar (`-r`):

```bash
mlc --idle_latency -e -r -l64 -c1 -i1 -b1g -D16777216   # la RAM, al azar por todo 1 GiB
mlc --max_bandwidth -e -k1 -b1g                         # un hilo
mlc --max_bandwidth -e -b84m                            # todos
```

`-D` es cuántas líneas de 64 bytes entran en el salto al azar: por defecto
8192 (512 KiB), y con eso da 31 ns donde todo el bloque da 85. Para
comparar con Silux, todas las líneas del bloque (`-b` entre 64) y la curva
de Silux con páginas de 4 KiB. En el ancho de banda, MLC cuenta cada
escritura dos veces (la lectura que la precede para traer la línea, y la
escritura), como la ve el controlador de memoria: su «1:1» son solo
escrituras y se compara con el doble de la escritura de Silux, y su «2:1»
es una copia contada tres veces por línea donde Silux cuenta dos.

## Validación

### Ryzen 7 5800X3D, DDR4-3200 en doble canal

El 24 de noviembre de 2026, con la prueba tal como la lanza la ventana, tres
veces, y cada referencia tres veces en la misma CPU. Kernel 7.3, gobernador
`performance`, páginas grandes en el 100 % del bloque.

| Bloque | Silux, ns | Frecuencia | multichase `-H`, ns |
|---|---|---|---|
| 4 MiB | 10,79 · 10,85 · 10,86 | 4,54 GHz | 10,79 · 10,80 · 10,79 |
| 16 MiB | 11,25 · 11,26 · 11,26 | 4,53 GHz | 11,25 · 11,26 · 11,28 |
| 64 MiB | 11,38 · 11,37 · 11,36 | 4,54 GHz | 11,38 · 11,39 · 11,47 |
| 96 MiB | 20,38 · 16,93 · 24,93 | 4,54 GHz | 20,68 · 20,22 · 20,37 |
| 192 MiB | 72,64 · 57,72 · 55,21 | 4,53 GHz | 55,07 · 56,96 · 54,38 |
| 384 MiB | 70,87 · 71,10 · 71,53 | 4,53 GHz | 69,57 · 70,03 · 69,55 |
| 1 GiB | 75,13 · 76,90 · 75,74 | 4,53 GHz | 75,25 · 75,22 · 75,32 |

Dentro de la L3 y en la RAM coincide al 1 %. Entre 96 y 192 MiB el bloque
está a medias en la L3 (96 MiB) y la cifra cambia de una prueba a otra, en
las dos herramientas: no se usa para ningún nivel.

| Nivel | ns | Ciclos |
|---|---|---|
| L1 | 0,88 · 0,88 · 0,88 | 4,0 · 4,0 · 4,0 |
| L2 | 2,65 · 2,65 · 2,65 | 12,0 · 12,0 · 12,0 |
| L3 | 11,00 · 11,10 · 11,06 | 49,9 · 50,3 · 50,1 |
| RAM | 75,13 · 76,90 · 75,74 | 341 · 349 · 343 |

Los ciclos son la comprobación de la frecuencia: Zen 3 contesta desde la L1
en 4 ciclos y desde la L2 en 12. Con el núcleo a 4,44 GHz en vez de a 4,54,
otra prueba dio 0,90 ns en la L1: los mismos 4,0 ciclos.

| Medida, GB/s | Silux | Referencia |
|---|---|---|
| Lectura, 1 hilo (AVX2) | 45,3 · 45,0 · 40,7 | `bw_mem rd` 38,6 · 38,6 · 38,6 |
| Escritura, 1 hilo | 21,2 · 21,0 · 21,0 | `bw_mem wr` 21,3 · 21,0 · 21,1 |
| Copia, 1 hilo | 28,8 · 28,5 · 28,6 | `bw_mem cp` × 2: 28,4 · 28,7 · 28,6 |
| Copia sin caché, 1 hilo | 41,0 · 41,2 · 40,5 | STREAM Copy 41,6 · 42,4 · 42,7 |
| Copia sin caché, 16 hilos | 38,7 · 38,8 · 38,8 | STREAM Copy 38,5 · 38,6 · 38,5 |

La lectura sale por encima de `bw_mem` porque el bucle es otro. Sobre 1 GiB
en la CPU 1, alternando seis veces cada uno, los vectores de 256 bits (AVX2)
dan 38,8–41,0 GB/s y los de 128 (SSE2), 35,4–37,1, a un 2 % de `bw_mem`
medido justo después (35,3–36,1). Con SSE2 las dos cuadran: la diferencia
es el bucle, no la memoria. Ese rato todo medía un 5 % menos que en la tabla
de arriba, `bw_mem` también; con el bloque viejo de 512 MiB, que la L3
servía en parte, había salido 45 frente a 39,5.

Esa tabla es de antes de subir el bloque de un hilo a 1 GiB; la prueba
entera con él, seis veces el 24 por la tarde (15 s cada una):

| Medida, GB/s | Un hilo | Todos los hilos |
|---|---|---|
| Lectura | 43,5 · 44,2 · 41,4 · 43,3 · 41,8 · 43,3 | 40,9 · 41,0 · 40,6 · 40,4 · 40,3 · 40,5 |
| Copia sin caché | 40,4 · 40,0 · 41,2 · 40,7 · 40,8 · 40,8 | 38,7 · 38,8 · 39,0 · 38,9 · 38,6 · 38,9 |

**La lectura con todos los hilos sale por debajo de la de uno, y es de la
memoria.** `bw_mem rd` con procesos en vez de hilos, sin fijar, con 1 GiB
repartido entre todos:

| Hilos o procesos | Silux, lectura | `bw_mem -P N rd` |
|---|---|---|
| 1 | 41–44 (1 GiB) | 37,1 · 37,7 · 37,5 |
| 2 | 47,8 · 47,8 · 46,7 | 44,6 · 45,6 · 45,8 |
| 4 | 44,9 · 45,4 · 42,7 | 44,1 · 44,9 · 44,9 |
| 8 | 41,2 · 41,5 · 40,9 | 39,9 · 39,9 · 39,0 |
| 16 | 40,2 · 40,5 · 40,2 | 39,7 · 39,6 · 40,0 |

Con 16 las dos dan lo mismo, y las dos tienen el máximo con dos o cuatro
flujos y bajan con más. La copia sin caché hace lo mismo con STREAM (42 con
un hilo, 38,5 con dieciséis). La explicación habitual es que muchas lecturas
a la vez abren más filas de la memoria y la obligan a cambiar de fila más a
menudo; no se ha medido aquí. La ventana lo dice debajo de la tabla cuando
pasa.

**Lo que varía la lectura de un hilo entre pruebas, y lo que no se sabe.**
Dentro de una medida, las siete repeticiones sobre el mismo bloque se
separan un 1 %. Entre una medida y la siguiente, cada una sobre un bloque
recién pedido, salen 44 la mayoría de las veces y 41–42 algunas. Con
páginas de 4 KiB sale más lento (36) y algo más estable. Medir tres bloques
y quedarse con la mediana no lo arregló (41,8–44,2 en seis pruebas, y 6 s
más), así que no es solo qué memoria física le toca a cada bloque. Con todos
los hilos varía un 1 %. Comparar dos lecturas de un hilo con menos de un 7 %
de diferencia no dice nada.

### Core i5-10400, dos módulos DDR4

El 25 de noviembre de 2026. Kernel 7.3, gobernador `performance` con
`performance` de preferencia, turbo encendido, páginas grandes en el 100 %
del bloque, CPU 1. Cada referencia, con su frecuencia medida con `perf`.

**Antes, auto-cpufreq.** Ese programa corre como servicio en este equipo y
enciende o apaga el turbo según la carga, también a mitad de una prueba:
una empezó la curva a 2,89 GHz y la acabó a 4,2. Explica lo que se vio con
la versión anterior (de la L3 hacia arriba, un 5 a un 25 % por encima de
multichase, y la L1 a 1,40 ns): 1,38 ns a 2,89 GHz son los mismos 4,0
ciclos que 0,95 ns a 4,2. Las tablas siguientes son con el servicio parado
y el turbo fijo encendido.

La latencia, en tres rondas, cada una con la prueba tal como la lanza la
ventana y justo después multichase en la misma CPU:

| Bloque | Silux, ns | GHz | multichase `-H`, ns | GHz |
|---|---|---|---|---|
| 16 KiB | 0,98 · 0,96 · 0,94 | 4,08–4,25 | 0,95 · 0,95 · 0,95 | 4,15–4,16 |
| 128 KiB | 2,98 · 2,88 · 2,82 | 4,05–4,26 | 2,88 · 2,87 · 3,74 | 4,14–4,16 |
| 4 MiB | 9,55 · 9,62 · 9,66 | 4,14–4,17 | 9,50 · 10,16 · 9,62 | 4,14–4,16 |
| 16 MiB | 49,67 · 49,28 · 48,95 | 4,08–4,22 | 48,08 · 47,46 · 46,71 | 4,15–4,17 |
| 48 MiB | 60,76 · 59,52 · 60,17 | 4,12–4,19 | 62,04 · 61,61 · 61,84 | 4,15–4,17 |
| 192 MiB | 64,01 · 66,39 · 63,60 | 4,05–4,18 | 65,53 · 66,02 · 65,42 | 4,13–4,14 |
| 1 GiB | 64,64 · 64,66 · 64,24 | 4,18–4,25 | 66,78 · 66,77 · 66,16 | 4,07–4,08 |

| Nivel | ns | Ciclos |
|---|---|---|
| L1 | 0,97 · 0,96 · 0,96 | 4,0 · 4,0 · 4,0 |
| L2 | 2,98 · 2,85 · 2,86 | 12,1 · 12,0 · 12,0 |
| L3 | 9,25 · 9,04 · 9,06 | 38,5 · 37,8 · 37,9 |
| RAM | 64,64 · 64,66 · 64,24 | 274 · 275 · 269 |

Dentro de las cachés coincide al 2 %, y en ciclos es lo mismo que
multichase (0,95 ns a 4,15 GHz son 3,9 ciclos; 2,87 ns, 11,9). En la RAM,
Silux sale un 3 % por debajo; multichase midió el GiB a 4,07 GHz y Silux a
4,2. En la primera pasada de la mañana, con el turbo encendido, dieron
64,5–64,7 y 64,3–64,4: la diferencia cambia de una sesión a otra en las
dos. 16 MiB es la transición (la L3 es de 12 MiB) y no se usa para ningún
nivel. El veredicto de la curva cuadró en las seis pruebas: la L1 sube
entre 32 y 48 KiB, la L2 entre 256 y 384 KiB y la L3 entre 8 y 16 MiB.

Intel MLC sin root no tiene páginas grandes, así que se compara con la
curva de Silux con páginas de 4 KiB, las dos al azar por todo el bloque:

| Bloque | Silux con 4 KiB, ns | MLC `-e -r`, ns |
|---|---|---|
| 4 MiB | 12,52 · 11,36 · 11,55 | 12,0 · 12,0 · 12,0 |
| 16 MiB | 51,75 · 51,61 · 49,11 | 55,0 · 54,6 · 55,3 |
| 48 MiB | 68,74 · 67,86 · 67,86 | 71,6 · 71,5 · 71,7 |
| 192 MiB | 75,78 · 75,87 · 76,52 | 79,4 · 79,3 · 78,9 |
| 1 GiB | 78,96 · 78,87 · 78,77 | 84,7 · 85,0 · 84,7 |

En esta tanda MLC sale entre un 4 y un 7 % por encima, a la misma
frecuencia (4,11–4,19 GHz). En la primera pasada de la mañana coincidían
al 1 % (1 GiB: 79,0 frente a 79,2–79,5; 192 MiB: 76,1–76,4 frente a
76,1–76,5). Sin explicar. Con sus opciones por defecto (saltos al azar
dentro de trozos de 512 KiB) MLC da 31 ns sobre 192 MiB y sobre 1 GiB.

El ancho de banda (12 hilos en total):

| Medida, GB/s | Silux | Referencia |
|---|---|---|
| Lectura, 1 hilo (AVX2) | 20,4 · 21,5 · 22,1 | `bw_mem rd` 18,1 · 18,1 · 18,2; MLC ALL Reads 18,5 · 17,3 · 20,1 |
| Escritura, 1 hilo | 12,5 · 13,6 · 13,4 | `bw_mem wr` 12,5 · 12,5 · 12,5; MLC 1:1 ÷ 2: 13,0 · 13,1 · 13,2 |
| Copia, 1 hilo | 14,3 · 14,8 · 14,8 | `bw_mem cp` × 2: 16,0 · 16,0 · 15,9; MLC 2:1 × ⅔: 16,9 · 16,5 · 16,8 |
| Copia sin caché, 1 hilo | 18,8 · 19,8 · 19,7 | STREAM Copy 27,9 · 27,8 · 27,8 |
| Lectura, 12 hilos | 30,5 · 31,6 · 31,9 | MLC ALL Reads 32,3 · 33,9 · 31,1 |
| Escritura, 12 hilos | 12,1 · 12,2 · 12,1 | MLC 1:1 ÷ 2: 11,8 · 11,9 · 10,9 |
| Copia, 12 hilos | 16,9 · 16,9 · 16,7 | MLC 2:1 × ⅔: 17,1 · 18,1 · 16,4 |
| Copia sin caché, 12 hilos | 25,3 · 25,5 · 25,4 | STREAM Copy 25,0 · 25,1 · 25,1 |

- Con todos los hilos, y la escritura de uno, cuadra a un 5 %.
- La lectura de un hilo sale por encima, como en el 5800X3D, y en parte es
  el bucle: alternando, AVX2 da 20,2–21,1 y SSE2 18,9–19,9. Aun con SSE2
  queda entre un 4 y un 10 % por encima de `bw_mem`, cuando en el 5800X3D
  quedaba al 2 %.
- **La copia de un hilo sale por debajo en este Intel**: un 8 a un 12 %
  la normal y un 30 % la que no pasa por la caché, donde en el 5800X3D
  cuadraban. La de STREAM es el `memcpy` de la glibc (arriba); falta ver qué
  hace distinto de nuestro bucle.

**El aviso de la frecuencia sale en todas.** Con el turbo fijo, los puntos
van de 4,05 a 4,27 GHz, y la prueba avisa desde un 3 % de diferencia. Lo
más probable es que sea el turbo bajando de escalón según cuántos núcleos
están despiertos; no se ha medido. El aviso dice la verdad, pero con un 5 %
cada nivel sigue estando bien en ciclos. Con auto-cpufreq la diferencia fue
del 32 %.

### Lo que falta por validar

- **El i5-10400 con páginas grandes en MLC** (`-L`, con `vm.nr_hugepages`
  reservadas por root), para comparar con la curva de verdad y no con la de
  4 KiB.
- **Un procesador con dos clases de núcleo.** El contador de ciclos se pide
  para la clase del núcleo donde se mide, sin haberlo probado en uno.
- **Un equipo antiguo**, con el AppImage compatible, y uno con poca memoria.
- **AVX-512**: el camino de 512 bits no ha corrido nunca en una pieza de
  verdad (el 5800X3D no lo tiene). Hace falta un Ryzen 7000 o 9000, o un
  Intel con AVX-512.
- **ARM**: escrito sin la pieza delante.

## Límites

- La latencia en nanosegundos depende de la frecuencia del núcleo en ese
  momento. Para comparar dos equipos, o el mismo en dos días, los ciclos.
- En una máquina virtual, las cachés y las páginas grandes son las que
  declara el invitado. Se mide igual; si la curva no cuadra con ellas, se
  dice.
- Sin páginas grandes (THP en `never`) la TLB adelanta los escalones y la RAM
  sale más lenta. La línea del método dice qué parte las tuvo.
- La prueba no deja menos de 512 MiB libres: con poca memoria mide un bloque
  más pequeño, o no mide la RAM, y lo dice.
