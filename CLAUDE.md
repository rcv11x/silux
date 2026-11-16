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
python3 tools/gen_lang.py --write      # poner al día los archivos de idioma
python3 tools/medir_referencia.py      # rehacer la escala de puntuación
python3 tools/anadir_puntuacion.py INFORMES  # sumar medidas ajenas a la tabla
python3 tools/install_desktop.py       # icono y entrada de menú
python3 tools/volcar_gpu.py            # lo que publica el kernel de cada gráfica
python3 tools/comprobar_privacidad.py  # antes de publicar nada
python3 tools/build_appimage.py --container   # el AppImage que se reparte
python3 tools/probar_en_minimo.py --container # la suite en el Python del suelo
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .
```

Los tests son **1527** y tardan cerca de dos minutos. Si sale bastante
menos, falta algo por recoger.

Que pasen aquí no dice que pasen en el mínimo: el suelo es Python 3.10 y el
CI lleva matriz con las dos puntas. Por qué, qué exige el AppImage que se
reparte, de dónde salen los techos de PySide6 y cómo funcionan las dos guardas
del procesador está en **[docs/empaquetado.md](docs/empaquetado.md)**.

**Un clic en un valor lo copia**, en las fichas y en las tablas. Se copia el
texto entero y no el que se ve: la fila que no cabe y sale con puntos
suspensivos es justo la que hace falta copiar. Un guion no se copia, porque es
la marca de un dato que falta.

Capturas sin pantalla, siempre en `"$(xdg-user-dir PICTURES)/silux-test/"` y
nunca dentro del repositorio:

```bash
mkdir -p "$(xdg-user-dir PICTURES)/silux-test"
XDG_CONFIG_HOME="$(mktemp -d)" QT_QPA_PLATFORM=offscreen \
  python3 -m silux.ui.app --screenshot "$(xdg-user-dir PICTURES)/silux-test/sensores.png" \
  --page Sensores --dark --compact --size 900x680
```

Acepta además `--accent` y `--font-scale`. **El `XDG_CONFIG_HOME` temporal no
es opcional** mientras siga abierto F-M1 de la quinta auditoría: al cerrar, la
ventana guarda en `settings.json` lo que se le haya forzado por la línea de
órdenes —tema, densidad, acento, letra y tamaño—, así que una captura sin él
cambia las preferencias de quien la saca.

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
├─ cli.py          volcado en terminal, JSON, sensores e informe
├─ settings.py     preferencias del usuario en ~/.config/silux
├─ tracking.py     mínimos, máximos y medias por sensor
├─ rawcpuid.py     CPUID desde Python, sin root (mmap + ctypes)
├─ gpuapi.py       OpenGL, Vulkan, OpenCL y VA-API por ctypes, en otro proceso
├─ amdgpu.py       ioctl DRM: tipo de VRAM, bus, unidades, ROP
├─ i915.py         ioctl DRM: las unidades de ejecución de una Intel
├─ edid.py         la chapa del monitor, con sus extensiones CTA-861
├─ report.py       informe en Markdown para reportar fallos
├─ gpumetrics.py   telemetría del firmware AMD: por qué se frena la tarjeta
├─ nvml.py         NVIDIA propietaria, que no publica nada en sysfs
├─ features.py     tabla declarativa de banderas de CPUID
├─ pciids.py       nombres de dispositivos PCI desde la base del sistema
├─ spd.py          decodifica el chip de identificación de la RAM (DDR4 y DDR5)
├─ smart.py        interpreta el diagnóstico de los discos, sin privilegios
├─ benchmark.py    prueba de CPU que reporta en qué condiciones midió
├─ membench.py     lo que la memoria mueve de verdad, medido en otro proceso
├─ history.py      historial de pruebas de este equipo
├─ score.py        la puntuación comparable entre equipos, y su escala
├─ privacidad.py   qué se omite de un informe público y qué no
├─ ui/tarjeta.py  la imagen del equipo para pegar en un chat, ya anonimizada
├─ ui/guarda.py   para antes de Qt: si el procesador no da, lo dice y no abre
├─ i18n.py        el idioma de la interfaz; el original es el español
├─ throttling.py  desde cuándo lleva frenándose algo, y por qué
├─ registro.py    graba la sesión a un CSV, fila a fila
├─ providers/      una fuente cada uno; ninguno conoce a los demás.
│                  `msr_voltage.py` pregunta el voltaje del núcleo al propio
│                  procesador, que es el único sitio donde está en cualquier
│                  equipo: los sensores de placa lo publican sin etiquetar.
│                  `imc.py` lee del PMU del uncore cuánto tráfico mueve la
│                  memoria ahora mismo, que es un sensor y no una prueba
├─ privileged/     ayudante root mínimo (helper.py) + cliente + SMBIOS.
│                  Lee DMI, MSR, el SMART de los discos y dos PMU: el de la
│                  iGPU y el del controlador de memoria. Del PMU solo cuenta;
│                  el cliente pide una familia y nunca un número de evento.
│                  instalar.py le da su acción de polkit para no pedir la
│                  contraseña en cada arranque; cargar_modulo.py carga un
│                  driver de sensores de una lista blanca fija
├─ db/             cpu_ids.json (generado; incluye la tabla de MIDR de ARM) +
│                  sockets.json y families.json (curados a mano; el segundo
│                  cubre lo que libcpuid no tiene)
└─ ui/             tema, hilo de muestreo, widgets, una página por sección.
                   `widgets.py` son las primitivas —las que usan varias
                   páginas—; el widget que solo monta una vive en su
                   propio módulo (`sensortree`, `corematrix`, `cachemap`,
                   `scorebar`), porque mezclados no se puede mirar la
                   lista antes de escribir uno nuevo
```

El orden de los proveedores en `collector.py` importa y está comentado ahí.

`providers/cppc.py` saca de ACPI CPPC, además de los relojes, **lo bien que
salió cada núcleo de la oblea**: los núcleos de una misma pieza no son
iguales, el firmware lo publica y el planificador lo usa para mandar ahí el
trabajo de un hilo suelto. Ryzen Master lo enseña en Windows con estrellitas;
en Linux no lo enseñaba nadie. Sale en la rejilla de núcleos de la página de
CPU y en el volcado del terminal.

## Estado

Terminadas las trece: **Inicio, CPU, Cachés, Placa base, Memoria, Gráficos,
Almacenamiento, Red, Batería, Sistema, Rendimiento, Sensores, Ajustes**. La de
Batería solo aparece en los equipos que tienen una: un sobremesa no va a tener
nunca, así que dejarla puesta para decirlo sería ruido permanente en el menú.

Qué sale de cada sección, qué se ha validado contra qué pieza y qué queda
pendiente por plataforma está en **[docs/hardware-validado.md](docs/hardware-validado.md)**;
la escala del benchmark y la medida de la memoria, en
**[docs/benchmark.md](docs/benchmark.md)**.

## Dónde está cada cosa ahora mismo

**Los informes de auditoría viven fuera del repositorio**, en la carpeta de
encima: `../auditoria-fase-4.md` y `-5.md`. De las fases 1 a 3 no queda el
informe, solo lo que se apuntó aquí. Aquí abajo va el índice: qué falta, dónde
y cómo de grave. La quinta lleva además su propio plan por fases;
la fase 0 de ese plan está hecha en la rama `fase-0` —el techo de PySide6, el
CI construyendo en contenedor, el AppDir incompleto que ya no se empaqueta, la
suite aislada de la carpeta personal, la escala que no puede desparejarse en
verde y ninguna página que se salga a lo ancho en compacto—, y detrás de ella
el techo de PySide6 en el `pyproject` para 3.10 y 3.11 y la guarda del AppRun,
que ya deja pasar el CLI, recomienda `$APPIMAGE` y elige idioma como POSIX
—`LC_ALL`, `LC_MESSAGES`, `LANG`—. Y antes de publicar la 0.3.0, la fuga
del informe anónimo (F-A1, F-M29): el informe pasa por
`privacidad.anonimizar`, que ahora sustituye las interfaces con nombre puesto
a mano, busca el hostname entero y sin mayúsculas, y tapa los puntos de
montaje y los números de serie de monitores y baterías. El resto de sus
hallazgos todavía no ha entrado en este índice.
Los pasos para reproducir cada cosa se quedan en los informes a propósito —el
del enlace simbólico del instalador es una receta y este archivo es público.

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
* `ui/widgets.py` · **media-baja** · `ElidingLabel._refresh` termina poniendo su
  propio tooltip, y corre en cada `resizeEvent`, así que borra el que le pasaron
  desde fuera. De 268 tooltips en nueve muestreos, 60 desaparecen con un solo
  redimensionado; los de la ficha de CPU vuelven al siguiente porque la página
  los repone, y los tres de cada módulo de memoria —«Chips», «Capacidad»,
  «Catalogado a»— no vuelven nunca, porque se ponen una sola vez.
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
* `providers/derived.py` · **baja** · «Core #0», «Core #1»… a pelo, 24 filas
  de un árbol de sensores en español, y en el mismo archivo donde el sensor de
  al lado va con `_("sensor.total")`. No es un dato del equipo: `coretemp`
  etiqueta «Core 0», sin almohadilla. `sensor.core` («Núcleo») ya existe en los
  dos idiomas. Es la misma familia que el `kind` de red de aquí arriba.
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

## Cosas que ya se probaron y no funcionaron

Están en **[docs/lecciones.md](docs/lecciones.md)**, agrupadas por tema. Antes
de tocar una zona, se lee su apartado.

## El idioma

La interfaz va en **español neutro**: `video` y no «vídeo», `archivo` y no
«fichero», `dispositivo` y no «aparato», `equipo` y no «ordenador». Nueve de
cada diez hispanohablantes están al otro lado del Atlántico y no hay motivo
para cerrarles la puerta por una tilde.

Los comentarios del código no siguen esa regla y van en el español del autor:
no los ve nadie desde la ventana y no se traducen.

**Las claves son símbolos** —`cpu.card.clocks`—, así que el español es un
idioma más y vive en `db/lang/es.json`. Retocar una frase en castellano es
cambiar un valor, no una clave: la traducción inglesa no se descuelga.

Lo malo conocido de las claves simbólicas —que una traducción incompleta
enseñe `cpu.card.clocks` en pantalla— aquí no pasa, porque `_()` tiene tres
escalones: el idioma pedido, el español y por último la clave. Un `en.json` a
medias enseña español entre inglés, que se lee; la clave solo asoma cuando la
frase no está escrita en ninguna de las dos lenguas, y entonces es justo lo
que hace falta ver.

Las categorías del árbol de sensores también son claves. Esos nombres
—«Temperaturas», «Ventiladores»— los inventa el programa para agrupar y no
salen del kernel, así que son interfaz: la frontera no está en de dónde viene
el dato sino en quién escribió la palabra.

Los nombres de sección son claves (`nav.sensors`), así que `select_section`
acepta tres cosas: lo que se ve, la clave y el nombre en español. Sin lo
tercero, `--page Sensores` dejaría de funcionar en cuanto alguien se pusiera
la interfaz en inglés.

Se eligió JSON sobre gettext por quién escribe los archivos: un `.po` hay que
compilarlo a binario antes de que sirva, y esto se corrige desde el navegador
de GitHub y se lee en el diff línea a línea.

**Los proveedores también traducen, pero solo lo que se inventan**: el aviso
que explica por qué falta un dato, el nombre que le ponen a un sensor —«Punto
caliente» donde amdgpu dice `junction`—, la función de un motor gráfico. Lo
que leen del equipo pasa entero y sin tocar. La línea se comprueba sin
ejecutar nada: a `_()` solo puede llegar un literal escrito en el archivo o
una variable que se rastree hasta una tabla declarada ahí mismo. Un
`_(entry["label"])` traduciría un dato, y eso rompe la detección de una
gráfica en cuanto alguien se pone la interfaz en inglés.

**Fuera de la interfaz, las claves no se traducen solas.** El informe agrupa
los sensores por categoría, y esas categorías son claves porque el nombre lo
inventa el programa. Como `report.py` no importaba nada de `i18n`, salían
crudas: «cat.temperature (2), cat.power (2)» en el archivo que se le pide a
quien reporta un fallo. Y la traducción que necesita ahí es `en_español` y no
`_()`: el informe es castellano fijo —«Procesador», «Placa base»—, así que con
la función normal, el de alguien con la interfaz en inglés mezclaría los dos
idiomas en la misma página.

**Nada de `_()` en una constante de módulo.** Se resuelve al importar, cuando
todavía no se sabe qué idioma quiere nadie, así que se queda con el castellano
para toda la sesión; y como quien monta la ficha vuelve a pasar cada entrada
por `_()`, la segunda llamada recibe «Uso» —que no es una clave— y devuelve
«Uso». Así salía la columna «LEYENDO» en medio de una tabla de discos en
inglés: la tupla llevaba once claves y una traducción ya hecha, y era la única
que no cambiaba de idioma. Hay un test que lo vigila.

La interfaz está entera en los dos idiomas: 957 claves, ninguna sin traducir,
y trece de ellas ya no las usa nadie (`gen_lang.py` solo ve cinco, ver lo
pendiente).
Hay un test que recorre el árbol de sintaxis de cada página buscando
constructores de widget con una cadena española a pelo, porque eso es lo que
no se ve hasta abrir la pantalla en el otro idioma y ningún test normal lo
nota. **Descubre los archivos solo**: con la lista escrita a mano se quedaron
cinco páginas enteras sin traducir y el test seguía en verde, porque no las
miraba.

**`_` no se puede usar de descarte.** `for _ in range(10)` o `ruta, _ =
dialogo()` es lo idiomático en Python para decir «esto no me importa», y aquí
sustituye la función de traducción dentro de esa función: la siguiente llamada
revienta con «'int' object is not callable», un error que no menciona ni el
idioma ni la traducción. Y lo hace meses después, cuando alguien añade una
cadena traducible en ese mismo método. Hay un test que lo vigila.

`tools/gen_lang.py` los mantiene al día. Solo recoge lo que ya está envuelto
en `_()`: adivinar qué cadena del código es texto de interfaz sale mal en
silencio, y un `"amdgpu"` traducido rompe la detección de la gráfica sin que
nadie lo relacione con el idioma. **Nada de `providers/` se traduce**: lo que
sale de ahí es el dato del equipo, no una frase del programa.

## Al reportar un fallo

`python3 -m silux.cli --report informe.md` recoge el hardware detectado y, sobre
todo, la sección de diagnóstico: qué fuentes respondieron, qué módulos del
kernel faltan y qué datos no se pudieron leer. Es lo primero que hay que pedir
cuando alguien dice que algo no le sale.

Desde el AppImage es `./silux-x86_64.AppImage --report informe.md`: el punto de
entrada reparte entre la interfaz y el volcado en terminal según con qué se le
llame, porque quien lo usa así no tiene otra forma de sacarlo.

Si hay alguna prueba de rendimiento medida con la escala vigente, el informe
lleva también su puntuación y las condiciones en que se tomó. Es lo que permite
juntar medidas de piezas que no están a mano: sin eso, quien manda un informe
manda su hardware pero no lo que rinde, y la tabla de puntuaciones no se llena
nunca.

Omite por defecto el nombre del equipo, las IP, las MAC y los números de serie
—está pensado para pegarlo en un issue público— y lo dice al terminar. Con
`--with-identifiers` se incluyen. Hay tests que vigilan que no se cuele nada.

## Al trabajar en este repositorio

**Los commits siguen Conventional Commits, en español.** La primera línea es
`tipo(zona): descripción`: el tipo es uno de los del estándar, sin traducir
—`fix`, `feat`, `test`, `docs`, `refactor`, `perf`, `build`, `ci`, `chore`—,
la zona es el módulo o la carpeta que se toca —`spd`, `providers/hwmon`,
`ui/widgets`, `privileged`, `bench`, `report`, `cli`, `i18n`, `appimage`, `ci`,
`tests`, `claude`— y la descripción va en minúscula y sin punto final. El
cuerpo explica el porqué del cambio: qué fallaba, cómo se vio y qué se
comprobó, incluido que el test se vio fallar antes del arreglo. El autor es el
del repositorio, y cuando el commit se escribe con Claude lleva al final la
línea `Co-Authored-By: Claude …` que corresponda al modelo.

```
fix(ui/widgets): la ficha que nace sin dato pinta el guion pequeño

Cuerpo: el porqué.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

**Nunca se empuja sin preguntar.** Commitear en local es reversible; publicar
no, y menos con el CI atado a cada empujón a master. Se pregunta siempre,
aunque el commit anterior se haya empujado hace un minuto.

**Lo que toca privilegios se propone antes de escribirlo.** Si el cambio roza
los permisos, la seguridad o un estado que sobrevive entre máquinas o entre
versiones, primero va la propuesta —medida, con lo que se ha comprobado— y se
espera respuesta. No se escribe código y luego se pregunta: para cuando hay un
parche delante, la conversación ya empieza discutiendo el parche en vez de si
el enfoque es el correcto.

**Una comprobación que nadie ha visto fallar no es una comprobación.** Toda
guarda nueva se ejecuta contra el caso concreto que pretende cazar, y se
enseña que lo caza. Vale para los tests y vale para las validaciones del
programa: si solo se ha visto pasar, lo único demostrado es que no estorba.

**Y si depende de que alguien se acuerde de subir un número, tampoco lo es.**
El ayudante privilegiado llevaba su `VERSION` para que el cliente detectara una
copia instalada que se hubiera quedado atrás, y habría dejado pasar los tres
arreglos de escalada de privilegios del 31 de agosto de 2026: ninguno de los
tres tocó ese número, porque ninguno cambiaba el contrato. Se compara el
contenido, que no se olvida de cambiar. Un número hay que acordarse de subirlo
justo el día que más prisa hay.

**El commit del CLAUDE.md es el último antes de empujar.** Nunca uno
intermedio: hoy se hizo en `096ace0` y el commit siguiente lo dejó atrasado
otra vez, con una fila de la ficha de procesador que el archivo no mencionaba
y dos cifras que ya no cuadraban. Se escribe cuando ya no va a entrar nada más.

**Un dato nuevo no está terminado hasta que hay un test que lo ve en pantalla**,
montando la página de verdad y comprobando la celda. Los 1352 tests pasaban con
el voltaje del núcleo medido, guardado en el modelo y sin ninguna fila donde
pintarlo: probaban el proveedor, la interpretación de los bits y el reparto de
avisos, y ninguno miraba si eso se veía. Probar la fuente no es probar que se
ve, y lo que no se ve no está hecho.

**Un commit por cambio lógico.** Un cambio lógico es una causa, no un archivo
ni un arreglo: cuatro correcciones que salen de la misma causa son un commit,
no cuatro. El arreglo y el test que lo vigila van en el mismo commit, y lo que
solo mueve código va en uno propio, para que `git log --follow` siga sirviendo.
La suite queda en verde entre uno y otro.

## Fuentes de datos y licencias

- [libcpuid](https://github.com/anrieff/libcpuid) — BSD-2 — tablas de identificación de CPU
- [CPU-X](https://github.com/TheTumultuousUnicornOfDarkness/CPU-X) — GPL-3.0 — tabla de sockets
- `pci.ids` del sistema (paquete hwdata) — nombres de dispositivos PCI
