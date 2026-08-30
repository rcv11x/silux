# silux — contexto del proyecto

Perfilador de hardware para Linux en Python + PySide6. La idea es juntar en
un solo programa nativo lo que en Windows hacen **CPU-Z, GPU-Z y HWMonitor**:
identificación del hardware y monitorización de sensores, con buena pinta.

**Lo que este programa no es: un administrador de tareas.** Los procesos son
software, no hardware, y Linux ya tiene buenos monitores de procesos. El
hueco está en el otro lado.

## Cómo se ejecuta

```bash
python3 -m silux.ui.app                 # interfaz
python3 -m silux.cli                    # volcado en terminal
python3 -m silux.cli --json             # API para otros programas
python3 -m silux.cli --sensors          # el árbol de sensores
python3 -m silux.cli --report FICHERO   # informe para adjuntar a un fallo
python3 tools/gen_cpu_db.py            # regenerar la base de datos de CPUs
python3 tools/gen_lang.py --write      # poner al día los archivos de idioma
python3 tools/medir_referencia.py      # rehacer la escala de puntuación
python3 tools/anadir_puntuacion.py INFORMES  # sumar medidas ajenas a la tabla
python3 tools/install_desktop.py       # icono y entrada de menú
python3 tools/build_appimage.py --container   # el AppImage que se reparte
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .
```

Los tests son **1192** y tardan poco más de un minuto. Si sale bastante
menos, falta algo por recoger.

`--container` no es opcional para repartir: sin él se construye contra el
Python y el Qt de la máquina, y sale un AppImage que exige el juego de
instrucciones y la glibc de quien lo compiló. Con contenedor sale
`x86-64` a secas —cualquier procesador de 64 bits, de 2003 en adelante— y
glibc **2.35**, que es la de Ubuntu 22.04, la base del contenedor. Eso deja
fuera Ubuntu 20.04, Debian 11, Mint 20 y RHEL 9, que se quedan en 2.31-2.34.
El símbolo que más alto pide es `hypot@GLIBC_2.35` del propio intérprete: para
bajar el suelo hay que construir sobre una base más antigua con Python 3.10
puesto a mano, no basta con tocar una opción. El paso final de comprobación recorre el
AppDir y avisa de lo que resuelve fuera. Si avisa de algo, hay que mirarlo:
lo que sale ahí es una biblioteca que el programa espera encontrar puesta en
la máquina ajena. Después mira el juego de instrucciones, por lo mismo: que
no se cuele un requisito de procesador que aquí no se nota.

**PySide6 está topado en `<6.10`, y el motivo no es de estilo.** Qt 6.10 pasó
a compilarse con `-march=x86-64-v2`, y no en rutas aparte que se eligen
mirando la CPU, sino dentro de funciones normales: `QString`,
`QUtf8::convertToUnicode`, `QPainterPath::quadTo`. En un procesador sin
SSE4.1 eso es «Instrucción ilegal» y un volcado antes de pintar nada; Qt trae
un aviso para ese caso —«Incompatible processor»— y ni siquiera llega a
salir, porque revienta antes de imprimirlo. x86-64-v2 es Nehalem (2008) en
Intel y Bulldozer (2011) en AMD, así que deja fuera los Core 2, los Athlon II
y los Phenom II: justo la clase de equipo cuyo dueño quiere saber qué lleva
dentro. Lo descubrió un Athlon II X2 250u ajeno, no una prueba de aquí. De
6.9 a 6.11 no hay nada en QtCore, QtGui ni QtWidgets que este programa use,
así que el techo no cuesta nada; lo que costaría es quitarlo sin mirar.

Cada copia lleva dentro de qué commit salió: debajo de la versión, en
`--version` y en la cabecera del informe. Lo escribe el empaquetador en
`silux/_build.txt` —dentro del AppImage no hay repositorio al que preguntar— y
desde el código fuente se lee de git en vivo. Un `+` al final avisa de que esa
copia tenía cambios sin guardar. Nace de que las capturas que manda la gente no
decían de qué versión eran, y un fallo ya corregido se investigaba dos veces.

**Un clic en un valor lo copia**, en las fichas y en las tablas. Se copia el
texto entero y no el que se ve: la fila que no cabe y sale con puntos
suspensivos es justo la que hace falta copiar. Un guion no se copia, porque es
la marca de un dato que falta.

Capturas sin pantalla: `python3 -m silux.ui.app --screenshot salida.png
--page Sensores --dark --compact --size 900x680`. Acepta además `--accent` y
`--font-scale` para forzar apariencia sin tocar los ajustes guardados.

## Las reglas que sostienen el diseño

Estas no son preferencias de estilo. Cada una viene de un problema concreto:

1. **El modelo guarda números, no texto.** `freq_hz: int`, nunca `"2.90 GHz"`.
   Todo el formateo vive en `silux/render.py` y ocurre al pintar. De ahí salen
   gratis la salida JSON, las gráficas y unos tests que comparan cifras. Es
   donde CPU-X se ató las manos.

2. **`Snapshot` es inmutable.** Los proveedores escriben en un `Draft`
   mutable y este se congela. La interfaz compara fotos y repinta lo que
   cambió.

3. **`cpu.types` es una lista desde el primer commit.** Cualquier Intel de
   12ª en adelante tiene núcleos P y E con cachés y frecuencias distintas.
   Asumir «una CPU, un juego de valores» obliga a reescribirlo todo después.

4. **Nada se lee en el hilo de la interfaz.** `silux/ui/sampler.py` es un
   QThread; ahí dentro se fija la afinidad para CPUID y ahí se abre el
   diálogo de polkit, que bloquea.

5. **Cuando falta un dato se explica.** Un `Note` con su motivo —root,
   driver, base de datos, hardware— en vez de esconder la sección. Cada
   página enseña solo sus propias notas (`snapshot.notes_for("cpu")`).

6. **Los widgets que se refrescan a menudo reutilizan.** Crear widgets en
   cada muestreo dejaba miles vivos y hacía crecer la memoria medio megabyte
   por minuto. `ChipRow` y `Table` reescriben el texto de lo que ya existe;
   hay tests que lo vigilan.

7. **Presupuesto de memoria: 300 MB.** Era de 100 y lo subió el autor a la
   vista de que la máquina de escritorio va sobrada: entre gastar memoria y
   enseñar un dato más, gana el dato. Ahora ronda los 130 MB con las ocho
   secciones y el árbol de sensores entero desplegado. Sigue sin ser excusa
   para malgastarla: el techo está para que alguien lo mire de vez en cuando,
   y la salida conocida es construir las páginas solo cuando se visitan.

8. **Lo que cueste memoria de forma permanente, en otro proceso.** Preguntar
   a OpenGL, Vulkan y OpenCL carga sus drivers: 118 MB de residente, de los
   que 83 son de rusticl arrastrando LLVM entero para decir «OpenCL 3.1».
   `gpuapi.consultar()` lanza `python3 -m silux.gpuapi`, lee el JSON y lo deja
   morir. De regalo, un driver que revienta ya solo se lleva al hijo.

## Cómo está repartido

```
silux/
├─ model.py        dataclasses congeladas: Snapshot, CpuType, Sensor, Board…
├─ render.py       ÚNICO sitio donde un valor se convierte en texto
├─ collector.py    orquesta los proveedores; separa estático de dinámico
├─ cli.py          volcado en terminal, JSON, sensores e informe
├─ settings.py     preferencias del usuario en ~/.config/silux
├─ tracking.py     mínimos, máximos y medias por sensor
├─ rawcpuid.py     CPUID desde Python, sin root (mmap + ctypes)
├─ gpuapi.py       OpenGL, Vulkan, OpenCL y VA-API por ctypes, en otro proceso
├─ amdgpu.py       ioctl DRM: tipo de VRAM, bus, unidades, ROP
├─ edid.py         la chapa del monitor, con sus extensiones CTA-861
├─ report.py       informe en Markdown para reportar fallos
├─ gpumetrics.py   telemetría del firmware AMD: por qué se frena la tarjeta
├─ nvml.py         NVIDIA propietaria, que no publica nada en sysfs
├─ features.py     tabla declarativa de banderas de CPUID
├─ pciids.py       nombres de dispositivos PCI desde la base del sistema
├─ spd.py          decodifica el chip de identificación de la RAM (DDR4 y DDR5)
├─ smart.py        interpreta el diagnóstico de los discos, sin privilegios
├─ benchmark.py    prueba de CPU que reporta en qué condiciones midió
├─ history.py      historial de pruebas de este equipo
├─ score.py        la puntuación comparable entre equipos, y su escala
├─ privacidad.py   qué se omite de un informe público y qué no
├─ ui/tarjeta.py  la imagen del equipo para pegar en un chat, ya anonimizada
├─ i18n.py        el idioma de la interfaz; el original es el español
├─ throttling.py  desde cuándo lleva frenándose algo, y por qué
├─ registro.py    graba la sesión a un CSV, fila a fila
├─ providers/      una fuente cada uno; ninguno conoce a los demás
├─ privileged/     ayudante root mínimo (helper.py) + cliente + SMBIOS.
│                  Lee DMI, MSR, el SMART de los discos y el PMU de la iGPU.
│                  instalar.py le da su acción de polkit para no pedir la
│                  contraseña en cada arranque; cargar_modulo.py carga un
│                  driver de sensores de una lista blanca fija
├─ db/             cpu_ids.json (generado; incluye la tabla de MIDR de ARM) +
│                  sockets.json y families.json (curados a mano; el segundo
│                  cubre lo que libcpuid no tiene)
└─ ui/             tema, hilo de muestreo, widgets, una página por sección
```

El orden de los proveedores en `collector.py` importa y está comentado ahí.

`providers/cppc.py` saca de ACPI CPPC, además de los relojes, **lo bien que
salió cada núcleo de la oblea**: los núcleos de una misma pieza no son
iguales, el firmware lo publica y el planificador lo usa para mandar ahí el
trabajo de un hilo suelto. Ryzen Master lo enseña en Windows con estrellitas;
en Linux no lo enseñaba nadie. Sale en la rejilla de núcleos de la página de
CPU y en el volcado del terminal.

## Estado

Terminadas las doce: **CPU, Cachés, Placa base, Memoria, Gráficos,
Almacenamiento, Red, Batería, Sistema, Rendimiento, Sensores, Ajustes**. La de
Batería solo aparece en los equipos que tienen una: un sobremesa no va a tener
nunca, así que dejarla puesta para decirlo sería ruido permanente en el menú.

De Gráficos sale todo lo que publica el nodo DRM —identidad, VRAM, tabla DPM,
enlace PCIe, sensores propios— más lo que solo da el ioctl de amdgpu (tipo de
memoria, anchura del bus, ancho de banda, unidades de cómputo y ROP), las tres
APIs y el EDID de cada monitor. De las Intel, el uso por motor y los vatios
salen del PMU de perf leído por el ayudante privilegiado (`gpu_pmu`); el
reposo (RC6) y los motores con sus capacidades, de sysfs sin permisos; y los
códecs que acelera, de VA-API atada a su nodo de render. Su temperatura no
existe por ningún camino. Queda pendiente:

- **Las versiones de `gpu_metrics` de la 1.4 en adelante**, que reordenaron los
  campos, y las 2.x de las APU. Hoy se reconocen y se dejan pasar en vez de
  interpretarlas mal.

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
(TU116) y una RTX 3050 Mobile (GA107M). Acertó en todo lo comprobable —núcleos
CUDA, anchura de bus, identificadores, UUID, el enlace bajado a PCIe 1.0 en
reposo con su máximo bien leído, los motivos de recorte— así que `nvml.py` y
`providers/nvidia.py` ya no son código de fe. Lo que sigue sin salir en NVIDIA
es el tipo de memoria y las unidades de rasterizado: NVML no los publica.

⚠ **ARM no se ha ejecutado contra hardware.** Está probado contra
`/proc/cpuinfo` de máquinas reales guardados en `tests/fixtures/arm/`, pero en
esta máquina no hay ningún aarch64. Quien lo pruebe en uno, que contraste con
`lscpu`.

## Cosas que ya se probaron y no funcionaron

- **Reconstruir un dataclass congelado campo a campo** al actualizarlo: se
  come en silencio los campos añadidos después. Usar `dataclasses.replace`.
- **Preguntar a Qt por `sizeHint` justo después de añadir widgets**: devuelve
  el valor anterior. O se calcula a mano, o se deja pasar un ciclo de eventos.
- **`sizeHintForColumn` en un árbol**: solo mira las filas de primer nivel.
  Hay que medir el texto recorriendo los hijos.
- **Estirar la primera columna de una tabla**: en pantalla completa manda las
  cifras a un palmo del nombre. El hueco sobrante va al final.
- **Dibujar flechas con bordes CSS en Qt**: salen cuadrados. Hay que darle una
  imagen; se generan en tiempo de ejecución en `ui/theme.py`.
- **Dar por hecho que la gráfica `N` es el nodo `cardN`**: con una sola tarjeta
  dedicada el kernel la numera `card1` y no hay `card0`. Hay que guardarse el
  nombre del nodo.
- **Leer `pp_dpm_sclk` como una tabla DPM**: en RDNA3 y RDNA4 son tres líneas
  —mínimo, actual y máximo— y la primera llega como `S:` en vez de un número
  cuando la GPU está en reposo profundo.
- **`valor or otro` con lecturas de hardware**: una GPU parada marca 0 MHz y un
  ventilador quieto 0 RPM. Eso no es un dato ausente, es la respuesta. Hay que
  comparar contra `None`.
- **Creerse el `enabled` y el `dpms` de los conectores DRM**: describen el
  modeset del kernel. Con un compositor Wayland al mando dicen «disabled» y
  «Off» de pantallas que están encendidas delante de uno.
- **Redondear al más cercano las latencias del SPD**: 16250 ps entre un ciclo
  de 357 son 45,5, y eso es un CL46: la memoria no puede responder antes de
  tiempo. Al más cercano sale un CL45 que no existe.
- **Copiar un código JEDEC tal y como se publica**: el byte que trae el SPD
  lleva paridad impar en el bit más alto, así que un módulo Crucial se presenta
  como 0x9B siendo 0x1B. Como la búsqueda quita ese bit, la tabla tiene que
  estar en la misma moneda; media lista estaba escrita con el byte completo
  —Samsung 0xCE, Kingston 0x98, SK Hynix 0xAD— y esas siete entradas no
  casaban nunca. Justo las tres marcas que más memoria venden salían sin
  fabricante. Hay un test que no deja entrar un código con el bit puesto.
- **Dar por perdida una gráfica porque su driver no diga nada**: con
  `simple-framebuffer` —el respaldo que pone el kernel al arrancar con
  nomodeset o sin driver instalado— la ficha salía entera a guiones, sin
  siquiera el nombre de la tarjeta. Ese driver cuelga de un dispositivo de
  plataforma y no de PCI, pero el bus sí la enumera aunque nadie sepa
  hablarle: de ahí salen la marca, el modelo y el enlace.
- **Dar una fila a cada conector vacío**: un MacBook Air de once pulgadas
  enseñaba cuatro filas seguidas con los seis campos a guiones —DP-1, DP-2,
  HDMI-A-1, HDMI-A-2— y solo la quinta, su pantalla, con datos. Son salidas
  que el chip expone y esa carcasa no trae. Van juntas en una línea.
- **Fiarse de `pci.ids` para el modelo exacto**: `7550` es «Radeon RX
  9070/9070 XT/9070 GRE», tres tarjetas. Quien desambigua es la línea de
  subsistema del propio fichero, y si no la hay, Vulkan.
- **Leer el enlace PCIe en el nodo de la gráfica**: las tarjetas modernas traen
  un conmutador dentro, y su lado interno negocia a la velocidad del chip
  aunque el puerto de la placa no dé para tanto. Una RX 9070 XT en una X570
  decía «PCIe 5.0» en una placa que no lo tiene. Vale el eslabón más lento de
  la cadena hasta el puerto raíz.
- **Enseñar el modo preferido del EDID como si fuera el máximo**: un OLED de
  240 Hz declara 60 como preferido. El rango real está en el descriptor 0xFD, y
  por encima de 255 Hz hay que sumarle unos bits de acarreo. Pero ese
  descriptor es opcional y los paneles de portátil casi nunca lo traen: sin
  respaldo, el eDP de un ThinkPad salía sin refresco teniendo el dato en su
  temporización detallada. Cuando no hay rango, el nativo es lo único que hay.
- **Confundir el reloj de la memoria de vídeo con su tasa de datos**: una GDDR6
  a 1258 MHz mueve 20 Gbps, dieciséis transferencias por ciclo. Los dos números
  son ciertos y hay que enseñar los dos.
- **Leer `gpu_metrics` sin mirar su versión**: el formato ha cambiado varias
  veces y no siempre añadiendo al final. Interpretar una v1.4 con las
  posiciones de una v1.3 no falla, devuelve cifras creíbles y equivocadas. Cada
  versión tiene su tabla de posiciones o se descarta entera.
- **Convertir el `highest_perf` de CPPC en una frecuencia**: la regla de tres
  que parece obvia —`nominal_freq × highest_perf ÷ nominal_perf`— da 4,96 GHz
  en un 5800X3D cuyo boost son 4,55. El número es creíble, comprobable y
  falso. Donde la plataforma ordena sus núcleos, ese campo deja de significar
  «hasta dónde llega la pieza» y pasa a ser el puesto de cada núcleo en el
  ranking. El techo lo da `amd_pstate_max_freq`, que es el cálculo ya hecho
  por quien conoce la curva.
- **Enseñar la nota de silicio de un núcleo como si fuera comparable entre
  máquinas**: 196 no significa nada por sí solo; es la escala de rendimiento
  de esa pieza. Lo comparable es la fracción respecto al mejor núcleo de la
  misma. Y si el firmware devuelve el mismo número para todos, no está
  midiendo: está rellenando el campo con la constante de la familia, y pintar
  ocho núcleos «igual de buenos» daría a entender que se comprobó algo.
- **Medir en píxeles lo que va dentro de algo que se pinta a mano**: la caja
  del texto de cada núcleo estaba fija en 12 px. Con la letra al máximo las
  letras medían 18 y se comían la gráfica por arriba dejando un hueco por
  abajo. Lo de dentro se mide contra la altura de línea de la fuente, que es
  lo único que crece cuando alguien pide letra grande.

- **Buscar el consumo de una iGPU Intel en `/sys/class/powercap`**: ahí están
  `package-0`, `core`, `uncore` y `dram`, y ninguno es la gráfica. El `uncore`
  es el falso amigo: se queda clavado en 3,2 W mientras el motor gráfico va de
  350 a 1050 MHz. El plano de la gráfica es RAPL PP1 y en estos Intel solo
  asoma por el PMU de perf, como evento `energy-gpu`. Contrastado contra
  `intel_gpu_top`, que enseña la misma cifra.
- **Dar por sabido cómo un PMU escribe sus eventos**: i915 los publica como
  `config=0x2000` y RAPL como `event=0x04`, que no es lo mismo. Cada PMU dice
  en `format/` en qué bits de `config` va cada campo (`event -> config:0-7`).
  Sin mirarlo, `energy-gpu` no se abre.
- **Mandar al usuario a bajar `/proc/sys/kernel/perf_event_paranoid`**: es un
  cerrojo de toda la máquina, no un permiso para este programa; a 0 —el único
  valor que sirve, con 1 sigue denegado— cualquier proceso sin privilegios
  puede perfilar el equipo entero. El ayudante privilegiado que ya pide la
  contraseña una vez para los discos abre el contador sin que el usuario toque
  nada del sistema. Hay un test que vigila que ningún aviso vuelva a nombrarlo.
- **Llamar a una función de ctypes sin declararle `argtypes`**: libva devuelve
  enteros en casi todo y perdona, pero `vaQueryConfigProfiles` escribe en
  memoria de quien llama, y sin declarar los tipos el puntero del display se
  trunca a 32 bits y el proceso se cae de golpe. Un SIGSEGV limpio, sin
  excepción que atrapar.
- **Volver a medir una columna con la tabla recién montada**: el fallo del
  árbol de sensores, repetido en `Table`. «Uso» se quedaba con el ancho de su
  cabecera y enseñaba «12…» en vez de «12.4 %». Se mide el texto que de verdad
  lleva y se ensancha; nunca se encoge.
- **Juntar decodificar y codificar en un «soporta AV1»**: casi todas las
  tarjetas modernas lo leen y muy pocas lo escriben, así que esa frase sería
  falsa la mitad de las veces. Van en dos columnas.
- **Pintar todos los avisos del mismo color**: la banda de `Notice` era ámbar
  para todo, así que «esta gráfica no trae sensor de temperatura» —que no va a
  cambiar nunca— se leía igual de urgente que algo que sí se arregla. Va por
  tono: ámbar lo accionable (`ROOT`, `DRIVER`, `DATABASE`), gris lo que es así
  y ya está (`HARDWARE`, `PLATFORM`), rojo lo que es un fallo nuestro.
- **Explicar que hace falta un permiso sin poner el botón al lado**: el aviso
  de Gráficos decía «Requiere permisos» y el único botón estaba en Memoria y
  en Almacenamiento. Quien lee por qué falta un dato es quien quiere
  arreglarlo, así que el botón va dentro del propio aviso.
- **Confundir el reposo con lo contrario del uso**: entre trabajar y dormir
  hay un término medio —encendida y sin trabajo— que gasta y que no cuenta
  como RC6. Un 40 % de uso no implica un 60 % de reposo.
- **Colgarle a la gráfica el ancho de banda del IMC**: `intel_gpu_top` lo
  enseña junto a la GPU porque en una integrada la RAM del sistema hace de
  VRAM, pero es el controlador de memoria entero, con el tráfico de la CPU
  dentro. Su sitio es la página de Memoria.
- **Poner en una tabla estática un aviso que depende de los permisos**: el
  de i915 vivía en `DRIVERS_CIEGOS`, que lee un proveedor `static`, o sea que
  corre una vez. Seguía pidiendo permisos después de que el usuario los diera.
  Lo que cambia a mitad de sesión lo pone un proveedor dinámico.
- **Escalar la tipografía y los márgenes al mismo ritmo**: quien pide letra
  grande quiere leer mejor, no que quepa la mitad. Los márgenes crecen a mitad
  de paso que el texto (`_escalar` en `ui/theme.py`).
- **Atar la medida de un hilo al «mejor» núcleo**: se hizo para quitar ruido
  —un hilo que salta de núcleo tira la caché— y hacía lo contrario. Medido
  alternando: atarlo cuesta un 40 % en la compresión pesada y un 11 % en la
  derivación de clave, y la dispersión entre repeticiones sale igual o peor
  que dejándolo suelto. Como la afinidad solo se fijaba al medir con un hilo,
  esa penalización caía siempre en la misma cifra y la escala entre uno y
  todos salía en catorce veces con ocho núcleos. Sin atar nada: ocho veces,
  como las demás cargas.
- **Compilar la carga del benchmark al vuelo**: funciona desde el código fuente
  y no dentro de un AppImage, que no lleva compilador. `zlib` y `hashlib` dan
  la misma estabilidad y su bucle también está en C, ya compilado.
- **Usar SHA-256 para medir**: `sha_ni` la acelera y a SHA-512 no, así que un
  chip que la tenga sale inflado y deja de poder compararse con uno que no.
- **Un cliente del ayudante por proveedor**: cada uno lanza su proceso y abre
  su propio diálogo de polkit, así que dos serían dos veces la contraseña para
  lo mismo. El colector crea uno y lo reparte.
- **Dar el enlace PCIe de un disco SATA**: quien negocia es su controladora, y
  la comparte con los demás discos del cable. Solo los NVMe tienen enlace
  propio.
- **Leer solo `*_input` en hwmon**: amdgpu publica el consumo como
  `power1_average`. Sin mirar ese sufijo, la gráfica se quedaba sin vatios.
- **Dar por parada una interfaz cuyo `operstate` no dice «up»**: el bucle local
  y los túneles responden «unknown» porque su driver no informa del enlace.
- **Redondear todos los sensores igual**: un voltaje a un decimal deja de ser
  un voltaje. 0,845 V se convierte en 0,8 y ya no dice nada.
- **Sacar la paleta con `theme.resolve` en vez de `theme.palette_for`**: la
  primera no aplica el color de acento elegido, así que el color llegaba a la
  hoja de estilos pero no a lo que se pinta a mano —gráficas, barras, matriz de
  núcleos— y el tema salía a medias.
- **Dejar que el patrón de marca gane sobre el modelo de CPUID**: la familia y
  el modelo los pone el silicio y no admiten interpretación; el nombre
  comercial es texto. Un Ryzen 7 7445HS (modelo 0x7C) se identificaba como
  «Dragon Range» (modelo 0x61) porque el patrón «Ryzen 7 7###H» le casaba. Los
  campos que identifican el silicio descartan la entrada, no restan puntos.
- **Enseñar el «Unknown …» de libcpuid como nombre en clave**: es su comodín
  para lo que no reconoce. Vale como no-identificación, nunca como respuesta.
- **Contar en unidades de cómputo lo que cada fabricante cuenta a su manera**:
  64 CU de AMD y 2048 núcleos CUDA de NVIDIA no son la misma unidad, y bajo la
  misma etiqueta parece que una tarjeta tiene treinta veces más que la otra.
- **Decir «sin cable» de lo que no lleva cable**: un puente de máquinas
  virtuales apagado está parado, no desenchufado.
- **Juntar un dato ausente con otro presente en el mismo renglón**: el
  ventilador salía como «—   (0.0 %)», que se lee como si faltara una cifra y
  sobrara otra. Las dos decían lo mismo: está parado.
- **Enseñar un rango entre la base y el máximo**: en un Xeon con el turbo
  apagado los dos valen 2.60 GHz y el renglón dice «2.60 – 2.60 GHz», que es
  cierto y no informa. Lo que se recorre es de la mínima al máximo.

- **Animar contra el intervalo que se pidió y no contra el que se cumple**:
  recorrer sysfs, hwmon y los discos lleva entre 330 y 450 ms, así que entre
  muestra y muestra pasan 1200 y no 1000. La animación llegaba al final y se
  quedaba parada esperando el dato: eso es lo que se ve como un tirón. El
  ritmo se mide sobre la marcha, con una media corrida para que un muestreo
  lento suelto no descoloque.
- **Un atajo de teclado que no aparece en ninguna parte**: no existe para
  quien no lo sabe. La barra de estado es donde se mira sin buscar.
- **Dar el respiro de una columna ensanchándola**: con el texto alineado a la
  derecha, ese hueco cae por la izquierda y la cifra sigue terminando pegada
  al borde, que es donde el árbol dibuja su marca de arrastre. El aire donde
  hace falta lo pone el relleno del propio renglón.
- **Leer el registro de salud de un disco y no enseñar ni una línea**:
  `critical_warning` es el campo por el que un NVMe avisa de que va camino de
  perder datos —reserva agotada, modo solo lectura, respaldo fallido— y estaba
  ahí sin que lo mirara nadie. Los apagones bruscos, en cambio, no son un
  aviso: cuentan cortes de luz y botones de reinicio.
- **Adivinar en qué canal está un módulo de memoria**: el firmware lo escribe
  de tres maneras distintas y ninguna es obligatoria. Donde no lo dice se
  calla: en canal único la memoria rinde la mitad, y decirlo al revés manda a
  alguien a abrir el equipo para nada.
- **Tomar por un arrastre lo que estira Qt**: la última columna absorbe el
  sobrante, así que se redimensiona sola con la ventana y emite la misma señal
  que un arrastre. Con eso, maximizar una vez dejaba los anchos guardados como
  si alguien los hubiera puesto a mano y el árbol no volvía a ajustarse nunca.
- **Reajustar anchos en el `resizeEvent`**: cambiar los valores recalcula la
  altura del árbol, y eso es un resize. Una columna estrechada a mano volvía a
  estirarse sola en el muestreo siguiente.
- **Que una herramienta borre lo que no entiende**: `gen_lang --write`
  reescribía los archivos de idioma solo con lo que su extractor veía, y el
  menú lateral se traduce con `_(name)` sobre una variable. Se perdieron doce
  traducciones en una pasada, sin aviso. Lo que ya está traducido se conserva
  aunque no se encuentre.
- **Aplicar una preferencia solo cuando cambia**: el idioma se cargaba al
  tocarlo en Ajustes y no al arrancar, así que guardarlo y volver a abrir el
  programa devolvía la interfaz al español.
- **Declarar `color` en `QTreeWidget::item`**: pisa el que cada celda pide con
  `setForeground`, en silencio y sin error. Con él puesto no llegaba a la
  pantalla ni el rojo de un sensor pasado de vueltas ni el ámbar del que se
  acerca: el árbol salía entero del mismo gris. El color base lo pone el árbol
  al montar cada fila, no la hoja.
- **Probar un color renderizando el widget suelto**: fuera de la ventana no se
  pinta como dentro —el estilo no se aplica igual— y la prueba dice cosas que
  no pasan de verdad. Lo que se vigila es la causa: que la hoja no declare ese
  color.
- **Escribir el mismo relleno en la hoja de estilos y en quien mide**: se
  desincronizan. Al subirlo de 6 a 10 px solo en el CSS, las cifras cabían en
  la cuenta y no en la columna, y los relojes de núcleo salían «4374.4 …».
- **Mezclar dos colores linealmente**: el ojo no los ve así. Entre el blanco
  de las cifras y el ámbar, el primer tercio del recorrido no se distingue de
  nada: una CPU a 78 grados de 95 salía igual que una a 50.
- **Teñir solo el valor de ahora**: quien lanza una prueba de dos minutos va a
  mirar después, y para entonces la columna «Actual» ya se ha enfriado. Lo que
  sobrevive al pico es el máximo, y es el que hay que teñir también.
- **Dejar que el árbol de sensores salga en el orden del kernel**: es el de
  los directorios de hwmon, un número arbitrario que cambia entre arranques.
  El procesador puede acabar debajo de la tarjeta de red. Se ordenan como se
  buscan: procesador, placa, memoria, gráficas, discos, red.
- **Teñir un valor por su fracción del umbral**: un procesador a 45 grados de
  90 no está «medio caliente», está bien. Si el color empieza en el cero es
  decoración; empezando a tres cuartos del límite, avisa.
- **Enseñar que algo recorta sin decir cuánto lleva**: medio segundo de límite
  de potencia en un cambio de escena es el funcionamiento normal de cualquier
  tarjeta; un minuto contra el límite térmico es un problema de refrigeración.
  El motivo es el mismo y la conclusión es la contraria, así que hace falta la
  duración, y por debajo de un segundo y medio no se dice nada.
- **Rellenar una rejilla con lo que quepa y ya**: dieciséis hilos salían doce
  arriba y cuatro abajo. Se elige el reparto con menos huecos en la última
  fila, y quitar columnas ensancha las celdas, así que hay suelo: el 60 % de
  lo que cabía.
- **Deduplicar las cachés por su nivel**: en un Ryzen de dos chiplets con
  V-Cache en uno solo hay dos L3 del mismo nivel y el mismo tipo con tamaños
  distintos —96 MB y 32—, y quedarse con la primera enseñaba la buena para
  todo el procesador. Es justo el dato por el que se compra esa pieza y justo
  la mitad del chip donde no es cierto. El tamaño entra en la clave.
- **Deducir el V-Cache del tamaño de la L3**: crece por otros motivos según la
  familia. Quien lo dice es el fabricante en la cadena de marca («X3D»); la
  asimetría entre chiplets es un hecho aparte, que se describe aunque el
  nombre no lo confirme.
- **Comparar la nota de silicio entre tipos de núcleo distintos**: un E-core
  con la mitad de nota que un P-core no salió peor de la oblea; es otro
  núcleo, con otro tamaño y otro propósito, y la plataforma lo puntúa más bajo
  por diseño. Un 12900K decía que su núcleo más flojo se quedaba en el 35 %
  del mejor: cierto en el número y falso en lo que da a entender. La nota solo
  compara piezas equivalentes, así que se agrupa por `type_key`.
- **Contar núcleos donde el usuario cuenta estrellas**: la leyenda decía
  «núcleo 1 y núcleo 3» y en pantalla se veían cuatro marcas, porque cada
  núcleo bueno marca sus dos hilos. Las dos cosas ciertas y ninguna evidente.
- **Dar por bueno lo que mide la primera vuelta de una carga**: la compresión
  pesada daba 1 780 operaciones por segundo la primera vez que corría en un
  proceso y 2 950 a partir de la segunda, un 65 % más, sin que cambiara nada
  del equipo. Lo que se paga ahí es del asignador: LZMA pedía un búfer holgado
  en cada llamada y glibc lo servía con `mmap` hasta subir su umbral por su
  cuenta. Y como el orden es un hilo primero y todos después, ese arranque lo
  pagaba siempre la medida de un hilo. Se arregla dejando rodar la carga unas
  centésimas antes de contar (`_rodar_en_vacio`); con ochenta vueltas basta.
  Ojo: por sí solo no bastaba, hacía falta quitar además la afinidad, y por
  eso costó encontrarlo —cada arreglo por separado parecía no servir—. Con
  bzip2, que es la carga desde la escala v4, el mismo efecto es del 2,7 %.
- **Achacar al calor una dispersión que no es térmica**: la puntuación
  multihilo se movía un 4,7 % entre repeticiones del mismo equipo sin tocar
  nada, y el calor era la explicación evidente. No lo era. Enfriando hasta los
  mismos grados antes de cada repetición seguía en un 4,2 %, así que la prueba
  que parecía confirmarlo era la que había que hacer para descartarlo. Era una
  sola carga: la compresión pesada con LZMA, que alterna entre 25 800 y 32 500
  operaciones por segundo —un 26 %— según le llueva o no una tormenta de
  fallos de página, 280 000 por segundo, de los búferes que pide en cada
  llamada. Quitándola, las otras cuatro dispersan un 0,29 %. Lo térmico existe
  y es de segundo orden: 1,74 % seguidas contra 0,29 % enfriando. El estado se
  decide por proceso y dentro de una medida es plano, así que alargarla no lo
  promedia: lo hereda entero.
- **Creerse una correlación sin mirar hacia dónde apunta la flecha**: la
  velocidad de esa misma carga correlacionaba con la temperatura a r = 0,98, y
  la lectura obvia —el calor la frena— era justo la contraria de lo que
  pasaba. El modo rápido corre a menos GHz que el lento (4,29 contra 4,34) y
  calienta más porque hace más trabajo por ciclo. La temperatura era la
  consecuencia, no la causa, y con r = 0,98 nadie lo habría dudado.
- **Creer que todo lo que dice ser una batería es la del equipo**:
  `/sys/class/power_supply` mezcla el cargador, los puertos USB-C y cualquier
  periférico con pila, y el ratón Logitech publica `hidpp_battery_0` con
  `type=Battery`. Con mirar el tipo, este sobremesa —que no tiene batería
  ninguna— declaraba una, y habría salido una ficha de batería en una torre.
  Quien lo distingue es `scope`: los periféricos dicen «Device» y la del equipo
  «System», o nada en los portátiles antiguos.
- **Dar la capacidad de una batería en miliamperios-hora**: el kernel la
  publica en `charge_*` (µAh) o en `energy_*` (µWh) según el firmware, y los
  mAh no se pueden comparar entre equipos sin saber el voltaje de la celda:
  4000 mAh a 7,6 V y 4000 mAh a 11,4 V son baterías muy distintas. Todo entra
  en vatios-hora, y para convertir manda el voltaje de diseño y no el de ahora,
  que sube y baja con la carga y daría otra capacidad en cada muestreo.
- **Poner un botón para arreglar algo que el ayudante no sabe arreglar**: el
  aviso de que el consumo del procesador «requiere permisos» lo pone el
  proveedor de RAPL, porque desde el kernel 5.10 `energy_uj` no se lee sin
  privilegios. Pero el ayudante sabía leer SMBIOS, MSR, SMART y el PMU de la
  gráfica, y no RAPL: el usuario daba los permisos, el ayudante arrancaba y
  nadie leía eso, así que la nota no se iba nunca. Lo reportó alguien con un
  Ryzen 7 7445HS —«le di permisos pero aún dice que 1 dato requiere permisos, y
  al tocarlo no abre el polkit»— y lo segundo también encaja: ya estaba
  conectado, no había nada que autorizar. Un contador de lo que falta solo vale
  si lo que cuenta se puede resolver.
- **Medir la carga de fondo solo antes de empezar**: `_carga_de_fondo` toma
  tres décimas y se acabó, y una prueba de quince segundos por carga dura dos
  minutos y medio. Quien la lanzaba y se iba a hacer otra cosa, o tenía una
  actualización en marcha sin saberlo, salía con «0 % de carga de fondo» y una
  cifra baja sin explicación en ninguna parte. Ahora el vigilante muestrea
  también mientras se mide, y se guarda el pico y no la media: algo que se
  despierta a mitad se diluye promediado entre dos minutos.
- **Que una herramienta reescriba entero un archivo que no llena ella sola**:
  `medir_referencia.py` volcaba `scores.json` con lo que acababa de medir, y
  las medidas de otros equipos que va acumulando `anadir_puntuacion.py` vivían
  en ese mismo archivo. Remedir la escala las borraba todas, sin decirlo. No
  llegó a costar nada porque cuando se vio todavía no había ninguna guardada.
- **Callarse igual ante un dato que no existe y ante uno que no se sabe leer**:
  las versiones de `gpu_metrics` que no están en la tabla se descartan a
  propósito, y hasta ahora acababan en el mismo silencio que no tener
  telemetría. En una APU —que publica las 2.x— los motivos de recorte y los
  voltajes salían vacíos sin nada que lo explicara. Se descarta igual, pero se
  dice cuál es y se lleva al informe, que es de donde puede salir su tabla de
  posiciones sin tener la pieza delante.
- **Buscar el ruido de fuera sin medir el de dentro**: con el navegador y el
  chat abiertos, lo ajeno se llevaba un 2,4 % de la máquina, pero de forma
  intermitente, que es lo que se confunde con una deriva. `/proc/stat` a secas
  no sirve mientras la prueba ocupa el equipo entero: lo que se busca es la
  resta, lo ocupado menos lo del propio proceso. Cerrar programas ayuda; poder
  demostrar que estaban cerrados es lo que deja concluir algo.
- **Sumar operaciones por segundo de cargas distintas para hacer una
  puntuación**: en un 5800X3D la compresión pesada da 28 494 op/s y la
  memoria 533, así que la primera pesaba el 82 % del total y las otras
  cuatro eran decoración. La cifra era, en la práctica, una sola carga.
  Cada una se divide por lo que da en la pieza patrón y así entran
  valiendo lo mismo.
- **Comparar dos pruebas de distinta duración**: tres segundos cogen el
  turbo entero y treinta lo pierden a mitad, así que la misma pieza da dos
  cifras muy distintas. Poder elegir la duración es lo que permite
  preguntar cuánto aguanta un equipo; puntuar con cualquiera de ellas es
  decir que uno es más lento cuando lo único que cambió fue la pregunta.
  Solo puntúan las de quince segundos.
- **Comparar temperaturas de dos momentos sin saber la ambiente**: ocho grados
  entre febrero y agosto son normales y salen iguales que ocho de pasta seca.
  Ningún sensor del equipo mide la habitación. Lo que sí se puede comparar es
  la misma carga con la misma puntuación, y aun así el aviso dice lo que ve
  —«más caliente para el mismo trabajo»— sin diagnosticar la causa.
- **Dejar en `tools/` algo que ejecuta el usuario final**: el AppImage copia
  `silux/` entero y no copia `tools/`, así que el botón de permisos permanentes
  se quedaba sin instalador que lanzar justo en la única forma del programa que
  se reparte. `tools/` es para quien desarrolla.
- **Subir por sysfs hasta encontrar lo que se busca**: el sensor de una
  tarjeta de red cuelga del bus MDIO, así que hay que subir; pero subiendo a
  ciegas se llega a `/sys/devices/virtual`, que también tiene un `net/` dentro
  —con el bucle local— y un ThinkPad enseñaba «Red (lo)» a 34 °C. No vale
  parar donde se acaben los dispositivos: el propio bus MDIO es un contenedor
  sin `uevent` y está en medio del camino bueno. Lo que se descarta es la rama
  virtual.
- **Avisar de un umbral en algo que se enchufa por fuera**: un puerto USB-C
  sin nada conectado marca 0 V, y eso queda por debajo de cualquier mínimo que
  declare el chip. Cero ahí no es una avería: es que no hay nada puesto. Lo
  mismo que ya valía para los ventiladores.
- **Pintar «sin dato» con la tipografía de las cifras**: el guion a treinta y
  seis píxeles es una raya gruesa, y en una Intel con cuatro de los seis
  cuadros vacíos la fila entera parecía tachada.
- **Poner una marca de color sin nada que la traduzca**: el punto que señala
  los mejores núcleos no significa nada por sí solo. Su leyenda va debajo de
  la propia rejilla, no en la ficha de al lado: separadas, el punto se queda
  sin explicar y la frase sin a qué referirse.

- **Creer que los códigos de vídeo del EDID describen el panel**: los VIC de
  CTA-861 son códigos de TV y HDMI, y no llegan a 1440p a 240 Hz. El AORUS
  FO27Q2 declara como mucho 1080p a 120 por ahí, y sus 240 Hz solo están en el
  descriptor de rangos 0xFD. Lo que sí aportan las extensiones y no está en
  ningún otro sitio es el HDR y los espacios de color.

- **Reorganizar un widget sin avisar al layout de arriba**: la fila de
  insignias pasa a dos líneas cuando la ventana se estrecha, pero sin
  `updateGeometry` nadie le da la altura nueva y acababa pintada encima de la
  barra. Se arreglaba sola al mover la ventana otra vez, que es la pista de
  que faltaba un recálculo y no espacio.
- **Compartir el estilo de un título con el de una cabecera de columna**: no
  pesan lo mismo. Un título nombra la tarjeta entera; una cabecera nombra una
  columna y tiene que quedarse por detrás del dato.
- **Meter una carga de benchmark sin comprobar que reparte**: `base64` escala
  ×1.0 con dieciséis hilos y la de coma flotante también. Si no suelta el GIL
  no mide el procesador, mide el candado, y hay un test que lo ejecuta de
  verdad para cada carga en vez de fiarse.

- **Fiarse de los umbrales que publica un chip sin mirarlos**: devuelven de
  fábrica los campos que nadie configuró. Un nct6798 da `min = 127` y
  `max = 127` en sus seis temperaturas, y con eso una placa a 34 °C queda «por
  debajo del mínimo»: seis avisos falsos de golpe. Un NVMe da 65261.85 °C, que
  son 0xFFFF en kelvin. Se descarta lo implausible y los pares donde el mínimo
  supera al máximo, y de los ventiladores no se avisa nunca: ir a tope bajo
  carga es lo normal y estar parado en reposo también.
- **Esperar que el hardware publique sus límites**: de 28 temperaturas de un
  equipo corriente, solo 7 traen umbral, y el procesador no suele traer
  ninguno. Sin estimar nada, el aviso no salta donde más falta hace. Se
  estiman por chip conocido (k10temp, coretemp, nvme, drivetemp), del lado
  prudente, y se dice en la ventana que son estimados.

- **Medir el coste de repintar sobre widgets que no están a la vista**: la
  primera medida del movimiento fluido dio un 117 % de un núcleo, y era falsa:
  forzaba el dibujo de las dieciséis gráficas montadas cuando Qt no repinta
  las de las páginas cerradas. A la vista hay cuatro, y el coste real es un
  2 %. Un número así de malo conviene comprobarlo antes de rendirse.

- **Medir el ancho de una columna cuando aún no hay nada que medir**: los
  anchos del árbol de sensores se calculan al montarlo, con las celdas
  vacías, y luego llegan los valores. La columna del reloj enseñaba
  «800.0 M…». Al cambiar un valor se ensancha si hace falta; nunca se encoge,
  o la tabla bailaría a cada muestreo.
- **Quedarse con el fabricante que publica sysfs en un disco**: dice «ATA» en
  SATA y nada en NVMe. El nombre solo está dentro del modelo, y hay que
  buscar el prefijo más largo primero: «wd_black» antes que «wd », «sk hynix»
  antes que «hynix».
- **Titular la ficha de la placa con la placa en un portátil**: un IdeaPad 330
  lleva dentro una «LNVNB161216», que no le dice nada a nadie. Ahí manda el
  nombre del equipo, que es el de la pegatina; en un sobremesa es al revés,
  porque la placa es lo que se compró.

- **Buscar los datos de i915 en `card0/device/`**: ese es el enlace al nodo
  PCI, e Intel publica las frecuencias del motor gráfico en el nodo DRM, un
  nivel más arriba. Encima cambiaron de sitio en el kernel 6.2, que las metió
  en `gt/gt0/` con prefijo `rps_` sin quitar las viejas. Hay que mirar en las
  cuatro rutas: una UHD 630 salía con todos los relojes en blanco.
- **Decidir si una gráfica es integrada por si tiene VRAM**: no leerla no es
  no tenerla. Con nouveau no se lee ninguna, y una GTX 1050 Mobile —una
  tarjeta dedicada— salía marcada como integrada; al revés, una APU reserva
  un trozo de la RAM del sistema y parecía tener memoria propia. En AMD lo
  dice el bit FUSION del ioctl, la integrada de Intel vive en 0000:00:02.0, y
  una NVIDIA en un PC nunca lo es. Lo que no se pueda decidir se queda en
  `None`.
- **Restarle lo ocupado a la capacidad para saber lo libre**: eso da por
  montado todo el disco. Con un Windows al lado, 570 GB de otra partición se
  contaban como espacio libre, y el recuadro de al lado —que suma el hueco de
  las particiones montadas— decía otra cifra en la misma pantalla. Lo que no
  está montado no está libre y se dice aparte.

- **Colgar OpenGL y OpenCL de la tarjeta que el kernel marca como principal**:
  no publican su nodo PCI, pero sí dicen quién contesta. En un portátil
  híbrido la principal es la integrada, porque lleva la pantalla, mientras
  quien responde es la dedicada: la ficha de una Radeon 740M salía con «GLSL
  4.60 NVIDIA» y con 16 unidades de cómputo que eran los 16 SM de la RTX 3050
  de al lado. Se casa por el fabricante que aparece en el texto, y lo que no
  se pueda atribuir no se atribuye.
- **Escribir una tabla nueva sin mirar si la generada ya la tiene**:
  `cpu_ids.json` ya traía el MIDR de ARM —198 piezas con nombre en clave y
  litografía— y el contador de la pantalla de ajustes lo venía diciendo desde
  el principio. La tabla escrita a mano tenía 138 y ninguna de las dos cosas.
- **Leer `/etc/os-release` mirando solo las comillas dobles**: el formato es
  el de un fragmento de shell y las simples valen igual. Gentoo las usa, y su
  nombre aparecía en la ventana como `'Gentoo Linux'`, con las comillas.
- **Dar por hecho que el kernel lo compiló gcc**: CachyOS usa clang, y el
  respaldo del que no casaba devolvía «Linux version 6.18.35-gentoo», que es
  repetir el kernel en el renglón de al lado.

- **Suponer que una bandera con el mismo nombre es la misma instrucción**: la
  `aes` de un aarch64 es la extensión criptográfica de ARMv8, y pintarla como
  «AES-NI» le pone a un procesador una instrucción de Intel que no tiene. Cada
  arquitectura necesita su tabla de nombres, no una compartida.
- **Marcar como «no aplica a esta plataforma» cualquier fallo de un proveedor**:
  un permiso denegado dice lo contrario de eso. En un entorno enjaulado acababa
  informando de que la red no aplicaba a un equipo que tiene red. Un
  `PermissionError` pide permisos, un fichero ausente es hardware que no lo
  publica, y lo demás es un fallo nuestro y se dice así.
- **Interpolar un valor opcional directamente en una cadena**: `f"familia
  {x}"` con `x` a `None` escribe «familia None». No se arregla con `or "—"`
  porque un stepping 0 es un stepping de verdad; va por `render.dec`, que
  compara contra `None`.
- **Probar la interfaz solo con `QT_QPA_PLATFORM=offscreen`**: ese plugin
  apenas necesita bibliotecas, así que un AppImage al que le falte medio Qt
  arranca igual. El fallo aparece en la primera máquina ajena con pantalla.
- **Recorrer solo las dependencias del ejecutable de Python**: los módulos de
  extensión de su biblioteca estándar tienen las suyas y viven aparte, en
  `lib-dynload`. Así `_hashlib` se quedaba sin `libcrypto` y `_lzma` sin
  `liblzma`, y dos de las cinco cargas del benchmark reventaban en cualquier
  máquina que no las trajera puestas: en las distribuciones con OpenSSL 1.1,
  siempre. De paso, los módulos que el programa no usa se borran antes de
  mirar de qué dependen: `nis` se lleva Kerberos entero detrás.
- **Tomar por normal un aviso del comprobador del AppImage**: decía que trece
  bibliotecas se cogían del sistema «y son normales», y dos de ellas hacían
  falta de verdad.
- **Que un test lea el hardware de quien lo ejecuta y además espere encontrar
  algo**: los del buscador de sensores montaban el árbol con
  `Collector().sample()` y luego exigían que filtrar por «temperatura» diera
  más de cero. En una máquina sin `hwmon` no hay ninguna, así que el filtro
  acierta al no devolver nada y el test lo llama fallo. Fallaba en el CI
  siempre y aquí de vez en cuando, según lo que publicara el equipo en ese
  momento, que es la peor mezcla: parece un fantasma. Comparar el árbol
  consigo mismo sí puede leer la máquina; exigir un resultado concreto, no.
- **Dar por probado lo que el `and` nunca llega a evaluar**: `_identidad` en
  `providers/drm.py` llamaba a `_igpu_de_la_cpu(draft)` sin tener `draft` en la
  firma, o sea un `NameError` escrito y esperando. No saltaba nunca aquí porque
  la condición de delante corta: solo se llega cuando una AMD **no** lleva
  «Radeon» en el nombre, y eso pasa en las APU —a las que `pci.ids` llama por
  su nombre en clave, «HawkPoint2»— y en cualquier equipo sin `hwdata`. Es
  decir, reventaba justo en los equipos que ese código intentaba mejorar, y en
  ninguno de los de casa. La suite lo cazaba, pero solo al ejecutarla donde
  falta `pci.ids`.
- **Tener el CI atado a los tags**: la acción del AppImage solo corría con
  `v*`, y como no hubo tag hasta la 0.2.0, la primera vez que se ejecutó
  llevaba meses sin probarse y falló entera. Enterarse el día que se publica es
  enterarse tarde. Ahora corre en cada empujón a master; publicar sigue
  dependiendo del tag.
- **Probar en un contenedor que corre como root y sin `hwdata`**: al buscar por
  qué fallaba el CI, cuatro de los fallos eran del entorno de pruebas y no del
  programa. Como root, el proveedor de memoria lee la tabla DMI directamente en
  vez de pedir permisos, así que sale `HARDWARE` donde el test espera `ROOT`; y
  sin `pci.ids` no hay nombres de dispositivo que buscar. Reproducir el CI es
  reproducir también quién lo ejecuta.
- **Buscar texto dentro de una imagen**: `comprobar_privacidad.py` recorre lo
  versionado buscando el nombre del equipo y las MAC, y por eso daba por buenas
  las capturas: lo que se ve en pantalla no está escrito en el archivo. Publicó
  su visto bueno a una que enseñaba la dirección física de esta máquina y su
  IPv6 pública, que es un prefijo global y dice de quién es la conexión. Como
  no se puede leer lo que enseña la imagen, se comprueba cómo se hizo: la
  captura escribe dentro del PNG si tapó los identificadores, y el comprobador
  exige esa marca. El valor va en ASCII, y tampoco es un descuido del idioma:
  con «sí», Qt lo escribe en Latin-1 —`s\xed`— y quien lo busque en UTF-8 no
  encuentra la marca que sí está.
- **Dejar que cada comprobación recorra el AppDir por su cuenta**: la del juego
  de instrucciones lo miraba entero y la de glibc solo `usr/lib/*.so*`, y de
  esas, las sesenta primeras de sesenta y cinco. Así el informe decía «exige
  glibc 2.34» de un paquete que exige 2.35, que es la diferencia entre que RHEL
  9 valga o no valga: el símbolo más alto, `hypot@GLIBC_2.35`, lo pide el
  propio `python3`, que cuelga de `usr/bin` y no se miraba. Los módulos de
  extensión de `lib-dynload` tampoco, que es el mismo agujero por el que
  `_hashlib` se quedó sin `libcrypto`. Equivocarse aquí solo cae hacia un lado
  —decir que hace falta menos de lo que hace falta—, y es el lado que manda a
  alguien a descargar algo que no le arranca. Ahora la lista es una,
  `objetos_del_appdir()`, y hay tests que vigilan que las dos la compartan y
  que nadie le vuelva a poner tope.
- **Dar por hecho que una dependencia sigue donde estaba**: el `pip install`
  del AppImage pedía `PySide6>=6.6`, sin techo, y durante un año eso fue
  inofensivo. Qt 6.10 subió su mínimo a x86-64-v2 y el AppImage dejó de
  arrancar en cualquier procesador anterior a 2008, sin que cambiara una línea
  del programa. Lo que no se fija cambia solo, y lo hace en la máquina de otro.
- **Contar instrucciones para saber si un binario es compatible**: libcrypto
  lleva AVX-512 y funciona en un Pentium 4, porque pregunta antes. Lo que hay
  que mirar es dónde caen: en una función con el juego en el nombre
  —`qt_convert_rgb888_to_rgb32_ssse3`— no se ejecutan salvo que toque; en
  `QString` no hay escapatoria. `.dynsym` sobrevive al `strip`, así que se
  puede saber cuál es cuál.
- **Fiarse de `ldd` en la máquina donde se construye**: resuelve contra lo que
  esa máquina tiene instalado, que es justo lo que se está empaquetando. Lo
  que no esté puesto no aparece como dependencia y se cae del paquete en
  silencio. `tools/build_appimage.py` termina comprobando que cada objeto del
  AppDir resuelve dentro o contra la lista de lo que se deja al anfitrión.
- **Filtrar bibliotecas por subcadena**: «libxcb» en la lista de lo que pone
  el sistema también descartaba `libxcb-cursor` y las nueve auxiliares que el
  plugin xcb necesita y que muchas distribuciones no traen. Se comparan por
  principio de nombre.
- **Medir el tráfico de red en potencias de 1024**: en redes la convención es
  decimal. Con 1024 los mismos datos salen 976 Mb/s donde un test de velocidad
  dice 931, y no hay forma de explicar la diferencia.

## El idioma

La interfaz va en **español neutro**: `video` y no «vídeo», `archivo` y no
«fichero», `dispositivo` y no «aparato», `equipo` y no «ordenador». Nueve de
cada diez hispanohablantes están al otro lado del Atlántico y no hay motivo
para cerrarles la puerta por una tilde.

Los comentarios del código no siguen esa regla y van en el español del autor:
no los ve nadie desde la ventana y no se traducen.

**Las claves son símbolos** —`cpu.card.clocks`—, así que el español es un
idioma más y vive en `db/lang/es.json`. Retocar una frase en castellano es
cambiar un valor, no una clave: la traducción inglesa no se descuelga.

Lo malo conocido de las claves simbólicas —que una traducción incompleta
enseñe `cpu.card.clocks` en pantalla— aquí no pasa, porque `_()` tiene tres
escalones: el idioma pedido, el español y por último la clave. Un `en.json` a
medias enseña español entre inglés, que se lee; la clave solo asoma cuando la
frase no está escrita en ninguna de las dos lenguas, y entonces es justo lo
que hace falta ver.

Las categorías del árbol de sensores también son claves. Esos nombres
—«Temperaturas», «Ventiladores»— los inventa el programa para agrupar y no
salen del kernel, así que son interfaz: la frontera no está en de dónde viene
el dato sino en quién escribió la palabra.

Los nombres de sección son claves (`nav.sensors`), así que `select_section`
acepta tres cosas: lo que se ve, la clave y el nombre en español. Sin lo
tercero, `--page Sensores` dejaría de funcionar en cuanto alguien se pusiera
la interfaz en inglés.

Se eligió JSON sobre gettext por quién escribe los archivos: un `.po` hay que
compilarlo a binario antes de que sirva, y esto se corrige desde el navegador
de GitHub y se lee en el diff línea a línea.

**Los proveedores también traducen, pero solo lo que se inventan**: el aviso
que explica por qué falta un dato, el nombre que le ponen a un sensor —«Punto
caliente» donde amdgpu dice `junction`—, la función de un motor gráfico. Lo
que leen del equipo pasa entero y sin tocar. La línea se comprueba sin
ejecutar nada: a `_()` solo puede llegar un literal escrito en el archivo o
una variable que se rastree hasta una tabla declarada ahí mismo. Un
`_(entry["label"])` traduciría un dato, y eso rompe la detección de una
gráfica en cuanto alguien se pone la interfaz en inglés.

**Fuera de la interfaz, las claves no se traducen solas.** El informe agrupa
los sensores por categoría, y esas categorías son claves porque el nombre lo
inventa el programa. Como `report.py` no importaba nada de `i18n`, salían
crudas: «cat.temperature (2), cat.power (2)» en el archivo que se le pide a
quien reporta un fallo. Y la traducción que necesita ahí es `en_español` y no
`_()`: el informe es castellano fijo —«Procesador», «Placa base»—, así que con
la función normal, el de alguien con la interfaz en inglés mezclaría los dos
idiomas en la misma página.

**Nada de `_()` en una constante de módulo.** Se resuelve al importar, cuando
todavía no se sabe qué idioma quiere nadie, así que se queda con el castellano
para toda la sesión; y como quien monta la ficha vuelve a pasar cada entrada
por `_()`, la segunda llamada recibe «Uso» —que no es una clave— y devuelve
«Uso». Así salía la columna «LEYENDO» en medio de una tabla de discos en
inglés: la tupla llevaba once claves y una traducción ya hecha, y era la única
que no cambiaba de idioma. Hay un test que lo vigila.

La interfaz está entera en los dos idiomas: 891 claves, ninguna sin traducir.
Hay un test que recorre el árbol de sintaxis de cada página buscando
constructores de widget con una cadena española a pelo, porque eso es lo que
no se ve hasta abrir la pantalla en el otro idioma y ningún test normal lo
nota. **Descubre los archivos solo**: con la lista escrita a mano se quedaron
cinco páginas enteras sin traducir y el test seguía en verde, porque no las
miraba.

**`_` no se puede usar de descarte.** `for _ in range(10)` o `ruta, _ =
dialogo()` es lo idiomático en Python para decir «esto no me importa», y aquí
sustituye la función de traducción dentro de esa función: la siguiente llamada
revienta con «'int' object is not callable», un error que no menciona ni el
idioma ni la traducción. Y lo hace meses después, cuando alguien añade una
cadena traducible en ese mismo método. Hay un test que lo vigila.

`tools/gen_lang.py` los mantiene al día. Solo recoge lo que ya está envuelto
en `_()`: adivinar qué cadena del código es texto de interfaz sale mal en
silencio, y un `"amdgpu"` traducido rompe la detección de la gráfica sin que
nadie lo relacione con el idioma. **Nada de `providers/` se traduce**: lo que
sale de ahí es el dato del equipo, no una frase del programa.

## Al reportar un fallo

`python3 -m silux.cli --report informe.md` recoge el hardware detectado y, sobre
todo, la sección de diagnóstico: qué fuentes respondieron, qué módulos del
kernel faltan y qué datos no se pudieron leer. Es lo primero que hay que pedir
cuando alguien dice que algo no le sale.

Desde el AppImage es `./silux-x86_64.AppImage --report informe.md`: el punto de
entrada reparte entre la interfaz y el volcado en terminal según con qué se le
llame, porque quien lo usa así no tiene otra forma de sacarlo.

Si hay alguna prueba de rendimiento medida con la escala vigente, el informe
lleva también su puntuación y las condiciones en que se tomó. Es lo que permite
juntar medidas de piezas que no están a mano: sin eso, quien manda un informe
manda su hardware pero no lo que rinde, y la tabla de puntuaciones no se llena
nunca.

Omite por defecto el nombre del equipo, las IP, las MAC y los números de serie
—está pensado para pegarlo en un issue público— y lo dice al terminar. Con
`--with-identifiers` se incluyen. Hay tests que vigilan que no se cuele nada.

## Fuentes de datos y licencias

- [libcpuid](https://github.com/anrieff/libcpuid) — BSD-2 — tablas de identificación de CPU
- [CPU-X](https://github.com/TheTumultuousUnicornOfDarkness/CPU-X) — GPL-3.0 — tabla de sockets
- `pci.ids` del sistema (paquete hwdata) — nombres de dispositivos PCI
