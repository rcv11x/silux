# Empaquetado: el suelo, el AppImage y las guardas

Qué exige el programa desde el código fuente, qué exige la copia que se
reparte y por qué, y cómo se comprueba. Las lecciones de esta zona están en
[lecciones.md](lecciones.md#empaquetado-y-ci).

## Los dos AppImage

| | normal | `-compat` |
|---|---|---|
| Python | 3.14, de python-build-standalone | 3.10, el de Ubuntu 22.04 |
| PySide6 | la última (6.12) | 6.9 (`<6.10`) |
| Procesador | x86-64-v2: Intel desde 2008, AMD desde 2011 | cualquier x86-64 |
| glibc | 2.34: RHEL 9, Ubuntu 22.04, Debian 12 y posteriores | 2.35: Ubuntu 22.04, Debian 12 y posteriores |
| Tamaño | 54 MB | 46 MB |

Los dos se construyen en un contenedor Ubuntu 22.04
(`tools/build_appimage.py --container`, con `--compat` para el segundo).
Sin contenedor salen con la glibc y el juego de instrucciones de quien los
compila: en CachyOS, x86-64-v3 y la glibc del mes.

La glibc la marca lo más exigente de lo que va dentro. En el normal son las
ruedas de PySide6 (`manylinux_2_34`); el intérprete solo pide 2.17. En el
compat es el propio intérprete: `hypot@GLIBC_2.35` del 3.10 de Ubuntu. Para
bajar cualquiera de los dos hace falta otra base, no una opción.

## El suelo del código: Python 3.10

`requires-python = ">=3.10"`, porque el compat lleva el 3.10 de Ubuntu 22.04
y su PySide6 6.9 es de antes del 3.14. Se desarrolla en 3.14, y lo que rompe
el suelo no se ve leyendo el código: `self.enterContext` es de 3.11 y se
llevó once tests en el CI, y hasta 3.12 un traceback perdía el texto de la
línea. `vermin -t=3.10` no cazaba ninguno de los dos.

Por eso el CI pasa la suite con las dos parejas que se reparten: 3.14 con la
PySide6 del normal y 3.10 con la del compat. `tests/test_empaquetado.py`
compara la matriz del CI con la tabla `PYTHON` del empaquetador. Antes de
empujar, lo mismo en local: `python3 tools/probar_en_minimo.py --container`.

El ayudante con permisos no corre con el Python del AppImage sino con el del
sistema: `pkexec` no ejecuta nada de un montaje `nosuid`, y root no puede
leer dentro de un montaje FUSE del usuario. Solo usa la biblioteca estándar
y arranca y contesta en 3.8 y 3.9 (RHEL 9 trae 3.9).

## El Python del normal

Viene de python-build-standalone, el mismo que instala `uv`. Dentro del
contenedor, la receta instala `uv` y pide `cpython-3.14-linux-x86_64-gnu`: la
variante x86-64 a secas, no la v2 ni la v3, para no exigir al procesador más
que Qt. Es un binario con la biblioteca estándar en C, OpenSSL, SQLite y
compañía enlazados dentro; de `lib-dynload` solo trae `_dbm` y `_tkinter`, y
se quitan.

Qué se gana:

- **Ningún cierre de PySide6 con Python viejo.** La 6.12.0 le quita una
  referencia a `None` en cada método que devuelve `void`; desde 3.12 `None`
  es inmortal, pero en 3.10 y 3.11 el proceso muere con «none_dealloc» al
  pintar la primera gráfica. Y con 6.11 en 3.10 y 3.11, Qt libera dos veces
  la llamada encolada con que un `QScrollBar` avisa de su rango, y la
  ventana se cierra sola al cambiar de forma (abajo).
- **La última PySide6**, con los arreglos de Qt de Wayland.
- **Un suelo de glibc más bajo**: 2.34 en vez de 2.35, así que entra RHEL 9.

Qué cuesta: el intérprete pesa 29 MB, frente a los 5,7 del 3.10 de Ubuntu,
porque lleva todo enlazado y conserva el código original junto al optimizado
con BOLT. El paquete pasa de 43 a 54 MB, contando los `.pyc`.

Dos comprobaciones en cada construcción, que paran si fallan:

- **TLS** (`comprobar_tls`): se arranca el Python del AppDir con su
  biblioteca y se le pide un contexto TLS. Sin `_ssl` no se abre ninguna URL
  `https://`, y el actualizador decía que no había red. Los certificados son
  de la máquina donde corre: con el AppImage nuevo, una petición a GitHub
  funcionó en CachyOS, Ubuntu 22.04 y 24.04, Debian 12, Arch, openSUSE
  Tumbleweed y Fedora, con el contexto por defecto y con el almacén del
  sistema.
- **Bytecode** (`compilar_bytecode`): los `.pyc` van dentro, compilados con el
  Python de dentro en modo `unchecked-hash`. El montaje es de solo lectura, y
  sin ellos cada arranque compilaba silux entero.

### Lo medido (5800X3D, 19 de noviembre de 2026)

Los dos del mismo commit, mediana de cinco a siete arranques con la caché de
disco caliente:

| | antes: 3.10 + 6.11 | después: 3.14 + 6.12 |
|---|---|---|
| Tamaño | 42,8 MB | 54,4 MB |
| `--version` | 295 ms | 139 ms |
| `--json` | 990 ms | 768 ms |
| Ventana hasta la captura de Inicio | 2154 ms | 1829 ms |

Lanzados como los lanza la gente, montados con FUSE, y alternando uno y otro
en cada vuelta. Sin los `.pyc`, el 3.14 arrancaba algo más despacio que el
3.10 (359 frente a 299 ms en `--version`): descomprimir un intérprete más
grande cuesta más de lo que gana. El compat también lleva los `.pyc` y pasa
de 42,4 a 45,6 MB.

## El cierre del `QScrollBar` (PySide6 6.11 en Python 3.10 y 3.11)

PySide6 6.11 con Python 3.10 o 3.11 revienta a veces con «Segmentation
fault» dentro del bucle de eventos: Qt libera dos veces la llamada encolada
con que un `QScrollBar` avisa de su rango a su `QAbstractScrollArea` (la pila
se sacó en la oficina de un volcado de memoria). Pasa cuando la ventana
cambia de forma: al dar permisos, al conectar un disco o un USB, o en los
tests, que pasan por la misma ventana fotos de equipos distintos.

**En la app de verdad, sí.** `tools/agitar_ventana.py` monta la ventana como
`main()`, con su bucle de eventos, le da cada 300 ms la foto de un equipo
distinto y cambia de página cada 70 ms. Seis ventanas, diez minutos, unas
2000 fotos cada una:

| Python + PySide6 | ventanas que revientan |
|---|---|
| 3.10 + 6.11.3 (la 0.3 y el borrador de la 0.4) | 3 de 6 |
| 3.11 + 6.11.3 | 3 de 6 |
| 3.14 + 6.11.3 | 0 de 6 |
| 3.10 + 6.9.3 (el compat) | 0 de 6 |
| 3.14 + 6.12.0 (el normal) | 0 de 6 |

Cambiando de página y de tamaño con las fotos de un solo equipo no revienta:
ocho ventanas diez minutos con 3.10 + 6.11.3 (90 000 cambios de página) y
cuatro con el Python y el Qt del AppImage nuevo. Quien tenga la 0.3 puede
verlo, pero en la app esos cambios de forma son pocos por sesión: en la
prueba, uno de cada unos 4000.

**En los tests**, la suite entera con `-n 4` en un contenedor como el runner
(Ubuntu 22.04, DejaVu, sin root): 3.10 + 6.11.3 revienta 6 vueltas de 8;
3.10 + 6.9.3, 0 de 7; 3.14 + 6.12.0, 1 de 12. Descartado, con 6.11: el
recolector en el hilo principal y no en los de Qt (lo empeoró, 4 de 4), que
Qt destruya las ventanas que sueltan los tests (3 de 5) y quitar los dos
tests que ponen un filtro de eventos de Python en toda la aplicación (1 de
5). Un reproductor mínimo con un `QScrollArea` cuyo rango cambia no
revienta con ninguna pareja.

Lo que falta: la causa, y un reproductor sin silux para bugreports.qt.io.

## Los techos de PySide6

Cada uno es por otra cosa.

**El `<6.10` del compat es de procesador.** Qt 6.10 pasó a compilarse con
`-march=x86-64-v2`, y no en rutas aparte que se eligen mirando la CPU, sino
dentro de funciones normales: `QString`, `QUtf8::convertToUnicode`,
`QPainterPath::quadTo`. En un procesador sin SSE4.1 eso es «Instrucción
ilegal» antes de pintar nada, y el aviso que Qt trae para ese caso no llega
a salir. x86-64-v2 es Nehalem (2008) en Intel y Bulldozer (2011) en AMD: deja
fuera los Core 2, los Athlon II y los Phenom II, justo la clase de equipo
cuyo dueño quiere saber qué lleva dentro. Lo descubrió un Athlon II X2 250u
ajeno.

**El normal no tiene techo**: se lleva la última que funciona a propósito.
Como lleva 3.14, los dos cierres de arriba no le alcanzan. El rango vive en
`RANGO_PYSIDE` y el CI lo pregunta con `--pyside-range`, así que alcanza
también a sus tests.

**`pyproject.toml` no le pone techo a PySide6**, con una excepción. No es su
trabajo decidir qué Qt corre en la máquina de otro, y quien instala desde el
código fuente casi siempre usa el PySide6 de su distribución, que no lee los
extras. La excepción es un cierre reproducido y limitado a donde se cae: el
extra `gui` pide `PySide6<6.11` con `python_version < '3.12'`: `<6.12` por lo
de `None` (2000 llamadas a `lineTo`: −2001 con 6.12.0, 0 con 6.11.3), y `<6.11` por
el cierre de arriba. Desde 3.12 las dos funcionan.
El `<6.10` del compat, que es de procesador y no de cierre, no entra.

## Las guardas del procesador

La guarda está en dos sitios, porque la pregunta se responde distinto según
de dónde se arranque. En el AppImage está en el AppRun, en shell, y es
**exacta**: el empaquetador lee el desensamblado de lo que acaba de meter y
le pasa las banderas que encontró. Desde el código fuente está en
`ui/guarda.py`, corre antes de importar Qt y es **una regla**, no una medida:
de 6.10 en adelante se pide x86-64-v2, porque leer el ELF del Qt del sistema
en cada arranque costaría más que arrancar. Como es una regla puede
equivocarse —una distribución es libre de compilar su 6.10 para x86-64 a
secas—, así que `SILUX_SIN_GUARDA=1` la desactiva. Las dos miran la misma
lista de cinco banderas y hay un test que no las deja separarse.

## La marca de construcción

Cada copia lleva dentro de qué commit salió: debajo de la versión, en
`--version` y en la cabecera del informe. Lo escribe el empaquetador en
`silux/_build.txt` —dentro del AppImage no hay repositorio al que preguntar— y
desde el código fuente se lee de git en vivo. Un `+` al final avisa de que esa
copia tenía cambios sin guardar. Nace de que las capturas que manda la gente no
decían de qué versión eran, y un fallo ya corregido se investigaba dos veces.

## Qué dice `pyproject.toml` y qué no

Su clasificador `Operating System :: POSIX :: Linux` es la casilla donde PyPI
archiva Linux, no una promesa: un BSD o un macOS son POSIX y ahí no hay
sysfs, ni hwmon, ni ioctl de DRM. Tampoco sabe nada de glibc. Desde el código
fuente los requisitos son Python 3.10, un kernel Linux (5.15 o posterior,
[kernel.md](kernel.md)) y PySide6 para la ventana; la glibc y el juego de
instrucciones son de la copia que se reparte, porque se los lleva dentro.
