# Lo que queda por arreglar, con su detalle

La tabla corta está en `CLAUDE.md`; aquí está cada punto con lo que se midió.
Este archivo es el registro completo: los informes de auditoría no viven en el
repositorio y no se puede contar con ellos. De las auditorías 1 a 3 no queda
otra cosa que lo apuntado aquí.

Lo que toca privilegios se describe por su clase de problema y dónde está, sin
los pasos para reproducirlo: este archivo es público.

## De dónde sale

Cinco auditorías. La quinta trajo además un plan por fases; su fase 0 —el
techo de PySide6, el CI construyendo en contenedor, el AppDir incompleto que
ya no se empaqueta, la suite aislada de la carpeta personal, la escala que no
puede desparejarse en verde, ninguna página que se salga a lo ancho, el techo
del `pyproject` para 3.10 y 3.11, la guarda del AppRun y la fuga del informe
anónimo— salió en la 0.3.0, y su fase 1 está en la rama `fase-1`. Lo que sigue
abierto de ella está en el último apartado de este archivo, con su código F-….

**La cuarta cubrió lo que las tres primeras no habían tocado**: el AppImage
construido de verdad y arrancado con pantalla, `ui/widgets.py` línea a línea, y
la interfaz usada con clics y arrastres inyectados a nivel de ventana. Once
fallos y diez observaciones, en un i5-10400 con Fedora 44, Wayland, SELinux en
enforcing y el PySide6 del paquete de la distribución. De paso confirmó con
herramienta propia dos cosas que este archivo afirma y que nadie había
comprobado desde fuera: que el AppImage exige glibc 2.35 y que quien la pide es
`hypot` del intérprete, y que el Qt 6.11 del paquete normal lleva SSE4.1 en
funciones sin despacho —`qFuzzyCompare`, `qt_from_latin1`— mientras el 6.9.3
del `--compat` solo lo lleva en rutas que se eligen mirando la CPU. La guarda
del AppRun corta de verdad, probada con un `/proc/cpuinfo` sin esas banderas.

## Lo que queda por arreglar

Sale de las cuatro primeras auditorías. **Nada de esto está arreglado**; lo
que sí se arregló —la escala del benchmark— es lo de la sección de arriba.

### Un dato, dos sitios que lo deciden, y uno lo hace mal

Es el mismo fallo repetido: existe una función que decide algo y alguien la
reimplementa al lado. La regla 1 lo dice para el formateo y vale igual para el
resto.

* `cli.py` · **baja** · `--json` vuelca todo sin anonimizar y sin avisar:
  seriales, IPv6 pública y puntos de montaje. Es la única salida sin aviso.
* `ui/pages/cpulive.py` · **media-alta** · compone los relojes a mano en vez de
  con `render.hz`, y no da lo mismo: 576 MHz sale como «0.58 GHz», 999 MHz como
  «1.00 GHz» y un bus de 100 MHz como «0.10 GHz».
* `ui/pages/graphics.py` · **baja** · lo mismo con la tasa de datos de la VRAM.
* `ui/pages/memory.py`, `ui/pages/battery.py` · **media** · cinco sitios
  redondean voltajes a dos decimales en vez de pasar por `render.volts`, que
  usa tres. Se pierde el decimal que distingue los escalones del VID.
* `providers/derived.py` · **media** · el tráfico de red del árbol de sensores
  va en potencias de 1024 y el de la página de Red en potencias de 1000: el
  mismo dato, el mismo instante, dos cifras que se llevan un 2,4 %.
* `spd.py` · **alta** · las latencias de DDR4 y las de los perfiles XMP se
  redondean al más cercano; solo la ruta de DDR5 redondea hacia arriba. Un
  módulo que necesita 13 875 ps con un ciclo de 625 sale como CL22 siendo CL23.

### Una bandera que entrega lo que no era y dice que todo fue bien

Es la lección que ya se arregló para los nombres de sección inexistentes, en
los casos que quedaron fuera.

* `ui/app.py` · **alta** · `--page` con una sección **oculta** —la de Batería en
  cualquier sobremesa— pasa la validación, devuelve 0, dice «captura guardada»
  y entrega el PNG de otra página. La validación corre antes del primer
  muestreo, cuando la sección todavía no se ha ocultado.
* `cli.py` · **baja** · `--report ''` ignora la bandera y hace el volcado normal
  sin decir nada.
* `cli.py` · **baja** · `--json`, `--sensors` y `--report` se pisan entre ellas
  en silencio, y `--with-identifiers` sin `--report` no hace nada y no avisa.
* `tools/build_appimage.py` · **baja** · `--container` solo reenvía `--compat`
  al build de dentro, así que `--keep` y `--appdir-only` se aceptan, se pierden
  y no se dice: el AppDir se borra igual. Para inspeccionar el árbol hay que
  extraer el AppImage ya hecho.

### Las primitivas de `widgets.py`

Seis fallos en el archivo que usan todas las páginas, y ninguno lo caza ningún
test: los que hay prueban la transición que sí ocurre. Los dos primeros son el
mismo caso, que además es el que menos se ve: un arreglo escrito dentro de una
rama que solo se recorre cuando algo cambia, y que por eso no alcanza al estado
con el que la cosa **nace**.

* `ui/widgets.py` · **media** · `StatTile.update_value` solo cambia la
  tipografía cuando el texto cambia, y la etiqueta nace con «—» a tamaño de
  cifra. Una ficha que nunca recibe un valor se queda con la raya gruesa toda
  la sesión, que es exactamente lo que la lección de los tres estados da por
  arreglado: en una UHD 630 sin permisos son cinco —uso, temperatura, consumo,
  VRAM ocupada y bus de memoria—, o sea la fila que parece tachada, que es
  justo la imagen que motivó aquel arreglo. Como está en `update_value`, solo
  alcanza a la ficha que tuvo un número y lo perdió.
* `ui/widgets.py` · **media-baja** · un `float` no finito en una gráfica
  —`_rango_redondo` hace `log10` de la amplitud— lanza una excepción en cada
  repintado, deja el `QPainter` abierto y al salir el proceso se va con un
  SIGSEGV sin traceback. Hoy no hay proveedor que produzca un infinito; es la
  primitiva la que no se defiende, y el fallo que causa no deja rastro.
* `ui/widgets.py` · **baja-media** · el globo «copiado» es un `QLabel` sin
  `WA_TransparentForMouseEvents` colocado a la derecha del valor, o sea encima
  de la columna siguiente cuando es una `Table`. En Almacenamiento: se copia la
  unidad, se va a copiar el modelo, y el segundo clic no hace nada durante 1,4 s
  y sin decirlo.
* `ui/widgets.py` · **baja** · la etiqueta es seleccionable con el ratón *y*
  copia al soltar, así que arrastrar para seleccionar «Intel» de un nombre de
  procesador copia el nombre entero y dice «copiado». Son dos gestos con el
  mismo botón y el segundo pisa al primero; el Ctrl+C de después sí copia la
  selección.
* `ui/widgets.py` · **baja** · `Table.set_rows` indexa fuera de rango si una
  fila trae más columnas que la anterior, y deja la celda sobrante con el valor
  viejo si trae menos. Hoy ninguna página cambia el número de columnas de una
  fila.

### Privilegios y privacidad

* `privileged/instalar.py` · **alta, condicionada** · escribe el ayudante y su
  acción de polkit sin comprobar que el destino no sea sustituible. La premisa
  está en su propio docstring y no se verifica en ninguna parte. No es
  explotable con `/usr/local` en su estado normal.
* `privileged/helper.py`, `privileged/client.py` · **media** · los dos topes de
  tamaño del protocolo se comprueban después de haber reservado la memoria, así
  que no limitan nada: el ayudante llega a 449 MB con un tope de 64 KB.
* `privileged/client.py` · **media** · el `timeout` de `request()` no acota la
  llamada: `select` se satisface con el primer byte y la lectura que viene
  detrás no tiene límite.
* `tools/comprobar_privacidad.py` · **media** · solo busca lo que identifica a
  la máquina donde corre, y es ciego a cualquier IPv6 —incluida la pública, que
  es el caso que motivó la marca del PNG—, a los números de serie y a todo dato
  de terceros, que es justo lo que llega en los informes ajenos. Además no está
  enganchado a ningún hook ni al CI.
* `ui/theme.py` · **media-baja** · cachea los iconos generados en un
  `/tmp/silux-icons` de nombre fijo y usa lo que encuentre sin comprobar quién
  lo puso.
* `data/org.silux.helper.policy.in` · **baja** · diverge de la plantilla que
  escribe `instalar.py` en `allow_inactive`, y nada vigila que no se separen;
  además no lo usa nadie. Ojo con lo que decide cada campo: una sesión por SSH
  no es local y la gobierna `allow_any`, que está en `auth_admin` en los dos.
  `allow_inactive` es para una sesión local que no está en primer plano, así
  que el comentario de `instalar.py` y el test que lo citan como el cerrojo del
  SSH afirman algo que esa línea no hace.
* `privileged/cargar_modulo.py` · **baja** · llama a `modprobe` sin ruta
  absoluta. Por `pkexec` da igual; por `sudo` depende de la configuración.

### Proveedores y modelo

* `providers/` (AMD) · **propuesta aplazada** · los límites de potencia de
  AMD (PPT, TDC, EDC) con `ryzen_smu`. El autor decidió el 18 de noviembre de
  2026 no hacerlo ahora: la tabla de `ryzen_smu` no está documentada, cambia
  con la BIOS y leerla manda órdenes al firmware, lo que haría que el ayudante
  dejara de solo leer. Si se retoma, en dos pasos: primero detectar el módulo
  sin cifras ni privilegios; después, experimental, con el mapa del 5800X3D
  verificado en la pieza. Todo, en `docs/propuesta-limites-amd.md`.

* `providers/hwmon.py` · **media-alta** · la clave de sensor no incluye de qué
  nodo `hwmon` viene, así que colisiona entre dos aparatos con el mismo chip:
  dos NVMe, dos gráficas del mismo fabricante, dos sockets. Con dos discos del
  mismo modelo ni el desambiguador del árbol los separa: una fila se queda
  vacía para siempre, el mín/máx es la unión de los dos y el CSV escribe el
  dato de uno bajo el nombre del otro.
* `spd.py` · **media** · `decode` revienta con `IndexError` si el chip devuelve
  menos de 384 bytes, y `read_all` no lo atrapa: se pierden todos los módulos,
  no solo el que vino corto. Esa ruta no la cubre ningún test.
* `providers/` · **media** · siete proveedores declaran `available()` y no
  `unavailable_reason()`, así que se callan cuando no pueden trabajar. Los dos
  que más se notan son los de red y almacenamiento: sus páginas se quedan
  vacías sin una línea que lo explique.
* `providers/rapl.py` · **media-baja** · en un contenedor afirma que la CPU no
  tiene contadores de energía sobre una que sí los tiene: distingue permiso de
  hardware, pero no el tercer caso, que es que el directorio esté ahí sin sus
  archivos.
* `providers/network.py` · **baja** · el tipo de interfaz se pinta crudo y
  mezcla los dos idiomas: `loopback`, `wifi`, `ethernet` en inglés y `puente`,
  `virtual`, `otro` en español, y ninguno está en los archivos de idioma.
* `providers/storage.py` · **baja** · el modelo de los discos SATA sale
  truncado a 16 caracteres, que es el campo de sysfs; el completo está sin
  permisos en `/dev/disk/by-id`.
* `collector.py` · **baja** · `_clone` reconstruye el borrador campo a campo y
  le faltan tres (`batteries`, `cpu_extra`, `memory_traffic`). Hoy no se pierde
  nada porque los llenan proveedores dinámicos; el día que uno se haga estático,
  su dato desaparece sin ruido.
* `render.py` · **baja** · dos módulos en canales distintos pueden salir los dos
  como «Canal A» en la misma pantalla que dice «doble canal».

### Interfaz y línea de órdenes

* `ui/pages/settings.py` · **propuesta, sin escribir** · no hay forma de quitar
  el ayudante instalado desde la interfaz: solo borrando sus dos archivos,
  que es la orden que da el diálogo «Qué hace esto». Un botón en Ajustes toca privilegios y va como
  propuesta aparte.
* `providers/cppc.py` · **media, sin comprobar** · con `acpi-cpufreq` el techo
  del silicio ya no sale inflado (4,96 GHz), pero el arreglo se hizo sin
  arrancar el equipo con ese driver: falta un volcado con
  `amd_pstate=disable`.

* `settings.py` · **media** · la ventana no arranca si `settings.json` es un
  JSON válido que no sea un objeto: el error se cuela entre las dos redes que
  ya hay. El CLI sí sigue funcionando, lo que despista.
* `cli.py` · **baja** · `--sensors` enseña las categorías sin traducir
  (`cat.temperature`); el informe sí las traduce.
* `cli.py` · **baja** · `--report -` no dice que ha omitido nada, y con archivo
  sí lo dice.
* `ui/app.py` · **baja** · cambiar el tema, la densidad, la letra o el acento
  reconstruye las páginas y las curvas de todas las gráficas vuelven a empezar
  (126 muestras acumuladas → 30). El `Tracker` de mín/máx sí sobrevive, que es
  para lo que se sacó a la ventana; el histórico que se ve, no. Quien está
  mirando un pico de temperatura y cambia a tema claro para verlo mejor, lo
  pierde.
* `ui/app.py` · **baja** · no hay forma de cambiar de sección con el teclado: la
  barra lateral es `NoFocus` y veinticinco tabuladores recorren tres widgets sin
  llegar nunca al menú. Solo por debajo de 620 px, donde aparece el desplegable
  compacto, se puede.
* `report.py` · **baja** · `_placa` recibe el parámetro `anonymous` y no lo usa.
* `ui/` · **baja** · `disk.pci_slot` y `net.vendor` están en el modelo y no se
  pintan en ninguna página.
* `db/lang/` · **baja** · cinco claves declaradas que ya no usa nadie;
  `gen_lang.py` las detecta y `--podar` las borra.
* `settings.py` · **baja** · el idioma guardado no se valida; el resto de
  preferencias sí se acotan.
* `registro.py` · **baja** · la hora del CSV va sin fecha, y las cabeceras de
  columna se repiten cuando un aparato publica varias etiquetas iguales.

### Fuera del programa

* `.github/workflows/appimage.yml` · **baja** · `contents: write` se concede a
  todo el workflow y no solo al paso que publica; la acción de terceros que
  crea la release está anclada a una etiqueta móvil y no a un SHA; y la
  comprobación de que el AppImage arranca es un `--help`, que no llega a cargar
  el plugin de plataforma.
* `tools/build_appimage.py` · **baja** · `appimagetool` se descarga el runtime
  de GitHub en cada construcción y nada fija el hash de lo que llega. Es la
  misma familia que la etiqueta móvil de aquí arriba: código de terceros que
  entra en el paquete que se reparte y que puede cambiar debajo sin que se
  note. De paso, construir sin red falla en el último paso.
* `tools/medir_referencia.py`, `history.py` · **hecho** · la cuenta que decide
  qué se puntúa estaba escrita en cuatro sitios.

## De la quinta auditoría

Lo que sigue abierto, con el código que lleva en la tabla de `CLAUDE.md`. Los
que ya estaban en los apartados de arriba (relojes de `cpulive`, voltajes,
hwmon, `spd.decode`, proveedores mudos, red en 1024, la caché de iconos, el
instalador, y F-M24 y F-M25 —los topes del protocolo del ayudante y el
`timeout` que no acota— en «Privilegios y privacidad») no se repiten.

### Altos

* **F-A2 · `spd.py`** · el XMP de DDR4 calcula el ciclo con la parte gruesa
  sola (`spd[offset+3] * 125`), sin la corrección fina. Un DDR4-3600 (555 ps)
  no se puede representar así y sale «XMP 1 3200». Además, las posiciones de
  los perfiles (`185, 220` con `- 176`) son las de XMP 1.x de DDR3, y el perfil
  2 de DDR4 caería dentro del primero (leído). No hay ningún volcado con XMP en
  `tests/fixtures`: **no se escribe sin uno real delante**. La mitad del
  redondeo de las latencias ya está arreglada en `fase-1`.

### Medios

* **F-M2 · `ui/widgets.py`** · además de nacer con la raya gruesa, el arreglo
  tampoco funciona al perder el dato: `style().unpolish()` restaura la fuente
  de la hoja y deshace el `setFont` de justo antes, así que de «5» a «—» queda
  `Muted` pero a 17 pt monoespaciada. No hay ni un test de `StatTile`.
* **F-M3 · `ui/sampler.py`** · cerrar la ventana durante un muestreo largo
  aborta el proceso con código 134: `stop()` espera 3 s, el `QThread` se
  destruye en marcha y `collector.close()` no llega a ejecutarse. Es lo que
  pasa con el diálogo de polkit abierto.
* **F-M5 · `ui/pages/performance.py`** · cambiar tema, densidad, letra,
  acento, idioma o unidades durante una prueba la mata sin decirlo: el hilo
  emite sobre la página destruida y el resultado no llega al historial. Le
  pasa lo mismo a la medida de memoria y a `SeguidorDeRecortes` (leído).
* **F-M7 · `ui/pages/performance.py`** · la carga de fondo máxima no se ve:
  `CONDITION_FIELDS` no incluye su fila e `InfoGrid.set` descarta en silencio
  una fila que no existe.
* **F-M8 · varios** · texto en español fijo con la interfaz en inglés: las
  cargas del benchmark, «semana N de AAAA» de `spd.py` y `edid.py` (que además
  guardan texto ya formateado en el modelo), «fija en … GHz», «Cargando…»,
  «Informe», «captura guardada en», y en proveedores «Bajada/Subida»,
  «BIOS heredada», «UEFI (64 bits)», «GLSL …», «Gráfica N». El test de cadenas
  sueltas no ve f-strings, `setText` ni texto que viene de otro módulo.
* **F-M9 · `ui/widgets.py`** · las 1299 etiquetas seleccionables con el ratón
  cuestan 22 MB de RSS (151 MB frente a 129 sin selección): cada una crea su
  `QTextDocument`. Quitar la selección arregla además que seleccionar copie el
  valor entero.
* **F-M12 · `settings.py`** · además del JSON que no es objeto: un solo campo
  de tipo erróneo tira al valor por defecto todas las preferencias, y
  `"fluid_charts": "false"` se lee como `True`.
* **F-M16 · `providers/spd_modules.py`** · `_merge` casa por referencia y, si
  no, «el primero pendiente» en una sola pasada: si la referencia del zócalo A
  no casa, A se lleva el SPD de B y B el de A, con su velocidad catalogada y su
  aviso. Encaja con el «solo sale el módulo A» del ThinkCentre M80q.
* **F-M17 · `providers/drm.py`** · sin `pci.ids`, una AMD dedicada sin
  «radeon» en el nombre recibe el de la integrada de la CPU: una Navi 33 sale
  «Radeon 780M». No se comprueba que sea integrada.
* **F-M18 · `smart.py`** · el atributo 202 cuenta como vida gastada sin mirar
  si el disco es mecánico, y en un WD es otro atributo: sale vida al 200 %.
* **F-M19 · `providers/storage.py`** · el estado de SMART va por nombre de
  dispositivo: un USB enchufado como `sdb` hereda 30 s el SMART del anterior,
  o se queda sin pedirlo.
* **F-M20 · `gpumetrics.py`, `nvml.py`, `providers/derived.py`** · `if v` con
  relojes y contadores: 0 MHz (GFXOFF) o 0 bytes llegan como `None`.
* **F-M21 · `providers/drm.py`** · `_pmu_ok` no vuelve nunca a `False`: si el
  ayudante muere, el aviso de Intel pasa a gris «no existe» y desaparece el
  botón (leído).
* **F-M26 · `privileged/client.py`** · tras una respuesta ilegible o que no es
  un objeto no se cierra el canal, y desde ahí cada respuesta llega con una
  petición de retraso.
* **F-M27 · `privileged/helper.py`** · la cadencia de lectura de RAPL y del MSR
  de energía por núcleo la decide el cliente y no el ayudante, que es el canal
  lateral por el que el kernel cerró `energy_uj`. La lista blanca de MSR tiene
  además nueve registros que no se usan. **Va como propuesta antes que
  código.**
* **F-M30 · `tools/comprobar_privacidad.py`** · además de ser ciego a IPv6 y
  seriales: usa rutas relativas al directorio actual, y lanzado desde otro
  sitio da su visto bueno sin haber mirado nada.
* **F-M31 · `report.py`** · los zócalos vacíos salen como módulos
  («DIMM_A1: 0 B   MT/s») y en una integrada «Memoria: — — · — · —».
* **F-M32 · `cli.py`** · el valor de un sensor se formatea de tres maneras
  —`--sensors`, el volcado y `render.sensor_value`—, con decimales distintos.
* **F-M37 · `tools/probar_en_minimo.py`** · anuncia «la suite no pasa» ante
  cualquier código que no sea 0 o 2 (apt sin red, pip, podman), y su
  comentario «lo mismo que el CI» es falso: dentro del contenedor corre como
  root.

### Bajos

* El ayudante muere con UTF-8 inválido y, en 3.10, con un JSON muy anidado;
  `DISK_NAME` acepta un salto de línea final (hay que usar `fullmatch`); `cpu:
  true` cuenta como CPU 1; `cargar_modulo` admite `i2c-dev`, que no es de solo
  lectura.
* `hwmon` lanza `modinfo` en cada muestreo; `pci.ids` sin caché; el estado
  anterior de red y discos crece sin límite con cada `veth`; el hostname
  `(none)` llega crudo; las salidas de vídeo no se actualizan al enchufar un
  monitor; `power_supply` no filtra por `scope`; `alarm_level` dice «alto»
  también por debajo del mínimo.
* «DDR4-2667» en Inicio, la tarjeta y el informe frente a 2666 en Memoria; al
  ordenar el árbol ascendente las celdas vacías salen primero; el CSV pierde
  precisión con `{v:g}`; un fallo al cargar un driver se titula «Se ha parado
  la grabación».
* Cancelar no interrumpe una medida en curso (`time.sleep` de hasta 1800 s);
  dos analizadores de `/proc/stat` con distinto «inactivo»; `mprotect` sin
  `argtypes`; `history.save` con un `.tmp` fijo y sin cerrojo.
* El paso de tests del CI solo busca `FAIL/ERROR/Ran`: un aborto sale sin la
  causa.


## De la tercera tanda de `ui-permisos` (17 de noviembre de 2026)

Lo que salió al hacerla y no entraba en ella:

* `ui/widgets.py`, `ui/pages/storage.py` · **media-baja** · `Table` solo
  sabe de texto, así que en la tabla de unidades la temperatura de un disco
  SATA sin `drivetemp` sigue con «—» aunque la ficha de ese mismo disco lleve
  candado. La celda ya explica por qué al pasar el ratón
  (`Table.set_cell_tooltip`); pintarle el candado es cosa de cuando se parta
  `widgets.py`.
* `privacidad.py` · **media-baja** · `anonimizar` da `192.0.2.11` y
  `2001:db8::11` a todas las interfaces. Es el mismo fallo que el de las
  direcciones físicas (arreglado en `4b38568`): dos tarjetas con la misma IP
  delatan que la captura está tocada.
* `tools/volcar_equipo.py` · **media-baja** · escribe `privacidad.MAC` en
  todas las interfaces, así que en un volcado las tarjetas comparten
  dirección física. Numerarlas como hace ya `anonimizar` pide volver a volcar
  los tres equipos, y que la comprobación final acepte la serie entera.
* `providers/dmi.py` · **baja** · la lista de chipsets de AMD
  (`_CHIPSETS_AMD`) es cerrada a propósito y hay que añadirle cada generación
  nueva. Solo está vista con una placa, la X570 AORUS ELITE.
* `providers/hwmon.py` · **baja** · los valores de relleno de `acpitz`
  (`VALORES_DE_RELLENO`: 16.8, 27.8 y 29.8 °C) son los tres que se conocen;
  una placa que devuelva otro número fijo no se marca.

## De la noche del 17 al 18 de noviembre de 2026 (rama `interfaz`)

- **`test_avisos.py::test_no_salta_ningun_aviso_en_reposo`** lee la máquina
  y falla a veces con la suite en paralelo. (El otro test de medida que
  fallaba solo, el del reparto entre hilos del benchmark, se arregló el 18:
  ahora mide tiempo de CPU y no rendimiento; ver `docs/lecciones.md`.)
- **El máximo oficial de memoria en AMD** (`silux/db/memory_limits.json`).
  La tabla solo tiene Intel de sobremesa de las generaciones 10 y 11: en AMD
  el máximo no es por modelo, depende de los módulos. La ficha del 5800X3D
  dice DDR4-3200 con dos módulos de uno o dos rangos, 2933 con cuatro de un
  rango y 2667 con cuatro de dos. Pide una fila con esa forma y leer los
  rangos (SPD o SMBIOS). Las generaciones 12 a 14 de Intel tienen dos cifras
  por tipo de memoria (DDR4 y DDR5) y caben en el formato de ahora.
- **Los motivos de limitación de una Intel reciente** (`gt/gt0/throttle_reason_*`
  de `i915`) se leen, pero escritos con la documentación del kernel: la UHD
  630 de la oficina no los publica, y en ella «Estado» se esconde y se dice al
  pie. Hay que verlos en una Iris Xe o una Arc. Lo mismo las rutas de `xe`
  para RP0, RP1 y RPn (`freq0/rp0_freq`, `rpe_freq`, `rpn_freq`).
- **El CI no mira si el AppImage pinta sus iconos.** Se comprobó a mano
  abriendo los dos con `--screenshot`. Un paso que lo haga y mire un píxel
  de la barra lateral lo habría cazado.
- **`tests/test_al_momento.py` no cubre Batería**: ningún volcado tiene una.
