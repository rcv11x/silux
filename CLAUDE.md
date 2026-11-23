# Silux — contexto del proyecto

Perfilador de hardware para Linux en Python + PySide6: lo que en Windows hacen
**CPU-Z, GPU-Z y HWMonitor**, en un solo programa nativo. Identificación del
hardware y monitorización de sensores.

**Lo que este programa no es: un administrador de tareas.** Los procesos son
software, no hardware, y Linux ya tiene buenos monitores de procesos.
Tampoco el uso de la gráfica ni de nada por programa (DRM `fdinfo` incluido),
aunque se lea sin permisos.

Este archivo es corto a propósito: se carga en cada sesión. El detalle vive en
`docs/` (índice al final). Antes de tocar una zona, se lee lo suyo en
[docs/pendientes.md](docs/pendientes.md).

## Cómo se ejecuta

```bash
python3 -m silux.ui.app                 # interfaz
python3 -m silux.cli                    # volcado en terminal
python3 -m silux.cli --json             # API para otros programas
python3 -m silux.cli --sensors          # el árbol de sensores
python3 -m silux.cli --report FICHERO   # el informe completo, de las páginas (--short, el corto)
python3 tools/gen_cpu_db.py            # regenerar la base de datos de CPUs (libcpuid, kernel, amd.com, cpuid)
python3 tools/gen_referencias_cpu.py --libcpuid DIR  # las 411 CPU de referencia de sus volcados
python3 tools/gen_memory_limits.py --intel-desde DIR  # el máximo de memoria por modelo
python3 tools/gen_smart_units.py       # las unidades de cada contador SMART, de smartmontools
python3 tools/gen_jep106.py            # los fabricantes de memoria (JEP106), de OpenOCD
python3 tools/gen_intel_gpus.py        # el nombre comercial de cada gráfica de Intel, de Mesa
python3 tools/gen_lang.py --write      # poner al día los archivos de idioma
python3 tools/medir_referencia.py      # rehacer la escala de puntuación
python3 tools/anadir_puntuacion.py INFORMES  # sumar medidas ajenas a la tabla
python3 tools/install_desktop.py       # entrada de menú: «Silux (desarrollo)»
python3 tools/volcar_gpu.py            # lo que publica el kernel de cada gráfica
python3 tools/volcar_equipo.py NOMBRE  # este equipo, anonimizado, a tests/fixtures/equipos/
python3 tools/montar_equipo.py NOMBRE ORDEN…  # ejecutar algo con un volcado montado, como los tests
python3 tools/importar_informe.py INFORME NOMBRE  # el anexo del informe de alguien, a volcado
python3 tools/update_screen_references.py  # rehacer lo que enseña cada volcado (y revisar el diff)
python3 tools/comprobar_privacidad.py  # antes de publicar nada
python3 tools/dump_fingerprint.py --save     # el JSON y el informe de cada volcado, antes de un cambio
python3 tools/dump_fingerprint.py --compare  # y después: tienen que salir idénticos
python3 tools/medir_consumo.py         # lo que gasta, contra sus objetivos (regla 7)
python3 tools/capturas_readme.py       # las capturas del README, con permisos
python3 tools/build_appimage.py --container   # el AppImage que se reparte
python3 tools/probar_en_minimo.py --container # la suite en el Python del suelo
python3 tools/agitar_ventana.py --ventanas 6  # cierres de Qt con la ventana cambiando de forma
python3 tools/probar_actualizador.py VIEJO NUEVO  # el actualizador contra un GitHub falso
uv sync --extra gui                    # el entorno de desarrollo: pytest y PySide6
QT_QPA_PLATFORM=offscreen uv run pytest -n auto -m "not a_solas"  # la suite, en paralelo (-n 4 si corre algo más)
QT_QPA_PLATFORM=offscreen uv run pytest -m a_solas  # los tres que miden, solos
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .  # sin instalar nada
```

En paralelo tardan unos seis minutos con seis núcleos: la suite los llena,
y el tiempo es su trabajo total, no el del test más largo. **`-n auto` cuando la suite es lo único pesado que corre** (sin
agentes en paralelo, sin un contenedor, sin otra suite a la vez); **`-n 4` si
hay algo más corriendo**: cada proceso carga Qt, y varias suites a la vez
llenan la memoria. Las dos pasadas son las del CI: tres tests comparan dos medidas de
rendimiento y van solos (`tests/conftest.py`). Cuántos son lo dice la suite al
terminar; no se apunta aquí a mano. Si sale bastante menos que en la
última ejecución, falta algo por recoger. Corren en una carpeta temporal propia
(`tests/__init__.py`): no tocan la configuración ni el historial de quien los
ejecuta.

**El suelo es Python 3.10** y aquí se desarrolla en 3.14: que pase aquí no dice
que pase en el mínimo, y lo que rompe el suelo no se ve leyendo el código. El
AppImage normal lleva 3.14 (python-build-standalone) y PySide6 6.12; el
compat, el 3.10 de Ubuntu 22.04 y PySide6 6.9. El CI pasa la suite con esas
dos parejas. **El AppImage se construye siempre con `--container`**:
sin él se lleva la glibc y el juego de instrucciones de quien lo compila. Por
qué, los dos techos de PySide6 y las dos guardas del procesador:
[docs/empaquetado.md](docs/empaquetado.md).

Un volcado se monta con `tools/montar_equipo.py`, no apuntando
`SILUX_SYSROOT` a su carpeta: git no guarda las carpetas vacías, y cuentan.

Capturas sin pantalla, siempre en `"$(xdg-user-dir PICTURES)/silux-test/"` y
nunca dentro del repositorio. **Nunca se captura la ventana activa ni la
pantalla a ciegas**: solo la ventana de Silux, buscada por su título o su
identificador; la ventana activa puede ser cualquier otra. Lo que se fuerza por la línea de órdenes —tema,
densidad, letra, acento, tamaño— vale solo para esa ejecución y no se guarda en
`settings.json`.

```bash
mkdir -p "$(xdg-user-dir PICTURES)/silux-test"
QT_QPA_PLATFORM=offscreen python3 -m silux.ui.app \
  --screenshot "$(xdg-user-dir PICTURES)/silux-test/sensores.png" \
  --page Sensores --dark --compact --size 900x680
```

Una sección que este equipo no tiene —Batería en un sobremesa— sale con código
2 en vez de guardar otra página.

Acepta además `--font-scale`, `--anonymous` y `--samples N` (con
`--interval 1`, `--samples 65` captura tras un minuto de gráficas).

## Las reglas que sostienen el diseño

No son preferencias de estilo: cada una viene de un problema concreto.

1. **El modelo guarda números, no texto.** `freq_hz: int`, nunca `"2.90 GHz"`.
   Todo el formateo vive en `silux/render.py` y ocurre al pintar. Vale igual
   para cualquier decisión: si ya hay una función que decide algo, no se
   reimplementa al lado.
2. **`Snapshot` es inmutable.** Los proveedores escriben en un `Draft` mutable
   y este se congela; la interfaz compara fotos y repinta lo que cambió.
3. **`cpu.types` es una lista.** Un Intel híbrido tiene núcleos P y E con
   cachés y frecuencias distintas.
4. **Nada se lee en el hilo de la interfaz.** `ui/sampler.py` es un QThread;
   ahí se fija la afinidad para CPUID y ahí se abre el diálogo de polkit.
5. **Cuando falta un dato se explica.** Un `Note` con su motivo en vez de
   esconder la sección; cada página enseña solo sus notas. Y lo que no existe
   en este hardware no se pinta con guion: se esconde y se nombra al pie. Lo
   que falta por permisos lleva candado, que es otro estado: tiene arreglo.
   Un fallo de nuestro código no se explica como algo que el equipo no
   tiene: es un error, y el informe lleva su traza (`silux/failures.py`).
6. **Los widgets que se refrescan a menudo reutilizan.** `ChipRow` y `Table`
   reescriben el texto de lo que ya existe; hay tests que lo vigilan.
7. **Presupuesto: 300 MB de memoria, y de CPU, en el equipo de referencia
   ([docs/rendimiento.md](docs/rendimiento.md)) y para la
   página que más gasta, 7 % de un núcleo a la vista sin movimiento fluido,
   9 % con él y 5,5 % escondida.** Ronda los 160 MB y 5,7 / 7,2 / 4,5 %. Lo
   comprueba `tools/medir_consumo.py`, que sale con 1 si algo se pasa; las
   tablas, cómo se mide y qué se arregló, en
   [docs/rendimiento.md](docs/rendimiento.md). Lo que no se ve no se pinta:
   la foto entera va a la página abierta y las demás guardan su historia
   (`record`). La salida conocida si la memoria se acerca es construir las
   páginas al visitarlas.
8. **Lo que cueste memoria de forma permanente, en otro proceso.** OpenGL,
   Vulkan y OpenCL se preguntan en un hijo (`gpuapi.query()`), que muere
   al contestar; un driver que revienta solo se lleva al hijo.
9. **La interfaz responde al momento.** Lo que cambia (permisos, un disco
   que se conecta, un dato que aparece o desaparece) se ve en la página
   abierta sin salir y volver. Toda acción que el usuario hace desde una
   página tiene su efecto visible en esa misma página. Lo comprueba
   `tests/test_al_momento.py`: una página abierta con una foto que recibe
   otra queda igual que montada directamente con la segunda.

El porqué largo de cada una y el resto de la arquitectura:
[docs/arquitectura.md](docs/arquitectura.md).

### Lo que enseñaron los informes de la gente

Cada una salió de un fallo en un equipo que no era el nuestro. Valen para el
código nuevo:

- **Lo que funciona con nuestros volcados no está probado.** Lo que lee o
  tapa el equipo se prueba también con lo de la gente montado encima
  (`tests/test_annex_on_other_machines.py`). Nuestros volcados ya llevan los
  sustitutos: volcarlos otra vez es el caso de quien tiene esos valores.
- **Un dato de la persona** (el nombre del equipo, el usuario) se busca y se
  tapa como palabra entera, nunca dentro de rutas, drivers, modelos ni
  marcas. Un nombre que es de todos (la marca, la familia, la distribución,
  un driver, uno corto) no se busca. Lo que pone el anonimizado nunca es un
  dato.
- **El tipo de un disco no sale solo de `rotational`**: el kernel lo pone a 1
  en un disco virtual y en casi todo lo que va por USB.
- **La identidad de una pieza necesita su modelo**, no solo la familia; lo que
  declara un hipervisor no se busca en la tabla.
- **Una unidad o un formato del fabricante sale de su fuente** (drivedb.h de
  smartmontools, NVML tal cual), no se supone; y un dato que no cuadra con
  otro (escrito menos que ocupado) no se enseña.
- **Un aviso dice lo que se sabe**: no culpa a un módulo si la causa puede ser
  la BIOS. Y «no lo tiene» no es «no lo sé»: lo primero se dice.
- **Lo que Silux lanza lleva `system_env.system_environment()`**; solo su
  propio Python se queda con el entorno del AppImage.
- **Lo que se usa del sistema va en `system_deps.py`**, con el paquete que lo
  trae en Debian, Ubuntu, Fedora, Arch y Gentoo, preguntado a su gestor de
  paquetes; si falta, Diagnóstico lo dice. `docs/dependencias.md` dice lo mismo
  (`tests/test_system_deps.py`). Un programa se busca también en `/usr/sbin`:
  el `PATH` de Debian no lo lleva.
- **Lo que vigila `os` o `io` se prueba en Python 3.10** (el compat): su
  `pathlib` guarda sus propias copias desde que se importa.
- **Ninguna resta de contadores sin ventana válida.** Todo lo que divide la
  diferencia de dos lecturas por el tiempo pasa por `providers/counters.py`:
  una ventana de menos de la mitad del intervalo, o un contador que va hacia
  atrás, no da dato, y esa lectura es la nueva base
  (`tests/test_counter_windows.py`). Las fotos de un test van separadas un
  intervalo de reloj falso (`tests/interval.py`), como en el muestreador.
- **Lo imposible se descarta solo**: un voltaje que no cuadra tira el voltaje,
  no la velocidad bien leída que venía al lado. Lo que sale de restar un
  contador también: un vatio negativo o por encima de lo que da la pieza no
  entra en la gráfica, ni en el máximo, ni en la media, y el informe dice sus
  números. Es la red, detrás de la ventana válida, no el arreglo.
- **Si el driver no da una medida, no se rellena con otra**: ni con un
  límite, ni con otra cifra que publique al lado (un búfer de muestras), ni
  con lo de otra pieza. Sale sin dato y con su nota, y el informe dice qué
  contestó cada llamada. La misma medida por otra vía del driver (la media
  de un segundo donde no está la instantánea) vale; lo que su propia
  herramienta da como N/A, no. Y **un dato solo aparece con su propio
  nombre**: lo que sale de otra fuente (el voltaje nominal del SPD, la
  resolución preferida del EDID) lo dice en el propio campo, no solo al pie,
  y en `--json` va en un campo que se llama como lo que es.
- **El color de una temperatura sale solo de los límites que declara la
  pieza** (`silux/thermal.py`): normal, ámbar desde su `max` y rojo desde
  su `crit`; sin límites, sin color, y nunca uno inventado ni un degradado.
  La única excepción es el Tjmax de la ficha de AMD (de Zen 2 en adelante),
  que solo avisa, nunca en rojo, y dice de dónde sale.
  Los valores de relleno (0, 0 K, 0xFFFF K) no son límites. Un solo código
  para Sensores, Inicio, CPU, gráfica y discos (`theme.LEVEL_COLOURS`,
  `widgets.paint_level`).
- **Toda temperatura y toda diferencia de temperatura que se enseña pasa por
  `render`** (`temperature`, `temperature_whole`, `temperature_difference`,
  `temperature_unit`): nunca «°C» a mano. El nivel se decide en °C; en °F se
  convierte y luego se redondea, y una diferencia es ×1,8 sin sumar 32
  (`tests/test_fahrenheit.py` recorre cada página de cada volcado).
- **Una lectura suelta no es el intervalo**: lo que el hardware da como un
  instante (el uso de una AMD, la frecuencia de una Intel) se lee entre
  muestras y se enseña su media. Y dormida no es 0: es «en reposo».
- **Lo que se dice de una pieza se mira en esa pieza**: que el ayudante
  devuelva algún contador no dice que devuelva los de esta gráfica. Y un
  estado que se activa también vuelve atrás.
- **Un arreglo se compara con la herramienta de referencia** (`df`,
  `sensors`…) en un equipo de verdad, no con que el síntoma desaparezca.
- **En pantalla, lenguaje normal**: ni rutas, ni nodos, ni hwmon. Dónde se
  buscó va al `detail` de la nota, que solo escribe el informe
  (`tests/test_igpu_temperature.py` lo mira en cada página de cada volcado).
- **La lógica nunca decide sobre un texto traducido.** Compara, agrupa y
  guarda con códigos, claves o valores en bruto (el código de SMBIOS,
  `Note.key`, `Segment.key`, `Sensor.device_key`); la traducción va al final,
  al pintar. Cada volcado en español y en inglés da el mismo modelo salvo sus
  textos (`tests/test_language_independence.py`), y cada página se ve solo en
  el idioma elegido (`tests/test_interface_language.py`). Ni una fecha se
  guarda ya escrita.
- **Un número con su nombre pasa por `render.counted`**: con 1, el singular
  (`clave.one`), en los dos idiomas (`tests/test_plurals.py`). «1 módulos»
  salía en la imagen para compartir.
- **Lo que corre como root no escribe ningún archivo**, sea el ayudante o
  cualquier otro guion que se lance con pkexec: lo que deja algo puesto
  para siempre lo copia el usuario.
- **Una gráfica dibuja una sola serie.** Cada punto entra con su
  `Series(clave, unidad)`: otra clave empieza de cero, y lo que no cabe en
  su unidad (`model.PLAUSIBLE`) no entra (`tests/test_chart_series.py`).
- **Los datos de prueba de un formato binario no se construyen con lo que
  entiende el decodificador**: se validan contra bytes reales o contra la
  especificación, byte a byte. Un constructor con los mismos offsets
  equivocados que el decodificador da una suite en verde y las cifras mal.

## Cómo está repartido

```
silux/
├─ model.py        dataclasses congeladas: Snapshot, CpuType, Sensor, Board…
├─ render.py       ÚNICO sitio donde un valor se convierte en texto
├─ collector.py    orquesta los proveedores; su orden importa y está comentado
├─ failures.py     los fallos de nuestro código, con su traza, para el informe
├─ cli.py          volcado en terminal, JSON, sensores e informe
├─ report.py       informe en Markdown para reportar fallos
├─ privacidad.py   qué identifica a alguien: lo usan el informe y las capturas
├─ desktop.py      la entrada de menú y sus iconos: la herramienta y Ajustes
├─ kernel.py       qué dato es de qué versión del kernel (docs/kernel.md)
├─ settings.py     preferencias en ~/.config/silux
├─ tracking.py     mínimos, máximos y medias por sensor
├─ throttling.py   desde cuándo lleva frenándose algo, y por qué
├─ registro.py     graba la sesión a un CSV
├─ i18n.py         el idioma de la interfaz; el original es el español
├─ volcado.py      volcar este equipo, anonimizado (tools/volcar_equipo.py)
├─ annex.py        el anexo del informe: ese volcado en texto, y de vuelta
├─ system_env.py   el entorno de lo que se lanza, sin lo que añade el AppImage
├─ system_deps.py  lo que se usa del sistema, con su paquete en cada familia
├─ rawcpuid.py     CPUID desde Python, sin root (mmap + ctypes)
├─ gpuapi.py       OpenGL, Vulkan, OpenCL y VA-API, en otro proceso
├─ amdgpu.py, i915.py   ioctl DRM de cada fabricante
├─ nvml.py         NVIDIA propietaria
├─ gpumetrics.py   telemetría del firmware AMD, por versión
├─ edid.py         la chapa del monitor, con CTA-861
├─ drmmode.py      el modo que tiene puesto cada salida, por los ioctl de DRM
├─ spd.py          el chip de identificación de la RAM (DDR4 y DDR5)
├─ smart.py        el diagnóstico de los discos
├─ features.py     tabla declarativa de banderas de CPUID
├─ pciids.py       nombres de dispositivos PCI
├─ usbids.py       nombres de dispositivos USB (la tarjeta de red USB)
├─ benchmark.py    prueba de CPU que reporta en qué condiciones midió
├─ membench.py     ancho de banda y latencia de la memoria, en otro proceso
├─ history.py      historial de pruebas de este equipo
├─ updates.py      lo único que sale a la red, y solo si se pide: la versión
│                  nueva y la sustitución comprobada del AppImage
├─ score.py        la puntuación comparable entre equipos, y su escala
├─ providers/      una fuente cada uno; ninguno conoce a los demás
│                  (pci.py, devices.py y cpuidle.py son los de los datos
│                  nuevos; `devices.py` no abre nunca un número de serie)
├─ privileged/     el ayudante root mínimo, su cliente, el instalador y el
│                  cargador de módulos de una lista blanca fija
├─ db/             cpu_ids.json (generado), sockets.json y families.json,
│                  memory_limits.json (el máximo de memoria por modelo),
│                  scores.json (la escala), lang/ (es.json, en.json) y
│                  THIRD_PARTY_NOTICES.md, los avisos de lo que es de otros
└─ ui/             tema, hilo de muestreo, una página por sección;
                   widgets.py son las primitivas que usan varias páginas,
                   y el widget de una sola página vive en su módulo;
                   icons.py dibuja los iconos de la barra lateral y la marca
                   (el logo vive en ui/assets/ y es uno solo para todo);
                   background.py espera a pkexec fuera del hilo de la
                   interfaz, dialogs.py son los diálogos de la ventana y
                   welcome.py la bienvenida de la primera vez
```

Cada módulo, comentado: [docs/arquitectura.md](docs/arquitectura.md#el-reparto-comentado).

## Estado

Terminadas las catorce: **Inicio, CPU, Cachés, Placa base, Memoria,
Gráficos, Almacenamiento, Red, Dispositivos, Batería, Sistema, Rendimiento,
Sensores, Ajustes**. La de Batería solo aparece en los equipos que tienen una.

- La escala del benchmark es la **v6**: puntúan dos cargas de las cinco, las
  que no dependen de la zlib de cada distribución. `score.VERSION` y
  `db/scores.json` van siempre en el mismo commit. [docs/benchmark.md](docs/benchmark.md)
- Qué se ha validado contra qué pieza y qué se escribió a ciegas (NVIDIA sí,
  ARM no): [docs/equipos-probados.md](docs/equipos-probados.md). Hay diecinueve
  equipos volcados para la suite: dos del i5-10400 (en reposo y con turbo),
  el Ryzen 7 5800X3D, una máquina QEMU/KVM como la de un probador
  (`qemu-kvm`, hecha aquí con QEMU), y quince importados del anexo de un
  informe: un ThinkPad T14 (`i5-1135g7`), un sobremesa con Gentoo,
  OpenRC y una RTX 4060 (`i7-10700f`), un Lenovo LOQ híbrido con una RTX
  4050 (`i5-12450h`), un portátil con un Celeron N4000 (`celeron-n4000`),
  un sobremesa con un Athlon 3000G sin turbo ni driver de frecuencia
  (`athlon-3000g`), otro con una Radeon RX 550 sin telemetría del
  firmware (`ryzen3-4100`), un i5-3330 con DDR3 de dos velocidades
  (`i5-3330`), un Acer con DDR3L y una partición de intercambio
  (`i5-5200u`), un ThinkPad T480s con batería y umbrales de carga
  (`i5-8350u`), un Core 2 Duo con antiX, runit, BIOS heredada y una
  Quadro con nouveau (`core2-p8400`), un Celeron 560 de un núcleo con DDR2
  (`celeron-560`), un ASUS con Optimus y la GeForce dormida (`i7-4710hq`),
  un sobremesa con un Celeron G3900, una Wi-Fi USB y una tele por HDMI
  (`celeron-g3900`), un HP con Fedora y GNOME (`i3-1115g4`) y un Ryzen 5
  5600G con la integrada desactivada y una RTX 4060 (`ryzen5-5600g`).
- Lo que enseña cada volcado, página a página, está en
  `tests/fixtures/screens/`: un cambio que lo altera falla en
  `test_screen_references` hasta que se rehace con
  `tools/update_screen_references.py`, y el diff se revisa en el commit.
- Lo que se lee en la ventana no lleva rellenos del firmware, razones
  sociales ni chips con su dirección: lo vigila `tests/test_nada_en_bruto.py`
  con cada volcado. Una marca sale de `render.maker`; un chip, de
  `render.chip_name`.
- Lo que se toma de otro proyecto (hoy, las tablas de libcpuid y CPU-X, la
  base de discos de smartmontools para las unidades del SMART, la lista
  JEP-106 de OpenOCD para los fabricantes de memoria y las tablas PCI de
  Mesa para el nombre de las gráficas de Intel) lleva
  su aviso en `silux/db/THIRD_PARTY_NOTICES.md`, que va en pip y en los
  AppImage; `tests/test_avisos_de_terceros.py` lo compara con las fuentes que
  declara la tabla. Un procesador que no está en ella dice «no está en la
  tabla de esta versión»: no se inventa ni se pinta con guion.
- Lo que libcpuid no tiene sale de fuentes vivas: de Intel, `intel-family.h`
  del kernel en una etiqueta fija (`KERNEL_TAG`); de AMD, su tabla oficial
  de amd.com (nombre en clave, encapsulado y nodo por modelo); y el nodo que
  falte, del `cpuid` de Todd Allen en una versión fija (`CPUID_VERSION`).
  libcpuid sigue mandando cuando reconoce el chip. Una generación nueva es
  subir la etiqueta o la versión y regenerar.
- La tabla se comprueba con 411 procesadores de verdad
  (`tests/test_referencias_cpu.py`); lo que hoy no sale como en libcpuid
  está en `tests/fixtures/referencias_cpu_pendientes.json`, que solo puede
  encoger. `.github/workflows/tabla-cpu.yml` la regenera el día 1 de cada
  mes y abre un PR si cambia.

## Convenciones

**Idioma.** La interfaz va en **español neutro** (`video`, `archivo`,
`dispositivo`, `equipo`); el código nuevo, en inglés (ver «Código»). Las claves
de idioma son símbolos (`cpu.card.clocks`) y `_()` cae al español y luego a la
clave. La interfaz está entera en los dos idiomas:
1939 claves, ninguna sin traducir. Tres reglas que no se ven hasta que fallan:

- **Nada de `_()` en una constante de módulo**: se resuelve al importar, antes
  de saber el idioma.
- **`_` no se usa de descarte** (`for _ in …`): tapa la función de traducción.
- **Los proveedores solo traducen lo que inventan**; el dato del equipo pasa
  tal cual. A `_()` solo llega un literal o una variable de una tabla del
  mismo archivo.

**Código (desde el 20 de noviembre de 2026).** Todo lo nuevo, en inglés y con
el estilo de PEP 8: `snake_case` para funciones, métodos, variables,
parámetros, atributos, módulos y tests; `CamelCase` solo para clases;
constantes en `MAYÚSCULAS`. También dentro de un módulo que siga en español,
y nunca las dos lenguas en el mismo nombre.

Los comentarios y docstrings nuevos, en inglés natural, como lo escribiría
alguien nativo: no se traducen frase a frase, se reescriben. Un comentario se
queda solo si explica lo que el código no dice (el porqué, una trampa del
hardware o del kernel, un límite que no es obvio); si repite el código, se
borra. Mejor un nombre claro que un comentario que explique un nombre malo.
Un docstring dice qué hace y lo que no es obvio, corto, sin historia ni
ejemplos de equipos concretos.
«Antes…», «se probó…» o «costó…» van al mensaje del commit; un porqué que no
cabe en un comentario, a `docs/decisiones/`.
ruff (las reglas F y el orden de imports, en `pyproject.toml`) pasa en el CI
y con `pre-commit`.

**Escribe para cualquiera que lo lea: corto, directo, sin rayas ni frases
solemnes, sin hablar de un equipo concreto; los comentarios explican el
porqué.** Vale para el código, la documentación, los commits y los textos
del repositorio. «Algunos portátiles declaran SODIMM también para la memoria
soldada», no «el T14 declara SODIMM»: el equipo concreto va en el test o en
su fixture.

Lo que ya existe no se renombra al pasar: se pasa a inglés por zonas, cada
una en su rama, con herramientas que entienden el código (LibCST o rope, no
buscar y reemplazar), la huella idéntica y los tests como red. En cada zona,
sus comentarios y docstrings se rehacen con el criterio de arriba, y al
acabarla se abren todas las páginas de todos los volcados en los dos
idiomas, además de la suite: rope falla sin avisar. Sigue
en español lo que lee la gente: la interfaz (`silux/db/lang/`, el original),
el CHANGELOG y las notas de las versiones. El README va en los dos idiomas:
`README.md` (español, el de por defecto) y `README.en.md`, con las mismas
secciones y los mismos enlaces (`tests/test_readmes.py`); si cambia uno,
cambia el otro.

**Tests.**
- Una comprobación que nadie ha visto fallar no es una comprobación: todo test
  o guarda nueva se ejecuta contra el caso que pretende cazar.
- Un dato nuevo no está terminado hasta que un test lo ve en pantalla,
  montando la página de verdad.
- Ningún test fabrica a mano un estado que la ejecución real no produce: está
  eligiendo también qué rama se ejecuta.
- Un test que lee el hardware de quien lo ejecuta no exige encontrar algo
  concreto: en el CI no está.
- Un test que recorre los volcados va uno por volcado (`tests/per_dump.py`),
  y la foto de cada uno se comparte en el proceso (`shared_snapshot`) salvo
  si el test parchea algo.
- **Ningún cambio visual se da por hecho sin mirarlo en la captura**, y el
  mensaje del commit dice solo lo que se ve en ella. La suite no pinta: lo
  que se pinta lo vigilan `test_todo_se_pinta.py` y los tests que miran la
  imagen.

**Flujo de trabajo.**
- **Nadie se nombra sin su permiso.** Los agradecimientos (Ajustes → Acerca
  de, «Gracias» en los README y «Con informes de…» bajo el título de cada
  versión del CHANGELOG) salen de `silux/db/thanks.json`, que solo rellena el
  autor con los nombres que cada uno le autoriza, y cada nombre tiene que
  estar también en la lista que él aprueba en `tests/test_thanks.py`.
- **Lo que toca privilegios se propone antes de escribirlo**, con lo que se
  ha medido, y se espera respuesta.
- **Lo que depende de que alguien se acuerde de subir un número no es una
  comprobación.** Se compara el contenido.
- **GitHub ordena las releases por el día del commit de su etiqueta y, dentro
  del mismo día, por el nombre como texto**: «0.4.0rc10» salió debajo de
  «0.4.0rc9» y «0.4.0rc8», publicadas el mismo día. No se publica una versión
  el día de otra cuyo nombre ordene por encima como texto, y después de
  publicar se mira que salga la primera en la página. «Buscar ahora» compara
  versiones, no ese orden (`updates.latest`).
- Lo local de quien trabaja aquí (sus notas, su equipo, su forma de trabajar)
  va en `CLAUDE.local.md`, que no se publica.

**Commits (desde el 20 de noviembre de 2026).** Conventional Commits, en
inglés y cortos: el título, una línea clara; el cuerpo, solo si hace falta
explicar el porqué. Los anteriores, en español, se quedan como están.

```
type(area): short lowercase description, no final period

Optional body: the why, only when the title does not say it.

Co-Authored-By: <el modelo de la sesión> <noreply@anthropic.com>
```

- Tipos del estándar, sin traducir: `fix`, `feat`, `test`, `docs`,
  `refactor`, `perf`, `build`, `ci`, `chore`.
- La zona es el módulo o la carpeta: `spd`, `providers/hwmon`, `ui/widgets`,
  `privileged`, `bench`, `report`, `cli`, `i18n`, `appimage`, `ci`, `tests`,
  `claude`.
- El autor es el del repositorio. Cuando el commit se escribe con Claude, lleva
  al final la línea `Co-Authored-By` del modelo con que se trabaja en esa
  sesión, no uno fijo.
- **Un commit por cambio lógico**: una causa, con su test en el mismo commit.
  Lo que solo mueve código va en uno propio. La suite queda en verde entre uno y
  otro.

El porqué de cada convención: [docs/convenciones.md](docs/convenciones.md).

## Lo que queda por arreglar

En [docs/pendientes.md](docs/pendientes.md), una sola lista por zonas con lo
que se midió; lo más grave, arriba. Los de la quinta auditoría llevan su
código (F-…), que es por el que se buscan. Lo que se arregla se quita de ahí
en el mismo commit; lo que se encuentra y no se arregla, se apunta.

## Dónde está cada cosa en docs/

- [docs/arquitectura.md](docs/arquitectura.md): cómo viaja un dato, el reparto
  comentado, las reglas con su porqué y cómo se ejecuta cada cosa.
- [docs/convenciones.md](docs/convenciones.md): cómo contribuir, el porqué de
  cada convención y todo lo del idioma.
- [docs/pendientes.md](docs/pendientes.md): lo que falta, con su detalle.
- [docs/empaquetado.md](docs/empaquetado.md): el suelo, el AppImage, los
  techos de PySide6 y las guardas.
- [docs/privilegios.md](docs/privilegios.md): el ayudante, pkexec y polkit.
- [docs/equipos-probados.md](docs/equipos-probados.md): qué se ha probado
  contra qué pieza, y los equipos volcados.
- [docs/kernel.md](docs/kernel.md): desde qué versión del kernel existe cada
  dato, con su fuente. El mínimo es 5.15.
- [docs/nvml.md](docs/nvml.md): desde qué driver de NVIDIA existe cada dato
  que se pide a NVML, y qué se prueba si una llamada no contesta.
- [docs/rendimiento.md](docs/rendimiento.md): lo que gasta Silux, cómo se
  mide y sus objetivos.
- [docs/benchmark.md](docs/benchmark.md): la escala y la medida de la memoria.
- [docs/motores-de-graficas.md](docs/motores-de-graficas.md): qué motor de
  cada gráfica se puede medir y de dónde sale en cada driver.
- [docs/comprobar.md](docs/comprobar.md): el comando equivalente a cada dato,
  para verificarlo a mano.
- [docs/decisiones/](docs/decisiones/): el porqué de cada decisión que no
  cabe en un comentario, con sus datos y lo descartado.

En la raíz, en inglés: `ARCHITECTURE.md`, `CONTRIBUTING.md` y `SECURITY.md`.
