# silux — contexto del proyecto

Si existe docs/en-curso.md, se lee lo primero.

Perfilador de hardware para Linux en Python + PySide6: lo que en Windows hacen
**CPU-Z, GPU-Z y HWMonitor**, en un solo programa nativo. Identificación del
hardware y monitorización de sensores.

**Lo que este programa no es: un administrador de tareas.** Los procesos son
software, no hardware, y Linux ya tiene buenos monitores de procesos.

Este archivo es corto a propósito: se carga en cada sesión. El detalle vive en
`docs/` (índice al final). Antes de tocar una zona, se lee su apartado de
[docs/lecciones.md](docs/lecciones.md).

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
python3 tools/volcar_gpu.py            # lo que publica el kernel de cada gráfica
python3 tools/volcar_equipo.py NOMBRE  # este equipo, anonimizado, a tests/fixtures/equipos/
python3 tools/comprobar_privacidad.py  # antes de publicar nada
python3 tools/build_appimage.py --container   # el AppImage que se reparte
python3 tools/probar_en_minimo.py --container # la suite en el Python del suelo
uv sync --extra gui                    # el entorno de desarrollo: pytest y PySide6
QT_QPA_PLATFORM=offscreen uv run pytest -n auto -m "not a_solas"  # la suite, en paralelo
QT_QPA_PLATFORM=offscreen uv run pytest -m a_solas  # los tres que miden, solos
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .  # sin instalar nada
```

En paralelo tardan medio minuto entre las dos pasadas; en serie, minuto y
medio. Las dos pasadas son las del CI: tres tests comparan dos medidas de
rendimiento y van solos (`tests/conftest.py`). Cuántos son lo dice la suite al
terminar; no se apunta aquí a mano. Si sale bastante menos que en la
última ejecución, falta algo por recoger. Corren en una carpeta temporal propia
(`tests/__init__.py`): no tocan la configuración ni el historial de quien los
ejecuta.

**El suelo es Python 3.10** y aquí se desarrolla en 3.14: que pase aquí no dice
que pase en el mínimo, y lo que rompe el suelo no se ve leyendo el código. El
CI lleva las dos puntas. **El AppImage se construye siempre con `--container`**:
sin él se lleva la glibc y el juego de instrucciones de quien lo compila. Por
qué, los dos techos de PySide6 y las dos guardas del procesador:
[docs/empaquetado.md](docs/empaquetado.md).

Capturas sin pantalla, siempre en `"$(xdg-user-dir PICTURES)/silux-test/"` y
nunca dentro del repositorio. Lo que se fuerza por la línea de órdenes —tema,
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

Acepta además `--accent`, `--font-scale` y `--anonimo`.

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
7. **Presupuesto de memoria: 300 MB.** Ronda los 130 con todo abierto. La
   salida conocida si se acerca es construir las páginas al visitarlas.
8. **Lo que cueste memoria de forma permanente, en otro proceso.** OpenGL,
   Vulkan y OpenCL se preguntan en un hijo (`gpuapi.consultar()`), que muere
   al contestar; un driver que revienta solo se lleva al hijo.

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
├─ privileged/     el ayudante root mínimo, su cliente, el instalador y el
│                  cargador de módulos de una lista blanca fija
├─ db/             cpu_ids.json (generado), sockets.json y families.json,
│                  scores.json (la escala) y lang/ (es.json, en.json)
└─ ui/             tema, hilo de muestreo, una página por sección;
                   widgets.py son las primitivas que usan varias páginas,
                   y el widget de una sola página vive en su módulo;
                   background.py espera a pkexec fuera del hilo de la
                   interfaz, y dialogs.py son los diálogos de la ventana
```

Cada módulo, comentado: [docs/arquitectura.md](docs/arquitectura.md#el-reparto-comentado).

## Estado

Terminadas las trece: **Inicio, CPU, Cachés, Placa base, Memoria,
Gráficos, Almacenamiento, Red, Batería, Sistema, Rendimiento, Sensores,
Ajustes**. La de Batería solo aparece en los equipos que tienen una.

- La escala del benchmark es la **v6**: puntúan dos cargas de las cinco, las
  que no dependen de la zlib de cada distribución. `score.VERSION` y
  `db/scores.json` van siempre en el mismo commit. [docs/benchmark.md](docs/benchmark.md)
- Qué se ha validado contra qué pieza y qué se escribió a ciegas (NVIDIA sí,
  ARM no): [docs/hardware-validado.md](docs/hardware-validado.md). Hay tres
  equipos volcados para la suite: dos del i5-10400 y el Ryzen 7 5800X3D.
- Lo que se lee en la ventana no lleva rellenos del firmware, razones
  sociales ni chips con su dirección: lo vigila `tests/test_nada_en_bruto.py`
  con cada volcado. Una marca sale de `render.maker`; un chip, de
  `render.chip_name`.
- Las ramas `escala-v5` y `escala-v6` están superadas y se pueden borrar, pero
  no se borran sin que lo diga el autor.

## Convenciones

**Idioma.** La interfaz va en **español neutro** (`video`, `archivo`,
`dispositivo`, `equipo`); los comentarios, en el español del autor. Las claves
de idioma son símbolos (`cpu.card.clocks`) y `_()` cae al español y luego a la
clave. La interfaz está entera en los dos idiomas:
1014 claves, ninguna sin traducir. Tres reglas que no se ven hasta que fallan:

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
probó…» o «costó…» van al mensaje del commit o a `docs/lecciones.md`.

**Tests.**
- Una comprobación que nadie ha visto fallar no es una comprobación: todo test
  o guarda nueva se ejecuta contra el caso que pretende cazar.
- Un dato nuevo no está terminado hasta que un test lo ve en pantalla,
  montando la página de verdad.
- Ningún test fabrica a mano un estado que la ejecución real no produce: está
  eligiendo también qué rama se ejecuta.
- Un test que lee el hardware de quien lo ejecuta no exige encontrar algo
  concreto: en el CI no está.

**Flujo de trabajo.**
- **Nunca se empuja sin preguntar.** Commitear es reversible; publicar no.
- **Lo que toca privilegios se propone antes de escribirlo**, con lo que se
  ha medido, y se espera respuesta.
- **Lo que depende de que alguien se acuerde de subir un número no es una
  comprobación.** Se compara el contenido.
- **El commit del CLAUDE.md es el último antes de empujar.**
- **Una rama por fase**, que sale de la anterior o de `master`. Las ramas no se
  empujan salvo que se diga; el CI de una rama se lanza a mano con
  `gh workflow run appimage.yml --ref RAMA` y se sigue con `gh run watch`.
- **A `master` solo con `git merge --ff-only`**, y solo con el CI de esa rama
  en verde. Si `master` avanzó, se rebasa la rama antes, no se fusiona.

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

Una línea por punto; el detalle de cada uno, con lo que se midió, está en
[docs/pendientes.md](docs/pendientes.md). Los de la quinta auditoría llevan su
código (F-…), que es por el que se buscan allí.

| Dónde | Gravedad | Qué |
|---|---|---|
| `spd.py` | alta | el XMP de DDR4 ignora la corrección fina del ciclo: un DDR4-3600 sale 3200 (F-A2); pide un volcado real con XMP |
| `privileged/instalar.py` | alta, condicionada | no comprueba que el destino no sea sustituible |
| `ui/pages/cpulive.py` | media-alta | relojes compuestos a mano: 576 MHz sale «0.58 GHz» |
| `providers/hwmon.py` | media-alta | la clave del sensor no incluye el nodo: dos discos iguales se pisan |
| `ui/widgets.py` | media | `StatTile` nace con la raya gruesa, y el arreglo tampoco funciona al perder el dato (F-M2) |
| `ui/sampler.py` | media | cerrar durante un muestreo largo aborta el proceso (F-M3) |
| `ui/pages/performance.py` | media | cambiar el tema mata la prueba en curso (F-M5); la carga máxima no se ve (F-M7) |
| varios | media | texto en español fijo con la interfaz en inglés (F-M8) |
| `ui/widgets.py` | media | las etiquetas seleccionables cuestan 22 MB (F-M9) |
| `ui/pages/memory.py`, `battery.py` | media | voltajes a dos decimales en vez de `render.volts` |
| `providers/derived.py` | media | el tráfico de red del árbol va en potencias de 1024 |
| `spd.py` | media | `decode` revienta con menos de 384 bytes y se pierden todos los módulos |
| `providers/spd_modules.py` | media | casar por referencia puede cruzar los módulos (F-M16) |
| `providers/drm.py` | media | sin `pci.ids`, una dedicada AMD toma el nombre de la integrada (F-M17); `_pmu_ok` no vuelve a `False` (F-M21) |
| `smart.py`, `providers/storage.py` | media | vida negativa en un HDD (F-M18); el estado va por nombre de dispositivo (F-M19) |
| `gpumetrics.py`, `nvml.py`, `derived.py` | media | `if v` con relojes: 0 MHz llega como `None` (F-M20) |
| `providers/` | media | siete proveedores sin `unavailable_reason()` |
| `settings.py` | media | un JSON que no es objeto impide arrancar; un campo malo tira todas las preferencias |
| `privileged/` | media | topes de tamaño después de reservar; el `timeout` no acota; el cliente se desincroniza (F-M24-26) |
| `privileged/helper.py` | media-baja | la cadencia de RAPL la decide el cliente (F-M27) |
| `tools/comprobar_privacidad.py` | media | ciego a IPv6 y seriales; desde otro directorio da su visto bueno sin mirar (F-M30) |
| `report.py`, `cli.py` | media | zócalos vacíos como módulos (F-M31); tres formateos del valor de un sensor (F-M32) |
| `tools/probar_en_minimo.py` | media | cualquier fallo del contenedor se anuncia como «la suite no pasa» (F-M37) |
| `ui/widgets.py` | media-baja | un `float` no finito tumba la gráfica |
| `ui/widgets.py`, `ui/pages/storage.py` | media-baja | `Table` no pinta un candado en una celda: la temperatura de un SATA sigue con guion en la tabla de unidades |
| `privacidad.py`, `tools/volcar_equipo.py` | media-baja | `--anonimo` da la misma IP a todas las interfaces; los volcados, la misma MAC |
| `ui/theme.py` | media-baja | caché de iconos en `/tmp/silux-icons` de nombre fijo |
| `providers/rapl.py` | media-baja | en un contenedor dice que la CPU no tiene contadores |
| `ui/widgets.py` | baja | el globo «copiado» se come el clic; seleccionar copia el entero; `Table.set_rows` con columnas distintas |
| `cli.py` | baja | `--json` sin aviso; `--report ''`; banderas que se pisan; `--with-identifiers` suelto; categorías sin traducir; `--report -` sin aviso |
| `ui/app.py` | baja | cambiar el tema reinicia las gráficas; no hay navegación por teclado |
| `ui/pages/graphics.py` | baja | tasa de datos de la VRAM compuesta a mano |
| `providers/cppc.py` | media, sin comprobar | el techo del silicio con `acpi-cpufreq`: falta el volcado con `amd_pstate=disable` |
| `ui/pages/settings.py` | propuesta | no hay botón para quitar el ayudante instalado; toca privilegios |
| `providers/network.py` | baja | tipo de interfaz sin traducir |
| `providers/storage.py` | baja | modelo SATA cortado a 16 caracteres |
| `collector.py` | baja | `_clone` sin `batteries`, `cpu_extra` ni `memory_traffic` |
| `render.py` | baja | dos canales distintos pueden llamarse «Canal A» |
| `db/lang/` | baja | trece claves muertas; `gen_lang.py` compara por subcadena y solo ve cinco |
| `settings.py`, `registro.py`, `report.py`, `ui/` | baja | idioma sin validar; CSV sin fecha; `_placa(anonymous)`; `disk.pci_slot` y `net.vendor` sin pintar |
| `data/…policy.in`, `cargar_modulo.py` | baja | plantilla huérfana y divergente; `modprobe` sin ruta |
| `tools/build_appimage.py` | baja | `--container` se traga `--keep` y `--appdir-only`; `appimagetool` sin hash |
| `.github/workflows/appimage.yml` | baja | `contents: write` global; acciones por etiqueta y no por SHA; arranque comprobado con `--help` |

## Dónde está cada cosa en docs/

- [docs/lecciones.md](docs/lecciones.md): lo que ya se probó y no funcionó,
  por temas. **Se lee el apartado de la zona antes de tocarla.**
- [docs/convenciones.md](docs/convenciones.md): el porqué de cada convención y
  todo lo del idioma.
- [docs/arquitectura.md](docs/arquitectura.md): cómo funciona por dentro, el
  reparto comentado y el informe de fallos.
- [docs/empaquetado.md](docs/empaquetado.md): el suelo, el AppImage, los
  techos de PySide6 y las guardas.
- [docs/benchmark.md](docs/benchmark.md): la escala y la medida de la memoria.
- [docs/privilegios.md](docs/privilegios.md): el ayudante, pkexec y polkit.
- [docs/hardware-validado.md](docs/hardware-validado.md): qué se ha probado
  contra qué pieza.
- [docs/pendientes.md](docs/pendientes.md): lo pendiente, con su detalle.
- [docs/en-curso.md](docs/en-curso.md): si existe, dónde se quedó la última
  sesión y qué sigue.
- [docs/historial/](docs/historial/): diarios de sesiones antiguas.
