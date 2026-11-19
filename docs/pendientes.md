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
* **F-A2 · `spd.py`** · alta · el XMP de DDR4 calcula el ciclo con la parte
  gruesa sola (`spd[offset+3] * 125`), sin la corrección fina: un DDR4-3600
  (555 ps) sale «XMP 1 3200». Las posiciones de los perfiles son las de XMP
  1.x de DDR3, y el perfil 2 de DDR4 caería dentro del primero. No hay ningún
  volcado con XMP en `tests/fixtures`: no se escribe sin uno real delante.
* **Los avisos de autoría de libcpuid y CPU-X** · alta · `silux/db/cpu_ids.json`
  sale de las tablas de libcpuid (BSD-2: nombres en clave, nodos, patrones de
  marca y las piezas ARM) y de la de encapsulados de CPU-X (GPL-3.0 o
  posterior). BSD-2 pide conservar su copyright, sus condiciones y su renuncia
  de garantía con el código y reproducirlos en la documentación del binario;
  hoy solo se los nombra (Ajustes, `--db-info`, `tools/gen_cpu_db.py`). Falta
  también la línea de copyright de CPU-X, y el AppImage no lleva ni el
  `LICENSE` de Silux. Arreglo: los avisos completos en un archivo, copiado al
  AppImage y enlazado desde Ajustes.
* **`privileged/instalar.py`** · alta, condicionada · escribe el ayudante y
  su regla de polkit sin comprobar que el destino no sea sustituible. No es
  explotable con `/usr/local` en su estado normal.
* **`providers/hwmon.py`** · media-alta · la clave de un sensor no incluye de
  qué nodo `hwmon` viene: dos aparatos con el mismo chip (dos NVMe iguales,
  dos gráficas) se pisan. Una fila se queda vacía, el mínimo y el máximo son
  la unión de los dos y el CSV escribe el dato de uno bajo el nombre del otro.
* **`ui/pages/cpulive.py`** · media-alta · compone los relojes a mano en vez
  de con `render.hz`: 576 MHz sale «0.58 GHz» y un bus de 100 MHz «0.10 GHz».

## Datos que se leen mal o no se leen

* `ui/pages/memory.py`, `ui/pages/battery.py` · media · cinco sitios
  redondean voltajes a dos decimales en vez de usar `render.volts`, que usa
  tres. Se pierde el decimal que distingue los escalones del VID.
* `providers/derived.py` · media · el tráfico de red del árbol de sensores va
  en potencias de 1024 y el de Red en potencias de 1000: dos cifras que se
  llevan un 2,4 %.
* `ui/pages/graphics.py` · baja · la tasa de datos de la VRAM, compuesta a
  mano.
* `spd.py` · media · `decode` revienta si el chip devuelve menos de 384 bytes,
  y se pierden todos los módulos, no solo el corto.
* **F-M16 · `providers/spd_modules.py`** · media · si la referencia del
  zócalo A no casa, A se lleva el SPD de B y B el de A.
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
* **F-M21 · `providers/drm.py`** · media · `_pmu_ok` no vuelve nunca a
  `False`: si el ayudante muere, el aviso de Intel pasa a «no existe».
* `providers/` · media · siete proveedores declaran `available()` y no
  `unavailable_reason()`: se callan cuando no pueden trabajar. Se nota en Red y
  en Almacenamiento, que se quedan vacías sin explicarlo.
* `providers/rapl.py` · media-baja · en un contenedor dice que la CPU no tiene
  contadores de energía.
* `providers/cppc.py` · media, sin comprobar · el techo del silicio con
  `acpi-cpufreq`: falta un volcado con `amd_pstate=disable`.
* `providers/cpuid_x86.py`, `ui/pages/cpu.py` · media · con un procesador
  que la tabla no conoce, lo del CPUID sale entero y no se inventa nada
  (comprobado con el volcado del 5800X3D sin su fila), pero «Nombre en
  clave», «Tecnología» y «Encapsulado» salen con «—» en vez de esconderse y
  nombrarse al pie, y la nota dice «Regenera la base con
  tools/gen_cpu_db.py», que no sirve a quien usa el AppImage: tiene que decir
  que ese dato no está en esta versión y pedir el informe. Con un test que
  quite la fila del volcado y mire la página.
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
* `ui/pages/cpulive.py` · baja, sin mirar · pintar CPU tras cada muestra
  cuesta 11,5 ms, frente a 2-4 en las demás páginas.
* `ui/app.py` · baja · cambiar el tema reconstruye las páginas y las gráficas
  vuelven a empezar.
* `ui/app.py` · baja · no se puede cambiar de sección con el teclado.
* `ui/` · baja · `disk.pci_slot` está en el modelo y no se pinta.
* `db/lang/` · baja · claves que ya no usa nadie; `gen_lang.py` las detecta y
  `--podar` las borra.

## Línea de órdenes, informe y registro

* `cli.py` · baja · `--json` vuelca todo sin anonimizar y sin avisar.
* `cli.py` · baja · `--report ''` hace el volcado normal sin decir nada;
  `--json`, `--sensors` y `--report` se pisan en silencio; `--report -` no
  dice que ha omitido nada; `--with-identifiers` sin `--report` no hace nada
  y no avisa.
* **F-M31 · `report.py`** · media · en el informe corto, los zócalos vacíos
  salen como módulos y en una integrada «Memoria: — — · — · —».
* **F-M32 · `cli.py`** · media · el valor de un sensor se formatea de tres
  maneras: `--sensors`, el volcado y `render.sensor_value`.
* `report.py` · baja · `_placa` recibe `anonymous` y no lo usa.
* `registro.py` · baja · la hora del CSV va sin fecha, y las cabeceras se
  repiten cuando un aparato publica varias etiquetas iguales.

## Privilegios y privacidad

* `privileged/helper.py`, `privileged/client.py` · media · los topes de
  tamaño del protocolo se comprueban después de reservar la memoria (F-M24),
  y el `timeout` de `request()` no acota la lectura (F-M25).
* **F-M26 · `privileged/client.py`** · media · tras una respuesta ilegible no
  se cierra el canal, y desde ahí cada respuesta llega con una de retraso.
* **F-M27 · `privileged/helper.py`** · media-baja · la cadencia de RAPL la
  decide el cliente y no el ayudante; la lista blanca de MSR tiene nueve
  registros que no se usan. Va como propuesta antes que código.
* `privileged/helper.py` · baja · el ayudante muere con UTF-8 inválido;
  `DISK_NAME` acepta un salto de línea final; un comentario dice que
  `uncore_imc_free_running` es de Ice Lake en adelante y no lo es
  ([kernel.md](kernel.md)). Va con el próximo cambio del ayudante, que obliga
  a reinstalarlo.
* `privileged/cargar_modulo.py` · baja · llama a `modprobe` sin ruta
  absoluta, y admite `i2c-dev`, que no es de solo lectura.
* `data/org.silux.helper.policy.in` · baja · diverge de la regla que escribe
  `instalar.py` y no lo usa nadie.
* `ui/theme.py` · media-baja · cachea los iconos en un `/tmp/silux-icons` de
  nombre fijo y usa lo que encuentre.
* `privacidad.py`, `tools/volcar_equipo.py` · media-baja · `--anonymous` da
  la misma IP a todas las interfaces, y los volcados la misma dirección
  física: dos tarjetas iguales delatan que la captura está tocada.

## Empaquetado y CI

* `tools/build_appimage.py` · baja · los AppImage llevan dentro
  `libresolv.so.2`, que es de glibc. Llega por el plugin de Qt para VNC, que
  arrastra QtNetwork y Kerberos; solo se carga con `QT_QPA_PLATFORM=vnc`.
  Hay que dejar fuera ese plugin y llevar `libresolv` a lo que se deja al
  sistema.
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
