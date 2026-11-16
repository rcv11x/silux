# En curso

Para retomar sin el contexto de la sesión anterior. Se borra cuando lo de
aquí esté hecho o pase a `docs/pendientes.md`.

Última sesión: 16 de noviembre de 2026, por la tarde-noche, en el 5800X3D de
casa (CachyOS). La anterior fue ese mismo día en el i5-10400 de la oficina.

## Estado y lo siguiente

**Las dos ramas están empujadas y con el CI en verde** (tests en 3.10 y 3.14,
y el AppImage): `fase-1` en `2f5cc9d` y `ui-permisos`, rebasada encima, en
`3a7dfaa` más el commit de este archivo, que solo toca documentación y no ha
pasado por el CI. **Nada ha pasado a `master`**, que sigue en `7609ea2`.

**La siguiente tanda** sale de revisar el autor las capturas del AMD
(`~/Imágenes/silux-test/ui-permisos-2/`). Un commit por cambio, con su test,
en `ui-permisos`:

- **Placa base en AMD**: el chipset sale «FCH LPC Bridge», que es un
  dispositivo PCI, no el chipset (es un X570).
- **`--anonimo`**: dos MAC distintas acaban siendo la misma falsa.
- **Sensores**: las zonas `acpitz` clavadas a 16.8 °C salen sin marcar como
  poco fiables; las de `gigabyte_wmi`, sin nombre y sin pie.
- **Discos SATA**: la temperatura sale con «—» en vez de candado o aviso
  (SMART o `drivetemp`).
- **Diálogo de permisos**: la orden de quitar el ayudante se parte a mitad de
  ruta; que vaya en un campo monoespaciado que se pueda copiar.
- **Etiquetas de pico** montadas encima de la curva en las fichas.
- **«NVME» → «NVMe»** en la ficha de cada disco.
- **Rendimiento**: botón «Borrar las de otra escala».
- **Gráficas de las fichas**: el eje vacío a todo el ancho, llenando desde la
  derecha (deshace el reparto de `Sparkline._geometria` de la segunda tanda).
- **Rehacer los dos volcados del i5-10400** en la oficina: `scaling_cur_freq`
  y el nombre de la gráfica grabado.

## Qué está hecho

### `fase-1` (sale de `master`, que sigue en 7609ea2 con la 0.3.0)

Los de la mañana, ya contados en CLAUDE.md: F-A3, F-M1, F-A4, F-A5, F-M33,
F-A6, F-M34, F-M35, F-A8, `_ciclos_jedec`, documentación y plan de la fase 3
(hasta `12486ee`). Los de la tarde, en orden:

| Commit | Qué |
|---|---|
| `391e45c` | `feat(providers)`: `SILUX_SYSROOT`, leer el sistema desde un equipo volcado (`silux/sysroot.py`) |
| `0677c40` | `feat(tools)`: `tools/volcar_equipo.py`, con su anonimizado y sus dos comprobaciones |
| `22131ab` | `test(equipos)`: el primer volcado, `tests/fixtures/equipos/i5-10400`, y `tests/test_equipos.py` |
| `e3cc82d` | `docs`: los volcados, sysroot y la lección del serie del SPD |
| `ecd6fd6` | `test(equipos)`: el mismo equipo con el turbo encendido, `i5-10400-turbo` |
| `3f6c1a6` | `fix(ui/cpulive)`: la gráfica de FRECUENCIA contra el techo del silicio (la barra vertical) |
| `68579f8` | `test(ui)`: Inicio, CPU y Sensores dicen la misma frecuencia con la misma foto |
| `f5a3efb` | `fix(providers/sysfs_cpu)`: la frecuencia de cada hilo sale de `cpuinfo_avg_freq` |
| `6c83db3` | `fix(ui)`: Inicio y la página CPU dan la misma temperatura (`CpuInfo.temperature_c`) |
| `3bf54ea` | `fix(providers/rapl)`: un contador de energía parado no es 0 W, se explica |
| `50df0fd` | `test`: `tests/qt.py`, la QApplication que se guarda (test 25 del plan) |
| después | este archivo y la línea de CLAUDE.md |

En casa, en el 5800X3D (puntos 0 y «AMD» del mensaje, hechos):

| Commit | Qué |
|---|---|
| `39df958` | `fix(tools)`: el volcado tapa los montajes donde están (`/proc/mounts` es un enlace) y solo deja las líneas de un dispositivo |
| `9e9ae51` | `feat(tools)`: de las interfaces en serie (`br-<id>`, `veth`) queda una de cada |
| `f9ce8b4` | `test(equipos)`: el volcado `5800x3d` |
| `39396a6` | `test(equipos)`: sin `cpuinfo_avg_freq` sale `scaling_cur_freq`; el volcado guarda las fuentes alternativas |
| `7ee762b` | `fix(providers/rapl)`: en AMD el dominio «core» es de un solo núcleo; no se enseña y se dice |
| `60e354e` | `fix(providers/hwmon)`: con Tdie y Tctl, la temperatura es Tdie |
| `35756d1` | `fix(providers/cppc)`: sin amd-pstate, el ranking de núcleos no da un techo |
| `bb62022` | `test(ui)`: la frecuencia y su eje, también con el volcado de AMD |
| después | `test(ui)`: lo que una tabla desplaza no cuenta como cortado; y el volcado rehecho con la nota de CPPC de cada núcleo |

Suite en serie en verde con todo: 1618 tests.

Lo que salió de comprobar AMD, en corto:

- **Temperatura**: el 5800X3D da Tctl y Tccd1; sale Tctl, que ahí es la
  buena, e Inicio y CPU coinciden. Tdie no existe en esta pieza: el caso
  «las dos» está arreglado por la documentación del kernel, sin pieza.
- **Frecuencia**: `amd-pstate-epp`, kernel 7.3. `cpuinfo_avg_freq` existe y
  coincide con `scaling_cur_freq` (mediana 0,000 % en 320 pares). La caída
  sin la primera está probada con el volcado.
- **Consumo**: aquí `energy_uj` se lee sin permisos. El paquete está bien; el
  dominio «core» no era la suma (ver `7ee762b`).
- **Eje de FRECUENCIA**: 576 MHz – 4,55 GHz, el techo de CPPC.

**Queda sin poder comprobarse aquí** y hay que hacerlo con la pieza delante:

- Arrancar el 5800X3D con `amd_pstate=disable` (driver `acpi-cpufreq`),
  volcarlo como `5800x3d-acpi-cpufreq` y ver que «Máxima (silicio)» sale sin
  dato y con su aviso, no a 4,96 GHz. `35756d1` está hecho sin ese arranque.
- Con el boost apagado (`echo 0 > /sys/devices/system/cpu/cpufreq/boost`,
  pide root): que el eje siga hasta 4,55 y no baje a 3,4.
- **Rehacer los dos volcados del i5-10400 en la oficina**
  (`i5-10400` en reposo, `i5-10400-turbo` con carga): los de ahora no llevan
  `scaling_cur_freq`, y el test de la caída (`39396a6`) los salta.

### `ui-permisos` (sale de `12486ee`, antes de lo de la tarde)

Un solo commit, `19672d8`: `docs/propuesta-permisos.md`. Sin código.

### `fase-2`

Está entera dentro de `fase-1` (su último commit es `da87e12`). No tiene nada
propio. No se ha borrado, porque las ramas no se borran sin que lo diga el
autor.

## Dónde se quedó exactamente

En el **test 25** del plan (`docs/plan-fase-3.md`, «Cómo bajar de los dos
minutos y medio»). El cambio está hecho y commiteado (`50df0fd`) y pasa en
serie. **Falta la medida en paralelo**, antes y después:

```bash
# antes: la suite con los tests del commit anterior
git stash -u   # solo si hay algo a medias; y luego `git stash pop`, comprobado con `git stash list`
git checkout 50df0fd~1 -- tests/
QT_QPA_PLATFORM=offscreen VENV/bin/python -m pytest -n auto -q -p no:cacheprovider tests
git checkout HEAD -- tests/
# después
QT_QPA_PLATFORM=offscreen VENV/bin/python -m pytest -n auto -q -p no:cacheprovider tests
```

Lo que se espera: antes, «Fatal Python error: Aborted» en algún trabajador
(se vio al hacer el plan); después, ninguno. Si después sigue abortando, el
test 25 no está terminado. El resultado se apunta en el plan, junto a la tabla
de tiempos.

**Hecho en casa**, con los tests 26 a 30 (ver más abajo). **Siguiente
paso**: el CI de `fase-1`, y después ui-permisos.

El venv de pytest ya no hace falta: `uv sync --extra gui` deja uno en `.venv`.

## Lo que falta del mensaje de la tarde, en orden

0. **HECHO** (arriba). Lo que decía: el volcado del 5800X3D, en cuanto se pueda:
   `python3 tools/volcar_equipo.py 5800x3d` en ese equipo, sin permisos
   concedidos, revisarlo, commit en `fase-1` con su fila en
   `docs/hardware-validado.md` (sección «Equipos volcados»). Si la
   herramienta se niega por privacidad, se arregla la herramienta, no se
   fuerza. Luego la suite entera: `test_equipos` monta todos los volcados.
   Lo que en `fase-1` quedó **comprobado solo en Intel** y hay que mirar en
   ese volcado:
   - si existe `cpuinfo_avg_freq` y si coincide con `scaling_cur_freq`
     (con `amd-pstate` o `acpi-cpufreq`, la segunda puede ser la pedida);
   - `max_turbo_hz`: en AMD no hay CPUID 0x16 y sale de CPPC
     (`providers/cppc.py`); es el techo del eje de FRECUENCIA;
   - la temperatura del encapsulado: en AMD es Tctl (`k10temp`); que Inicio
     y la página CPU digan lo mismo (`tests/test_temperatura_cpu.py`);
   - RAPL de AMD: que el volcado no dé 0 W (`test_equipos`).
   Si algo de esto no sale bien en AMD, se arregla en `fase-1` con su test
   contra ese volcado. `test_frecuencia.py` y `test_temperatura_cpu.py`
   dicen hoy en su cabecera que solo están comprobados en Intel: se
   actualiza cuando lo estén en los dos.
1. **Tests 25-30** del plan, en ese orden, en `fase-1`, un commit cada uno
   con su medida antes y después:
   - 25: **hecho**. La medida en paralelo destapó que no estaba terminado:
     tres commits más (`QGuiApplication` del instalador, `test_arm`, y la
     violación de segmento al salir). Tabla en el plan.
   - 26: **hecho** (`db6e0d0`): `benchmark.run(loads=…)`. Serie 150 → 121 s.
   - 27: **hecho** (`e881db9`): `muestras.foto_real()`.
   - 28: **hecho**: `TestVentanaQueSoloSeMira`. Aquí son 1,3 s, no 8.
   - 29: **hecho**: solo dos tests compartían medida. 1,3 s, no 6.
   - 30: **hecho** (`1b53d04`): `uv`, grupo `dev`, `uv.lock`,
     `tests/conftest.py` y el CI en dos pasadas. De camino salieron dos
     fallos del empaquetado, cada uno con su commit: `pip install .` no
     terminaba desde que hay volcados, y la rueda salía sin los archivos de
     idioma.
   - La suite: de 150 s a 96 s en serie, y 20 s + 13 s con pytest.
   - Al acabar: empujar `fase-1`, `gh workflow run appimage.yml --ref
     fase-1` y `gh run watch`. **Es lo siguiente.**
2. **ui-permisos: escrita entera, sin empujar, y parada ahí** a la espera de
   que el autor mire las capturas. La rama `ui-permisos` sale de `fase-1`.
   Un commit por cambio, cada uno con su test:

   | Qué | Dónde mirar |
   |---|---|
   | F-M4, `pkexec` fuera del hilo de la interfaz | `ui/background.py` |
   | `Note.what` y `Snapshot.permission_notes` (en la propuesta, `que`) | `model.py` |
   | El aviso de Inicio, con «Ahora no» y «No volver a mostrar» sin aspa | `PermissionNotice` |
   | «Qué hace esto» | `ui/dialogs.py` |
   | La barra de estado sin jerga; fuera la insignia de Inicio | `ui/app.py` |
   | Las barras: leyenda con color y la caché distinguible | `StackedBar`, `memory_segments` |
   | Red: «dúplex completo», no «full» | `render.link_summary` |
   | «Gigabyte X570 AORUS ELITE», no «Gigabyte -CF» | `model.py` (salió al hacer la tarjeta de la placa) |
   | Inicio: temperaturas con nombre, red y placa; copiar en la fila de insignias | `ui/pages/home.py` |
   | La temperatura que la gráfica no publica, escondida y nombrada en los tres sitios | `Gpu.no_temperature_sensor` |
   | Memoria: «catalogados a 3200 MT/s» | `ui/pages/memory.py` |
   | Los títulos de las tablas pegados a sus filas | `Table` |
   | Las gráficas de Inicio dibujan muestras reales (solo test: ya lo hacían) | `tests/test_inicio_graficas.py` |
   | El candado: voltaje, uso y consumo de la gráfica, velocidad y banco de cada módulo | `set_locked`, `permission_note` |
   | Los dos botones de apartar, iguales en las cuatro páginas que piden permisos | `dismiss_buttons` |

   **Capturas** de este equipo (AMD con gráfica dedicada), en
   `~/Imágenes/silux-test/ui-permisos/`: `antes/` y `despues/`, el mismo
   juego —siete páginas a 1440×880 y en compacto a 900×680—, más
   `despues/inicio-alto-1440.png` (la página entera), `cpu-alto-1440.png` (el
   candado del voltaje) y `dialogo-que-hace-esto.png`. Lo que solo se ve en un
   Intel —el candado en las fichas de Gráficos y en los módulos, la
   temperatura de la gráfica nombrada al pie— está probado con el volcado del
   i5-10400 pero **no tiene captura**: hay que sacarla en la oficina.

   **Lo que se apartó de la propuesta**, para que no sorprenda:
   - el campo es `Note.what` y la preferencia `permission_notice_dismissed`,
     en inglés como el resto de la API;
   - la nota de la gráfica no se partió en dos: `permission_note` contesta
     por campo con la nota de la pieza;
   - el diálogo no dice «se quita desde Ajustes», porque en Ajustes no hay
     con qué: da la orden. **Un botón para quitar el ayudante sería una
     propuesta aparte**, que toca privilegios;
   - los dos botones de apartar valen para todas las páginas a la vez.

   **Segunda tanda, tras revisar el autor las capturas** (aprobada la
   primera). Un commit por cambio, con su test, en `ui-permisos`:

   | Qué | Cómo quedó |
   |---|---|
   | Sensores: «Core #N» | «CPU N», de `model.thread_name`, igual que en la página CPU |
   | Sensores: «Tensión 0, 1, 2» | `it87` no las nombra (solo 3VSB y Vbat); `Sensor.unnamed` y un pie que lo dice |
   | CPU: «núcleos» con Tctl | la línea solo sale si hay sensores por núcleo |
   | Fecha de la BIOS | `render.bios_date`, «2025-10-28» |
   | Identificador único a ceros | `render.unique_id`; la fila se esconde |
   | Orden de desinstalar del diálogo | `sudo rm` de los dos archivos, que vale con paquete y con AppImage |
   | `acpi_enforce_resources=lax` | el aviso dice el riesgo y que no merece la pena solo por ese dato |
   | Rendimiento: pruebas de otra escala | la celda dice «escala v5» y por qué, no «—» |
   | Inicio: el titular de Temperaturas | no cambia hasta que otra pieza le saca 2 °C |
   | Gráficas a todo el ancho | `Sparkline._geometria` reparte las muestras mientras se llena |
   | Red: interfaces virtuales | plegadas debajo de las físicas, en un renglón que se abre |
   | Tabla de monitores | «Gigabyte AORUS FO27Q2», y las tablas miden con decimales |

   Lo de las gráficas **cambia una decisión anterior**: con el paso fijo la
   curva no se recolocaba al entrar cada muestra; ahora, hasta que se llena
   (minuto y medio), cada muestra nueva la aprieta un poco. Si molesta, es
   una función.

   Capturas de esta tanda en `~/Imágenes/silux-test/ui-permisos-2/`,
   `antes/` y `despues/`: nueve páginas a 1440×1300 y en compacto, más el
   diálogo y `red-virtuales-abiertas.png`.

   En el equipo de casa ya hay `gh`, pero el remoto sigue siendo HTTPS sin
   credenciales: se empuja con la URL de SSH
   (`git push git@github.com:rcv11x/silux.git RAMA:RAMA`).

   **El primer CI de las dos ramas falló**, por dos cosas que aquí no se
   veían y que están arregladas en `fase-1` (`ui-permisos` va rebasada
   encima):
   - el nombre de la gráfica del volcado salía del `pci.ids` de quien
     ejecuta, y el de la Ubuntu del runner no trae la RX 9070 XT. Ahora se
     graba en el volcado (`pciids` pasa por `sysroot`); el `5800x3d` se
     volvió a volcar. Los del i5-10400 no lo llevan: otra razón para
     rehacerlos en la oficina;
   - con la tipografía del runner (DejaVu, más ancha) la cabecera de
     Sensores pedía 643 px en una página de 640. Cortar el contador no
     bastaba: lo que empujaba era el buscador, fijo a 190 px, que ahora
     encoge hasta 60. El test se reproduce aquí con DejaVu Sans.

   Al cuarto intento, **las dos en verde**. Nada ha pasado a `master`.

   La lista original, un commit por cambio, con su test:
   - **F-M4 primero** (`pkexec` en el hilo de la interfaz), antes de hacer
     más visible el botón.
   - Inicio no dice «usa 11.6 GB de la RAM»: lo que diga Gráficos, o nada.
   - La temperatura de la GPU que no se publica se esconde y se nombra al pie
     en todas partes: ficha de Gráficos, Sensores y tarjeta Temperaturas de
     Inicio (regla 5).
   - Tarjeta Temperaturas: cada cifra con su nombre («Procesador 32 °C ·
     Disco 25 °C») y el título acorde.
   - Red: «full» sin traducir.
   - Con permisos, la tarjeta de la GPU enseña el uso y los vatios.
   - Dos botones de texto, «Ahora no» y «No volver a mostrar», iguales en
     Inicio y en las páginas; sin X.
   - **Propuesto en casa, sin aprobar todavía**: la tabla de monitores de
     Gráficos a 900 px. El nombre («GIGA-BYTE TECHNOLOGY CO., LTD. AORUS…»)
     se lleva el ancho y la resolución sale cortada, «2560 × 14…». Captura
     en `~/Imágenes/silux-test/amd/graficos-900-pantallas.png` (casa).
   - Barras de Inicio, Memoria y Almacenamiento: la caché distinguible del
     fondo, leyenda con color en las tres, y los chips de Almacenamiento bien
     colocados en compacto.
   - Comprobar que las gráficas de las tarjetas de Inicio dibujan muestras
     reales.
   - Memoria: la cabecera dice «catalogados a 3200 MT/s» mientras no se sepa
     la velocidad real.
   - El hueco entre la cabecera y la primera fila de las tablas.
   - Al final, capturas antes/después en
     `"$(xdg-user-dir PICTURES)/silux-test/ui-permisos/"`, y **parar**.
3. **Plan de la fase 3**: corregir `docs/plan-fase-3.md` para que los módulos
   nuevos sigan la norma de nombres (los módulos son API, en inglés):
   `model/memory.py`, `render/units.py`, `ui/text.py`, `layout.py`… Los
   bloques A y B **no se empiezan hasta que ui-permisos esté en `master`**.
4. **Capturas del README**, cuando ui-permisos esté en `master` y con
   permisos: **avisar antes al autor** para que conceda los permanentes.

Las ramas no se empujan salvo para lanzar el CI. Si algo bloquea, se salta,
se apunta y se sigue con lo siguiente.

## Decisiones de hoy que no están en otro sitio

- **Ningún arreglo se valida solo con lo que dice una máquina.** Cada dato
  tiene que salir bien en Intel y en AMD; si en uno no se puede comprobar, se
  dice en vez de suponerlo. Con varias fuentes para el mismo dato, se usa la
  más fiable, explícitamente, documentado, con un test de que las páginas no
  se contradicen con la misma foto. Mejor un dato que falta y se explica que
  uno que parece bueno y no lo es.
- **Los volcados son sin permisos**: el ayudante solo se conecta al pulsar el
  botón, y un `Collector()` recién creado no lo hace. Lo que no se graba
  (NVML, lo del ayudante, lo que sale de restar dos lecturas: uso por hilo y
  RAPL) lo dice el `manifiesto.json` de cada volcado.
- **Un estado que cambia solo se vuelca dos veces.** En el i5-10400,
  `auto-cpufreq` apaga el turbo en reposo y lo enciende a los 3 s de haber
  carga; por eso hay `i5-10400` y `i5-10400-turbo`. El segundo se hizo con
  once hilos ocupados (`python3 -c "while True: pass"`) y el turbo ya
  encendido.
- **`test_equipos` solo comprueba lo que vale para cualquier equipo.** Lo
  que vale para uno va en el test del arreglo, contra el volcado donde se vio.
- **Lo de las tres frecuencias distintas no era un fallo de silux**: Inicio,
  CPU y Sensores leen la misma fuente y se repintan con cada foto; las
  pantallas se vieron en momentos distintos con `auto-cpufreq` cambiando el
  turbo. Lo que sí estaba mal era la gráfica (barra vertical y muestras
  recortadas) y, de paso, salieron la temperatura y los 0 W.
- **Nombres de los volcados**: minúsculas, cifras, puntos y guiones; el del
  equipo de casa, `5800x3d`.

## Lo que solo existe en la máquina de la oficina

Nada de esto hace falta para seguir, pero si se echa en falta:

- **El venv de pytest** estaba en el scratchpad de la sesión, en `/tmp`, y no
  sobrevive. Se rehace con el Python y el PySide6 del sistema:
  ```bash
  python3 -m venv --system-site-packages /tmp/venv-pytest
  /tmp/venv-pytest/bin/pip install "pytest==9.2.*" "pytest-xdist==3.8.*"
  ```
  (con el test 30 esto pasa a `uv` y deja de hacer falta).
- **Las maquetas de ui-permisos** (00-07, a 1440 y en compacto) y el script
  que las genera, `maquetas_permisos.py`, están en
  `~/Imágenes/silux-test/permisos/` de la oficina. La propuesta escrita sí
  está en el repositorio (`docs/propuesta-permisos.md`, rama `ui-permisos`).
  Para las capturas «antes» del punto 2 no hacen falta: se sacan de la rama
  antes de tocarla.
- **Capturas de hoy**: `~/Imágenes/silux-test/frecuencia/` (la ficha antes y
  después) y `~/Imágenes/silux-test/readme/` (las del README, sin commitear,
  que se rehacen en el punto 4).
- **Pythons 3.10 y 3.11 de `uv`**, que instaló un agente en la oficina para
  probar el suelo.
