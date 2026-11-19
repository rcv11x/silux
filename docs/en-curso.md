# En curso

Para retomar sin el contexto de la sesión anterior. Se borra cuando lo de
aquí esté hecho o pase a `docs/pendientes.md`.

Última sesión: la mañana del 19 de noviembre de 2026 en el i5-10400 de la
oficina (Fedora 44, KDE). La anterior, la noche del 18 en el 5800X3D de casa.

## 19 de noviembre, mañana en la oficina (i5-10400): dónde se quedó

Para la tarde en casa. Orden del autor: los puntos 0-10 de la mañana más lo
que añadió a media mañana (historial, informe completo, ayuda).

### Hecho

- **Ramas**: `oficina` pasó a `master` y se borró. Ya no hay rama fija por
  equipo: una por tema (CLAUDE.md). Borradas también `fase-1`, `fase-2`,
  `interfaz`, `ui-permisos`, `contraste`, `escala-v6` y `volcados` (lo suyo
  estaba en `master` con otro hash). Quedan `master`, `privacidad` y
  `actualizaciones`.
- **Auditoría de privacidad**: gitleaks limpio en los 562 commits de todas
  las ramas; nada de claves, tokens, WireGuard ni SSH. En el estado actual
  había media IPv6 de enlace de la oficina en un test: arreglado. En el
  historial, y solo ahí, quedan datos de un equipo del autor en tests y en
  una captura de agosto (el detalle no se escribe aquí: sería publicarlo
  otra vez). `tools/comprobar_privacidad.py` nuevo (F-M30): IPv6 y medias
  IPv6, números de serie, volcados, claves, correos; dice archivo y línea,
  nunca el dato; el CI lo pasa siempre; lee de `.privado` (ignorado por git)
  lo que no puede escribirse en el repositorio.
- **El anonimizado pone `silux-pc` y `192.168.1.120`** (puerta `.1`).
- **Inicio se recolocaba con las cifras** (el rojo intermitente de 3.14):
  las tarjetas reservan el ancho de su cifra; `render.possible_texts` cuenta
  «1000.0 MB/s».
- Todo eso va en `privacidad`, empujada. **No ha pasado a `master`**: su CI
  (44524215683) sale rojo en 3.10 por el reventón, dentro de `recorrer`
  como siempre. El de 3.14 cayó porque el runner no pudo bajar paquetes de
  Ubuntu y se relanzó solo ese trabajo, para que sus tests corrieran. El de
  3.10 no se relanza hasta que salga verde: o se arregla el reventón, o el
  autor decide pasarla con ese rojo.

### El reventón de 3.10: lo averiguado

- **Se reproduce** en un contenedor Ubuntu 22.04 como el runner (Python
  3.10.12, PySide6 6.11.3, DejaVu): una de cada dos o tres vueltas de la
  suite entera con `-n 4`. En Fedora no sale nunca; en serie, tampoco.
  La imagen se rehace así (podman, sin root):
  `podman run --name base docker.io/library/ubuntu:22.04 sh -c 'apt-get update && apt-get install -y python3 python3-venv python3-dbg gdb libgl1 libegl1 libxkbcommon-x11-0 libdbus-1-3 libfontconfig1 libfreetype6 libglib2.0-0 hwdata fonts-dejavu-core libasan6 && useradd -m runner && su runner -c "python3 -m venv ~/v && ~/v/bin/pip install \"PySide6>=6.6,<6.12\" pytest==9.2.* pytest-xdist==3.8.*"'`
  y `podman commit base silux-ci:22.04`. Se monta el repositorio en `/src`
  de solo lectura y se copia dentro antes de correr.
- **La pila** (core por `systemd-coredump`, con `--ulimit core=-1` y como
  root del contenedor para poder leerlo): en el hilo de la interfaz,
  `processEvents` → `sendPostedEvents` → `~QQueuedMetaCallEvent` →
  `~QAbstractMetaCallEvent` decrementa un puntero basura. El emisor del
  evento es un **`QScrollBar`**: es la llamada encolada con que
  `QAbstractScrollArea` enseña o esconde sus barras al cambiar su rango. El
  evento estaba ya liberado: un doble borrado.
- **Descartado, medido con una sonda** (un plugin de pytest fuera del
  repositorio): ningún `QThread` ni hilo de Qt en el trabajador que revienta;
  el recolector de Python no estaba en marcha; vaciar los `deleteLater()`
  en los tests no lo quita (revienta igual en la segunda vuelta).
- **Otro reventón distinto, al salir**: `shiboken6.delete` de la aplicación
  en `tests/qt.py` (`_cerrar`), puntero nulo en `releaseWrapper`. Lo vio ASan
  dos veces; no tumba tests porque pasa al acabar el trabajador.
- **Lo siguiente** (el autor lo pidió así): 1) si el doble borrado puede
  pasar en la app de verdad, no solo en los tests; 2) buscar en el gestor
  de errores de Qt/PySide (bugreports.qt.io) un fallo conocido de 6.11 con
  Python 3.10 y probar otras versiones dentro de `<6.12` en el mismo
  contenedor. Sin reintentos ni esconderlo.

### La reescritura del historial (esta tarde, una sola vez)

Decidido por el autor: que no quede nada de los datos viejos, ni en GitHub ni
en cachés, conservando el historial. **No se toca nada en GitHub sin su OK.**

- **Hecho**: 0 forks, 1 estrella, 0 issues, 0 PR, ningún `refs/pull`; 89
  ejecuciones del CI guardadas; descargas: v0.2.0, 5 + 1; v0.3.0, 4 + 1;
  borrador v0.4.0, 2 + 0. Clones en 14 días: 514 (87 únicos), casi todos del
  propio CI. Lo que alguien clonó ya no se puede borrar con ninguna opción.
- **Copias**: espejo de GitHub en `~/Documentos/silux-espejo-20261119-1141.git`
  y el `.git` local en `~/Documentos/silux-git-local-20261119-1141.tar.gz`
  (en la oficina). En casa, antes de nada, un espejo nuevo: `git clone
  --mirror git@github.com:rcv11x/silux.git ~/silux-espejo-$(date +%F).git`.
- **Qué se sustituye** (los valores no se escriben aquí; están en los tests
  de agosto, commits `3131aec` a `99abf22`, y en `pestana-sistema.png` de
  `60cc5ff`): el nombre de la oficina → `silux-pc`; la IP de agosto →
  `192.168.1.120` y su puerta → `192.168.1.1` (también el prefijo de red
  suelto, sin el último número); la MAC → `00:00:5e:00:53:21`; la serie →
  `0f1e2d3c4b5a6978`; la IPv6 de enlace (completa y su primer grupo) →
  `fe80::21`; la `fe80` hexadecimal de `test_volcar_equipo.py` →
  `fe800000000000000000000000000001`; y lo de `.privado` (el nombre del
  equipo de casa) → `silux-pc`. Con `git filter-repo --replace-text REGLAS
  --replace-message REGLAS` sobre un clon `--mirror`, y la captura con
  `--blob-callback` que cambia el blob de `pestana-sistema.png` por una
  tapada (ImageMagick: rellenar con `rgb(22,26,32)` los rectángulos
  150,48-332,66 y 261,434-335,451, y escribir «silux-pc · encendido 2 h 38
  min» y «silux-pc» en Noto Sans 12,5 y Noto Sans Mono 12). En la oficina el
  guion y la captura están en `~/Documentos/silux-reescritura/`.
- **Probado en la oficina, sin empujar**: 561 commits (uno queda vacío),
  cero restos, gitleaks limpio; el árbol de `master` solo cambia en esa
  línea de la IPv6 y los de `v0.2.0` y `v0.3.0` quedan idénticos.
- **Las dos opciones**, para que decida el autor:
  1. *Reescribir y forzar*: force-push de las ramas y las etiquetas; las
     releases siguen colgadas de su etiqueta (el nombre no cambia) con sus
     AppImage y sus descargas; se conservan la estrella, el CI y su
     historial. Pero los commits viejos siguen accesibles en GitHub por su
     hash hasta que su soporte los purgue: formulario de datos sensibles
     («Remove sensitive data», docs.github.com), que además quita las vistas
     en caché. Sin plazo garantizado. Las ejecuciones viejas del CI apuntan a
     hashes que ya no existen.
  2. *Borrar y crear de nuevo* con el mismo nombre y el historial limpio: lo
     viejo deja de servirse en el acto, sin depender del soporte. Se pierden
     la estrella, las 89 ejecuciones del CI con sus registros y artefactos y
     las cifras de descarga; las releases y sus AppImage se vuelven a subir
     (y el borrador de la 0.4). El actualizador busca por nombre de
     repositorio, así que no le afecta.
  Recomendación de la sesión: la 2, porque es la única que garantiza «nada
  en GitHub» sin esperar a nadie, y lo que se pierde es poco. Lo decide él.
- **Después, en los dos equipos**: `git fetch --all` y `git reset --hard
  origin/RAMA` en cada rama (o volver a clonar), borrar los stashes viejos
  y `git reflog expire --expire=now --all && git gc --prune=now`. La copia
  `.tar.gz` de la oficina y los espejos llevan lo viejo: se guardan fuera
  de cualquier sitio que se sincronice, o se borran cuando todo esté bien.

### Polkit (antes de la prueba1)

Opción (a) del autor: seguir con `python3 -c` (un archivo con nombre reabre
el agujero de `docs/lecciones.md`), avisar antes de abrir la ventana de qué
va a pedir y por qué, y ofrecer «Para siempre» como la forma recomendada.
Texto de la regla: «Silux necesita permiso para leer datos del hardware
reservados al administrador: memoria, discos, voltaje, consumo y uso de la
gráfica. Solo lee, no cambia nada.» y en inglés. La regla la escribe root
sin poder leer el AppImage: el texto va copiado en `instalar.py` con un test
que lo compara con `es.json` y `en.json`. Captura del antes y el después
sin la regla instalada. **Sin empezar.**

### Sin empezar

4 (lo pequeño de 3d), 5 (datos baratos), 6 (referencias por volcado), 7
(actualizaciones, con la versión de prueba `0.4.0rc1`, «0.4-prueba1» en
pantalla), 8 (el informe completo desde la descripción de páginas, con
`--short`, secciones y anonimizado siempre), la ayuda en español con las
opciones en inglés y alias ocultos, 9 (prueba1) y 10 (medidor). Las
capturas con permisos las hace el autor.


## Noche del 18, en casa (5800X3D): lo hecho y lo que queda

Rama `oficina`, empujada al acabar, con el CI en verde: el último con
código, 44417500614 sobre `83f6055` (tests en 3.10 y 3.14, y los dos
AppImage). Su artefacto «appimages» es la versión de prueba para el
Discord (descargarlo pide sesión en GitHub). Dos CI se cayeron en Python 3.10
(PySide6 6.11) con un `Segmentation fault`, por dos fallos de esta tarde: un
pintor que se quedaba abierto si fallaba pintar el fondo de la matriz de
núcleos (`ba814e7`), y un `singleShot` que saltaba sobre una ventana ya
borrada (el commit siguiente). La suite pasa entera dos veces seguidas en
3.10 aquí (`UV_PROJECT_ENVIRONMENT=… uv sync --python 3.10`, sin tocar
`.venv`). La rama `actualizaciones`, con su CI en verde (tests y
AppImage), empujada en la suya. **`master` y el borrador de la 0.4 no se
han tocado**, ni ninguna propuesta pendiente (polkit, uso de gráficas,
ayudante).

### Lo que hay que mirar o decidir

0. **Lo primero: un reventón intermitente en el CI con Python 3.10.** El
   último CI (44419430358, sobre `9aa14ab`, que solo cambia documentos)
   cayó en 3.10 con `Fatal Python error: Segmentation fault`. Dos procesos,
   los dos dentro de un `processEvents` de `tests/pantalla.py` (`recorrer`),
   en `test_nada_en_bruto`, sin un marco de silux. Es el mismo de
   44409114356: `5e8830b` (el `singleShot` sobre una ventana borrada) quitó
   una causa, pero no todas. Esta noche cayeron tres CI de seis en 3.10
   (44407519687, 44409114356, 44419430358) y pasaron 44411531475 y
   44417500614. 3.14 nunca. Aquí la suite pasó entera tres veces en 3.10
   (PySide6 6.11.3, `UV_PROJECT_ENVIRONMENT=… uv sync --python 3.10`). Para
   reproducirlo, repetir `test_nada_en_bruto` en bucle en 3.10, con `-n 4`
   y sin él. Pistas sin comprobar: lo que salta después de borrar una
   ventana (los `QTimer.singleShot` que quedan en `widgets.py:94`,
   `dialogs.py:162` y `app.py:1371`; las señales conectadas a lambdas), y
   que `pantalla.Ventana` deje sus ventanas para el recolector en vez de
   borrarlas. Hasta que se arregle, un CI rojo en 3.10 con ese reventón no
   dice nada del commit.

1. **Abrir «Silux» desde el menú** y ver que se mueve. La entrada vieja
   (`Exec=/usr/bin/python3 -m silux.ui.app`, que apuntaba a la carpeta
   `cpuz-linux`, ya inexistente: era el acceso que no abría) la arregló
   Ajustes desde el AppImage, que ahora vive en
   `~/AppImages/silux-x86_64.AppImage`: el del CI de `83f6055`, con el
   arreglo del parpadeo (el de `39df74e`, en `~/AppImages/anteriores/`).
   KWin ve la ventana
   como `silux` con el logo nuevo. **Lo que no se pudo ver**: las ventanas
   que se lanzan desde la terminal de Claude no se repintan en la pantalla
   tras el primer fotograma, aunque por dentro tengan los datos. Le pasa
   igual a una ventana de Qt de diez líneas y al AppImage del borrador, así
   que no es de silux, pero hay que verlo con los ojos.
2. **El texto de polkit**: el que leíste viene de la regla instalada el 17
   (`instalar.PLANTILLA`), no de la propuesta. Tu texto para que nombre
   todo lo que abre el permiso está en
   `docs/propuesta-mensaje-de-polkit.md`, sin aplicar.
3. **El actualizador** (`actualizaciones`): probado de punta a punta, ver
   abajo. Falta decidir cuándo se rebasa sobre `oficina` (choca en el paso
   de la release del CI) y probarlo una vez a mano con los botones.
4. **La 0.4**: lo de hoy va en ella (CHANGELOG al día). Publicarla sigue
   los pasos de «3. Publicar», más abajo.
5. **Gráficos ya no parpadea** (`4bf4ca5`, `61d98f4`): hay que verlo en la
   pantalla, reiniciando la ventana que tienes abierta desde la terminal
   (es de antes del arreglo). Y mirar si las cifras de las fichas te gustan
   arrimadas a su unidad, con el hueco a la izquierda: «0 MHz» de la
   gráfica parada lleva tres cifras de hueco. Capturas en
   `~/Imágenes/silux-test/casa-18/parpadeo/` (`antes.gif` con el estado
   intermedio, `despues.gif`, y las diferencias) y `fichas/`.

### Lo hecho, por puntos

| Commit | Qué |
|---|---|
| `bd747ca` | Un test de Ajustes leía el ayudante instalado de quien ejecuta |
| `8577e57` | **1. Barras fluidas**: llegan a su dato en 180 ms frenando, desde donde están y nunca desde cero; ritmo de la pantalla mientras se mueven. Con un video en la RX 9070 XT, el 90 % del camino pasó de 990 ms a 89 |
| `a02a4e6` | El uso de una AMD es la media del intervalo (MangoHud daba 80-86 %, una lectura suelta 15-93) |
| `4f766bc` | **Barras de motores en todas las gráficas**: AMD «Render / 3D» y una sola de video (el VCN unificado: decodificar va por la cola de codificar); NVIDIA, NVDEC y NVENC aparte; lo que el driver no da, al pie. `docs/motores-de-graficas.md` |
| `e0f83c8` | El fondo de las barras de «Ahora mismo» no cambia de largo con las cifras |
| `bf74fd0` … `4443931` | **2. Rendimiento**, once commits medidos con py-spy (`docs/rendimiento.md`) |
| `18887c1` | `tools/medir_consumo.py` y los objetivos (7 % sin fluido, 9 % con él, 5,5 % escondida, 300 MB) |
| `39df74e` | **4.** El volcado del 5800X3D, rehecho con la fase 0 y revisado a mano (sin WireGuard, usuario, equipo ni IP) |
| `da00a98` | El texto de polkit del autor, en la propuesta |
| `6b89508` | La medida final en la pantalla; lo validado en la RX 9070 XT |
| `4bf4ca5` | **Gráficos parpadeaba**: cuatro filas de relojes se enseñaban y se escondían en cada muestra, y la página crecía 23 px y volvía; Almacenamiento hacía lo mismo con sus candados. Gráficos, de 18,3 a 6-8 ms por muestra. `tests/test_nada_se_mueve.py`, en todas las páginas |
| `61d98f4` | Las fichas grandes reservan el ancho de su cifra: «9 %» → «10 %» ya no mueve la unidad ni la fila |

**Rendimiento en la pantalla** (DP-1, la página que más gasta / la media,
en % de un núcleo): a la vista sin fluido, 9,3 / 7,6 → 6,2 / 4,3; con
fluido, 31,3 / 13,0 → 9,4 / 5,3; escondida, ~8 → ~4,3, igual con fluido
que sin él. Inicio con fluido, 15,3 → 6,6 (en la oficina eran 16,5).

**3. Comprobado en este equipo**: Gráficos de la RX 9070 XT sin cambios a
peor (`active`, PCIe 4.0 × 16, `gpu_metrics` 1.3 casa con hwmon), barras
con un video y con un juego (lo jugó el autor); CPU, Memoria y Sensores
sin permisos y con ellos (contraseña del autor, en
`~/Imágenes/silux-test/casa-18/comprobacion/`): voltaje con candado y
luego 1.100 V, «Módulo 1/2» con su zócalo, el SPD con su motivo, sin
sugerir XMP; «Qué pasa al dar permisos» con ellos dados, sin «esta vez»;
Ajustes en los dos temas con los controles a la vista y el interruptor
ámbar.

**5. El actualizador, de punta a punta sin publicar nada**: el AppImage de
la rama contra un GitHub de mentira (mitmproxy), con su propio Python.
Encontró dos fallos que los tests no podían ver: **el AppImage no traía
`_ssl`**, así que no podía abrir ninguna URL `https://` y decía «no hay
conexión con GitHub» (`de60ed1`, que además se fía del almacén de
certificados del sistema), y un corte a `http://` también salía como falta
de red (`f3c8721`). Con los dos: bien, SHA malo, `http://` y solo lectura,
los cuatro como deben (`tools/probar_actualizador.py`, `91f6a0f`).

Capturas en `~/Imágenes/silux-test/casa-18/`: `barras-fluidas/` (tiras de
fotogramas antes y después), `graficos/`, `motores/` (reposo, YouTube,
grabando, las dos cosas), `fondo-fijo/` y `comprobacion/`.

## Para esta noche en casa (5800X3D), tras el cierre de la oficina del 18

Hecho la noche del 18: ver el apartado de arriba.

**El borrador de la 0.4 sigue como estaba.** Es de `c01944d`, con las notas
de entonces y título «v0.4.0». `master` también está en `c01944d`.
`oficina` va muy por delante y está empujada, con su CI en verde (el número,
en `gh run list --branch oficina --limit 1`). **No se ha pasado nada a
`master`**: se hará cuando la 0.4 esté lista para publicar, con los pasos de
«3. Publicar» más abajo.

### Qué probar en el 5800X3D (desde `oficina`: `uv run python -m silux.ui.app`)

**La RX 9070 XT**, que no debe haber cambiado para mal:
- El subtítulo con «PCIe 4.0 × 16».
- Consumo, punto caliente, memoria, VR y ventilador.
- «Ahora mismo» con VRAM, consumo y bus, y **sin** barras de motores: no es
  integrada.
- Ninguna nota de «en reposo»: es una dedicada de sobremesa, y su
  `power/runtime_status` debería decir `active`. Si dijera `suspended` con
  la tarjeta dibujando, el arreglo de la dedicada dormida estaría mal: mandar
  `cat /sys/bus/pci/devices/*/power/runtime_status`.

**Movimiento fluido** (Ajustes › Apariencia, ahora se llama así):
- Encendido, las gráficas y las barras se deslizan: las de «Ahora mismo»,
  la memoria en Inicio y en Memoria, los discos y el uso de cada hilo en
  CPU.
- Las cifras saltan al dato y no se animan.
- La barra espaciadora lo congela todo.
- Mirar el consumo con `top` (silux encendido y apagado). Aquí, sin
  pantalla: en Gráficos, 6,6 % de un núcleo apagado y 9,8 % encendido; en
  Inicio, 5,9 % y 16,5 %.

**Permisos:**
- «Qué pasa al dar permisos» con los permisos ya dados: sin «Dar permisos
  esta vez», con la frase «Los permisos ya están concedidos en esta
  sesión».
- Memoria con permisos, abierta después de darlos: tiene que verse bien,
  como en la oficina.
- El ayudante permanente de esa máquina sigue al día: no ha cambiado.

### Steam Deck: el primer volcado real de una APU

En modo escritorio, sin instalar nada. SteamOS trae `python3` (3.11 o
más) y `curl`; la herramienta solo usa la biblioteca estándar.

1. Botón de encendido › «Cambiar a escritorio».
2. Abrir **Konsole** (menú › Sistema).
3. Bajar el código de `master` y entrar:

   ```bash
   cd ~
   curl -L -o silux.zip https://github.com/rcv11x/silux/archive/refs/heads/master.zip
   python3 -m zipfile -e silux.zip .
   cd silux-master
   python3 -V          # tiene que ser 3.10 o más
   ```

4. Que la APU esté despierta y haciendo algo: un video de YouTube en el
   navegador, en otra ventana. Volcar:

   ```bash
   python3 tools/volcar_equipo.py steamdeck
   python3 tools/comprobar_privacidad.py
   ```

   La primera orden ya revisa la privacidad. Si encuentra algo de la Deck,
   no escribe nada y dice qué: entonces se arregla la herramienta, no se
   fuerza.
5. Empaquetarlo y pasarlo al PC (por un USB, KDE Connect o subiéndolo):

   ```bash
   tar czf ~/steamdeck-volcado.tar.gz -C tests/fixtures/equipos steamdeck
   ```

6. En el PC, antes de commitear nada, se mira el contenido. Se quiere ver
   sobre todo:
   - `gpu_metrics`: la Deck (Van Gogh) da la versión 2.2, que silux
     todavía no lee (fallo 14 de la propuesta de gráficas).
   - El hwmon de amdgpu.
   - `vcn_busy_percent`, si el kernel de SteamOS lo tiene.
   - El ioctl con FUSION.

   Después, la suite con el volcado nuevo.

Si el `curl` falla por la red de la Deck, el zip se baja desde el navegador
(«Code › Download ZIP» en `master`) a `~/Descargas`, y se sigue
desde el paso 3 con `cd ~/Descargas`.

## Cierre de la oficina del 18 (17:20-18:00): lo que se hizo

| Commit | Qué |
|---|---|
| `bbffa88` | 4. Con los permisos ya concedidos, el diálogo no ofrece «Dar permisos esta vez» |
| `f8e8e42` | 2. «Movimiento fluido» desliza también las barras; las cifras no se animan; medido |
| `552934d` | 3. `docs/propuesta-mensaje-de-polkit.md`: el texto de la ventana de la contraseña, sin aplicar |
| `be52fae` | 5. Los volcados graban NVML, `xe`, los puentes PCIe y `event_source` |
| `9b63a6e` | Un enlace que no se deja leer ya no tumba el volcado con Python 3.10 |

El autor comprobó en una ventana de verdad que lo de Memoria (campos montados) y Gráficos (sin insignias) era solo de la captura. Las barras de motores de la UHD 630 se mueven con un video de YouTube.

## Tarde del 18 (16:00-18:00), en la oficina: lo que miente, arreglado

Rama `oficina`, sin pasar a `master` (el autor: «no toques el borrador ni
master»). Un commit por cambio, con su test visto fallar.

**A las 16:25 el equipo se congeló.** Había tres agentes de Claude en
paralelo y `pytest -n auto` (12 procesos con Qt) en 16 GB, y el autor lo
apagó a lo bruto. El repositorio quedó sano: `git fsck --full` sin errores,
sin `.lock` ni procesos colgados. Desde entonces:

- **nada de agentes en paralelo** en estos equipos;
- **`pytest -n 4` como máximo**, en los dos equipos.

Está en CLAUDE.md. Lo que dejaron los agentes se revisó, se terminó en la
sesión principal y se quitaron sus worktrees.

| Commit | Qué |
|---|---|
| `56d67e6` | **1a.** Una gráfica suspendida (`power/runtime_status`) no se lee: ni enlace, ni hwmon, ni ioctl, ni NVML, ni las API. Se dice «En reposo» con lo último que se supo. Al despertar se relee lo estático |
| `bd9c255` | **1f.** Inicio, su temperatura y la imagen para compartir usan la gráfica que trabaja (`Snapshot.working_gpu`) |
| `48d19b7` | **1b.** APU de AMD: sin el consumo del encapsulado ni la temperatura del SoC como de la gráfica; se dice al pie |
| `92ae5eb` | **1c.** Arc: sin enlace PCIe en vez de «PCIe 1.0 × 1» |
| `b0113b9` | **1d.** Arc: con `i915` pide su propio PMU (sin uso, y con nota, hasta cambiar el ayudante); con `xe`, la temperatura de `pkg` |
| `be8c988` | **1e.** `gpu_metrics` 1.0 no se lee; se dice que no se interpreta |
| `b4bd118` | Fallo 4: la actividad de una APU en `gpu_metrics` 2.1, que viene en centésimas, no se lee |
| `883afd3` | **9.** Una barra por motor en «Ahora mismo» de una integrada; candado sin permisos |
| `ac2dd32` | **5.** Las ocho capturas del README, con permisos |
| `a4fb777` | **6.** La versión se enseña «0.4»; el CHANGELOG titula `## 0.4` |
| `59eddd6` | **4.** El CI no pisa las notas de la release |
| `562fd1d` | **4.** Lo de hoy, en la entrada de la 0.4 |
| `d52f28c` | **3 y 9.** `docs/propuesta-uso-de-graficas.md`: los dos cambios del ayudante, sin aplicar, y el uso por programa de DRM fdinfo |
| `7052f2d` | **2.** Los volcados no despiertan una gráfica dormida (fase 0, primera parte) |
| `831d2d4`, `710366f` | **10.** Contraste de los controles en reposo, en los dos temas; el interruptor encendido en ámbar |

Para el número exacto de cada commit: `git log --oneline c01944d..oficina`.

**Sin hacer:**

- **2, el resto de la fase 0.** Grabar NVML, ver los archivos de `xe` en el
  nodo PCI, recorrer la cadena de puentes y grabar `event_source`. Sin eso,
  un volcado de una NVIDIA o de una Arc llega cojo.
- **7.** Rama `actualizaciones`, sale de `c01944d` (el estado de la noche
  del 18, más arriba):
  - La propuesta, `silux/updates.py` (buscar, bajar, comprobar el SHA-256
    y sustituir) y el paso del CI que publica `SHA256SUMS`, con sus tests.
  - **La interfaz está hecha** (`3d363d8`): el interruptor «Buscar
    actualizaciones al iniciar» (apagado) y «Buscar ahora» en Ajustes, y
    «Actualizar a X» bajo la versión de la barra lateral.
  - Al rebasarla sobre `oficina` chocará en el paso de la release del CI,
    porque los dos lo tocan.
- **8.** Solo la estimación, en la respuesta de la sesión: no cabe en la
  0.4.

**Para mirar en una ventana de verdad, con permisos.** Pasó al capturar y
sin ventana real no se sabe si es de la captura:

- Memoria abierta *después* de dar permisos sale con los campos de los
  módulos montados unos encima de otros. Con la página abierta desde el
  principio sale bien.
- La cabecera de Gráficos sale sin las insignias.

Las dos son de una página que se pinta escondida.

**Capturas** en `~/Imágenes/silux-test/oficina-18/`:

- `readme-permisos/`: las del README.
- `motores/`: antes y después, con y sin permisos.
- `contraste/`: antes y después, en los dos temas.
- `version-corta.png`.

## Para casa: probar la 0.4.0 en el 5800X3D y publicarla

La 0.4.0 está preparada y **sin publicar**:

- `oficina` pasó a `master` con `--ff-only`: el último commit es el del
  CLAUDE.md de esta tanda («docs(claude): la 0.4.0 en borrador…»).
- El CI de `master` está en verde: la ejecución de ese commit. Se ve con
  `gh run list --branch master --limit 1`.
- Existe la release **v0.4.0 en borrador**, con las notas de la entrada
  0.4.0 del CHANGELOG y los dos AppImage de esa ejecución.
- La etiqueta **no existe todavía**: la crea GitHub al publicar.
- La fecha del CHANGELOG es el 18 de noviembre.

### 1. Bajar los AppImage del borrador

```bash
mkdir -p ~/silux-0.4.0 && cd ~/silux-0.4.0
gh release download v0.4.0 --repo rcv11x/silux --pattern '*.AppImage'
chmod +x silux-x86_64*.AppImage
./silux-x86_64.AppImage --version     # 0.4.0 y el commit de master
git -C ~/Documentos/Coding/silux rev-parse --short origin/master   # tiene que coincidir
```

### 2. Qué probar antes de publicar

**Permisos:**
- Inicio avisa de lo que falta.
- «Qué hace esto» se lee entero.
- «Dar permisos» pide la contraseña sin congelar la ventana, y los candados
  desaparecen en la página abierta, sin cambiar de página.
- Si el ayudante permanente de una versión anterior está instalado, el
  botón para actualizarlo.
- Pulsar un candado también los pide.

**Memoria (X570, Gigabyte):**
- Las fichas se llaman «Módulo 1», «Módulo 2»…, con y sin permisos, y el
  zócalo («Canal A · DIMM 1») va en su campo.
- No se dice cuántos zócalos hay ni cuántos quedan libres.
- Sin SPD (el firmware se reserva el SMBus), el pie da ese motivo y no
  culpa a «la placa» sin más.
- El fabricante, «Crucial» o el que sea, sale igual con y sin permisos.
- El máximo del procesador según la disposición de los módulos (2x2R o
  4x1R): si van a ese máximo, no se sugiere XMP.

**Gráficos (RX 9070 XT):**
- Que no haya cambiado nada para mal: «Ahora mismo», sensores (punto
  caliente, memoria, VR, ventilador), códecs y motores.
- Todo en ámbar, ni rastro de azul salvo candados e interruptores.
- Los cambios de la integrada (pie en una frase, sin AMD en los textos) no
  deberían tocar a una dedicada; mirarlo igual.

**Acceso directo (Ajustes, «Integración con el escritorio»):**
- Desde el AppImage: «Añadir al menú» pone «Silux» con el icono nuevo y
  apunta al AppImage.
- El acceso en el escritorio, si se marca.
- Quitarlo lo quita.
- Desde el código, «Silux (desarrollo)» va aparte y no pisa la otra
  entrada.

**De paso:**
- Sistema con Limine: las cinco fases del arranque y el total, sin pie.
- Los miles con espacio fino.
- `--report` y `--json` sin errores.
- Si se puede, volcar el 5800X3D otra vez (`tools/volcar_equipo.py
  5800x3d`): ahora grabaría la FPDT y lo que contesta systemd. Eso va en un
  commit aparte, después de la versión.

Si algo sale mal: se arregla en una rama desde `master`, con su test y el CI
en verde, `--ff-only` a `master`. Después se borra el borrador y se crea
otra vez desde la ejecución nueva (o se sustituyen los AppImage con `gh
release upload v0.4.0 … --clobber`).

### 3. Publicar

**El borrador está atrasado.** Se creó desde `c01944d` a las 15:30, y por
la tarde entraron en `oficina` once arreglos que deben ir en la 0.4. Antes
de publicar, por orden:

1. `oficina` a `master` con `--ff-only`, con su CI en verde. **No está
   hecho**: el autor dijo «no toques el borrador ni master».
2. Sustituir los AppImage del borrador por los de esa ejecución del CI de
   `master`:
   `gh run download RUN -n appimages -D /tmp/ai` y después
   `gh release upload v0.4.0 /tmp/ai/*.AppImage --clobber`.
3. Las notas y el título, con la versión corta («0.4»; por debajo sigue
   siendo `v0.4.0`):

```bash
awk '/^## 0\.4 /{f=1; next} /^## 0\.3 /{f=0} f' CHANGELOG.md > /tmp/notas.md
gh release edit v0.4.0 --title "0.4" --notes-file /tmp/notas.md
# Si se publica otro día, antes la fecha en CHANGELOG.md («## 0.4 (DÍA de
# noviembre de 2026)»), con su commit en master.
```

4. Publicar. Esto crea la etiqueta `v0.4.0` sobre `master`:

```bash
gh release edit v0.4.0 --draft=false --latest --target "$(git rev-parse origin/master)"
gh run watch     # el CI de la etiqueta
```

**Las notas ya no se pisan.** El paso de la release del CI ya no lleva
`body_path` (`59eddd6`). Según el código de `softprops/action-gh-release`,
sin cuerpo deja el de la release que existe. Ese CI vuelve a subir los dos
AppImage del mismo commit. **Comprobar en la release, después de
publicar**, que las notas son solo las de la 0.4.

Después de publicar, empezar en el CHANGELOG la entrada «## 0.4.1 (sin
publicar)» o «## 0.5 (sin publicar)», y quitar de CLAUDE.md y de
`docs/pendientes.md` lo que ya no esté pendiente.

**Probar también en casa** lo que entró por la tarde:

- Gráficos de la RX 9070 XT: no debe cambiar nada.
  - Con `integrated=False` no hay barras de motores.
  - El consumo y el punto caliente siguen saliendo.
- Ajustes en los dos temas:
  - Los controles apagados se ven.
  - El interruptor encendido es ámbar.
- «versión 0.4» abajo a la izquierda.

## Tarde del 18, en la oficina: la 0.4.0 preparada y la propuesta de gráficas

| Commit | Qué |
|---|---|
| `34370c8` | Los miles con espacio fino (U+202F) en toda la app; una guarda contra `:n` y `:,` |
| `04ae63c` | Cada velocidad de memoria con su grado JEDEC en todas las generaciones (DDR2-667, LPDDR5-5500, LPDDR5X-7467/7500) |
| `3b34004` | CHANGELOG de la 0.4.0 por zonas, con fecha y limitaciones conocidas |
| `f2e0657`, `c8617c7` | README al día y sus ocho capturas, sin permisos |
| `f114c85` | **`docs/propuesta-graficas.md`**: las gráficas no probadas, 25 fallos por gravedad, plan en seis fases y los volcados que hacen falta |

**Las capturas del README van sin permisos**: el autor no estaba para meter
la contraseña. Para rehacerlas con permisos, como las de septiembre, hay que
usar la ventana de verdad (`--screenshot` no eleva): abrir el AppImage, dar
permisos y capturar cada página a 1000×760 con `--anonimo`. Este equipo
o el 5800X3D: el de casa enseñaría la RX 9070 XT, que luce más que la UHD.

**La propuesta de gráficas** sale de cuatro investigaciones en paralelo
(AMD, Intel, NVIDIA, y dos gráficas más la revisión del código), con los
fallos más graves vueltos a mirar en el código. Lo primero de su plan es la
fase 0 (que las herramientas de volcado no despierten la tarjeta, graben
NVML y vean `xe`), y lo más urgente para quien usa el programa, el fallo 1:
silux despierta la dedicada dormida de un portátil en cada muestreo. Nada
de esto se ha empezado: espera a que el autor la lea.

## Tarde del 18, en la oficina (rama `oficina`, tercera tanda)

Tras revisar el autor `comprobacion/`, `kernel/`, `memoria-permisos/` y
`appimage-2/`. Un commit por cambio, con su test visto fallar y capturas
antes y después en `~/Imágenes/silux-test/oficina-18/tanda-3/` (el número
del principio es el punto de la revisión).

| Commit | Qué |
|---|---|
| `32d69c8` | `gen_memory_limits.py` lee las comparaciones de ARK: una página por serie |
| `c5ae87c` | 1. Memoria no dice cuántos zócalos hay ni cuántos quedan libres |
| `bab1456` | 6. La ficha de consumo solo dice «permisos» si faltan permisos |
| `6f7da14` | 2. Sin SPD no se culpa a la placa: el motivo del diagnóstico, y candado si es un driver |
| `b8546c5` | 7. «No traen perfiles rápidos», una vez |
| `2688d85` | 7. El fabricante de memoria, igual venga del SPD o de SMBIOS («Crucial») |
| `9b26b93` | 7. Las fichas se llaman «Módulo N» con y sin permisos; el zócalo, en su campo |
| `8209325` | 3. **Un solo acento, el ámbar**: fuera de Ajustes, de las preferencias y `--accent` |
| `f5b00d8` | 4. iGPU: lo que no tiene, nombrado al pie en una frase; sin el driver de AMD; eficiente = mínima, una fila |
| `52f799c` | 5. **Tiempos de arranque con GRUB**: firmware y cargador de la FPDT, el resto de systemd |
| `4b7aeb9` | 8. «Intel, audio HD (8086:f0c8)» en vez de «no está en la lista de nombres PCI» |

**Los zócalos (1)**. El «2 de 4» con permisos sale de SMBIOS: la tabla del
tipo 17 de esta MSI H510M PRO-E trae cuatro entradas, dos «No Module
Installed» (`…ChannelA-DIMM1`, `…ChannelB-DIMM1`), y la placa tiene dos
ranuras. El «2 de 2» sin permisos era de una captura montada a mano. Nada
de la tabla distingue una ranura fantasma de una vacía de verdad, así que
no se dice ninguna de las dos cifras.

**El acento (3)**. El `settings.json` de la oficina tenía `"accent": "azul"`,
y lo leen el AppImage y `--screenshot`; lo montado con las preferencias de
serie salía ámbar. Al cerrar la ventana se guardó sin la clave.

**El arranque (5)**. Los dos volcados del i5-10400 ganan la FPDT y lo que
contestó `systemctl show`, de este equipo el 18. El del 5800X3D no los tiene:
volcarlo de nuevo en casa los grabaría (lo hace `volcar_equipo.py` solo).

**Lo que se rompió en medio**: dos commits (6 y 2) dejaban un test atrás
cada uno porque antes de commitear se pasó solo una parte de la suite; se
arreglaron dentro de su commit con un `fixup`. Desde ahí, suite entera antes
de cada commit.

**ARK**: la comparación de la serie 10.ª i5 trae los 23 modelos de su página
de serie (sin tope visto) con la memoria de cada uno; la página de serie no
la trae. La exportación no llegó a guardarse y no hace falta. Lo que tiene
que guardar el autor es una comparación por serie (lista en la respuesta de
la sesión).

## Tarde del 18, en la oficina (rama `oficina`, segunda tanda)

Tras revisar el autor las capturas de la mañana. Un commit por cambio, con
su test visto fallar y su captura. **Empujada y con el CI lanzado al acabar;
parada ahí.** Nada ha pasado a `master`.

| Commit | Qué |
|---|---|
| `65ff4bf` | Ajustes: fluidas en Apariencia, instrucciones en Muestreo. El desplegable cortado era una captura vieja |
| `4a842fd` | `Table.set_cell_locked`: candado en el uso de cada motor de la iGPU |
| `3316e89` | «Sabe hacer» vacío, no «—» |
| `d6a0cf8` | iGPU: sin «Consumo y temperaturas»; su explicación debajo de la fila |
| `881ee7a` | Memoria: sin «Perfiles rápidos —» en módulos sin XMP; la nota del SPD ya no habla de activarlo |
| `b3e81e3` | Memoria: el fabricante del SPD («Crucial»), no el de SMBIOS («Crucial Technology») |
| `a414181` | **Benchmark: el reparto se mide con tiempo de CPU** (el ×1.76 era el SMT del runner) |
| `0cf232f` | **`tools/gen_memory_limits.py`**: 155 Ryzen desde amd.com, con el máximo por disposición de módulos |
| `22425d2` | `--intel-desde CARPETA`: fichas de ARK guardadas desde el navegador |
| `0158bea` | Antes de Nehalem la memoria es del chipset, y Memoria lo dice |
| `11219c7` | **`docs/kernel.md`, `silux/kernel.py`**: «Tu kernel (5.15) no publica esto; existe desde Linux X.Y»; mínimo 5.15 en el README |
| `62b0a7b` | La nota de amd-pstate solo en un AMD |
| `b8c9816` | Un test que `d6a0cf8` dejó atrás (la suite estuvo roja en medio, sin empujar) |

**Memoria con permisos de verdad**: el autor metió la contraseña dos veces.
Este equipo da 2 de 4 zócalos, SPD de los dos módulos, 2666 configurados de
3200 y «al máximo del procesador». La foto que leyó el ayudante se guardó en
el scratchpad de la sesión (no sobrevive) y con ella se hicieron las
capturas de después, en `~/Imágenes/silux-test/oficina-18/memoria-permisos/`.
De paso: Placa base no saca la columna «Ranura» (el firmware de esta MSI no
lo dice) y Almacenamiento enseña «Vida restante —» en el Kioxia (pendientes).

**El test del benchmark**: con `taskset` a 0,6,1,7 (dos núcleos con SMT, como
un runner de 4 vCPU) la escala de `compresion_dura` da ×2,3–2,5 y en cuatro
núcleos ×3,9; el tiempo de CPU sumado da ×3,9 en los dos y ×1,0 con Python
puro. Lección en `docs/lecciones.md`.

**La tabla de memoria**. AMD: 76 modelos con disposición (2x1R, 2x2R, 4x1R,
4x2R) y 79 con la cifra plana de la tabla; fuera 11 que AMD no tiene en
ninguna ficha (5700X3D, 5600X3D, 3950X, 5500GT, 3400G, dos GE, cuatro PRO
7x45). Intel: no se descarga (403 a un cliente que no es un navegador; no se
intenta saltar). Siguen las 53 filas a mano de 10.ª y 11.ª, cada una con su
ficha. **Pendiente del autor**: guardar las fichas de ARK en
`~/Descargas/intel-ark/` y avisar (la lista está en la respuesta de esta
sesión); antes, una muestra de tres páginas para confirmar el formato.
`ficha_intel` está escrita sin haber visto una ficha guardada de verdad, y
su test lo dice.

**El kernel**: la investigación la hizo un agente mirando el código de cada
etiqueta de mainline, con los commits comprobados. Dos de los tres primeros
ganchos se quitaron por falsos (el «Estado» de i915 depende de la
generación; el uso de video de AMD sale también de `gpu_metrics`); quedan el
techo de AMD (amd-pstate, 5.17) y el SPD de DDR5 (spd5118, 6.11). Probado
convirtiendo los dos volcados a 5.15; sin un equipo con 5.15 de verdad.

## Mañana del 18, en la oficina (rama `oficina`)

Sale de `master` en `67aa368`. Cinco puntos del autor; un commit por cambio,
con su test visto fallar y su captura. **Empujada y con el CI lanzado al
acabar el punto 4, y parada ahí** a la espera de que el autor mire las
capturas. Nada ha pasado a `master`.

| Commit | Qué |
|---|---|
| `3703b7d` | La instalación del menú pasa al paquete (`silux/desktop.py`); solo mueve código |
| `d3af27f` | **La ventana se presenta con el icono del paquete**, no con el del tema (el logo viejo en la barra de tareas) |
| `37ef079` | Reinstalar quita lo de `cpuz`, los tamaños viejos, y avisa a Plasma (`kbuildsycoca6` y `org.kde.KIconLoader.iconChanged`) |
| `d27a7bf` | Cada forma de ejecutar tiene su entrada: AppImage → `$APPIMAGE`; código → «Silux (desarrollo)», `silux-dev.desktop`, con su `app_id`; `Exec=` con comillas |
| `d7e1c43` | Los dos volcados del i5-10400, rehechos (lista de archivos aprobada por el autor) |
| `41f88b8` | Reposo: «C2», no «C2_ACPI» |
| `36feac5` | Sistema: «GRUB 2.12 no publica cuánto tarda el arranque» al pie |
| `60c8c70` | Placa base: la integrada «en el procesador»; el audio sin nombre, «Intel · no está en la lista de nombres PCI» |
| `25911fa` | Sensores: «Paquete» y «Núcleo N» |
| `e82238d` | La tabla de códecs no se desplaza por dentro; guarda general para todas las tablas |
| `09296d6` | La guarda mira también los árboles medidos a mano (USB) |
| `041a84f` | i915: RP0, RP1 y RPn; RC6 desactivado; motivos de limitación donde existan (volcados rehechos otra vez para llevar esos archivos) |
| `68ff3f3` | Memoria: al máximo oficial del procesador no se sugiere XMP (`silux/db/memory_limits.json`) |
| `ed87010` | Pendientes: los límites de AMD, aplazados |
| `3108f0e` | `desktop.status()` y el acceso en el escritorio |
| `2fabe76` | **Ajustes con la maqueta aplicada** y el grupo «Integración con el escritorio» |

### El acceso directo que no abría y el icono viejo (punto 1)

Tres causas, las tres arregladas. Lo que pasaba en casa no se ha visto, así
que no se sabe cuál de las tres era:

1. `application_icon()` prefería el icono del tema al del paquete: con los PNG
   de una instalación anterior al logo nuevo, la ventana se presentaba al
   compositor con el viejo y la barra lateral pintaba el nuevo.
2. `plasmashell` guarda los iconos en memoria; sobrescribir el PNG no basta.
3. Lo de versiones viejas no se quitaba: en la oficina había un
   `cpuz.desktop` que lanzaba `python3 -m cpuz.ui.app` desde una carpeta
   que ya no existe. La instalación de aquí lo ha quitado.

**Probado aquí**: `uv run python tools/install_desktop.py` instaló
«Silux (desarrollo)»; lanzado con `gtk-launch silux-dev`, KWin ve la ventana
con `desktopFile: silux-dev` y `resourceClass: silux-dev`, y la barra de
tareas pinta el logo nuevo (captura recortada, no guardada).

**En casa**, desde el repositorio en la rama `oficina`:

```bash
uv run python tools/install_desktop.py --estado    # cómo está, sin tocar nada
grep -l -i -e silux -e cpuz ~/.local/share/applications/*.desktop ~/Escritorio/*.desktop 2>/dev/null
uv run python tools/install_desktop.py             # instala «Silux (desarrollo)»
```

Con `uv run` y no con `python3` a secas: la entrada apunta al intérprete con
el que se instala, y tiene que ser uno con PySide6. Si el `grep` enseña una
entrada de AppManager (Exec a `~/AppImages/…`) es la del AppImage: se arregla
abriendo el AppImage nuevo, Ajustes › «Arreglar». Si la barra de tareas
sigue con el logo viejo tras todo esto, mandar la salida de las dos primeras
órdenes.

### Intel, comprobado en la pieza (punto 2)

PL1 65 W y PL2 115 W; reposo C1/C2 (tras el arreglo); 19 vulnerabilidades,
10 mitigadas, ninguna sin mitigar; zram con `lzo-rle`; GRUB 2.12 con su pie;
VT-x en uso por KVM, Above 4G y ALC892; la tabla PCIe (tras los arreglos);
Gráficos sin nada de AMD, «23 unidades de ejecución», candado en el uso de
video; Dispositivos con teclado y ratón. **Sin hacer: enchufar y quitar un
USB con la página abierta**, que pide manos.

### Lo que queda escrito a ciegas o sin ver

- Los motivos de limitación de i915 (`throttle_reason_*`): esta pieza no los
  tiene. Y las rutas de `xe` para RP0, RP1 y RPn.
- El máximo de memoria con permisos de verdad: la captura monta los módulos
  a mano. Dar permisos en la oficina y mirar Memoria.
- El botón de Ajustes desde el AppImage: lo construye el CI; hay que abrirlo
  y pulsar «Añadir».
- AMD en la tabla de memoria (su máximo depende de los módulos), en
  pendientes.

### Capturas

En `~/Imágenes/silux-test/oficina-18/` (oficina): `intel/` (las páginas de
este equipo antes de los arreglos), `comprobacion/` (la de cada commit) y
`ajustes/` (oscuro y claro a 1440, oscuro a 2560, compacto a 900 y la
página entera).

## Madrugada del 18, en casa: trabajo sin supervisión (rama `interfaz`)

El autor dejó cinco bloques y se fue a dormir. Se empujó `interfaz` al
acabar cada uno.

### Resumen para la oficina (18 de noviembre de 2026)

**Los cinco bloques están hechos.** `interfaz` y `master` apuntan al mismo
commit y están empujadas. `master` avanzó con `git merge --ff-only`, **sin
etiqueta**: la 0.4.0 sigue «sin publicar» en el CHANGELOG.

**El CI.** Dos intentos de esta madrugada:

- El primero (run 44188932876, sobre `06d825f`) **falló en los dos Python**
  por un test nuevo, `test_tabla_encaja.py::…en_compacto_a_900…`: con la
  letra del runner (DejaVu) las tarjetas de Placa base y Sistema caben de
  una en una a 900 px y el test exigía dos por fila. El fallo era del test,
  no de la página. Arreglado en `d3ae5e4`, que además lo repite con DejaVu.
- El segundo (run 44189790198, sobre `d3ae5e4`): **en verde**, tests en 3.10
  y 3.14 y los dos AppImage. Abiertos con `--screenshot`: salen los catorce
  iconos de la barra lateral, el de Dispositivos incluido
  (`~/Imágenes/silux-test/interfaz-casa/comprobacion/ci3-barras.png`).
- Este resumen es un commit posterior, solo de documentación; pasó su
  propio CI antes de llegar a `master` (el número está en el mensaje del
  commit siguiente si hubo que añadirlo, y en `gh run list`).

La suite son 2060 tests; con Python 3.10 pasa también aquí
(`uv run --python 3.10`).

**Qué había que hacer en la oficina, por orden** (hecho el 18 por la mañana,
salvo enchufar un USB y lo que pide permisos; ver arriba):

1. **Rehacer los dos volcados del i5-10400.** Son de antes de los datos
   nuevos y de eso no traen nada: en Intel está todo sin comprobar.
   `rm -rf tests/fixtures/equipos/i5-10400 tests/fixtures/equipos/i5-10400-turbo`,
   `python3 tools/volcar_equipo.py i5-10400` en reposo y
   `python3 tools/volcar_equipo.py i5-10400-turbo` con el turbo encendido
   (cómo, en «Decisiones de hoy», más abajo). Después la suite entera:
   `tests/test_equipos_nuevo.py::TestElVolcadoDeAntes` espera que el del
   i5-10400 **no** traiga USB ni vulnerabilidades y va a fallar; es la
   señal de que hay que escribir para él lo que `TestElVolcadoNuevo`
   comprueba para el 5800X3D. La herramienta quita la marca y el modelo de
   lo enchufado por USB: si se niega a escribir, es que encontró algo de
   esa máquina; se arregla la herramienta, no se fuerza.
2. **Mirar en Intel**, con la aplicación abierta:
   - CPU › «Potencia y reposo»: PL1 65 W y PL2 115 W, y la barra de reposo
     con los estados de Intel (C1, C6…).
   - Sistema: vulnerabilidades y sus mitigaciones (un Comet Lake tiene más
     que un Zen 3; ninguna debería salir «sin mitigar»), intercambio, y el
     arranque: con GRUB no hay tarjeta y sale una línea al pie.
   - Placa base: la tabla PCIe (la integrada no es un dispositivo de
     ranura) y la tarjeta Plataforma (VT-x).
   - Dispositivos: enchufar y quitar un USB con la página abierta.
   - Gráficos: lo de la tanda A (sin los guiones de lo que solo existe en
     AMD; «Uso del motor de video» con candado).
3. **Con permisos**, en cualquiera de las dos máquinas: dar permisos
   **desde Memoria y desde Almacenamiento sin salir de la página** (el
   fallo del bloque 1); la columna «Ranura» de Placa base, que está escrita
   a ciegas; y el «Diagnóstico completo» de cada disco.
4. **Decidir**: las cuatro preguntas del final de
   `docs/propuesta-limites-amd.md`, y la maqueta de Ajustes
   (`~/Imágenes/silux-test/ajustes/`, en casa).

**Lo que se rompió y se arregló por el camino**, para que no sorprenda en
el historial: el fallo de Memoria era del arreglo del hueco de Gráficos de
esa misma noche (`aff559c`); el test general encontró dos más (una tarjeta
de Almacenamiento que no volvía a su texto y una tabla que reventaba al
volver un monitor).

**Lo que no se hizo**: wifi, LUKS y secundarias del SPD (sin pieza); el
tiempo de arranque del kernel; los estados vacíos de una ficha, los
identificadores en monoespaciada y el contraste de la paleta (el «punto 3»
de la lista del 17, que sigue pendiente).

**En casa queda** (no está en el repositorio): las capturas de
`~/Imágenes/silux-test/interfaz-casa/`, las maquetas de `datos-nuevos/` y
de `ajustes/`, y el volcado anterior del 5800X3D solo en el historial de
git. El ayudante de permisos de esa máquina es el de antes de esta
madrugada: no cambió nada del ayudante, así que sigue al día.

El detalle de cada bloque:

### Bloque 1, hecho: la página abierta se pone al día sola

| Commit | Qué |
|---|---|
| (storage) | La tarjeta de permisos de Almacenamiento vuelve a su texto si el diagnóstico se pierde |
| (widgets) | Una fila de tabla con menos celdas que columnas no deja datos viejos ni revienta |
| (widgets) | **Las tarjetas que nacen con la página abierta se ven sin salir y volver** (el fallo de Memoria) |

El fallo de Memoria era del arreglo del hueco de Gráficos (`aff559c`), de
esta misma noche: `ResponsiveRow` tomaba por escondido un widget recién
creado. `tests/test_al_momento.py` es el test general (regla 9 de
CLAUDE.md): trece secciones, cada volcado, cuatro sentidos (dar permisos,
perderlos, quitar hardware, volver a ponerlo). **No cubre Batería** (ningún
volcado tiene una) **ni un USB que se quita** (la sección Dispositivos no
existía todavía; entra en el bloque 3 con su propia foto).

**A probar en la pieza**: dar permisos desde Memoria y desde
Almacenamiento sin salir de la página.

### Bloque 2, hecho: detalles de la tanda A

- **Sensores, «Último minuto»**: la curva se queda con todo el ancho que
  sobra (tenía un tope de 460 px). Visto a 2560×1440.
- **Sensores, el chip entre paréntesis**: en todas las filas de la
  categoría cuando hay nombres repetidos, en ninguna cuando no. La placa:
  seis «(it8688)» y tres «(acpitz)»; la gráfica, ninguno.
- **Notas como frases**: «Los chips, los perfiles rápidos y la fecha de
  fabricación salen del chip SPD de cada módulo, y esta placa no deja
  leerlo.» y «El firmware de esta placa no dice su revisión ni el fabricante
  del chasis.» (`render.enumeration`).
- **CPU en compacto**: la especificación en dos líneas
  (`ElidingLabel.permitir_lineas`). Con la letra normal ya cabía; el corte
  era con la letra por omisión, que es la «grande».
- **El test de benchmark de ×1.8**: apuntado en `docs/pendientes.md` y en
  CLAUDE.md para la fase del benchmark. El umbral no se ha tocado.

### Bloque 3, hecho: los datos nuevos de `docs/propuesta-datos.md`

| Commit | Qué | Visto en |
|---|---|---|
| `492c8b2` | Sistema: vulnerabilidades, intercambio, arranque, Mesa; procesos bien contados en un volcado | captura de este equipo |
| `e5740a5` | Placa base: una tabla de dispositivos PCIe y la tarjeta Plataforma | captura de este equipo |
| `a594a40` | **Sección nueva, Dispositivos** (la decimocuarta), con su privacidad | capturas normal y `--anonimo` |
| `709e6c7` | CPU: residencia en C-states; PL1 y PL2 sin permisos | captura de este equipo (AMD) |
| `3c7bc13` | Cachés: la latencia medida, en la fila de su nivel | captura midiendo de verdad |
| `c598bca` | Almacenamiento: TRIM y diagnóstico completo | solo tests (ver abajo) |
| `1c9b909` | `volcar_equipo.py` al día: tapa lo enchufado | — |
| `531fd11` | **El volcado del 5800X3D, rehecho** | privacidad limpia |

Las correcciones a las maquetas están todas aplicadas (una sola tabla PCIe
con los nombres de cada página, el enlace de la gráfica como en Gráficos,
«Ranura» solo con permisos, la dirección al pasar el ratón, «Above 4G
Decoding»; zram en una fila, las tres cifras del arranque, las mitigaciones
enteras; el USB en árbol sin contar concentradores, clases que dicen lo que
es, «Velocidad completa · 12 Mb/s», sonido con nombres que se entienden,
icono propio y la privacidad antes que la página).

**Escrito a ciegas o sin ver, para probar:**

1. **Todo en Intel.** El volcado del i5-10400 no trae nada de esto.
   **Hay que rehacerlo en la oficina**: `rm -rf
   tests/fixtures/equipos/i5-10400 tests/fixtures/equipos/i5-10400-turbo`
   y `python3 tools/volcar_equipo.py i5-10400` (y el `-turbo` con carga,
   como dice «Decisiones de hoy» más abajo). Después, la suite: los tests de
   `test_equipos_nuevo.py` que hoy solo miran el 5800X3D son la plantilla
   para mirar ese. Lo que más interesa ver allí: PL1 y PL2 en CPU (65 y
   115 W), los C-states de Intel, GRUB sin tarjeta de Arranque y con su
   línea al pie, y la tabla PCIe con la integrada.
2. **La columna «Ranura»** de Placa base: sale de la tabla del firmware,
   que pide permisos. Probada con una estructura fabricada según la norma,
   no con la de ninguna placa. Dar permisos y mirar si los nombres casan.
3. **El diagnóstico completo** de cada disco (Almacenamiento, plegado):
   con permisos. Y el TRIM, dentro de «Firmware y sectores».
4. **Dispositivos**: enchufar y quitar un USB con la página abierta; un
   disco USB 3 en un puerto USB 2 tiene que salir con su aviso.

**Lo que no se hizo, a propósito**: wifi, LUKS y secundarias del SPD (sin
pieza); el tiempo de arranque del kernel y de los servicios (pide lanzar
`systemd-analyze`).

### Bloque 4, hecho: `docs/propuesta-limites-amd.md` (solo documento)

PPT, TDC y EDC con `ryzen_smu`. **Recomendación: no ahora, y no entero.**
Va contra «mejor un dato que falta que uno que parece bueno» (la tabla no
está documentada y cambia con la BIOS), y haría que el ayudante dejara de
ser «solo lee»: cada lectura de esa tabla manda una orden al firmware. Si
aun así se quiere, en dos pasos: primero solo detectar el módulo, sin cifras
y sin privilegios; después, experimental y con un único mapa, el del
5800X3D, verificado en la pieza. **En este equipo `ryzen_smu` no está
instalado**, así que nada de su tabla está comprobado: lo dice el documento.
Lo que sí propone para ya, en Intel: las ventanas de tiempo de PL1 y PL2,
PL4 donde exista y si los límites están bloqueados (el registro ya está en
la lista del ayudante). **Hay cuatro decisiones del autor al final.**

### Bloque 5, hecho: maqueta de Ajustes (sin aplicar)

En `~/Imágenes/silux-test/ajustes/` (casa), con su guion
`maqueta_ajustes.py`: la ventana real con una página nueva en el sitio de
Ajustes, en oscuro y claro, a 1440×900, 2560×1440 y compacto a 900×680. Cada
una tiene además su `-entera` (la página no cabe en esas alturas; a 1440 de
ancho ni la entera llega al final de «Acerca de», que la ventana no pasa de
2160 de alto).

Una columna centrada con ancho máximo; cada opción en un renglón, texto a la
izquierda y control a la derecha; seis grupos: General, Apariencia,
Muestreo, Permisos, Compartir e informes y Acerca de (con «Restablecer» al
final). **Nada de esto está en el programa.** Dos cosas son nuevas y hay que
decidirlas: el grupo **Permisos** (en la maqueta dice el estado real del
ayudante de este equipo; el botón «Quitar el ayudante…» sale apagado porque
toca privilegios y es solo propuesta) y **la descripción de Claude** en
Autoría, que lleva delante la palabra PROPUESTA con un texto para corregir.

## Sesión del 17 por la noche, en casa (rama `interfaz`)

Dos tandas. La primera (el hueco de Gráficos, el corte de Red, la raya de
las tablas, Cachés que no se pintaba y el botón del ayudante atrasado) se
empujó en `24cb4ef` con el CI en verde. **La segunda, la tanda A, está
empujada hasta `91512f7` con el CI en verde** (tests en 3.10 y 3.14 y los
dos AppImage). Por delante de eso hay dos commits locales sin empujar: la
propuesta de datos y este archivo.

### Tanda A: un commit por arreglo, con su test y su captura

| Commit | Qué | Visto en |
|---|---|---|
| `0d9b0a3` | test: el del diálogo fija que no hay ayudante instalado (leía el de quien ejecuta) | — |
| `b800c61` | Sensores: ventiladores a 0 RPM y redes sin tráfico nacen plegados | este equipo |
| `7d5055e` | «en reposo» en vez de «0 MHz»; «Uso del motor de video» | este equipo (lo segundo) |
| `bc39c9a` | **El AppImage salía sin iconos ni marca**: `imageformats` vacío | los dos del CI, y uno reconstruido aquí |
| `057cac3` | La barra lateral mide su nombre más largo | compacto, normal y letra máxima |
| `6af4d7f` | Una tabla que no cabe cede su texto largo (`Table(cede=…)`) | Almacenamiento y Gráficos en compacto |
| `0739dc4` | `tools/montar_equipo.py`: un volcado montado como en los tests | — |
| `5cb84ff` | iGPU de Intel: escondido lo que solo existe en AMD; candado en el uso de video | volcado del i5-10400, oscuro y claro |
| `519e86c` | «Encendido desde 2026-11-17 18:15» | este equipo |
| `e06eeb5` | El diálogo de permisos abre con el alto de su contenido | **en la sesión real (Wayland)** |
| `ad05880` | Zócalos de memoria con nombre único (`render.slot_names`) | página pintada con una tabla de prueba |
| `91c0237` | Sin SPD, Chips, Perfiles rápidos y Fabricado se esconden y se nombran | ídem |
| `e066d83` | De las ramas de Sensores solo se guarda lo hecho a mano (`sensor_expanded`) | configuración vacía |
| `337078c` | `gigabyte_wmi` repite al IT8688: seis temperaturas, no doce | este equipo |
| `e03f7e1` | Un HDD no enseña «Vida restante» | este equipo |
| `6799467` | Ajustes: ni «las 53» ni «sin dependencias» | este equipo |
| `244cd4b` | Pulgadas del monitor desde sus milímetros: 26.7" y 27.0" | este equipo |
| `8ea9dc0` | Ventana grande: las tablas se reparten; Placa base y Sistema en una fila | 2560×1440, 1440×900 y compacto |

**Lo que hay que mirar en la pieza, porque aquí no se pudo:**

1. **Con permisos, en el 5800X3D**: Memoria tiene que titular los módulos
   «Canal A · DIMM 1» y «Canal B · DIMM 1», decir «2 zócalos libres: Canal A
   · DIMM 0, Canal B · DIMM 0» y no enseñar Chips, Perfiles rápidos ni
   Fabricado (los dice al pie). Está probado con una tabla de firmware de
   prueba con las cadenas que el autor describió («DIMM 0/1», «P0 CHANNEL
   A/B»), no con la de esa placa: no se piden permisos desde la sesión de
   Claude. **Si sale otra cosa, mandar `sudo dmidecode -t 17`.**
2. **Con permisos**, Almacenamiento: los HDD sin «Vida restante» y sin
   guion en su sitio.
3. **En la oficina (i5-10400)**: Gráficos sin «Unidades de rasterizado»,
   «Motores de sombreado», «SoC», «Perfil de rendimiento», «Enlace»,
   «Voltaje» ni «Voltaje del SoC»; con «23 unidades de ejecución»; «Uso del
   motor de video» con candado. «Estado —» se queda a propósito. Y Sensores
   con `interfaz1` y `tailscale0` plegadas.
4. **«En reposo»** (el motor gráfico a 0 MHz) no tiene captura: ni esta
   gráfica ni el volcado están a cero. Lo ve el test.
5. Las capturas de `tanda-A/` son de `2d54c36`: la barra lateral sale en
   ellas 8 px más estrecha que tras `91512f7`.

**Decisiones de esta tanda que cambian algo anterior:**

- **`sensor_collapsed` ya no es el estado entero del árbol**, sino lo que
  el usuario cerró a mano; `sensor_expanded` es lo que abrió de entre lo
  que nace cerrado. Quien tuviera «Relojes · 16» abierta la verá cerrada
  una vez.
- **El enlace PCIe sí se esconde en una integrada de Intel** (antes «no se
  esconde nunca», por la Radeon 740M; para AMD sigue valiendo).
- **Un volcado se monta con `tools/montar_equipo.py`**, no con
  `SILUX_SYSROOT` a la carpeta: faltan las carpetas vacías. Las capturas del
  i5-10400 de la primera tanda (`antes/` y `despues/`) están hechas con la
  variable a pelo y por eso su Gráficos dice «Unidades de proceso —».
- **La barra lateral es unos 15 px más ancha** en compacto y en normal.
- **Las columnas de todas las tablas** quedan unos 3 px más juntas (de la
  primera tanda) y, con sitio, se separan hasta un tope.

**Capturas** en `~/Imágenes/silux-test/interfaz-casa/` (casa):

- `antes/` y `despues/`: la primera tanda.
- `tanda-A/`: cómo queda todo. `5800x3d-este-equipo/` e `i5-10400-volcado/`
  (montado con `montar_equipo.py`), en `oscuro-1440/`, `claro-1440/`,
  `compacto-900/` y `oscuro-2560/`, doce páginas, tras 65 muestras a 1 s y
  con las preferencias por omisión. Su «antes» es `despues/`.
- `comprobacion/`: las que se miraron para cada commit, entre ellas
  `dialogo-real-antes.png` y `dialogo-real-despues.png` (el diálogo abierto
  en la sesión de verdad), `appimage-barras.png` (los AppImage del CI sin
  iconos) y las `2k-antes-*` y `2k-despues-*`.

**El CI de la tanda A.** El primer intento (sobre `2d54c36`) falló en los
dos Python por `test_barra_lateral`: con DejaVu, la letra del runner, a
«Almacenamiento» le faltaban 6 px. Arreglado en `91512f7` (el relleno de la
lista no estaba en la cuenta) con un test que pone DejaVu a mano. En el
segundo (run 44176463759) pasó 3.14 y en 3.10 falló **un test que mide
rendimiento y no es de esta rama**: `test_benchmark.py::TestCargasNuevas::
test_todas_reparten_de_verdad_entre_hilos`, `compresion_dura` repartió ×1.76
y pide ×1.8. Relanzado solo ese trabajo, pasó. Es ruido del runner, pero es
la segunda vez que un test de medida falla solo: el umbral es cosa del
autor. Con Python 3.10 la suite pasa también aquí (`uv run --python 3.10`).
**Los dos AppImage de ese CI, abiertos con `--screenshot`: la barra lateral
sale con sus trece iconos y la marca**, en el normal y en el compatible
(`comprobacion/ci2-barras.png`). En los del CI anterior no salía ninguno
(`comprobacion/appimage-barras.png`).

**B, hecha y parada para revisar**: `docs/propuesta-datos.md` (`bd020e5`,
**sin empujar**). Solo documento. Maquetas en
`~/Imágenes/silux-test/datos-nuevos/` (casa), con su guion
`maquetas_datos.py`: Placa base, Sistema y la sección Dispositivos, con los
dos volcados, a 1440×900 y 2560×1440 (y `-entera` cuando la página no cabe).
Las del 5800X3D llevan datos leídos en esa máquina sin permisos; **las del
i5-10400 llevan valores de ejemplo en lo nuevo**, y lo dicen arriba: su
volcado no trae nada de eso.

**Punto 3 de la lista anterior, sin hacer**: estados vacíos de una ficha,
identificadores en monoespaciada y contraste de la paleta.

De «Para mirar esta noche en el 5800X3D» (más abajo) sigue sin mirarse lo
que pide reiniciar; lo que pide permisos lo vio el autor esa noche y de ahí
salió media tanda A.

## Sesión del 17, en la oficina

**Cómo quedan las ramas (17, tarde).** `ui-permisos` acaba aquí y pasa a
`master` con `--ff-only`, **sin etiqueta**: la 0.4.0 sigue «sin publicar» y
no se publica nada sin que lo diga el autor (está en CLAUDE.md). El rediseño
de la interfaz va en la rama **`interfaz`**, que sale de `ui-permisos`. Las
dos se empujan a mano por el autor: a la sesión de Claude el `git push` se lo
bloquea su control de permisos.

**Punto 1, hecho: los dos volcados del i5-10400, rehechos** (`f59e55f`).
Llevan `scaling_cur_freq` y el nombre de la gráfica grabado; el de reposo con
`no_turbo` a 1 y 2,9 GHz, el de carga con `no_turbo` a 0 y 4,0 GHz.

- Al rehacerlos salió **un fallo de privacidad de la herramienta**
  (`ef8d8c3`): el nombre de una interfaz puesta a mano (una WireGuard nueva
  en la oficina) se quedaba en `/proc/net/route` aunque su carpeta saliera
  como `interfaz1`. Arreglado antes de commitear ningún volcado; el nombre
  entra además en lo que la comprobación final busca en cada byte.
- **El volcado del `5800x3d` ya publicado está limpio de eso**: sus ocho
  interfaces (`enp5s0`, `enp6s0`, `docker0`, `virbr0`, `tailscale0`, un
  `br-…`, un `veth…`, `lo`) son todas nombres que pone el sistema, y son las
  mismas en `sys/class/net`, en `route`, en `if_inet6` y en lo grabado. No
  hay que reescribir la rama. Lo que desde la oficina no se puede repetir es
  la búsqueda byte a byte del nombre del equipo y las MAC de casa: esa la
  hizo la herramienta allí al volcarlo.
- **Las capturas de «antes» de la tanda** están en
  `~/Imágenes/silux-test/tanda-3/antes/` (oficina): este equipo y el volcado
  del 5800X3D montado con `SILUX_SYSROOT`, en oscuro a 1440×900 y en compacto
  a 900×680.

**Punto 2, hecho: la tercera tanda de `ui-permisos`**, un commit por cambio
con su test (el orden es el de la lista de abajo):

| Commit | Qué | Comprobado en |
|---|---|---|
| `013c098` | Placa base en AMD: «AMD X570», del nombre de la placa, no «FCH LPC Bridge» | volcado AMD e Intel |
| `4b38568` | `--anonimo`: cada MAC distinta, una falsa distinta | foto de prueba y página de Red |
| `f310582` | Sensores: las `acpitz` clavadas van apagadas y dicen lo que son (`Sensor.placeholder`); pie para las temperaturas sin nombre de `it87` y `gigabyte_wmi` | los dos volcados |
| `2d52ddf` | `ElidingLabel` no borra el tooltip de fuera (estaba en pendientes, y bloqueaba lo siguiente) | — |
| `85cd8cb` | Discos: temperatura, horas, escrito y vida con candado mientras no se lea el diagnóstico | volcado AMD |
| `6b912a6` | «NVMe», no «NVME» (`render.disk_bus`) | volcado AMD |
| `ca91750` | Diálogo de permisos: la orden en un campo de ancho fijo, una ruta por renglón, con «Copiar» | — |
| `d31428d` | Gráficas: llenan desde la derecha sobre un eje entero; la cifra del pico no tapa la curva | — |
| `e78f45a` | «Borrar el historial» vaciaba el archivo y no la tarjeta (F-M6) | — |
| `ebd1a31` | Rendimiento: botón «Borrar las de otra escala» | — |
| `3e36f9b` | «31.3 GB · Desconocido» en Inicio, y la guarda general: `tests/test_nada_en_bruto.py` | los tres volcados |

Capturas de antes y después en `~/Imágenes/silux-test/tanda-3/` (oficina):
`antes/` y `despues/`, cada una con `i5-10400-este-equipo/` y
`5800x3d-volcado/`, en `oscuro-1440/` y `compacto-900/`, más
`5800x3d-volcado/detalle/` con las páginas largas enteras y el diálogo.

### Para mirar esta noche en el 5800X3D

Lo que se arregló con su volcado y **no se ha visto en la pieza**:

1. **Con permisos concedidos**, Inicio › Memoria: tiene que decir
   «31.3 GB · DDR4-…» y no «Desconocido». El arreglo supone que el
   «Desconocido» venía del primer zócalo, vacío (tipo «Unknown» en la tabla
   del firmware); está probado con una tabla SMBIOS de prueba de cuatro
   zócalos y dos módulos, no con la de esa placa. **Si sigue saliendo mal,
   mandar `sudo dmidecode -t 17`.**
2. **Con permisos**, Almacenamiento: los candados de temperatura, horas,
   escrito y vida de cada disco se van y sale el dato; en los tres SATA, la
   temperatura que trae el SMART. Si un SATA se queda sin temperatura, el
   guion tiene que explicar lo de `drivetemp` al pasar el ratón.
3. Placa base: «Chipset: AMD X570», y «Identificación PCI: FCH LPC Bridge».
4. Sensores: las tres `acpitz` a 16.8 °C apagadas, con su renglón al pie; y
   que no cambien de valor nunca (si alguna se mueve, deja de marcarse sola,
   y entonces no era de relleno: apuntarlo).
5. `python3 -m silux.ui.app --anonimo`, Red: las dos tarjetas con dirección
   física distinta (`…:af` y `…:b0`).
6. Lo que ya estaba pendiente de esa máquina: el arranque con
   `amd_pstate=disable` y el boost apagado (más abajo).

Lo que la tanda deja a medias, apuntado en `docs/pendientes.md`:

- La **tabla de unidades** de Almacenamiento sigue con «—» en la temperatura
  de un SATA (ahora con su explicación al pasar el ratón): `Table` no sabe
  pintar un candado en una celda.
- En los **volcados**, todas las interfaces comparten dirección física:
  la iguala `volcar_equipo.py` al escribir. Numerarlas pide volver a volcar
  los tres.
- `--anonimo` da **la misma IPv4 y la misma IPv6** a todas las interfaces:
  es el mismo fallo que el de las MAC y no estaba en la lista.
- El campo **«Especificación»** de la página CPU enseña la cadena del
  procesador tal cual («Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz»). Es la
  única excepción de la guarda, a propósito; si no se quiere, es una línea.
- El **informe y el CLI** siguen dando fabricantes y chips en crudo.

**Punto 3, a medias: el CI de `ui-permisos` NO está lanzado.** Las capturas
sí. El empuje de la rama lo paró el control de permisos de la sesión de
Claude, así que hay commits locales por delante de `origin/ui-permisos`.
Para lanzarlo:

```bash
git push origin ui-permisos
gh workflow run appimage.yml --ref ui-permisos && gh run watch
```

En su lugar se pasó `tools/probar_en_minimo.py --container` y **no vale como
sustituto**: dentro del contenedor la suite corre como root, y fallan 44
tests que dependen de no serlo (los del aviso de permisos, el candado y las
notas, de antes y de esta tanda, y el de la carpeta personal de los
volcados). Es el F-M37 de pendientes. Lo que sí dice: los 1843 tests se
importan y corren en Python 3.10 con PySide6 6.11.3, y ninguno falla por el
lenguaje. La suite de aquí (3.14) está en verde en las dos pasadas.

**Punto 4, hecho: la 0.4.0 preparada** (`08f7c9e`): `silux/__init__.py`, la
línea del README y la entrada del CHANGELOG, como «sin publicar». Nada ha
pasado a `master`.

**Las propuestas, escritas y sin código**, a la espera de que el autor elija:

| Documento | Lo que hay que decidir |
|---|---|
| `docs/propuesta-interfaz.md` | Dirección visual (A «instrumento» o B «tablero») y logo (cuatro conceptos). Maquetas y logos en `~/Imágenes/silux-test/propuesta-interfaz/` (oficina), con los guiones que los generan |
| `docs/propuesta-precision.md` y `docs/comprobar.md` | Si se amplía el volcado con las salidas de otras herramientas, las invariantes, la procedencia y «Contribuir mi equipo». Trae discrepancias reales medidas en el i5-10400 |
| `docs/propuesta-benchmark.md` | Si `7z b` pasa a ser la cifra comparable y el benchmark propio se queda como prueba del equipo, con la escala congelada en la v6 |

Las dos últimas las escribieron agentes de Claude leyendo el repositorio y
midiendo en esta máquina; lo que no pudieron comprobar lo dicen al final de
cada una. **No están revisadas línea a línea.**

**La rama `interfaz` (17, última vuelta), parada para revisar.** Sale de
`master` y lleva el rediseño: la estructura de las nueve páginas, las barras
en tonos del acento, lo accionable en azul con el ámbar como acento por
omisión, «Qué hace esto» en lugar de «No volver a pedirla», y `--samples`
para capturar con las gráficas llenas. Y, tras la última revisión del autor:
el bloque «Ahora mismo» de Gráficos, la tabla de códecs con «✓» y «✗» y sin
fondo negro, **el estilo de la dirección A** (`value_font`, `ui/icons.py`,
la paleta de las maquetas) **y el logo `5-chaflan-ambar`** en el paquete, la
barra lateral, la imagen para compartir y el README. La lista de commits y
lo que queda sin hacer está arriba del todo en `docs/propuesta-interfaz.md`.
Sin empujar: el autor empuja a mano.

Capturas con el estilo en `~/Imágenes/silux-test/interfaz/estilo/` (oficina):
las nueve páginas en los dos equipos, y `claro/` con cuatro en tema claro.

**El AppImage con el logo nuevo no se ha construido aquí.** Lo construye el
CI al lanzarlo sobre `interfaz`; es donde se ve si los iconos de la barra
lateral salen dentro del paquete (se leen con el complemento `qsvg`, que ya
va dentro, y no con `QtSvg`, que no va).

Un test de la suite lee esta máquina y falla a veces cuando la suite corre
en paralelo con carga (`test_avisos.py::test_no_salta_ningun_aviso_en_reposo`):
solo, pasa. No es de esta rama.

## Estado y lo siguiente

**Las dos ramas están empujadas y con el CI en verde** (tests en 3.10 y 3.14,
y el AppImage): `fase-1` en `2f5cc9d` y `ui-permisos`, rebasada encima, en
`3a7dfaa` más el commit de este archivo, que solo toca documentación y no ha
pasado por el CI. **Nada ha pasado a `master`**, que sigue en `7609ea2`.

**La tercera tanda (hecha el 17, ver arriba)** salió de revisar el autor las capturas del AMD
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
- ~~Rehacer los dos volcados del i5-10400~~: hecho el 17 (`f59e55f`).

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
- ~~Rehacer los dos volcados del i5-10400 en la oficina~~: hecho el 17; el
  test de la caída (`39396a6`) ya corre contra los tres.

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
  `auto-cpufreq` apaga el turbo en reposo y lo enciende cuando hay carga;
  por eso hay `i5-10400` y `i5-10400-turbo`. **No lo enciende a un plazo
  fijo**: el 17 tardó más de 40 s con once hilos al 100 %, y otra vez lo
  encendió el propio volcado en reposo. No se espera un tiempo: se espera a
  ver `/sys/devices/system/cpu/intel_pstate/no_turbo` en el estado buscado y
  se comprueba después dentro del volcado. El segundo se hizo con once hilos
  ocupados (`python3 -c "while True: pass"`) y el turbo ya encendido.
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
