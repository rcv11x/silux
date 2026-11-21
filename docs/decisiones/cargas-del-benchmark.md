# Las cargas del benchmark: cuáles, cómo se miden y lo que falta

**Decisión.** Cinco cargas de la biblioteca estándar (`zlib`, `bz2`,
`hashlib`), cada una rodada antes de medirla y sin atar el hilo a ningún
núcleo. La compresión pesada es bzip2. No hay carga de coma flotante.

**Por qué bzip2 y no LZMA** (escala v4). La compresión pesada fue
`lzma.compress(MEDIO, preset=0)` hasta que se midió de dónde venía la
dispersión de la puntuación multihilo. LZMA alterna entre dos velocidades
(25 800 y 32 500 operaciones por segundo en un 5800X3D, un 26 %) según le
caiga o no una tormenta de fallos de página: 280 000 por segundo contra
ninguno, de los búferes que pide en cada llamada. El estado se decide por
proceso, tarda de cero a más de veinticinco segundos en asentarse y a veces
no se asienta; dentro de una medida es plano, así que alargarla no lo
promedia. La puntuación entera dispersaba un 4,7 % entre repeticiones del
mismo equipo; sin esa carga, un 0,3 %.

Se intentó domarla:

- rodar más no basta, porque a veces no se calma nunca;
- `mallopt` con el umbral de `mmap` fijo lo empeora (a 256 KB baja a
  4 787 op/s), porque apaga el ajuste dinámico de glibc, que es lo que
  llevaba al estado bueno;
- bajar el diccionario lo hunde a un tercio, y subirlo a 1 MB, a un octavo;
- con `preset=1` los fallos casi desaparecen y sigue dispersando un 18 %:
  LZMA tiene otra fuente de inestabilidad que no se aisló.

bzip2 dispersa un 2,1 % en vez de un 20,6 % y reparte igual de bien (×9,9
con dieciséis hilos, contra ×10,9). Es más lenta en operaciones por segundo,
y da igual: se compara contra el patrón.

**Sin coma flotante.** Todo lo que la haría en Python sin dependencias
(sumar o multiplicar listas) tiene el bucle en C pero maneja objetos del
intérprete, así que no suelta el GIL: escala ×1,0 con dieciséis hilos. Una
prueba multihilo que no reparte mide el candado, no el procesador.

**El rodaje.** La primera vez que una carga corre en un proceso da una cifra
distinta de las siguientes: lo que se paga es del asignador, que sirve con
`mmap` los búferes holgados hasta que glibc sube su umbral. Con LZMA eran
1 780 op/s la primera vez y 2 950 después (un 65 %); con bzip2, un 2,7 % a un
hilo (151,7 y 156,0). Como el orden es un hilo primero, el sesgo caía
siempre en la cifra de un hilo. Con unas ochenta vueltas ya está en régimen;
se dejan ciento veinte.

**Sin atar el hilo** (se quitaron `_fijar_afinidad` y `_nucleo_preferido`).
Atar la medida de un hilo al núcleo que el firmware señala como mejor iba a
quitar ruido y hacía lo contrario: costaba un 40 % en la compresión pesada y
un 11 % en la derivación de clave, con la misma dispersión o peor. Y como
solo se ataba al medir con un hilo, la penalización caía siempre ahí: 1 771
op/s a un hilo y 24 842 a dieciséis, catorce veces en un procesador de ocho
núcleos. Sin atar, 3 004 y 24 099, ocho veces. Si vuelve a hacer falta, con
una medición delante: la dispersión sin atar, con el gobernador en
«performance», fue del 1,3 % al 3,3 % según la carga.

**Lo que costó quitar zlib de la puntuación** (escala v6, en
[escala-del-benchmark.md](escala-del-benchmark.md)). No se fueron tres
cargas: se fue un perfil. Las dos únicas donde tener más hilos por núcleo
resta estaban entre las que salieron. En un i5-10400, doce hilos contra sus
seis núcleos:

| Carga | Con SMT |
|---|---|
| Compresión | +0,5 % |
| Resumen criptográfico | +4,0 % |
| Compresión pesada | +15,0 % |
| Derivación de clave | −5,3 % |
| Verificación | −13,1 % |

Con las cinco, el SMT sale a +0,2 % neto (481 contra 483); con las dos que
quedan, a +9,5 %. La cifra sigue distinguiendo piezas (las distancias entre
cuatro configuraciones se mantienen o crecen), pero premia el SMT más de lo
que el equipo da en un abanico de trabajos.

**Lo que falta.** La carga que tape ese hueco tiene que ser código máquina
propio, como el de `membench`: lo único que no cambia de un entorno a otro
(12,95 y 13,02 millones de saltos por segundo en Python 3.14 y 3.10, ±0,7 %).
Y con dos condiciones, las dos medidas:

1. **De lectura secuencial, no de latencia.** La persecución de punteros
   escala ×12,24 con doce hilos: premia el SMT aún más, porque la latencia
   es lo que el SMT tapa. Hace falta saturar el bus: leyendo, un i5-10400 da
   21-27 GB/s con un hilo, 32 con seis y 29 con doce (×0,89 de seis a doce).
2. **Un bloque propio por hilo.** Con el bloque compartido, como el de la
   verificación, los hilos recorren el mismo camino y se sirven unos a otros
   desde la caché: doce hilos «miden» 131 GB/s en un equipo cuya RAM da 32.

**Dónde vive.** `silux/benchmark.py`.
