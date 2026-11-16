# Plan de la fase 3: limpiar el código, y la velocidad de los tests

Es la sección 5 de la quinta auditoría, puesta al día con lo que entró en la
0.3.0 y en la rama `fase-1`, y convertida en commits. Las reglas de siempre:
un commit por cambio lógico, la suite en verde entre uno y otro, y lo que solo
mueve código en commits propios, sin cambiar ni una línea de lógica, para que
`git log --follow` y la revisión sirvan.

Cada commit va marcado:

- **[mueve]**: solo mueve o renombra; el comportamiento no cambia y no hace
  falta test nuevo (la suite entera es el test).
- **[cambia]**: cambia lógica o comportamiento; lleva su test visto fallar.
- **[tras ui-permisos]**: toca lo que la propuesta de permisos va a reescribir
  —`ui/app.py`, `ui/pages/home.py`, `StatTile`, `Notice`, `InfoGrid`, `Note`,
  la barra de estado—; se hace después de esa rama para no pelearse con ella.

## Qué ha cambiado desde la auditoría

- **Ya resuelto**: el informe anonimiza con `privacidad.anonimizar` y no por
  su cuenta; `comprobar_autocontenido` recorre `objetos_del_appdir()`; el
  historial compara con la puntuación de `score` y no con una suma propia;
  las herramientas nombran las piezas con `render.cpu_short_name`.
- **Nuevo desde entonces**: `ResponsiveRow` creció (el reparto por columnas) y
  `ui/app.py` también (`_guardar`, `section_row`, `seccion_que_falta`).
  Tamaños de hoy: `model.py` 1462, `widgets.py` 1378, `render.py` 1077,
  `build_appimage.py` 1074, `app.py` 1021, `drm.py` 976, `sensortree.py` 862.
- **Nombres públicos de hoy que hay que mirar contra la norma**: `de_sistema`
  (en `privacidad`, que es toda en español: cumple), `multihilo_exacta` (en
  `score`, toda en español: cumple), `misma_duracion` (en `history`, que mezcla
  `load/save` con `comparar`: la familia ya estaba rota) y
  `seccion_que_falta` (función de módulo en `app.py`, al lado de `build_app` y
  `main`: no cumple).
- **Comentarios de hoy que narran historia** y que, por la norma, van al
  commit: el docstring de `Entry.total` («Era la suma en crudo…»), el de
  `medir_referencia.por_que_no_escribir` («Antes se escribía igual…»), el de
  `comprobar_autocontenido` («El de la v0.2.0 avisaba…») y el comentario del
  `if comprobar_autocontenido()` en `main`. Se recortan a una línea con el
  porqué en el bloque de comentarios.

## Bloque A — solo mueve código

Los primeros, porque no cambian nada y despejan el resto.

1. **[mueve]** `refactor: imports sin uso` — `collector.copy`,
   `network.Iterator`, `armcpu.Need`, `cppc.read_text`,
   `spd_modules.DriverHint/MemoryModule`, `gpumetrics.field`,
   `report.Iterable` y `sys`, `performance.QTimer` y el `QWidget` repetido,
   `render.pretty_feature`.
2. **[mueve]** `refactor(providers): drmioctl.py con render_node e _iowr` —
   las dos copias idénticas de `amdgpu.py` e `i915.py`.
3. **[mueve]** `refactor(providers): pcie.py con la ranura y el enlace` — la
   expresión de la dirección PCI de `drm`, `hwmon` y `storage`, los dos
   `_enlace`, y la tabla de generación a GT/s de `nvidia.py` y `model.py`.
4. **[mueve]** `refactor(tools/appimage): partir build_appimage.py` —
   `tools/appimage/` con `config.py`, `copiar.py`, `comprobar.py`,
   `contenedor.py` (compartido con `probar_en_minimo.py`) y `empaquetar.py`;
   `build_appimage.py` se queda como punto de entrada que reexporta lo que
   importan los tests.
5. **[mueve]** `refactor(tools/appimage): AppRun y guarda como plantillas .sh`
   — archivos de verdad; el CI les pasa `sh -n` y `shellcheck` (eso sí añade un
   paso al CI, en el mismo commit).
6. **[mueve]** `refactor(model): paquete model/` — `base`, `cpu`, `memoria`,
   `sistema`, `placa`, `gpu`, `discos`, `red`, `bateria` y `sensores`, con
   `__init__` que reexporta: `from silux.model import X` no cambia. **[tras
   ui-permisos]** la parte de `Note`, que la propuesta cambia: o se hace
   antes del todo o después del todo, no a medias.
7. **[mueve] [tras ui-permisos]** `refactor(ui): widgets.py en cinco módulos`
   — `texto.py`, `grafica.py`, `tabla.py`, `avisos.py`, `disposicion.py`, con
   `widgets.py` reexportando mientras se migra.
8. **[mueve] [tras ui-permisos]** `refactor(render): paquete render/` —
   `unidades`, `cpu`, `memoria`, `gpu`, `discos`, `red`.
9. **[mueve] [tras ui-permisos]** `refactor(ui): app.py en permisos.py,
   compartir.py y arranque.py`.
10. **[mueve]** `refactor(ui): sensortree en cabecera, anchos y orden`.
11. **[mueve]** `chore(tests): unittest.main() al final de los 24 archivos
    que lo tienen en medio`.

## Bloque B — cambia comportamiento o lógica

12. **[cambia]** `refactor(render): °C/°F en un solo sitio` — ocho copias
    (`render.py`, `cpulive`, `cpu`, `storage`, `graphics`, `monitor` ×3), con
    un test que compare la salida de cada página con la de `render`.
13. **[cambia]** `refactor(render): MT/s y la velocidad de memoria en un solo
    sitio` — `tarjeta`, `home`, `memory` ×4, `report`; arregla de paso el
    «DDR4-2667» de Inicio frente al 2666 de Memoria.
14. **[cambia]** `fix(ui/cpulive): los relojes con render.hz` — 576 MHz sale
    hoy «0.58 GHz».
15. **[cambia]** `fix(ui): voltajes con render.volts` — cinco sitios a dos
    decimales, más `report.py`.
16. **[cambia]** `refactor(render): la lógica numérica a analisis.py` —
    `memory_channels`, `memory_theoretical_bandwidth`, `best_core_ids`,
    `core_quality_by_type` devuelven números y no texto.
17. **[cambia]** `refactor(providers): Derivada en base` — el «contador
    anterior → ritmo» escrito siete veces, y de paso el `_previo` que crece
    sin límite con cada `veth`.
18. **[cambia]** `refactor(providers): TypedDict para el Draft` — hoy `freeze`
    descarta en silencio una clave mal escrita; el test demuestra que una
    errata ya no se pierde.
19. **[cambia]** `refactor(privileged): fuera VERSION y la rama que la
    compara` — `helper.VERSION`, `protocol.VERSION_REQUERIDA`, la rama de
    `client.connect` que no se ejecuta nunca, el test
    `test_la_version_subio_al_anadir_la_accion` y las constantes muertas de
    `protocol.py`. **Toca privilegios: va como propuesta antes.**
20. **[cambia]** `refactor: código muerto` — `score.piezas_conocidas`, los
    oyentes de `i18n`, `Sampler.__del__`, `RANGOS_DE_DOCUMENTACION`, los
    campos del modelo que nadie lee (con cuidado: `Disk.rotational` hace falta
    para F-M18, y `disk.pci_slot`/`net.vendor` se pintan o se quitan).
21. **[cambia]** `fix(i18n): gen_lang compara claves enteras` y después
    `chore(i18n): podar las trece claves muertas`.
22. **[cambia]** `refactor: nombres` — solo las colisiones: las dos clases
    `Medida` (`benchmark` y `membench`), `rapl._por_ayudante` frente a
    `_por_el_ayudante`, y `seccion_que_falta` **[tras ui-permisos]**. El resto
    se corrige al tocar cada archivo.
23. **[cambia]** `refactor: comentarios que cuentan historia` — por zonas, y
    los de hoy los primeros (lista arriba). Lo que se quita no se pierde: ya
    está en los mensajes de commit o en `docs/lecciones.md`.
24. **[cambia]** `refactor(cli): grupo excluyente de argparse` — `--json`,
    `--sensors`, `--report`, `--watch`, `--db-info`, con `--report ''` y
    `--with-identifiers` suelto rechazados con `parser.error`. Cierra los
    bajos del CLI.

## Los tests: dónde se va el tiempo

Medido en el i5-10400 con Python 3.14 y PySide6 6.11.2, sobre `fase-1`.

**Por archivo**, cada uno en su propio proceso (la suma, 155 s, incluye el
arranque de cada proceso):

| Archivo | Segundos | Tests |
|---|---:|---:|
| `test_benchmark` | 59,4 | 62 |
| `test_window` | 20,3 | 24 |
| `test_system` | 17,1 | 74 |
| `test_membench` | 14,2 | 30 |
| `test_arranque` | 10,6 | 24 |
| `test_fluidez` | 5,5 | 34 |
| `test_inicio` | 5,1 | 25 |
| `test_gpu` | 2,5 | 139 |
| el resto (53 archivos) | menos de 2,3 cada uno | |

Cinco archivos se llevan 121 de los 155 s.

**Los 20 más lentos**, con `pytest --durations`, y por qué:

| s | Test | Por qué |
|---:|---|---|
| 22,5 | `test_benchmark::…test_la_medida_de_un_hilo_no_paga_el_arranque_de_la_carga` | lanza la prueba entera de verdad: cinco cargas, un hilo y todos, con su rodaje |
| 21,9 | `test_benchmark::TestDuracion::test_se_puede_pedir_cuanto_dura` | lo mismo, para comprobar un tope de duración |
| 6,9 | `test_window::…test_los_extremos_sobreviven_a_un_cambio_de_tema` | la ventana entera, muestras reales y una reconstrucción |
| 5,8 | `test_window::…test_apply_deja_estilo_paleta_y_hoja` | la ventana entera y el tema aplicado dos veces |
| 4,7 | `test_benchmark::TestCancelar::…` | una prueba real cancelada después de la primera medida |
| 4,1 | `test_benchmark::…test_todas_reparten_de_verdad_entre_hilos` | cada carga con uno y todos los hilos: es lo que vigila el GIL, hace falta |
| 3,6 | `test_window::…cambiar_la_densidad…` | ventana entera y reconstrucción |
| 3,6 | `test_window::…cambiar_de_tema_cambia_la_paleta` | ídem |
| 3,5 | `test_benchmark::…el_tamano_del_bloque_no_cambia_lo_que_se_puntua` | CRC de verdad sobre bloques de 64 a 384 MB |
| 3,2 | `test_arranque::…de_punta_a_punta_en_un_equipo_sin_bateria` | lanza el programa en un proceso hijo |
| 3,2 | `test_arranque::…una_captura_no_cambia_las_preferencias` | ídem |
| 3,0 | `test_system::…muchos_refrescos_no_dejan_widgets_vivos` | muchas muestras reales |
| 2,9 | `test_window::…fahrenheit…` | ventana entera |
| 2,4 | `test_window::…el_contenido_cabe_en_el_suelo…` | ventana entera |
| 2,3 | `test_arranque::…lo_que_se_cambia_en_ajustes_si` | ventana entera |
| 2,0 | `test_benchmark::…una_carga_lentisima_no_alarga_la_prueba` | una carga real lenta a propósito |
| 2,0 | `test_fluidez::…se_ajusta_a_lo_que_de_verdad_tarda` | espera en tiempo real |
| 1,9 | `test_fluidez::…la_barra_de_estado_lo_dice` | ventana entera y espera |
| 1,5 | `test_window::…una_muestra_real_llena_la_pagina` | `Collector` de verdad |
| 1,5 | `test_window::…la_pagina_de_caches_se_llena` | ídem |

Y uno que no sale en la tabla porque se reparte: **34 llamadas a
`Collector()` de verdad** en siete archivos de interfaz, a 0,7 s la primera
y 0,4 las siguientes. Son unos 15-20 s de la suite (estimado: 34 × 0,4-0,7).

**Tests repetidos o que prueban lo mismo**: casi no hay. Un cuerpo idéntico,
el de «los datos de prueba no son los de sustitución», en `test_report` y en
`test_tarjeta` (lo escribí hoy; va a un ayudante común). Los demás nombres
repetidos prueban cosas distintas (los patrones del contrato del ayudante en
`test_imc` y `test_privileged` son de PMU distintos). Lo que sí hay es un test
que prueba un número que ya no decide nada: `test_imc::…la_version_subio…`
(ver el commit 19).

## Los tests en paralelo

Con `pytest-xdist`, en un venv de pruebas fuera del repositorio con pytest
9.2 y xdist 3.8 sobre el Python y el PySide6 del sistema. La suite es de
`unittest` y pytest la ejecuta sin tocar nada.

| | Tiempo |
|---|---:|
| `unittest discover` | 133-157 s |
| pytest en serie | 170 s |
| pytest `-n 4` | 68 s |
| pytest `-n auto` (12) | 69 s |
| pytest en serie, sin los dos tests de 22 s | 127 s |
| pytest `-n 4`, sin los dos de 22 s | 36 s |
| pytest `-n 8`, sin los dos de 22 s | 24 s |

**El aislamiento aguanta**: cada proceso importa `tests/__init__.py` y se hace
su propia caja, y el `settings.json` de verdad no cambió en ninguna de las
ejecuciones. Lo único que queda son las cajas de los procesos que mueren de
golpe, que no llegan a borrarse.

**Y destapa un fallo de los tests**: 22 archivos crean su `QApplication` con
`QApplication.instance() or QApplication([])` sin guardar la referencia. El
objeto se destruye en el acto, y si ningún test anterior del mismo proceso dejó
otra viva, el siguiente widget aborta el proceso («Fatal Python error:
Aborted», desde `Sparkline.__init__` en `test_fluidez`). En serie no se ve
porque algún módulo anterior la deja creada; en paralelo, el orden cambia y
salta. También pasa en uno que escribí hoy, `test_anchura`.

### La medida del test 25, en el 5800X3D

`pytest -n auto` (16 procesos), `--ignore=tests/fixtures`, tres commits:

| | Resultado | Tiempo |
|---|---|---:|
| antes de `50df0fd` (dos veces) | 2 procesos abortados, 4 tests fallidos | 62-64 s |
| con `50df0fd` (dos veces) | 2 procesos abortados, 4 tests fallidos | 63-64 s |
| con los dos arreglos de después (tres veces) | 1620 pasan, ningún aborto | 62-64 s |

Guardar la referencia no bastaba. Quedaban dos dependencias del orden, cada
una con su commit: la `QGuiApplication` del instalador de iconos, que deja al
proceso sin `QApplication` si `test_desktop` corre primero, y `test_arm`, que
al sustituir `Path.read_text` se llevaba por delante la carga del idioma.

Dos cosas más que salieron al medir:

- **pytest no acaba de recoger los tests si entra en `tests/fixtures/`**: los
  volcados de equipo son árboles de `/sys` con enlaces que dan la vuelta, y
  dieciséis procesos se quedaron diez minutos al 100 % sin ejecutar nada. Con
  `--ignore=tests/fixtures` recoge en un segundo. Va a la configuración en el
  test 30, no a la memoria de quien lance la suite.
- En serie, `unittest discover` terminaba en verde y el proceso salía con una
  violación de segmento (código 139). Lo trajo el propio `50df0fd`, al dejar
  la aplicación viva hasta el final; arreglado en `c86d183`.

### Lo medido después de cada test, en el 5800X3D

| | `unittest discover` | `pytest -n auto` (16) |
|---|---:|---:|
| al empezar (25 sin terminar) | 148-152 s | 62-64 s, con abortos |
| 25 terminado | 150 s | 62-64 s |
| 26 | 121 s | 27 s |

## Cómo bajar de los dos minutos y medio sin perder cobertura

En este orden, cada uno un commit con su medida antes y después:

25. **[cambia]** `test: una QApplication que se guarda, en tests/qt.py` — los
    22 archivos la piden ahí. Arregla el aborto en paralelo y la dependencia
    del orden, que es un fallo aunque no se use xdist.
26. **[cambia]** `test(bench): los dos tests de 22 s miden lo que dicen y nada
    más` — el del tope de duración, con `_medir` sustituido (como el test de al
    lado) y una sola medida real; el del rodaje, con la carga en que se vio el
    efecto, un hilo y todos. Pide que `benchmark.run` acepte qué cargas medir.
    Medido: −43 s en serie.
27. **[cambia]** `test: una foto real por proceso` — las 34 llamadas a
    `Collector()` de los tests de interfaz que solo necesitan *una* foto
    real comparten una (estimado: −15 s). Los que comparan el árbol consigo
    mismo siguen leyendo la máquina; los que exigen algo concreto, con
    `tests/muestras.py`.
28. **[cambia]** `test(window): una ventana por clase donde no se cambia nada`
    — los tests de `test_window` que solo miran comparten la ventana
    (estimado: −8 s).
29. **[cambia]** `test(membench): una medida en otro proceso por clase`
    (estimado: −6 s).
30. **[cambia]** `build: pytest y pytest-xdist como dependencias de
    desarrollo` — con el `uv` de la propuesta de entorno, y `pytest -n 4`
    como orden recomendada; `unittest discover` sigue funcionando y es la del
    CI hasta que se decida. Medido: la suite en 24-36 s según los procesos.

Con 25-29 la suite en serie quedaría en unos 85-95 s (los 127 medidos sin los
dos tests lentos, menos lo estimado de 27-29); en paralelo, entre 24 y 36 s,
medido. Ninguno quita un test ni una comprobación: los cinco cambian cómo se
prepara el estado, no qué se comprueba.
