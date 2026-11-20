# Lo que falta

Todo lo pendiente de Silux, en una lista, por zonas. Cada punto dice dónde
está, cuánto importa y qué pasa. Los que llevan un código (F-…) salieron de
una auditoría del código y se buscan por él.

Lo que toca privilegios se describe por su clase de problema y dónde está,
sin los pasos para reproducirlo: este archivo es público.

## Lo más importante


* **El cierre del `QScrollBar` en los tests** · Qt libera dos veces la
  llamada encolada con que un `QScrollBar` avisa de su rango, y el proceso
  muere. Con PySide6 6.11 en Python 3.10 o 3.11 pasa también en la app de
  verdad al cambiar de forma la ventana (dar permisos, conectar un disco):
  `tools/agitar_ventana.py` tumba tres ventanas de seis en diez minutos. Los
  AppImage no lo llevan y el `pyproject` pide `<6.11` en Python < 3.12. En
  los tests sale todavía, raro, con 3.14 + 6.12.0: una vuelta de 32 de la
  suite entera en un contenedor. Falta la causa y un reproductor sin Silux
  para bugreports.qt.io. Lo descartado y cómo se mide, en
  [empaquetado.md](empaquetado.md#el-cierre-del-qscrollbar-pyside6-611-en-python-310-y-311).
  El 20 de noviembre de 2026 salió dos veces en el CI (3.14 + 6.12) en el
  árbol USB de Dispositivos, justo después de `self.usb.clear()`. Ese día se
  reprodujo fuera de los tests: la página sola, vaciando y rehaciendo el árbol
  con subconjuntos al azar de los USB del test y `processEvents` tras cada
  foto, revienta 3 de 3 vueltas antes de 4000 fotos, con la misma pila
  (`sendPostedEvents` → `QMetaCallEvent::placeMetaCall` sobre un `QFrame`).
  Actualizando las filas en vez de vaciar el árbol, 0 de 3 en 6500. Con la
  ventana entera y su bucle de eventos, el código viejo no cayó en 4
  ventanas de cinco minutos: en la app puede pasar, pero raro. Sigue
  abierto en el resto: es el primer reproductor, y apunta a vaciar y rehacer
  el contenido de un área de desplazamiento.
* **`privileged/instalar.py`** · alta, condicionada · escribe el ayudante y
  su regla de polkit sin comprobar que el destino no sea sustituible. No es
  explotable con `/usr/local` en su estado normal.
* **`providers/hwmon.py`** · media-alta · la clave de un sensor no incluye de
  qué nodo `hwmon` viene: dos aparatos con el mismo chip (dos NVMe iguales,
  dos gráficas) se pisan. Una fila se queda vacía, el mínimo y el máximo son
  la unión de los dos y el CSV escribe el dato de uno bajo el nombre del otro.
* **`ui/pages/cpulive.py`** · media-alta · compone los relojes a mano en vez
  de con `render.hz`: 576 MHz sale «0.58 GHz» y un bus de 100 MHz «0.10 GHz».

## De los informes de la prueba1 (20 de noviembre de 2026)

Lo que salió de los informes de anianin27 (Gentoo, i7-10700F, RTX 4060) y
widecoocaa23 (Lenovo LOQ con i5-12450H y RTX 4050, y su VM de Proxmox) y no se
pudo arreglar sin un volcado de su equipo, o quedó por hacer.

Desde la prueba3, el volcado llega en el anexo de su informe completo
(`tools/importar_informe.py`). El anexo lleva lo que se lee sin permisos, y
eso ya cubre casi todo lo de abajo: el SPD sale de `eeprom` en sysfs, y NVML,
las API gráficas y `cpuidle` van grabados. Lo que lee el ayudante (SMART,
SMBIOS, MSR, RAPL, los contadores de la memoria) no: está propuesto en las
notas (`propuesta-anexo-con-permisos.md`). Lo marcado «con el ayudante» lo
necesita.

* **Necesita el volcado de anianin27:**
  - NVIDIA · media · el consumo de la RTX 4060 salía «— (de 115 W)»: NVML dio
    el tope y no el consumo, con el driver 595. En el portátil (550) sí sale.
    Con el volcado, `nvidia-smi -q -d POWER` al lado.
  - Discos · baja · con el ayudante · el modelo entero por el IDENTIFY de
    `ata_device` (para buscar la unidad en drivedb) está probado aquí con dos
    Seagate y un Crucial; con el A400 de verdad, falta verlo.
* **Necesita el volcado del portátil de widecoocaa23:**
  - Memoria · media · el SPD de la DDR5 no se lee con permisos aunque
    `spd5118` está cargado y da su temperatura. Sospecha: el firmware bloquea
    el cambio de página del chip. Un solo `spd5118` para dos módulos.
  - Gráficos · media · la UHD sale «Sin bibliotecas gráficas»: OpenGL lo
    contesta la NVIDIA (EGL sin superficie, por el orden de glvnd) y no hay
    Vulkan de Intel (sin `mesa-vulkan-drivers`, o sin casar). Con el AppImage
    normal, además, la NVIDIA despierta salió sin la fila de OpenGL que sí dio
    el compat.
  - Gráficos · media · con el ayudante · la UHD sin uso por motor: el ayudante
    abrió `power/energy-gpu` y ningún contador de la i915, y su nodo DRM no
    enumeró motores (`engine/`). El aviso ya dice lo que se sabe; el porqué,
    con el volcado (¿qué eventos publica `event_source/devices/i915`?).
  - Memoria · baja · con el ayudante · «Este equipo no publica cuánto tráfico
    mueve el controlador de memoria» en un Alder Lake-H, con la explicación de AMD
    («Solo lo publican los procesadores Intel»).
  - Cachés y temperatura de un híbrido · se arreglaron con la topología del
    informe; con el volcado, conviene verlo en un equipo de verdad.
* **Sin volcado, sin hacer todavía:**
  - Gráficos · baja · «PCIe 1.0 × 8» de una NVIDIA en reposo, sin explicar
    que baja el enlace para ahorrar (sube con carga): la gente lo reportará
    como fallo.
  - SMART · baja · atributos conocidos (4, 192, 193, 196…) salen «propio del
    fabricante»; la temperatura en crudo sale empaquetada (64 427 589 655) y un
    HDD enseña «Escrito en total: —» en vez de esconderlo.
  - Batería · baja · «Retenida en el tope» al 78 % (un límite de carga) y
    «Autonomía: —» enchufado.
  - Informe · baja · los títulos de núcleos P/E y de la segunda gráfica no son
    encabezados; «sostenida  ·» con doble espacio (`bench.dur.comparable`
    empieza con dos).
  - Modelo · baja · `dmi._firmware` guarda «BIOS heredada» y «UEFI (64
    bits)» en español: sale así en inglés y en `--json`. Cambiarlo es cambiar
    la API.
  - VM · baja · el historial de Rendimiento de la VM tenía una prueba «15 s ·
    — · — · —»: preguntar si la canceló.

## Datos que se leen mal o no se leen

* `ui/pages/memory.py`, `ui/pages/battery.py` · media · cinco sitios
  redondean voltajes a dos decimales en vez de usar `render.volts`, que usa
  tres. Se pierde el decimal que distingue los escalones del VID.
* `providers/derived.py` · media · el tráfico de red del árbol de sensores va
  en potencias de 1024 y el de Red en potencias de 1000: dos cifras que se
  llevan un 2,4 %.
* `ui/pages/graphics.py` · baja · la tasa de datos de la VRAM, compuesta a
  mano.
* `spd.py` · media · el perfil 2 de XMP en DDR4 no se lee: no hay fuente de
  dónde va (memtest86+ solo lee el 1) ni un módulo que lo traiga. El
  perfil 1 (F-A2) se arregló con los módulos de anianin27.
* `spd.py` · media · `decode` revienta si el chip devuelve menos de 384 bytes,
  y se pierden todos los módulos, no solo el corto.
* `spd.py` · media · la tabla de fabricantes JEDEC tiene 15: con cualquier
  otro, el SPD no da marca y el firmware que escribe el código (MSI: «04EF»)
  lo enseña en bruto. Es el caso general del Team Group de anianin27. Falta la
  tabla JEP-106 entera de una fuente, con su aviso en THIRD_PARTY_NOTICES y su
  licencia comprobada, y decir «código JEDEC sin nombre» en vez del número.
* **F-M17 · `providers/drm.py`** · media · sin `pci.ids`, una AMD dedicada
  sin «radeon» en el nombre recibe el de la integrada («Radeon 780M»).
* **F-M18 · `smart.py`** · media · el atributo 202 cuenta como vida gastada
  sin mirar si el disco es mecánico: sale vida al 200 %. Un SSD SATA Kioxia
  enseña «Vida restante —»: su atributo de desgaste no se reconoce.
* **F-M19 · `providers/storage.py`** · media · el estado de SMART va por
  nombre de dispositivo: un USB enchufado como `sdb` hereda 30 s el del
  anterior.
* **F-M20 · `gpumetrics.py`, `nvml.py`, `providers/derived.py`** · media ·
  `if v` con relojes y contadores: 0 MHz (GFXOFF) llega como `None`.
* `providers/` · media · siete proveedores declaran `available()` y no
  `unavailable_reason()`: se callan cuando no pueden trabajar. Se nota en Red y
  en Almacenamiento, que se quedan vacías sin explicarlo.
* `providers/rapl.py` · media-baja · en un contenedor dice que la CPU no tiene
  contadores de energía.
* `providers/cppc.py` · media, sin comprobar · el techo del silicio con
  `acpi-cpufreq`: falta un volcado con `amd_pstate=disable`.
* `ui/pages/cpu.py` · media-baja · «Preferencia de energía —» con
  `acpi-cpufreq`, que no tiene EPP: la fila tendría que esconderse y decirse.
* `providers/storage.py` · baja · el modelo de los discos SATA sale cortado a
  16 caracteres; el completo está sin permisos en `/dev/disk/by-id`.
* `render.py` · baja · dos módulos en canales distintos pueden salir los dos
  como «Canal A».
* `collector.py` · baja · a `_clone` le faltan `batteries`, `cpu_extra` y
  `memory_traffic`. Hoy no se pierde nada; el día que uno de sus proveedores
  sea estático, sí.
* `providers/dmi.py` · baja · la lista de chipsets de AMD es cerrada y hay que
  añadirle cada generación nueva.
* `providers/hwmon.py` · baja · los valores fijos de relleno de `acpitz`
  (16.8, 27.8 y 29.8 °C) son los que se conocen; otro número fijo no se marca.
* `db/memory_limits.json` · media · de Intel solo están las generaciones 10.ª
  y 11.ª: faltan las demás, que se generan con `--intel-desde` de las fichas
  de ARK guardadas. Y once Ryzen sin ficha en amd.com.
* `ui/pages/board.py` · media, sin comprobar · la columna «Ranura» (SMBIOS
  tipo 9) no se ha visto con la tabla de ninguna placa.
* **Escrito sin la pieza delante**: los motivos de limitación de `i915` y las
  frecuencias de `xe`; el uso de NVENC y NVDEC de `nvml.py` (contrastar con
  `nvidia-smi dmon -s u`); los volcados de una NVIDIA, una Arc y una Steam
  Deck con `tools/volcar_equipo.py`. Ver [equipos-probados.md](equipos-probados.md).
* **Datos baratos que faltan** (de la lista de la noche del 19; ya están el
  kernel contaminado, la línea de arranque, el límite de fábrica de la
  gráfica, los errores PCIe de la gráfica, la ventana de PL1 y PL2 y los
  frenos por temperatura):
  - **Placa base**: los errores AER de los puertos raíz
    (`aer_rootport_total_err_cor`, `_fatal` y `_nonfatal`). Son un número
    suelto, no las líneas `TOTAL_ERR_*` de los `aer_dev_*` que lee
    `drm._aer`. En el 5800X3D solo los publican los puertos internos 00:07.1
    y 00:08.1, no el de la gráfica (00:03.1). Falta decidir dónde se
    enseñan.
  - **Cachés**: la TLB, de CPUID (0x80000005/6 y 0x80000019 en AMD; 0x18
    en Intel, y la hoja 2 en los viejos). `grabado.json` guarda solo las
    hojas que se leyeron, así que hay que volver a volcar los tres equipos.

* `membench.py`, `ui/pages/memory.py` · media · con dos CCD de L3 distinta
  (7950X3D) o núcleos P y E (Intel híbrido) salen dos niveles con el mismo
  nombre («L3» de 16 y 48 MB): el proceso que mide no está fijado a ningún
  núcleo, así que el bloque de 48 MB puede medirse en el CCD de 32 MB y dar
  la RAM llamándola L3, y los resultados se guardan por nombre y el segundo
  pisa al primero. Hace falta fijar el proceso a una CPU (la de la L3 mayor)
  y medir los niveles de esa CPU. Sin un volcado de dos CCD delante.
* `membench.py` · media · repetir el 5800X3D contra AIDA64 ahora que el
  bloque tiene páginas grandes ([benchmark.md](benchmark.md)), y ver por qué
  las primeras vueltas de la L3 salen ruidosas (20 ns frente a 12).
* `providers/cpuid_x86.py` · baja · la máquina virtual se reconoce solo por
  CPUID (el bit «hypervisor» y la hoja 0x40000000). Un anfitrión que lo
  esconde (KVM con `kvm=off`, típico al pasar una gráfica) no se ve; el
  firmware lo diría (`sys_vendor` «QEMU», `product_name` «VirtualBox»,
  «VMware Virtual Platform»). Sin un volcado de máquina virtual delante.

## Interfaz

* **F-M2 · `ui/widgets.py`** · media · `StatTile` nace con «—» a tamaño de
  cifra y solo cambia la letra cuando cambia el texto: una ficha que nunca
  recibe un valor se queda con la raya gruesa. Y al perder el dato,
  `unpolish()` deshace el `setFont` de justo antes.
* **F-M3 · `ui/sampler.py`** · media · cerrar la ventana durante un muestreo
  largo (con el diálogo de polkit abierto) aborta el proceso con código 134.
* **F-M5 · `ui/pages/performance.py`** · media · cambiar tema, densidad,
  letra, idioma o unidades durante una prueba la mata sin decirlo. Lo mismo a
  la medida de memoria.
* **F-M7 · `ui/pages/performance.py`** · media · la carga de fondo máxima no
  se ve: `CONDITION_FIELDS` no incluye su fila.
* **F-M8 · varios** · media · texto en español fijo con la interfaz en
  inglés: las cargas del benchmark, «semana N de AAAA» (que además se guarda
  ya formateado en el modelo), «Cargando…», «Bajada/Subida», «BIOS
  heredada», «UEFI (64 bits)», «Gráfica N».
* **F-M9 · `ui/widgets.py`** · media · las etiquetas seleccionables con el
  ratón cuestan 22 MB: cada una crea su `QTextDocument`.
* `ui/pages/memory.py` · baja · «Banco: P0 CHANNEL A» sale en bruto del
  firmware (el «Bank Locator» de SMBIOS). Al lado de «Zócalo», que ya dice
  «Canal A · DIMM 1», no aporta nada: o se lee mejor, o no sale.
* `ui/widgets.py` · media-baja · un `float` no finito en una gráfica lanza
  una excepción en cada repintado y deja el `QPainter` abierto.
* `ui/widgets.py`, `ui/pages/storage.py` · media-baja · la temperatura de un
  disco SATA sigue con «—» en la tabla de unidades aunque su ficha lleve
  candado: `Table.set_cell_locked` existe y falta usarlo ahí.
* `ui/widgets.py` · baja · el globo «copiado» se come el clic siguiente durante
  1,4 s; y arrastrar para seleccionar parte de un valor copia el valor entero.
* `ui/widgets.py` · baja · `Table.set_rows` indexa fuera de rango si una fila
  trae más columnas que la anterior.
* `ui/widgets.py` · baja · una gráfica transparente repinta su tarjeta y la
  página de detrás en cada fotograma; y cada `setText` de un `ElidingLabel`
  recoloca la página (de 0,2 a 1,8 ms por muestra). [rendimiento.md](rendimiento.md)
* `ui/corematrix.py` · baja · pintar CPU tras cada muestra cuesta 13,7 ms
  (aplicarla, 5,4, como las demás): la matriz de núcleos repinta su fondo
  entero y la curva suave de los dieciséis hilos (`curva_suave`, unos 4 ms
  por muestra). Pintar solo lo que cambia lo bajaría. [rendimiento.md](rendimiento.md)
* `ui/app.py` · baja · Inicio y Gráficos reciben la foto entera en cada
  muestra aunque no se vean: tienen gráficas y no tienen `record`, así que
  `_distribute` les hace `apply`. Son unos 3 ms por muestra tirados.
* `ui/app.py` · baja · cambiar el tema reconstruye las páginas y las gráficas
  vuelven a empezar.
* `ui/app.py` · baja · no se puede cambiar de sección con el teclado.
* `ui/pages/performance.py` · media-baja · borrar una medida del historial
  pregunta con los botones estándar de Qt, que salen en inglés («Cancel»,
  «Yes») con la interfaz en español: no se carga ninguna traducción de Qt
  (`QTranslator`), y en el AppImage tampoco está la integración de Plasma
  que los traduce. Lo mismo el «OK» de los avisos de `QMessageBox`.
* `ui/` · baja · `disk.pci_slot` está en el modelo y no se pinta.
* `db/lang/` · baja · claves que ya no usa nadie; `gen_lang.py` las detecta y
  `--podar` las borra.

## Línea de órdenes, informe y registro

* `cli.py` · baja · `--json` vuelca todo sin anonimizar y sin avisar.
* `cli.py` · baja · `--json`, `--sensors` y `--report` se pisan en silencio;
  `--report -` no dice que ha omitido nada; `--with-identifiers` sin
  `--report` no hace nada y no avisa.
* **F-M31 · `report.py`** · media · en el informe corto, los zócalos vacíos
  salen como módulos y en una integrada «Memoria: — — · — · —».
* **F-M32 · `cli.py`** · media · el valor de un sensor se formatea de tres
  maneras: `--sensors`, el volcado y `render.sensor_value`.
* `report.py` · baja · `_placa` recibe `anonymous` y no lo usa.
* **El informe con permisos, sin probar con los AppImage de la prueba1** ·
  media · sin permisos se generó con los dos AppImage del CI, en este equipo
  y con los tres volcados, y con entradas raras. Con permisos no: polkit
  pide la contraseña (`auth_admin_keep`) y la noche del 19 no había nadie
  delante. Probar `--report` y «Ver y guardar el informe…» → «Dar
  permisos» con los dos antes de publicar.
* `registro.py` · baja · la hora del CSV va sin fecha, y las cabeceras se
  repiten cuando un aparato publica varias etiquetas iguales.

## Privilegios y privacidad

* `privileged/helper.py`, `privileged/client.py` · media · los topes de
  tamaño del protocolo se comprueban después de reservar la memoria (F-M24),
  y el `timeout` de `request()` no acota la lectura (F-M25).
* **F-M26 · `privileged/client.py`** · media · tras una respuesta ilegible no
  se cierra el canal, y desde ahí cada respuesta llega con una de retraso.
* **F-M27 · `privileged/helper.py`** · media-baja · la lista blanca de MSR
  tiene nueve registros que no se usan. Va como propuesta antes que código.
* `privileged/helper.py` · baja · el ayudante muere con UTF-8 inválido;
  `DISK_NAME` acepta un salto de línea final; un comentario dice que
  `uncore_imc_free_running` es de Ice Lake en adelante y no lo es
  ([kernel.md](kernel.md)). Va con el próximo cambio del ayudante, que obliga
  a reinstalarlo.
* `privileged/cargar_modulo.py` · baja · admite `i2c-dev`, que no es de
  solo lectura.
* `updates.py` · baja · sin firma: el SHA-256 sale del `SHA256SUMS` de la
  misma release, así que protege de una descarga rota, no de quien pudiera
  escribir en las releases del repositorio.
* `privileged/instalar.py` · baja · el ayudante llega por la tubería sin
  longitud ni suma: si Silux muriera a mitad de escribirlo se instalaría
  cortado (no arrancaría y saldría como desactualizado). Son 27 KB, que caben
  en el búfer de la tubería, así que en la práctica no pasa.
* `privileged/helper.py` · baja · un JSON anidado miles de veces cabe en el
  tope de petición; con 3.14 no pasa nada, con el Python del sistema de una
  distribución vieja podría lanzar `RecursionError` y cerrar el ayudante (solo
  a sí mismo). Por comprobar con 3.10; va con el próximo cambio del ayudante.
* `data/org.silux.helper.policy.in` · baja · diverge de la regla que escribe
  `instalar.py` y no lo usa nadie.
* `privacidad.py`, `tools/volcar_equipo.py` · media-baja · `--anonymous` da
  la misma IP a todas las interfaces, y los volcados la misma dirección
  física: dos tarjetas iguales delatan que la captura está tocada.

## Empaquetado y CI

* `tools/build_appimage.py` · baja · `--container` se traga `--keep` y
  `--appdir-only`; `appimagetool` se descarga en cada construcción sin fijar
  su hash.
* `.github/workflows/appimage.yml` · baja · `contents: write` para todo el
  flujo; las acciones van por etiqueta y no por SHA; comprobar que el
  AppImage arranca es un `--help`, que no carga el plugin de plataforma ni
  mira si pinta sus iconos.
* **F-M37 · `tools/probar_en_minimo.py`** · media · cualquier fallo del
  contenedor se anuncia como «la suite no pasa», y dentro corre como root.
* El paso de tests del CI solo busca `FAILED` y `ERROR`: un aborto sale sin
  la causa.
* Tests que leen la máquina y fallan a veces con la suite en paralelo:
  `test_avisos.py::test_no_salta_ningun_aviso_en_reposo` y
  `test_segundo_plano.py::TestCargarUnModulo::test_un_fallo_de_verdad_se_ensena`.
* `tests/test_al_momento.py` no cubre Batería: ningún volcado tiene una.
* `.github/workflows/tabla-cpu.yml` · baja · el paso que abre el PR no se ha
  visto correr. Se lanzó a mano tres veces (el 19 y el 20 de noviembre de
  2026): dos sin nada nuevo, y la del medio falló antes, al bajar el
  `cpuid`. Todo lo anterior a ese paso, con las cinco fuentes, sí ha
  corrido.

## Menores

De la quinta auditoría, sin comprobar uno a uno si siguen igual:

* `privileged/helper.py`: `cpu: true` cuenta como CPU 1.
* `providers/hwmon.py` lanza `modinfo` en cada muestreo; `pci.ids` se lee sin
  caché; el estado anterior de red y discos crece sin límite con cada `veth`;
  el nombre de equipo `(none)` llega crudo; las salidas de video no se
  actualizan al enchufar un monitor; `power_supply` no filtra por `scope`;
  `alarm_level` dice «alto» también por debajo del mínimo.
* «DDR4-2667» en Inicio, la tarjeta y el informe frente a 2666 en Memoria; al
  ordenar el árbol ascendente las celdas vacías salen primero; el CSV pierde
  precisión con `{v:g}`; un fallo al cargar un driver se titula «Se ha parado
  la grabación».
* Cancelar no interrumpe una medida en curso (`time.sleep` de hasta 1800 s);
  dos analizadores de `/proc/stat` con distinto «inactivo»; `mprotect` sin
  `argtypes`; `history.save` con un `.tmp` fijo y sin cerrojo.

## Propuestas sin aplicar

* **Leer con el ayudante instalado sin contraseña** (idea a revisar con
  calma, no decidida). Hoy la regla es `auth_admin_keep`: la contraseña se
  pide al dar permisos y polkit la recuerda unos minutos para ese proceso.
  La idea: `allow_active = yes` para la sesión local activa, y que Silux se
  conecte al abrirse solo si `pkcheck` confirma que no saldrá ninguna
  ventana. Lo que lee el ayudante quedaría al alcance de **cualquier
  proceso** del usuario de esa sesión, sin contraseña: la tabla SMBIOS
  entera (números de serie de placa y memoria), SMART (serie del disco), 16
  MSR de una lista blanca, los contadores de la gráfica y del tráfico de
  memoria y la energía de RAPL. Riesgos: (1) un proceso comprometido de la
  sesión llega a un proceso root sin contraseña, y un fallo del ayudante
  pasaría a ser root sin contraseña; (2) la energía y los contadores leídos
  miles de veces por segundo reabren el canal lateral por el que el kernel
  cerró `energy_uj` en la 5.10 (Platypus, CVE-2020-8694) y por el que los
  contadores uncore van detrás de `perf_event_paranoid`; (3) las series
  dejan de ser solo de root. Lo que haría falta en el lado de root si algún
  día se hace: un solo ayudante a la vez (cerrojo en `/run`); el mínimo de
  100 ms entre lecturas de energía y contadores ya está. Las sesiones remotas o
  inactivas seguirían pidiendo la contraseña. El 20 de noviembre de 2026 el
  autor prefirió pedir la contraseña antes que dar root sin ella a cualquier
  proceso de la sesión.

* **Grabar una sesión** (después de la 0.4): empezar, pausar y parar, por
  ejemplo mientras se juega, con un resumen al final: máximos, medias y si
  algo se frenó por temperatura. Hoy `registro.py` graba a CSV sin resumen.
* **La última hora de cada sensor** (después de la 0.4): un historial en
  memoria mientras Silux está abierto, en Sensores y en las gráficas de cada
  página, con un selector de tramo (1 min, 10 min, 1 h) y, al pasar el ratón,
  el valor y la hora de ese punto. Se pinta agrupando por píxel (el mínimo y
  el máximo de cada columna), para no perder picos ni gastar CPU, y dentro de
  los 300 MB de la regla 7.
* **Modo bandeja del sistema** (después de la 0.4): opcional y apagado de
  serie, en Ajustes «Al cerrar la ventana: salir / seguir en la bandeja». En
  la bandeja no se pinta nada: solo se leen los sensores para el historial,
  gastando lo mínimo. Por seguridad, en la bandeja el ayudante con permisos
  se cierra (o lo elige el usuario). Comprobar GNOME (necesita la extensión
  AppIndicator) y KDE. Y con eso, alertas opcionales por notificación del
  sistema (la temperatura del procesador o de la gráfica por encima de un
  límite).
* **Medidas finas, solo si se pueden hacer de forma fiable** (después de la
  0.4):
  - La topología exacta del procesador desde CPUID: qué núcleos comparten
    cada caché, núcleos P y E en Intel y, en los Ryzen X3D, qué CCD lleva la
    3D V-Cache (clave en los de dos CCD, como el 7950X3D). Es la base del
    mapa de núcleos dibujado.
  - La latencia de caché en ciclos y en curva (latencia según el tamaño de
    los datos), que enseñe dónde acaba cada nivel, como AIDA64.
  - El ancho de banda de la memoria con instrucciones vectoriales: lectura,
    escritura y copia por separado.
  - En el benchmark, el rendimiento con y sin AVX2 y AVX-512.
* **Un benchmark de gráfica** (después de la 0.4).
* **Diagramas que salen de datos reales**, no decorativos: el mapa de
  núcleos de la CPU (CCD, núcleos P y E, hilos hermanos, mejores núcleos) y
  la jerarquía de cachés dibujada. Nada de dibujos inventados del hardware.
  El mapa de núcleos (después de la 0.4), en la página CPU: un recuadro por
  CCD (o por clúster en Intel) con sus núcleos dentro; los dos hilos de cada
  núcleo con su frecuencia y su uso en directo; la estrella de los mejores
  núcleos; la L3 de cada CCD debajo, marcando la 3D V-Cache en los X3D; y,
  en Intel, los núcleos P y E en grupos distintos. Todo de datos reales
  (sysfs y CPUID), y validado con informes de equipos de dos CCD y con
  núcleos P y E antes de enseñarlo.
* **Bienvenida la primera vez** (cuando aún no hay `settings.json`): una
  ventana pequeña con idioma, tema y tamaño de letra, que se vean cambiar en
  el momento, y «Empezar» para guardarlos. El idioma por defecto ya sigue al
  del sistema.
* **Escritorios**. Probado aquí (KDE Plasma): los dos AppImage abren por
  Wayland y por X11 (`QT_QPA_PLATFORM=xcb`, XWayland) y pintan bien; llevan
  los plugins de plataforma de los dos y los de Wayland (decoraciones, shell).
  En KDE, `styleHints().colorScheme()` dice «oscuro» por los dos. Falta una
  máquina virtual con GNOME (Wayland: la barra de título la pinta Qt), con
  Cinnamon y con XFCE (X11 de verdad, no XWayland). Propuesta: que el tema
  «sistema» lea `QStyleHints.colorScheme()` (Qt 6.5 o posterior, que sigue el
  portal de apariencia de GNOME) en vez de deducirlo del color de la paleta,
  y que se repinte con `colorSchemeChanged` (regla 9).
* **Sensores: las interfaces virtuales**. Con Docker, el árbol y el informe
  llevan veinte bloques «Red (veth…)» a cero. Red las enseña a propósito,
  después y marcadas; en Sensores podrían ir plegadas en un grupo o fuera.
  Decisión del autor.
* **Fabricantes de memoria y marcas de disco**: la tabla JEP106 (14 marcas)
  desde `decode-dimms` de i2c-tools, y la marca de un NVMe por el `pci.ids` de
  su controladora. Detalle en las notas (`revision-memoria-discos-placas.md`).

* **El código, en inglés (después de la 0.4).** Los nombres de funciones,
  variables, parámetros, atributos y clases, y los comentarios y docstrings,
  pasan a inglés en un proyecto propio, módulo a módulo y con los tests como
  red: un módulo por commit, sin cambiar nada de lo que hace. Cómo está el 19
  de noviembre de 2026, contado con los propios archivos de idioma como
  vocabulario (`es.json` frente a `en.json`); lo «neutro» son siglas y
  palabras que valen en los dos:

  | | Nombres | En español | En inglés | Mezclados | Neutros | Comentarios y docstrings en español |
  |---|---|---|---|---|---|---|
  | `silux/` | 7918 | 29 % | 35 % | 1 % | 35 % | 99 % de 4648 |
  | `tests/` (sin el `test_` de unittest) | 7659 | 66 % | 6 % | 1 % | 27 % | 96 % de 2192 |
  | `tools/` | 960 | 46 % | 6 % | 0 % | 48 % | 98 % de 487 |

  En `silux/`, las clases van sobre todo en inglés (67 %) y las variables,
  mitad y mitad. Los textos de la interfaz no se tocan: viven en
  `silux/db/lang/` y el original sigue siendo el español.

* **Identificar procesadores sin depender de nadie.** Hoy el nombre en clave,
  el nodo y el encapsulado salen de una tabla generada una vez (26 de agosto
  de 2026) de libcpuid y CPU-X. CPU-X está archivado desde el 27 de
  septiembre de 2026, y desde 2022 casi todos los commits a las tablas de
  Intel y AMD de libcpuid son de la misma persona. El plan:
  - Una tabla propia en `silux/db/`, con la fuente y la fecha en cada regla.
  - Intel: `arch/x86/include/asm/intel-family.h` del kernel, fijado a una
    etiqueta (modelo → nombre en clave y segmento). Se toman los números y
    los nombres, que son datos, no código.
  - AMD: no hay cabecera equivalente. Rangos de familia y modelo de las guías
    de AMD (PPR y guías de revisión), con el enlace en cada regla, como ya
    hace `families.json`; el `amd.c` del kernel confirma la generación Zen de
    cada rango.
  - ARM: `arch/arm64/include/asm/cputype.h` del kernel (MIDR → núcleo).
  - Nodo y encapsulado por modelo: de las fichas oficiales (ARK, amd.com), que
    ya lee `tools/gen_memory_limits.py` para el máximo de memoria.
  - `tools/gen_cpu_db.py` regenera la tabla de esas fuentes, y un test compara
    el JSON con lo regenerado (el contenido, no un número de versión).
  - Los informes de la comunidad: `tools/anadir_cpu.py INFORME` saca la firma
    CPUID y la marca, dice qué regla falta y escribe un caso en
    `tests/fixtures/cpus/` con lo esperado; un test parametrizado los pasa
    todos. Una generación nueva es subir la etiqueta del kernel, añadir la
    regla de AMD con su enlace y pasar un informe real.
  - Transición: la tabla de libcpuid se queda congelada, con su aviso, como
    último recurso, hasta que la propia cubra lo mismo (un script lo mide
    fila a fila). Luego se quita.

* **Límites de potencia de AMD** (PPT, TDC, EDC) con `ryzen_smu`. Aplazado:
  la tabla de `ryzen_smu` no está documentada, cambia con la BIOS y leerla
  manda órdenes al firmware, así que el ayudante dejaría de solo leer. Si se
  retoma, en dos pasos: detectar el módulo sin cifras ni privilegios, y
  después, experimental, el mapa del 5800X3D verificado en la pieza.
* **El uso de una Arc con `i915` y el de `xe`**: el ayudante tendría que
  abrir también el PMU de esas gráficas. Toca privilegios: va como propuesta.
* **Gráficos**: de la revisión de gráficas quedan el framebuffer de respaldo y
  dos de nouveau, y leer lo que publican `xe`, NVML, `radeon` y nouveau.
