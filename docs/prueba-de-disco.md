# La prueba de disco: cómo comprobarla tú mismo

La pestaña Disco de Rendimiento da cuánto lee y escribe un disco, seguido y a
saltos, y cuánto tarda en contestar una petición suelta. Aquí está cómo se
mide, qué acompaña a cada cifra para que te puedas fiar de ella, las órdenes
para repetirla con fio y en qué se diferencia de CrystalDiskMark y de
KDiskMark.

Lo mide un módulo nativo en Rust (`native/silux_bench/`), en un proceso
aparte y sin permisos de administrador. Las tablas de abajo son de un solo
equipo y de lecturas; lo que falta por validar está al final.

## Qué mide y cómo

Las cuatro pruebas de CrystalDiskMark, con su misma notación:

| Prueba | Qué hace |
|---|---|
| SEQ1M Q8T1 | Bloques de 1 MiB uno tras otro, ocho peticiones a la vez |
| SEQ1M Q1T1 | Lo mismo, de una en una |
| RND4K Q32T1 | Bloques de 4 KiB en cualquier parte del archivo, 32 a la vez |
| RND4K Q1T1 | Lo mismo, de una en una; además da las peticiones por segundo y cuánto tarda cada una |

Q es cuántas peticiones se mantienen en cola y T cuántos hilos las hacen.
Cada una se mide en lectura y, si se pide, en escritura. Las cifras van en
MB/s de un millón de bytes.

Son el perfil **Estándar**. El perfil **Uso real** hace solo las dos de una
en una, que es lo que pide casi cualquier programa, y tarda la mitad. El
historial agrupa cada perfil aparte: sus cifras no se comparan entre sí.

- **El archivo.** Un archivo temporal de 1 GiB en la carpeta que se elija,
  nunca el dispositivo. **No tiene nombre**: se crea con `O_TMPFILE` (o con
  un nombre que se le quita antes de escribir el primer byte, donde el
  sistema de archivos no admite lo primero), así que el kernel lo libera
  cuando el proceso termina, se cancela o muere. No queda nada que borrar.
  Antes se comprueba que cabe con un margen libre, y se reserva su espacio.
  El margen es 1 GiB en el sistema de archivos del sistema (el de `/`,
  `/home` o `/var`), donde quedarse sin sitio rompe los registros y las
  actualizaciones, y en btrfs, que lleno puede quedarse sin sitio para sus
  metadatos. En los demás, el 5 % de su tamaño, entre 32 MiB y 1 GiB: así
  un pendrive pequeño casi lleno se puede probar. La pestaña lo mira antes
  de empezar: ofrece el mayor tamaño que cabe, o dice que no cabe ninguno.
- **Sus datos.** Al azar, para que nada los comprima, y con un sello cada
  4 KiB que dice a qué parte del archivo va cada bloque: no hay dos bloques
  iguales, y cada lectura se comprueba contra el sello del bloque que pidió.
  Sellar cuesta 0,5 ns por bloque de 4 KiB y 1,1 µs por bloque de 1 MiB.
- **Sin pasar por la memoria del sistema.** Lee y escribe con `O_DIRECT`. En
  btrfs el archivo se aparta además de las copias y las sumas (`+C`): sin
  eso, desde Linux 6.15 una escritura directa pasa por la caché, y la
  lectura sale hasta un 40 % más baja (tabla de abajo).
- **La cola.** Con io_uring, un hilo mantiene la cola llena. Donde no hay
  io_uring (un contenedor, o un sistema que lo prohíbe), la cola se hace con
  hilos de una petición cada uno, y **la prueba se llama por lo que es**:
  «RND4K Q1T32», no «RND4K Q32T1». No es la misma prueba ni da la misma
  cifra.
- **Por tiempo, no por cantidad.** Antes de cada prueba, 5 s de pausa y una
  vuelta que no cuenta; después, cinco vueltas de 5 s. **La cifra es la
  vuelta del medio.** La mejor y la peor están en «Detalles».
- **Cuánto escribe.** El archivo una vez y, con la escritura marcada, todo
  lo que el disco admita durante dos minutos: 242 GB en un NVMe PCIe 4.0 y
  216 GB en uno PCIe 3.0, medidos. La pestaña lo dice antes de empezar y el
  resultado dice lo que escribió de verdad.
- **En un pendrive o una tarjeta.** FAT32 no guarda archivos de 4 GiB o
  más: la pestaña lo dice antes de empezar y ofrece 4095 MiB, si hay sitio
  libre para ellos. Si escribir el
  archivo va a tardar, lo dice también: con lo que escribió ese disco la
  última vez, o al menos lo que tarda por su conexión. Mientras lo escribe,
  dice lo que falta.
- **Un disco que se va.** «Dónde» sigue a lo que está montado. Si el disco
  elegido se desconecta o se desmonta, la pestaña lo dice y deja de estar
  elegido; si se va a mitad de la prueba, el error es que se desconectó.

## Lo que acompaña a cada cifra

- **Qué pasó por la caché.** Tras cada prueba se pregunta al kernel cuánto
  del archivo tiene en memoria (`mincore`). Leyendo y escribiendo directo es
  cero; si no, el resultado lo dice y las cifras no son las del disco. En
  FAT32, exFAT y NTFS la prueba se para ahí: pasan por la caché sin dar
  error, y lo que siguiera sería la memoria.
- **Lo que movió el disco.** Sus propios contadores (`/sys/block/…/stat`)
  antes y después de cada prueba, contra lo que contó el motor. Si movió
  menos, algo contestó por él; si movió bastante más, otro programa lo
  estaba usando.
- **Si las vueltas variaron.** Una prueba cuyas vueltas se separan más de un
  5 % sale marcada, con la mejor y la peor.
- **La temperatura** del disco al empezar, la más alta y al acabar.
- **Dónde se midió**: el disco, su conexión, el sistema de archivos, el
  motor, y lo que hay entre la carpeta y el disco (cifrado, varios discos,
  un driver fuera del kernel), cada cosa con su aviso.
- **Dónde no se mide**: una carpeta en memoria (`/tmp` en muchos sistemas),
  en red o de solo lectura se rechaza antes de crear nada, con su motivo.

## Cómo repetirlo con fio

fio no viene con Silux. Con los mismos parámetros que cada prueba:

```bash
fio --name=prueba --filename=ARCHIVO --size=1g --direct=1 \
    --ioengine=io_uring --rw=read --bs=1m --iodepth=8 \
    --runtime=5 --time_based --randrepeat=0 --output-format=json
```

Las demás cambian `--rw` (`write`, `randread`, `randwrite`), `--bs` (`4k`) y
`--iodepth` (1, 32). La cifra es `bw_bytes` entre un millón, no `bw`. Cuatro
cosas que cambian el resultado y no se ven:

1. **En btrfs, el archivo de fio tiene que llevar `+C`, y fio lo pierde.**
   fio borra y vuelve a crear el archivo al prepararlo, así que
   `chattr +C ARCHIVO` no sirve. Va dentro de una carpeta con el atributo:
   `mkdir carpeta && chattr +C carpeta`, y el archivo dentro. Sin eso su
   archivo lleva sumas y se lee más despacio.
2. **fio envía las peticiones de una en una.** Para la RND4K Q32T1 hay que
   añadir `--iodepth_batch_submit=32 --iodepth_batch_complete_min=1
   --iodepth_batch_complete_max=32`; sin ellas fio da un 35 % menos en un
   disco rápido, limitado por su propio hilo.
3. **Los dos sobre el mismo archivo.** Dos archivos en dos sitios del disco
   difieren del 2 al 4 %. Mientras la prueba de Silux tiene su archivo
   abierto, fio puede leer ese mismo por `/proc/PID/fd/N`.
4. **Sin io_uring**, la prueba equivalente es
   `--ioengine=psync --numjobs=N --thread --group_reporting`.

## En qué se diferencia de CrystalDiskMark y de KDiskMark

| | Silux | CrystalDiskMark | KDiskMark |
|---|---|---|---|
| Motor | propio, io_uring | diskspd | fio con `libaio` |
| Permisos | ninguno | administrador | root, con un ayudante |
| Cifra de las vueltas | la del medio | la mejor | la media |
| MB/s | de un millón de bytes | de un millón de bytes | KiB/s entre 1000: un 2,4 % de más |
| Caché del sistema | se salta y se comprueba | se salta | se salta y se vacía |
| Archivo | sin nombre | con nombre, se borra al acabar | con nombre, se borra al acabar |

Para comparar con CrystalDiskMark, la cifra es «Mejor» en «Detalles».

## Validación

SN850X de 1 TB (PCIe 4.0 ×4, btrfs con `+C`) y 970 EVO Plus de 2 TB
(PCIe 3.0 ×4, ext4) en un Ryzen 7 5800X3D, Linux 7.3.5, fio 3.43,
planificador kyber. 24 de noviembre de 2026. Solo lecturas; MB/s; fio lee el
mismo archivo, por turnos, con 5 s de pausa antes de cada medida.

### 970 EVO Plus, ext4

| | Silux io_uring | fio io_uring | Silux con hilos | fio psync |
|---|---|---|---|---|
| SEQ1M Q8 | 3615 · 3576 | 3606 · 3579 | 3616 · 3591 | 3615 · 3615 |
| SEQ1M Q1 | 2691 · 2694 | 2695 · 2691 | 2692 · 2694 | 2691 · 2695 |
| RND4K Q32 | 1009 · 1014 | 666 · 677 | 1076 · 1076 | 1073 · 1074 |
| RND4K Q1 | 48,8 · 48,7 | 49,0 · 49,0 | 48,8 · 48,7 | 48,7 · 48,6 |
| °C antes → después | 43 → 48 · 48 → 51 | | | |

Todo a menos del 0,7 %, salvo la RND4K Q32 por io_uring. Con las opciones de
lotes de fio (tres rondas, 50 → 52 °C):

| RND4K Q32 | Silux io_uring | fio por defecto | fio con lotes |
|---|---|---|---|
| | 1073 · 1073 · 1074 | 675 · 675 · 679 | 1066 · 1065 · 1065 |

### SN850X, btrfs con `+C`

| | Silux io_uring | fio io_uring | Silux con hilos | fio psync |
|---|---|---|---|---|
| SEQ1M Q8 | 6392 · 6302 | 6764 · 6643 | 6745 · 6625 | 6712 · 6564 |
| SEQ1M Q1 | 2371 · 2091 | 3081 · 2111 | 3082 · 2087 | 3071 · 3207 |
| RND4K Q32 | 294 · 291 | 296 · 309 | 345 · 354 | 352 · 342 |
| RND4K Q1 | 59,0 · 59,0 | 59,2 · 59,2 | 59,3 · 59,4 | 59,3 · 59,2 |
| °C antes → después | 44 → 47 · 47 → 47 | | | |

La RND4K Q1 y la Q32 cuadran. La SEQ1M Q8 por io_uring sale un 5 % por
debajo de fio las dos veces, sin explicar todavía. La SEQ1M Q1 cambia de una
medida a otra con los dos programas: ver «Límites».

### El archivo de fio en btrfs, sin `+C`

fio leyendo por turnos su propio archivo y el de Silux:

| | SN850X btrfs, el suyo | el de Silux | 970 ext4, el suyo | el de Silux |
|---|---|---|---|---|
| SEQ1M Q1 | 2245 · 2077 | 3016 · 2957 | 2604 · 2601 | 2658 · 2658 |
| RND4K Q1 | 57,9 · 57,4 | 61,3 · 61,3 | 46,8 · 46,9 | 48,6 · 48,7 |
| SEQ1M Q8 | 6140 · 6228 | 6670 · 6630 | 3500 · 3507 | 3616 · 3615 |
| °C antes → después | 47 → 54 | | 45 → 51 | |

### Dos tandas seguidas, cada una con su archivo

La cifra de cada prueba (la vuelta del medio), con archivo nuevo cada vez:

| | 970 ext4, tanda 1 | tanda 2 | SN850X btrfs, 1 | 2 | 3 |
|---|---|---|---|---|---|
| SEQ1M Q8 | 3571 | 3601 | 6642 | 6119 | 6740 |
| SEQ1M Q1 | 2664 | 2652 | 2999 | 2493 | 2956 |
| RND4K Q32 (hilos) | 1052 | 1126 | 349 | 350 | 316 |
| RND4K Q1 | 47,8 | 51,6 | 61,1 | 60,8 | 60,4 |
| °C antes → después | 41 → 51 | 51 → 57 | 51 → 55 | 55 → 56 | 56 → 57 |

### Una tanda entera, con escritura

| | SN850X, btrfs con `+C` | 970 EVO Plus, ext4 |
|---|---|---|
| SEQ1M Q8T1, lectura · escritura | 6592 · 3946 | 3579 · 3322 |
| SEQ1M Q1T1 | 3172 · 3390 | 2644 · 3082 |
| RND4K Q32T1 | 268 · 363 | 1075 · 507 |
| RND4K Q1T1 | 63,3 · 222 | 48,1 · 258 |
| Escribió | 241,7 GB | 216,2 GB |
| °C al empezar · la más alta · al acabar | 50,9 · 62,9 · 53,9 | 39,9 · 56,9 · 55,9 |

En las 16 medidas, nada en la caché y los contadores del disco a 1,00 de lo
contado (una a 1,03). Las escrituras no se han comparado con fio.

### Lo que falta por validar

- **Las escrituras contra fio**, en los dos discos.
- **Un disco de platos, un SSD SATA y una memoria USB.**
- **El camino sin io_uring en un sistema que lo prohíbe**
  (`sysctl kernel.io_uring_disabled=2`), y dentro de un contenedor.
- **ext4, XFS, f2fs, exFAT, NTFS y FAT32** más allá de ext4 y btrfs. vfat,
  exfat y ntfs3 aceptan `O_DIRECT` y tienen caminos que pasan por la caché
  sin dar error: la comprobación de la caché tiene que verlo en un disco de
  verdad.
- **La SEQ1M Q8 por io_uring en btrfs**, un 5 % por debajo de fio.
- **Otro equipo.**

## Límites

- **En el SN850X con btrfs las pruebas de una en una salen en varios
  modos.** La RND4K Q1 da 87 MB/s (47 µs por petición) si el disco no ha
  parado, y 60 (77 µs) si ha estado quieto más de unos 150 a 300 ms; con la
  pausa de 5 s antes de cada prueba, que es también la de CrystalDiskMark,
  sale siempre la segunda. La SEQ1M Q1 da 4,7, 3,2 o 2,3 GB/s sin una regla
  que se haya encontrado. fio da lo mismo en el mismo momento. No es el
  reposo del procesador (probado con C2 desactivado), ni el ahorro de
  energía de la conexión (ASPM está apagado), ni el del disco (probado con
  APST desactivado). Queda el propio disco o btrfs, sin separar. El 970 con
  ext4 no lo hace.
- **La RND4K Q32 en ese mismo disco da 270 a 400 MB/s**, cuatro veces menos
  que el 970 con ext4, con los dos programas. No es la temperatura. Sin
  separar si es btrfs con muchas lecturas directas a la vez sobre un archivo
  o el disco.
- **Una cola hecha con hilos no es una cola.** En un disco rápido, 32 hilos
  con una petición cada uno dan más que una cola de 32 en un hilo. Por eso
  lleva otro nombre.
- **En un disco de platos** la velocidad seguida depende de en qué parte del
  plato cae el archivo, y cae donde hay hueco. El resultado dice entre qué
  porcentajes del disco quedó, preguntándolo al kernel (`FIEMAP`): el
  principio es la parte de fuera, la más rápida. Solo se sabe con ext4, XFS
  o f2fs directamente sobre una partición; con btrfs, LVM, RAID o cifrado,
  dice que no se sabe.
- **La cifra incluye lo que hay entre la carpeta y el disco**: el cifrado,
  el sistema de archivos, un RAID. Es la velocidad de esa carpeta.
