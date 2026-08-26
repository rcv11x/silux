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
python3 tools/install_desktop.py       # icono y entrada de menú
python3 tools/build_appimage.py --container   # el AppImage que se reparte
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .
```

Los tests son **582** y tardan quince segundos. Si sale otra cifra, falta algo.

`--container` no es opcional para repartir: sin él se construye contra el
Python y el Qt de la máquina, y sale un AppImage que exige el juego de
instrucciones y la glibc de quien lo compiló. Con contenedor sale
`x86-64-baseline` y glibc 2.34. El paso final de comprobación recorre el
AppDir y avisa de lo que resuelve fuera; los módulos opcionales de Python
(`libssl`, `libsqlite3`, `libncurses`) salen ahí y son normales.

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
├─ tracking.py     mínimos, máximos y medias por sensor
├─ rawcpuid.py     CPUID desde Python, sin root (mmap + ctypes)
├─ gpuapi.py       OpenGL, Vulkan y OpenCL por ctypes, en un proceso aparte
├─ amdgpu.py       ioctl DRM: tipo de VRAM, bus, unidades, ROP
├─ edid.py         decodifica la chapa de identificación del monitor
├─ report.py       informe en Markdown para reportar fallos
├─ gpumetrics.py   telemetría del firmware AMD: por qué se frena la tarjeta
├─ nvml.py         NVIDIA propietaria, que no publica nada en sysfs
├─ features.py     tabla declarativa de banderas de CPUID
├─ pciids.py       nombres de dispositivos PCI desde la base del sistema
├─ spd.py          decodifica el chip de identificación de la RAM (DDR4 y DDR5)
├─ smart.py        interpreta el diagnóstico de los discos, sin privilegios
├─ benchmark.py    prueba de CPU que reporta en qué condiciones midió
├─ providers/      una fuente cada uno; ninguno conoce a los demás
├─ privileged/     ayudante root mínimo (helper.py) + cliente + SMBIOS
├─ db/             cpu_ids.json (generado; incluye la tabla de MIDR de ARM) +
│                  sockets.json y families.json (curados a mano; el segundo
│                  cubre lo que libcpuid no tiene)
└─ ui/             tema, hilo de muestreo, widgets, una página por sección
```

El orden de los proveedores en `collector.py` importa y está comentado ahí.

## Estado

Terminadas las once: **CPU, Cachés, Placa base, Memoria, Gráficos,
Almacenamiento, Red, Sistema, Rendimiento, Sensores, Ajustes**.

De Gráficos sale todo lo que publica el nodo DRM —identidad, VRAM, tabla DPM,
enlace PCIe, sensores propios— más lo que solo da el ioctl de amdgpu (tipo de
memoria, anchura del bus, ancho de banda, unidades de cómputo y ROP), las tres
APIs y el EDID de cada monitor. Queda pendiente:

- **Las extensiones del EDID** (bloques CTA-861), con los modos de vídeo que
  el monitor admite además del preferido.
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
  por encima de 255 Hz hay que sumarle unos bits de acarreo.
- **Confundir el reloj de la memoria de vídeo con su tasa de datos**: una GDDR6
  a 1258 MHz mueve 20 Gbps, dieciséis transferencias por ciclo. Los dos números
  son ciertos y hay que enseñar los dos.
- **Leer `gpu_metrics` sin mirar su versión**: el formato ha cambiado varias
  veces y no siempre añadiendo al final. Interpretar una v1.4 con las
  posiciones de una v1.3 no falla, devuelve cifras creíbles y equivocadas. Cada
  versión tiene su tabla de posiciones o se descarta entera.
- **Medir en píxeles lo que va dentro de algo que se pinta a mano**: la caja
  del texto de cada núcleo estaba fija en 12 px. Con la letra al máximo las
  letras medían 18 y se comían la gráfica por arriba dejando un hueco por
  abajo. Lo de dentro se mide contra la altura de línea de la fuente, que es
  lo único que crece cuando alguien pide letra grande.

- **Escalar la tipografía y los márgenes al mismo ritmo**: quien pide letra
  grande quiere leer mejor, no que quepa la mitad. Los márgenes crecen a mitad
  de paso que el texto (`_escalar` en `ui/theme.py`).
- **Medir un hilo sin fijarle la afinidad**: el planificador lo va moviendo, y
  cada salto tira la caché y obliga al núcleo nuevo a subir de frecuencia desde
  abajo. Dos ejecuciones seguidas salen con un 10 % de diferencia por eso solo.
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

## Al reportar un fallo

`python3 -m silux.cli --report informe.md` recoge el hardware detectado y, sobre
todo, la sección de diagnóstico: qué fuentes respondieron, qué módulos del
kernel faltan y qué datos no se pudieron leer. Es lo primero que hay que pedir
cuando alguien dice que algo no le sale.

Desde el AppImage es `./silux-x86_64.AppImage --report informe.md`: el punto de
entrada reparte entre la interfaz y el volcado en terminal según con qué se le
llame, porque quien lo usa así no tiene otra forma de sacarlo.

Omite por defecto el nombre del equipo, las IP, las MAC y los números de serie
—está pensado para pegarlo en un issue público— y lo dice al terminar. Con
`--with-identifiers` se incluyen. Hay tests que vigilan que no se cuele nada.

## Fuentes de datos y licencias

- [libcpuid](https://github.com/anrieff/libcpuid) — BSD-2 — tablas de identificación de CPU
- [CPU-X](https://github.com/TheTumultuousUnicornOfDarkness/CPU-X) — GPL-3.0 — tabla de sockets
- `pci.ids` del sistema (paquete hwdata) — nombres de dispositivos PCI
