# Silux — contexto del proyecto

Si existe `../silux-notas/` (las notas privadas del autor, clonadas al lado),
se leen lo primero su `en-curso.md` y su `claude.md`.

Perfilador de hardware para Linux en Python + PySide6: lo que en Windows hacen
**CPU-Z, GPU-Z y HWMonitor**, en un solo programa nativo. Identificación del
hardware y monitorización de sensores.

**Lo que este programa no es: un administrador de tareas.** Los procesos son
software, no hardware, y Linux ya tiene buenos monitores de procesos.
Tampoco el uso de la gráfica ni de nada por programa (DRM `fdinfo` incluido),
aunque se lea sin permisos.

Este archivo es corto a propósito: se carga en cada sesión. El detalle vive en
`docs/` (índice al final). Antes de tocar una zona, se lee lo suyo en
[docs/pendientes.md](docs/pendientes.md) y, si están las notas, en
`../silux-notas/lecciones.md`.

## Cómo se ejecuta

```bash
python3 -m silux.ui.app                 # interfaz
python3 -m silux.cli                    # volcado en terminal
python3 -m silux.cli --json             # API para otros programas
python3 -m silux.cli --sensors          # el árbol de sensores
python3 -m silux.cli --report FICHERO   # el informe completo, de las páginas (--short, el corto)
python3 tools/gen_cpu_db.py            # regenerar la base de datos de CPUs
python3 tools/gen_memory_limits.py --intel-desde DIR  # el máximo de memoria por modelo
python3 tools/gen_lang.py --write      # poner al día los archivos de idioma
python3 tools/medir_referencia.py      # rehacer la escala de puntuación
python3 tools/anadir_puntuacion.py INFORMES  # sumar medidas ajenas a la tabla
python3 tools/install_desktop.py       # entrada de menú: «Silux (desarrollo)»
python3 tools/volcar_gpu.py            # lo que publica el kernel de cada gráfica
python3 tools/volcar_equipo.py NOMBRE  # este equipo, anonimizado, a tests/fixtures/equipos/
python3 tools/montar_equipo.py NOMBRE ORDEN…  # ejecutar algo con un volcado montado, como los tests
python3 tools/comprobar_privacidad.py  # antes de publicar nada
python3 tools/medir_consumo.py         # lo que gasta, contra sus objetivos (regla 7)
python3 tools/capturas_readme.py       # las capturas del README, con permisos
python3 tools/build_appimage.py --container   # el AppImage que se reparte
python3 tools/probar_en_minimo.py --container # la suite en el Python del suelo
python3 tools/agitar_ventana.py --ventanas 6  # cierres de Qt con la ventana cambiando de forma
uv sync --extra gui                    # el entorno de desarrollo: pytest y PySide6
QT_QPA_PLATFORM=offscreen uv run pytest -n auto -m "not a_solas"  # la suite, en paralelo (-n 4 si corre algo más)
QT_QPA_PLATFORM=offscreen uv run pytest -m a_solas  # los tres que miden, solos
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .  # sin instalar nada
```

En paralelo tardan medio minuto entre las dos pasadas; en serie, minuto y
medio. **`-n auto` cuando la suite es lo único pesado que corre** (sin
agentes en paralelo, sin un contenedor, sin otra suite a la vez); **`-n 4` si
hay algo más corriendo**: cada proceso carga Qt, y varias suites a la vez
llenan 16 GB. Las dos pasadas son las del CI: tres tests comparan dos medidas de
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
6. **Los widgets que se refrescan a menudo reutilizan.** `ChipRow` y `Table`
   reescriben el texto de lo que ya existe; hay tests que lo vigilan.
7. **Presupuesto: 300 MB de memoria, y de CPU, en el 5800X3D y para la
   página que más gasta, 7 % de un núcleo a la vista sin movimiento fluido,
   9 % con él y 5,5 % escondida.** Ronda los 160 MB y 5,7 / 7,2 / 4,5 %. Lo
   comprueba `tools/medir_consumo.py`, que sale con 1 si algo se pasa; las
   tablas, cómo se mide y qué se arregló, en
   [docs/rendimiento.md](docs/rendimiento.md). Lo que no se ve no se pinta:
   la foto entera va a la página abierta y las demás guardan su historia
   (`record`). La salida conocida si la memoria se acerca es construir las
   páginas al visitarlas.
8. **Lo que cueste memoria de forma permanente, en otro proceso.** OpenGL,
   Vulkan y OpenCL se preguntan en un hijo (`gpuapi.consultar()`), que muere
   al contestar; un driver que revienta solo se lleva al hijo.
9. **La interfaz responde al momento.** Lo que cambia (permisos, un disco
   que se conecta, un dato que aparece o desaparece) se ve en la página
   abierta sin salir y volver. Toda acción que el usuario hace desde una
   página tiene su efecto visible en esa misma página. Lo comprueba
   `tests/test_al_momento.py`: una página abierta con una foto que recibe
   otra queda igual que montada directamente con la segunda.

El porqué largo de cada una y el resto de la arquitectura:
[docs/arquitectura.md](docs/arquitectura.md).

## Cómo está repartido

```
silux/
├─ model.py        dataclasses congeladas: Snapshot, CpuType, Sensor, Board…
├─ render.py       ÚNICO sitio donde un valor se convierte en texto
├─ collector.py    orquesta los proveedores; su orden importa y está comentado
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
├─ rawcpuid.py     CPUID desde Python, sin root (mmap + ctypes)
├─ gpuapi.py       OpenGL, Vulkan, OpenCL y VA-API, en otro proceso
├─ amdgpu.py, i915.py   ioctl DRM de cada fabricante
├─ nvml.py         NVIDIA propietaria
├─ gpumetrics.py   telemetría del firmware AMD, por versión
├─ edid.py         la chapa del monitor, con CTA-861
├─ spd.py          el chip de identificación de la RAM (DDR4 y DDR5)
├─ smart.py        el diagnóstico de los discos
├─ features.py     tabla declarativa de banderas de CPUID
├─ pciids.py       nombres de dispositivos PCI
├─ benchmark.py    prueba de CPU que reporta en qué condiciones midió
├─ membench.py     ancho de banda y latencia de la memoria, en otro proceso
├─ history.py      historial de pruebas de este equipo
├─ score.py        la puntuación comparable entre equipos, y su escala
├─ providers/      una fuente cada uno; ninguno conoce a los demás
│                  (pci.py, devices.py y cpuidle.py son los de los datos
│                  nuevos; `devices.py` no abre nunca un número de serie)
├─ privileged/     el ayudante root mínimo, su cliente, el instalador y el
│                  cargador de módulos de una lista blanca fija
├─ db/             cpu_ids.json (generado), sockets.json y families.json,
│                  memory_limits.json (el máximo de memoria por modelo),
│                  scores.json (la escala) y lang/ (es.json, en.json)
└─ ui/             tema, hilo de muestreo, una página por sección;
                   widgets.py son las primitivas que usan varias páginas,
                   y el widget de una sola página vive en su módulo;
                   icons.py dibuja los iconos de la barra lateral y la marca
                   (el logo vive en ui/assets/ y es uno solo para todo);
                   background.py espera a pkexec fuera del hilo de la
                   interfaz, y dialogs.py son los diálogos de la ventana
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
  ARM no): [docs/equipos-probados.md](docs/equipos-probados.md). Hay tres
  equipos volcados para la suite, los tres con los datos nuevos: dos del
  i5-10400 (en reposo y con turbo) y el Ryzen 7 5800X3D.
- Lo que se lee en la ventana no lleva rellenos del firmware, razones
  sociales ni chips con su dirección: lo vigila `tests/test_nada_en_bruto.py`
  con cada volcado. Una marca sale de `render.maker`; un chip, de
  `render.chip_name`.

## Convenciones

**Idioma.** La interfaz va en **español neutro** (`video`, `archivo`,
`dispositivo`, `equipo`); los comentarios, en el español del autor. Las claves
de idioma son símbolos (`cpu.card.clocks`) y `_()` cae al español y luego a la
clave. La interfaz está entera en los dos idiomas:
1383 claves, ninguna sin traducir. Tres reglas que no se ven hasta que fallan:

- **Nada de `_()` en una constante de módulo**: se resuelve al importar, antes
  de saber el idioma.
- **`_` no se usa de descarte** (`for _ in …`): tapa la función de traducción.
- **Los proveedores solo traducen lo que inventan**; el dato del equipo pasa
  tal cual. A `_()` solo llega un literal o una variable de una tabla del
  mismo archivo.

**Nombres.** La API —módulos, clases, métodos públicos, campos del modelo,
claves del JSON y banderas del CLI— en inglés; lo interno que nombra algo del
dominio del programa, en español. Nunca las dos en el mismo identificador ni
en la misma familia. Se aplica a lo nuevo y al tocar cada archivo.

**Comentarios.** Explican por qué el código es así ahora. «Antes…», «se
probó…» o «costó…» van al mensaje del commit o a las lecciones de las notas.

**Tests.**
- Una comprobación que nadie ha visto fallar no es una comprobación: todo test
  o guarda nueva se ejecuta contra el caso que pretende cazar.
- Un dato nuevo no está terminado hasta que un test lo ve en pantalla,
  montando la página de verdad.
- Ningún test fabrica a mano un estado que la ejecución real no produce: está
  eligiendo también qué rama se ejecuta.
- Un test que lee el hardware de quien lo ejecuta no exige encontrar algo
  concreto: en el CI no está.
- **Ningún cambio visual se da por hecho sin mirarlo en la captura**, y el
  mensaje del commit dice solo lo que se ve en ella. La suite no pinta: lo
  que se pinta lo vigilan `test_todo_se_pinta.py` y los tests que miran la
  imagen.

**Flujo de trabajo.**
- **Nunca se empuja sin preguntar.** Commitear es reversible; publicar no.
- **No se publica ninguna versión sin que lo diga el autor.** Ni etiqueta, ni
  release, ni fecha en el CHANGELOG. Lo que entra en `master` se queda como
  «sin publicar» en la entrada de arriba del CHANGELOG, que sigue acumulando
  hasta que él decida cortarla.
- **Lo que toca privilegios se propone antes de escribirlo**, con lo que se
  ha medido, y se espera respuesta.
- **Lo que depende de que alguien se acuerde de subir un número no es una
  comprobación.** Se compara el contenido.
- **Lo que se añade y lo que se quita se enseña en la terminal.** Tras cada
  cambio, Claude escribe en su respuesta el diff de lo que ha tocado (líneas
  con `+` y con `-`), no solo el resumen: el autor lo sigue por ahí.
- **El commit del CLAUDE.md es el último antes de empujar.**
- **Una rama por tema** (`contribuir`, `graficas`, `rendimiento`…), que sale
  de `master`; no hay una rama de trabajo fija por equipo. Un tema terminado
  y con su CI en verde pasa a `master` enseguida: tandas pequeñas, no una
  rama que acumula días. Las ramas no se empujan salvo que se diga; el CI
  de una rama se lanza a mano con
  `gh workflow run appimage.yml --ref RAMA` y se sigue con `gh run watch`.
- **A `master` solo con `git merge --ff-only`**, y solo con el CI de esa rama
  en verde. Si `master` avanzó, se rebasa la rama antes, no se fusiona. Pasar
  a `master` no es publicar: ni etiqueta ni release.

**Commits.** Conventional Commits con la descripción en español:

```
tipo(zona): descripción en minúscula y sin punto final

Cuerpo: el porqué. Qué fallaba, cómo se vio, qué se comprobó, y que el
test se vio fallar antes del arreglo.

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
- [docs/rendimiento.md](docs/rendimiento.md): lo que gasta Silux, cómo se
  mide y sus objetivos.
- [docs/benchmark.md](docs/benchmark.md): la escala y la medida de la memoria.
- [docs/motores-de-graficas.md](docs/motores-de-graficas.md): qué motor de
  cada gráfica se puede medir y de dónde sale en cada driver.
- [docs/comprobar.md](docs/comprobar.md): el comando equivalente a cada dato,
  para verificarlo a mano.

Las notas de trabajo —dónde se quedó cada sesión, las lecciones, las
propuestas y el historial— están en el repositorio privado
`rcv11x/silux-notas`, no aquí.
