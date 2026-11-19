# Benchmark, puntuación y medida de la memoria

Cómo se puntúa, por qué así, y lo que mide la pestaña de Memoria con su
referencia externa.

## La escala

**La escala del benchmark está cerrada y en master.** La rama `escala-v6`
contestó la pregunta que dejó abierta la `escala-v5`: si el factor de zlib era
una constante que se pudiera registrar o algo que había que quitar de en medio.
Lo contestó la máquina de la cuarta auditoría, un i5-10400, midiendo la misma
pieza el mismo día con lo que trae cada distribución: 14,9 GB/s de
verificación con la zlib-ng de Fedora, 3,9 con la de Debian, 2,0 con la de Arch
y 1,5 con la de Ubuntu 22.04, que es la que va dentro del AppImage. Un ×9,7
que no es del procesador, y `libz.so.1` elige ruta mirando el CPUID, así que
registrar la implementación tampoco habría bastado.

Así que **desde la v6 puntúan dos cargas de las cinco**: el resumen
criptográfico —190,05 · 190,13 · 190,17 op/s en tres distribuciones y dos
versiones mayores de OpenSSL— y la compresión pesada, que se mueve un 3 %. Las
otras tres se siguen midiendo y enseñando con un asterisco y con la biblioteca
que las midió al lado, porque son buen diagnóstico: son justamente las que
delatan qué hay debajo. `scores.json` está remedido en el patrón y la escala
sube a v6, así que las pruebas guardadas con la anterior se quedan sin cifra
—y no llegó a haber ninguna v5 publicada—.

**La `escala-v5` no se fusiona**: quedó superada, y su único commit se replicó
al poner la v6 encima de master. Las dos ramas se pueden borrar y
no se han borrado todavía: siguen en local y en el remoto.

## La memoria, medida

De Memoria sale el detalle de cada módulo —lo que publica SMBIOS y, cuando el
firmware suelta el bus i2c, el chip SPD entero—, el ancho de banda de lectura
medido con su fracción del teórico, y **la latencia por nivel de caché y de la
RAM**, que es la fila que separaba esta pestaña del Cache & Memory Benchmark de
AIDA64. Sale de doce bytes de código máquina que persiguen punteros, la misma
técnica que `rawcpuid.py` usa para CPUID desde el primer día: 0,9 · 2,7 · 12,3
· 80,6 ns en un 5800X3D con DDR4-3200 contra los 0,9 · 2,7 · 12,4 · 66,1 de AIDA64 en
esa misma pieza con memoria más rápida.

Hay una referencia con la que contrastar, y es de la misma pieza: la captura
del Cache & Memory Benchmark de AIDA64 de otro 5800X3D —DDR4-3600 CL14 en una
MSI B550, o sea otra memoria y otra placa—. Da **L1 0,9 ns · L2 2,7 · L3
12,4 · RAM 66,1**, y **lectura 51,8 GB/s ·
escritura 28,8 · copia 50,1**, con las cachés a 2192, 1111 y 623 GB/s de
lectura. Las latencias de caché valen como comprobación directa porque
dependen del silicio y del reloj y no de la memoria: el kernel de código
máquina dio aquí 0,9, 2,8 y 11,4. Lo que cambia con la RAM —la latencia de
memoria y los anchos de banda— solo sirve de orden de magnitud.

De ahí sale además una duda resuelta: **la escritura a 25 GB/s que se midió
aquí no era un artefacto de `memset`.** Ese 5800X3D da 28,8 escribiendo contra
51,8 leyendo, así que en Zen 3 la escritura ronda la mitad de la lectura y la
cifra es del hardware. Lo que despistaba era la comparación con un i7-8700K,
donde escribir sale tan rápido como leer.

Queda pendiente:

- **El ancho de banda de las cachés**, que hoy topa en los 112 GB/s de `memchr`
  cuando una L1 anda por los 1400. Pide el mismo camino que la latencia y no
  está probado.
- **La escritura y la copia**, medidas ya (25 y 41 GB/s) y sin enseñar. La
  duda que las tenía apartadas —si la escritura a la mitad de la lectura era
  del hardware o de cómo escribe `memset`— está resuelta arriba: es del
  hardware. Solo falta pintarlas.
- **El FCLK de los Ryzen**, que es de lo más mirado en esa plataforma —la
  sincronía con el reloj de memoria— y no está por ningún lado. En las APU sí
  hay por dónde, y es una tabla que ya se parsea: `gpu_metrics` v2.x lo trae en
  `average_fclk_frequency` (offset 70) y `current_fclk` (82), al lado del
  `current_uclk` que ya se lee como reloj de memoria. Son dos posiciones más en
  `_V2_1`. En un sobremesa con gráfica dedicada no hay tabla del SoC a la que
  preguntar y lo único que queda es `ryzen_smu`, que es un módulo fuera del
  kernel: ahí no se llega.
