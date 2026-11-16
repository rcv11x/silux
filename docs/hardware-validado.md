# Qué se ha probado contra qué hardware

Lo que sale de cada fuente, qué se ha validado con una pieza delante y qué
se escribió a ciegas, y lo que queda pendiente por plataforma.

## Equipos volcados

En `tests/fixtures/equipos/`, cada uno con su `manifiesto.json`. La suite
monta el Collector contra todos (`tests/test_equipos.py`).

| Volcado | Procesador | Gráfica | Notas |
|---|---|---|---|
| `i5-10400` | Intel Core i5-10400 (Comet Lake-S) | UHD Graphics 630 | Fedora 44; volcado con el turbo apagado por el gestor de energía |
| `i5-10400-turbo` | el mismo | el mismo | con carga, a los 5 s: `auto-cpufreq` ya había encendido el turbo (techo 4,3 GHz, los 12 hilos a 4,0) |
| `5800x3d` | AMD Ryzen 7 5800X3D (Zen 3, AM4) | Radeon RX 9070 XT | CachyOS, kernel 7.3; placa X570, dos monitores, cinco discos (dos montados fuera del sistema); en reposo. De las interfaces de Docker queda una de cada |

Todos son sin permisos. Lo que se arregle en lo que lee el procesador o la
gráfica se comprueba contra un volcado de Intel y contra el de AMD.

## Por plataforma

De Gráficos sale todo lo que publica el nodo DRM —identidad, VRAM, tabla DPM,
enlace PCIe, sensores propios— más lo que solo da el ioctl de amdgpu (tipo de
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

**El contador del IMC ya está**, que era la otra mitad de esa línea: cuánto
tráfico mueve la memoria ahora mismo, en la ficha, en el árbol de sensores y en
el informe. Sale del PMU del uncore por el ayudante privilegiado —los
contadores de perf piden CAP_PERFMON y `perf_event_paranoid` viene a 2 en
cualquier distribución—, y el nombre del PMU cambia con la generación:
`uncore_imc` hasta Comet Lake, `uncore_imc_free_running_N` de Ice Lake en
adelante y `uncore_imc_N` en los de servidor, que además llaman a sus eventos
por el comando de la DRAM. Va en bytes por segundo para compartir con
`membench` el porcentaje del teórico, que si no serían dos cifras de la misma
página que no se pueden comparar. Se validó contra tráfico de tamaño conocido
en el i5-10400: diez GiB leídos a propósito con `memchr` y diez escritos con
`memset`, y el contador vio 9,95 y 10,30 descontando el fondo. En el árbol de
sensores estrena la rama «Tráfico» y el aparato «Memoria», cuyo hueco llevaba
reservado en `_puesto_del_aparato` desde que se escribió el orden, vacío.

**Y es de Intel a propósito, no por falta de ganas.** De Zen 4 en adelante
existe `amd_umc_N`, pero el kernel le registra `format` y no `events/`: los
nombres viven en el JSON de la herramienta `perf` y no en sysfs, así que
habría que escribir el número de evento a mano —`event=0x05` con su
`rdwrmask`— y afirmar lo que significa sin ninguna pieza donde comprobarlo. De
Zen 3 para atrás no hay ni eso: `amd_df` existe y sus eventos de DRAM no están
documentados. Escribir ese camino sería dejarlo estrenándose en la máquina de
otro, que es la forma exacta del `NameError` de `_identidad`. Así que en AMD
sale el aviso gris de que este equipo no lo publica, y cuando aparezca un Zen 4
al que preguntarle, lo que falta es una tabla de posiciones más.

La ficha ya está: los zócalos vacíos van juntos en una línea como las salidas
de vídeo libres, y el título de cada uno sale de `render.slot_labels`, que
compone el mínimo que lo distingue —«Canal A», y el controlador o el DIMM solo
cuando sin ellos dos se llamarían igual—, así que se acabaron los dos «DIMM 0».
Sin SMBIOS no hay zócalo que dar y se numeran «Módulo 1», «Módulo 2»: el `slot`
del SPD es la dirección en el bus i2c y no la posición en la placa.

**ARM se identifica, sin dejar de ser un programa de x86.** Donde no hay
CPUID, `providers/armcpu.py` lee el MIDR de `/proc/cpuinfo` —quién hizo el
núcleo, cuál es y en qué revisión va— y lo cruza con `db.identify_arm`, que
ya estaba escrita y sin usar. Sale «ARM Cortex-A76 r0p0», nombre en clave
«Enyo» y 10-7 nm, en vez de una interrogación. Un big.LITTLE se reparte en tipos de núcleo por el mismo
sitio por el que se reparte un Intel híbrido, que para eso `cpu.types` es una
lista. Lo atado a x86 no se finge: CPUID, DMI, RAPL y el SPD por i2c salen
como «no aplica». El resto —sysfs, hwmon, red, discos— funciona igual porque
sysfs es igual en toda arquitectura.

**NVIDIA ya está probada contra hardware.** Se escribió a ciegas siguiendo la
API documentada, porque en esta máquina no hay ninguna GeForce, y el 26 de
agosto de 2026 llegaron las capturas de dos equipos ajenos: una GTX 1660 Ti
(TU116) y una RTX 3050 Mobile (GA107M). Acertó en casi todo lo comprobable
—anchura de bus, identificadores, UUID, el enlace bajado a PCIe 1.0 en reposo
con su máximo bien leído, los motivos de recorte— así que `nvml.py` y
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
—i5-10500T, UHD 630, 31 GB en dos SODIMM, Manjaro con XFCE— y con los permisos
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
  catalogado a 2667 y funcionando a 2666 es el mismo grado JEDEC —DDR4-2666 son
  1333,33 MHz, o sea 2666,67 MT/s, que unos redondean arriba y otros abajo— y
  `MemoryModule.underclocked` comparaba `actual < rated` a pelo. **Hecho**:
  margen del 1 %, que no puede confundir dos grados —los contiguos están a 133
  MT/s en DDR4 y a 400 en DDR5— y absorbe el redondeo, que es de un MT/s.
- **Y el consejo manda a la BIOS a por algo imposible**: con un módulo de 3200
  y otro de 2667, la frase «va a 2666 de los 3200 que declara admitir, suele ser
  el perfil rápido sin activar» es falsa, porque el conjunto va al ritmo del más
  lento y ese equipo no verá 3200 active lo que active. `_apply_avisos` toma
  `lentos[0]` y usaba su velocidad catalogada, así que el diagnóstico salía
  del módulo rápido e ignoraba al que manda. **Hecho**: el techo es el mínimo
  de los catalogados y hay tres respuestas donde había dos —hay margen, no hay
  margen pero uno declara más, o no hay nada que decir—, en
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
