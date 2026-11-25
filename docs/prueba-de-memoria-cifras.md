# La prueba de memoria: las cifras de la validación

Lo que dio la prueba en cada equipo, frente a las herramientas de referencia.
Cada equipo abre con sus condiciones, y cada tabla lleva debajo lo que dice.
Cómo mide la prueba y cómo repetir estas cifras: [prueba-de-memoria.md](prueba-de-memoria.md).

## Core i5-10400, DDR4-2666 en doble canal

| Condición | |
|---|---|
| Fecha | 25 de noviembre de 2026 |
| Sistema | Fedora 44, kernel 7.3 |
| CPU | Core i5-10400 (L1d 32 KiB, L2 256 KiB, L3 12 MiB), medido en la CPU 1 |
| Memoria | dos módulos DDR4-3200 que van a 2666 MT/s |
| Energía | turbo encendido y fijo, gobernador `performance`; lo que no pasa por la caché, con tuned en `balanced` |
| Repeticiones | tres pruebas de Silux y tres de cada referencia; en la latencia, alternando por rondas; la frecuencia de cada referencia, medida con `perf` |
| Otros programas | en la latencia, ninguno abierto; en el ancho de banda, un navegador y Discord abiertos y quietos |
| Páginas grandes | en el 100 % del bloque de Silux; MLC, sin ellas (pide root) |

### Latencia

| Bloque | Silux, ns | GHz | multichase `-H`, ns | GHz |
|---|---|---|---|---|
| 16 KiB | 0,98 · 0,96 · 0,94 | 4,08–4,25 | 0,95 · 0,95 · 0,95 | 4,15–4,16 |
| 128 KiB | 2,98 · 2,88 · 2,82 | 4,05–4,26 | 2,88 · 2,87 · 3,74 | 4,14–4,16 |
| 4 MiB | 9,55 · 9,62 · 9,66 | 4,14–4,17 | 9,50 · 10,16 · 9,62 | 4,14–4,16 |
| 16 MiB | 49,67 · 49,28 · 48,95 | 4,08–4,22 | 48,08 · 47,46 · 46,71 | 4,15–4,17 |
| 48 MiB | 60,76 · 59,52 · 60,17 | 4,12–4,19 | 62,04 · 61,61 · 61,84 | 4,15–4,17 |
| 192 MiB | 64,01 · 66,39 · 63,60 | 4,05–4,18 | 65,53 · 66,02 · 65,42 | 4,13–4,14 |
| 1 GiB | 64,64 · 64,66 · 64,24 | 4,18–4,25 | 66,78 · 66,77 · 66,16 | 4,07–4,08 |

Dentro de las cachés coincide al 2 %. En la RAM hay un 3 % en nanosegundos,
pero multichase midió más despacio: en ciclos son 269–275 frente a 269–272.

| Nivel | ns | Ciclos |
|---|---|---|
| L1 | 0,97 · 0,96 · 0,96 | 4,0 · 4,0 · 4,0 |
| L2 | 2,98 · 2,85 · 2,86 | 12,1 · 12,0 · 12,0 |
| L3 | 9,25 · 9,04 · 9,06 | 38,5 · 37,8 · 37,9 |
| RAM | 64,64 · 64,66 · 64,24 | 274 · 275 · 269 |

Los ciclos de la L1 y la L2 son los de multichase (3,9 y 11,9). La curva
sube donde acaba cada caché en las seis pruebas.

| Bloque | Silux con páginas de 4 KiB, ns | MLC `-e -r`, ns |
|---|---|---|
| 4 MiB | 12,52 · 11,36 · 11,55 | 12,0 · 12,0 · 12,0 |
| 16 MiB | 51,75 · 51,61 · 49,11 | 55,0 · 54,6 · 55,3 |
| 48 MiB | 68,74 · 67,86 · 67,86 | 71,6 · 71,5 · 71,7 |
| 192 MiB | 75,78 · 75,87 · 76,52 | 79,4 · 79,3 · 78,9 |
| 1 GiB | 78,96 · 78,87 · 78,77 | 84,7 · 85,0 · 84,7 |

MLC queda entre un 2 y un 4 % por encima en ciclos, y un 7 % en la
transición de 16 MiB. No está explicado: su frecuencia es la media de sus
hilos, y uno de ellos lo lanza en la CPU 0.

### Ancho de banda

| Medida, GB/s | Silux | Referencia |
|---|---|---|
| Lectura, 1 hilo (AVX2) | 20,4 · 21,5 · 22,1 | `bw_mem rd` 18,1 · 18,1 · 18,2; MLC ALL Reads 18,5 · 17,3 · 20,1 |
| Escritura, 1 hilo | 12,5 · 13,6 · 13,4 | `bw_mem wr` 12,5 · 12,5 · 12,5; MLC 1:1 ÷ 2: 13,0 · 13,1 · 13,2 |
| Copia, 1 hilo | 14,3 · 14,8 · 14,8 | `bw_mem cp` × 2: 16,0 · 16,0 · 15,9; MLC 2:1 × ⅔: 16,9 · 16,5 · 16,8 |
| Lectura, 12 hilos | 30,5 · 31,6 · 31,9 | MLC ALL Reads 32,3 · 33,9 · 31,1 |
| Escritura, 12 hilos | 12,1 · 12,2 · 12,1 | MLC 1:1 ÷ 2: 11,8 · 11,9 · 10,9 |
| Copia, 12 hilos | 16,9 · 16,9 · 16,7 | MLC 2:1 × ⅔: 17,1 · 18,1 · 16,4 |

Con todos los hilos y en la escritura cuadra a un 5 %. La copia de un hilo
sale entre un 8 y un 12 % por debajo, cuando en el 5800X3D cuadraba.

La lectura de un hilo sale por encima, en parte por el bucle. Alternando,
AVX2 da 20,2–21,1 GB/s y SSE2 18,9–19,9: aun así, SSE2 queda entre un 4 y
un 10 % por encima de `bw_mem`.

| Sin pasar por la caché, GB/s | Silux | MLC (`--loaded_latency -T -d0`) | STREAM Copy |
|---|---|---|---|
| Escritura, 1 hilo | 37,3 · 36,9 · 36,2 | `-W6` 34,9 · 35,4 · 35,4 | |
| Escritura, 12 hilos | 33,7 · 34,2 · 33,1 | `-W6` 31,9 · 32,1 · 31,6 | |
| Copia, 1 hilo | 19,8 · 19,9 · 19,9 | `-W8` 26,2 · 24,4 · 26,2 | 27,9 · 27,8 · 27,8 |
| Copia, 12 hilos | 25,4 · 25,5 · 25,4 | `-W8` 25,2 · 25,2 · 25,2 | 25,0 · 25,1 · 25,1 |

La escritura sin caché va más deprisa que la lectura, también en MLC: no
trae la línea antes de escribirla. La copia de un hilo se queda un 25 a un
30 % por debajo de MLC y de STREAM; con doce hilos, cuadra.

### La frecuencia, según el gestor de energía

| Gestor | Frecuencia de los puntos | Aviso |
|---|---|---|
| auto-cpufreq | de 2,89 a 4,25 GHz en una misma prueba | sí, un 32 % |
| Turbo fijo encendido | de 4,05 a 4,27 GHz | no |
| tuned, perfil `balanced` | de 4,13 a 4,27 GHz | no |

auto-cpufreq apaga el turbo a mitad de la prueba, y lo medido con el reloj
bajo sale más lento en nanosegundos. Con los otros dos, el turbo solo baja
algún escalón y la prueba no avisa: lo hace desde un 10 %.

### El máximo de la memoria

En la ventana, con permisos: la lectura más rápida, 33,2 GB/s con 12 hilos,
es el 78 % de 2 canales × 2666 MT/s × 8 B = 42,7 GB/s.
