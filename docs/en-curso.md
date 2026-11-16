# En curso

Para retomar sin el contexto de la sesión anterior. Se borra cuando lo de
aquí esté hecho o pase a `docs/pendientes.md`.

Última sesión: 16 de noviembre de 2026, por la tarde-noche, en el 5800X3D de
casa (CachyOS). La anterior fue ese mismo día en el i5-10400 de la oficina.

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
| `d767d0f` | `fix(tools)`: el volcado tapa los montajes donde están (`/proc/mounts` es un enlace) y solo deja las líneas de un dispositivo |
| `931f22a` | `feat(tools)`: de las interfaces en serie (`br-<id>`, `veth`) queda una de cada |
| `3638b05` | `test(equipos)`: el volcado `5800x3d` |
| `ca21bf9` | `test(equipos)`: sin `cpuinfo_avg_freq` sale `scaling_cur_freq`; el volcado guarda las fuentes alternativas |
| `bf87cf8` | `fix(providers/rapl)`: en AMD el dominio «core» es de un solo núcleo; no se enseña y se dice |
| `37d9009` | `fix(providers/hwmon)`: con Tdie y Tctl, la temperatura es Tdie |
| `d0057ea` | `fix(providers/cppc)`: sin amd-pstate, el ranking de núcleos no da un techo |
| `e1b094e` | `test(ui)`: la frecuencia y su eje, también con el volcado de AMD |
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
  dominio «core» no era la suma (ver `bf87cf8`).
- **Eje de FRECUENCIA**: 576 MHz – 4,55 GHz, el techo de CPPC.

**Queda sin poder comprobarse aquí** y hay que hacerlo con la pieza delante:

- Arrancar el 5800X3D con `amd_pstate=disable` (driver `acpi-cpufreq`),
  volcarlo como `5800x3d-acpi-cpufreq` y ver que «Máxima (silicio)» sale sin
  dato y con su aviso, no a 4,96 GHz. `d0057ea` está hecho sin ese arranque.
- Con el boost apagado (`echo 0 > /sys/devices/system/cpu/cpufreq/boost`,
  pide root): que el eje siga hasta 4,55 y no baje a 3,4.
- **Rehacer los dos volcados del i5-10400 en la oficina**
  (`i5-10400` en reposo, `i5-10400-turbo` con carga): los de ahora no llevan
  `scaling_cur_freq`, y el test de la caída (`ca21bf9`) los salta.

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

**Hecho en casa** (ver más abajo). **Siguiente paso**: el test 27.

Para medir con pytest hasta que llegue el test 30: `--ignore=tests/fixtures`
siempre, o la recogida no termina (los volcados tienen enlaces en círculo).

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
   - 26: **hecho** (`d0a8ea0`): `benchmark.run(loads=…)`. Serie 150 → 121 s.
   - 27: una foto real por proceso para los tests de interfaz que solo
     necesitan una.
   - 28: una ventana por clase en `test_window` donde no se cambia nada.
   - 29: una medida de `membench` en otro proceso por clase.
   - 30: **uv + pytest + pytest-xdist como dependencias de desarrollo, y el CI
     pasa a `pytest -n auto` en el mismo commit** (decidido por el autor; el
     plan todavía dice `-n 4` y que el CI siga con unittest: se corrige el
     plan en ese commit).
   - Al acabar: empujar `fase-1`, `gh workflow run appimage.yml --ref
     fase-1` y `gh run watch`.
2. **ui-permisos**, aprobada con estos cambios del autor. Antes de empezar,
   rebasar `ui-permisos` sobre `fase-1`. Un commit por cambio, con su test:
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
