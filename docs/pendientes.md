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

* **El recuento de subtests varía** · baja · con el mismo código, la suite
  dio 62 798 en una ejecución y 62 822 en las demás. Algún test recorre algo
  que cambia de una vez a otra, y eso le quita valor a comparar el recuento
  con el de la última ejecución. Falta encontrar cuál (`-v` en dos
  ejecuciones y comparar los SUBPASSED por test).

## De los informes de las pruebas

Lo que salió de los informes de las pruebas y no se pudo arreglar sin más
datos de su equipo, o quedó por hacer. El volcado llega en el anexo de cada
informe completo (`tools/importar_informe.py`): lleva lo que se lee sin
permisos. Lo que lee el ayudante (SMART, SMBIOS, MSR, RAPL, los contadores de
la memoria) no va: está propuesto en las notas
(`propuesta-anexo-con-permisos.md`). Lo marcado «con el ayudante» lo necesita.

* **De los informes de la prueba7** (volcados `i5-3330`, `i5-5200u`,
  `i5-8350u`, `core2-p8400`, `celeron-560` e `i7-4710hq`), lo que queda:
  - Memoria · media · con el ayudante: en el T480s, el módulo 1 (Samsung
    M471A1K43BB1-CRC, sin SPD en el bus) es casi seguro la memoria soldada,
    pero la tabla del firmware lo llama SODIMM en «ChannelA-DIMM0» y la regla
    de lo soldado no lo ve. Hace falta su tabla SMBIOS para decidir con qué.
  - Memoria · baja · el chip SPD que el kernel no busca (0x52 con dos
    zócalos) se explica, con la orden para registrarlo a mano, solo con
    permisos: hace falta la tabla del firmware para saber que es un módulo
    en un zócalo y no memoria soldada. Sin permisos, systemd publica esa
    tabla en `/run/udev/data/+dmi:id` (`MEMORY_DEVICE_*`, de su
    `dmi_memory_id`), legible por cualquiera; con eudev o sin udev, no.
    Sería una fuente de los módulos sin permisos, con su número de serie
    tapado en el anexo. La causa, confirmada con el dmesg del Vostro: el
    kernel registró solo 0x50 (`spd`, 256 bytes) y no probó 0x52, porque
    `i2c_register_spd` prueba 0x50 + n por cada zócalo que declara el
    firmware, 0x50 y 0x51 con dos. La orden que da Silux es la correcta.
  - Almacenamiento · media · los atributos SMART estándar de un WD
    (3, 4, 7, 10, 11, 183, 184, 190-193, 196, 200) salen como «propio del
    fabricante»: tienen nombre por defecto en smartmontools (`ata_get_attr_name`).
  - Red · baja · un adaptador Wi-Fi por USB enseña «Ranura PCI: 5-2:1.0», que
    es su ruta USB.
  - Gráficos · baja · la velocidad del enlace DisplayPort de cada monitor solo
    la publica amdgpu en debugfs, que es de root.
  - Gráficos · baja · el modelo comercial exacto de una tarjeta
    (Hellhound, Reaper, Red Devil) no está en pci.ids: para 148C:2435 dice
    «Radeon RX 9070 XT 16GB». Habría que mandarlo a la base de pci-ids.
  - Volcados · baja · `PrivilegedState.supported` mira el pkexec del equipo
    que pasa la suite, no el del volcado: el del P8400 ofrece «dar permisos»
    en los tests aunque en su equipo no haya pkexec.
  - Volcados · baja · el anexo de un informe puede llegar sin `uname`: el
    volcado se queda sin versión del kernel ni nombre del equipo, que
    `/proc/sys/kernel/osrelease` y `hostname` darían. Ningún volcado lo
    enseña ya (el `i7-4710hq` se rehízo con la prueba9).

* **Del T14 del autor** (volcado `i5-1135g7`):
  - Gráficos · media · el pico de 1336648637.3 W en la gráfica del consumo
    de la Iris Xe (glmark2, en batería) no está reproducido: 9 J en unos
    7 ns, pero el valor y su marca viajan juntos en la respuesta del
    ayudante y no se ha encontrado un camino que dé esa ventana. Ningún
    ritmo sale ya de una ventana de menos de medio intervalo
    (`providers/counters.py`), lo imposible se descarta y el informe dice sus
    números (`report.power.discarded`): con el siguiente que lo traiga, si
    fue la ventana o el contador.
* **Del sobremesa con i7-10700F y RTX 4060** (volcado `i7-10700f`, de la
  prueba5):
  - Discos · baja · con el ayudante · el modelo entero por el IDENTIFY de
    `ata_device` (para buscar la unidad en drivedb) está probado aquí con dos
    Seagate y un Crucial; con el A400 de verdad, falta verlo.
* **De los informes de la prueba8** (volcados `celeron-g3900` y `i5-12450h`,
  rehecho):
  - Memoria · media · con el ayudante · los contadores libres del controlador
    del LOQ (`event=0xff,umask=0x20`, dos campos) los abre ya el ayudante,
    que coloca cada campo en sus bits como `perf`. Falta comprobarlo en el LOQ
    contra `perf stat`.
  - Memoria · baja · el SPD de su DDR5 se lee página a página, sin búfer, y
    un volcado guarda la página que se leyó y el error de las demás. El del
    LOQ lleva la página 0 que leyó su dueño con `dd`. Falta ver en un equipo
    así que el volcador copia la página 0 (el test vuelve a volcar el
    volcado montado, que ya la tiene).
  - Gráficos · baja · el modo que tiene puesto cada salida sale de los ioctl
    de modesetting y se graba en los volcados nuevos; los de la suite no lo
    tienen, y lo dicen al pie. El anexo ya lleva el EDID con solo el número
    de serie tapado: falta ver con el EDID real de la tele que la regla del
    tamaño (160 × 90 cm, su 16:9) es la suya.
  - Dispositivos · baja · nombra lo USB por lo que dice el propio aparato
    («802.11n NIC»), no por `usb.ids` como Red; ahora que el anexo guarda
    vendor:product, podría hacerlo igual.
  - Red · baja · con la tarjeta Wi-Fi USB sin modelo, el pie dice «El kernel
    no publica modelo»: el modelo de una USB no lo publica el kernel, sale de
    `usb.ids` o de la tarjeta.
* **De los informes de la prueba10** (volcados `i3-1115g4`, un HP con
  Fedora y GNOME, y `ryzen5-5600g`, con la integrada desactivada en la BIOS
  y una RTX 4060):
  - Batería · baja · la segunda lectura del volcado no guarda la batería:
    la potencia que sale de `energy_now` no se puede comprobar con un
    informe, solo en el equipo.
  - Gráficos · baja · las dos RTX 4060 de sobremesa (esta, con el 620, y
    la del volcado `i7-10700f`, con el 595) dan N/A en los tres consumos de
    `nvidia-smi`: sus 53 W salían de la media de las muestras, que ya no se
    usa, y ahora salen sin consumo. El volcado guarda qué llamada dio el
    consumo (`power_source`): falta confirmarlo con la próxima prueba de
    cada uno. El estado P (`GetPerformanceState`) no se graba.
  - Memoria · baja · el HP tiene `uncore_imc_free_running` con eventos de dos
    campos: sirve para probar el ayudante de la prueba11 con el IMC, además
    del Lenovo LOQ con DDR5.
* **De los informes de la prueba9** (volcados `i5-5200u`, `i7-4710hq`,
  `celeron-560`, `i5-8350u` y `core2-p8400`, rehechos; el informe del E6400
  con Mint en sesión live es el mismo equipo y no se vuelca):
  - Gráficos · baja · con una tarjeta en reposo no se pregunta a OpenGL,
    Vulkan ni OpenCL hasta que despierte, y la integrada se queda sin su
    versión del driver mientras tanto. OpenGL abre solo la gráfica de la
    pantalla: medir si `glxinfo` o EGL despiertan a la dormida
    (`power/runtime_status`) y, si no, preguntarle ya a OpenGL.
  - Memoria · baja · un zram con 0 B dentro dice «comprime 55.4 a 1».
  - Memoria · baja · el E6400 (ICH9M, DDR2) no registra ningún SPD, ni con
    5.10 ni con 6.14: `dmesg | grep -i spd` diría por qué.
* **Del portátil Lenovo LOQ 15IRH8** (volcado `i5-12450h`, de la prueba5):
  - Gráficos · baja · Mesa rechaza la UHD en Vulkan («Vulkan requires
    context isolation»), y desde la prueba6 la fila de Vulkan lo dice con
    ese motivo. Falta saber por qué su i915 no da aislamiento de contextos.
    Y «Versión del driver» y «Tomada del sistema» salen con guion porque
    vienen de esas API: esconderlas y decirlo al pie.
  - Red · baja · «J6C1» como ranura de la Ethernet: es lo que el firmware
    declara en SMBIOS tipo 9, y no le dice nada a nadie.
  - Placa · baja · la cabecera repite el firmware y el TPM de debajo.
  - Sensores · baja · la Wi-Fi sale como dos aparatos.
  - Gráficos · baja · la UHD no da uso por motor porque su PMU no publica
    eventos `*-busy` (solo frecuencia, RC6 e interrupciones). El aviso ya lo
    dice bien.
* **Del portátil Lenovo V130 y del sobremesa con Athlon 3000G** (anexos de la
  prueba5, sin volcado en la suite):
  - Memoria · baja · «Rangos: —» y «Voltaje: —» sin explicar cuando la
    tabla SMBIOS no los trae.
  - CPU · baja · en un Zen sin CPPC ni driver de frecuencia, «Multiplicador»
    y «Bus (BCLK)» salen con guion sin explicar: existen, pero sin CPPC no
    se derivan. Con la base leída de su P0 se podrían derivar (el reloj de
    referencia de Zen es de 100 MHz).
  - Almacenamiento · baja · se propone `drivetemp` aunque SMART ya da la
    temperatura. Y el firmware de un pendrive sale con guion.
  - Red · baja · `lo` sale con «Driver», «Modelo» y «Ranura PCI» a guion
    (también en los volcados de la suite).
  - Volcados · baja · `edid.resolve_vendors` lee el `pnp.ids` de quien
    ejecuta, no el del volcado; y un volcado sin el `name` de un bus i2c
    hace que `_hay_bus_de_memoria` abandone al primer fallo.
* **Del sobremesa con Ryzen 3 4100 y RX 550** (volcado `ryzen3-4100`, de la
  prueba6):
  - Gráficos · media · los códecs solo dicen MPEG-2 y JPEG: la Mesa de Fedora
    no trae H.264 ni HEVC (patentes), y los añade `mesa-va-drivers-freeworld`
    de RPM Fusion. Se podría decir en la tabla de códecs.
  - Gráficos · baja · el enlace va a x4 de x8 a 8 GT/s: hace falta saber si
    es el ahorro de energía de Polaris o el enlace de verdad. El volcado no
    guarda `pp_dpm_pcie`, que diría qué líneas pide la tarjeta en cada
    nivel.
* **Con la prueba7:**
  - Escritorio · baja · el monitor del sistema de KDE enseña Silux como
    `app.slice/app-@…` cuando se abre el AppImage con doble clic: Plasma
    nombra el *scope* de systemd por la entrada `.desktop` que lanzó, y un
    ejecutable suelto no tiene. `setDesktopFileName` ya está y no lo cambia.
    Abierto desde su entrada de menú sale con nombre. Arreglo posible: al
    arrancar en un `app-@…`, pedir a systemd (por D-Bus, sin permisos) un
    *scope* `app-silux@…` para el propio proceso, como hace Plasma.
* **Sin volcado, sin hacer todavía:**
  - SMART · baja · atributos conocidos (4, 192, 193, 196…) salen «propio del
    fabricante», y la temperatura en crudo sale empaquetada (64 427 589 655).
  - Modelo · baja · `dmi._firmware` guarda «BIOS heredada» y «UEFI (64
    bits)» en español: sale así en inglés y en `--json`. Cambiarlo es cambiar
    la API.
  - VM · baja · el historial de Rendimiento de la VM tenía una prueba «15 s ·
    — · — · —»: preguntar si la canceló.

## Datos que se leen mal o no se leen

* `providers/sysfs_cpu.py` · media · la máxima del kernel de cada tipo de
  núcleo se lee solo en su primera CPU. Con Turbo Boost Max 3.0 (o los
  núcleos preferidos de AMD) cada núcleo tiene la suya: un i7-12700KF da
  4,90 GHz en cpu0 y 5,00 en sus núcleos favoritos, y la página dice «El
  kernel limita a 4.90 GHz de los 5.00 GHz del silicio», que casi seguro es
  falso. Tiene que ser la máxima de las CPUs del tipo. El anexo guarda la
  `cpufreq` de una CPU por tipo: hace falta que guarde las de todas para
  probarlo con el volcado `i7-12700kf`.
* `providers/privileged_memory.py` · media · antes de SMBIOS 3.2, la velocidad
  configurada de un módulo (tipo 17) se daba en MHz de reloj, no en MT/s: en
  una DDR3-1600 son 800. Un FX-8150 con una BIOS de 2013 salía «800 MT/s de
  los 1600» con su aviso de que va lento, y probablemente va a 1600. Hace
  falta la versión de la tabla, que lee el ayudante y no va en el anexo: con
  el anexo ampliado se puede comprobar.
* `providers/hwmon.py` · baja · el ventilador de una GeForce con nouveau
  (`pwm1`, en %) sale en el grupo «Uso» de Sensores y no en «Ventiladores».
* `providers/hwmon.py` · media · `fam15h_power` publica como `power1_crit`
  el TDP del procesador (15,05 W en un A8-6410), y Silux lo trata como
  umbral crítico: a 16,6 W, dentro del turbo, Inicio dice «1 sensor en
  crítico». El ABI de hwmon dice que `crit` es donde el sistema actúa
  (apagar, frenar); en este driver es el TDP. Propuesta: no contar como
  alarma el `power1_crit` de `fam15h_power`, y enseñarlo como TDP. Además,
  su `power1_average` dio 0,7 mW y 8 mW en reposo en el volcado
  `a8-6410`, imposible con el equipo encendido: falta ver si la media del
  driver es fiable en la familia 16h.
* `providers/sysfs_cpu.py` · baja · con acpi-cpufreq y el turbo activo,
  `cpuinfo_max_freq` es la máxima sin turbo, que en AMD con CPB es la
  frecuencia base (2,0 GHz en el A8-6410): hoy dice «Base: —». Falta
  comprobar que vale en otros AMD anteriores a Zen y qué pasa en un Intel
  con acpi-cpufreq (su P0 es la base más 1 MHz).
* `providers/storage.py` · baja · la velocidad de giro de un SATA de platos
  conectado por dentro sale del mismo IDENTIFY que ya se lee de sysfs
  (palabra 217) y hoy no se lee: solo la tienen los discos de una caja USB,
  por udev.
* `smart.py` · media · en un SATA, atributos estándar como el 3 (tiempo de
  arranque), 4, 7, 10, 11, 192, 193 (ciclos de carga), 196 y 200 salen como
  «propio del fabricante». `drivedb.h` de smartmontools trae sus nombres por
  defecto; habría que sacarlos de ahí como las unidades. Visto en el informe
  de la prueba11 de un Athlon 3000G (un WD5000LPVX).
* `providers/storage.py` · baja · el modelo de un NVMe SK hynix sale con el
  guion bajo del firmware («SKHynix_HFS512GEJ4X112N») como nombre del
  dispositivo en Sensores.
* `amdgpu.py` · baja · los volcados de antes no guardan la revisión del chip
  ni la máscara de los «render backends»: una Navi 1x o 2x volcada así no
  tiene ROPs. Se arregla al volcarla otra vez.
* `ui/pages/memory.py`, `ui/pages/battery.py` · media · cinco sitios
  redondean voltajes a dos decimales en vez de usar `render.volts`, que usa
  tres. Se pierde el decimal que distingue los escalones del VID.
* `ui/pages/graphics.py` · baja · la tasa de datos de la VRAM, compuesta a
  mano.
* `spd.py` · media · el perfil 2 de XMP en DDR4 no se lee: no hay fuente de
  dónde va (memtest86+ solo lee el 1) ni un módulo que lo traiga. El
  perfil 1 (F-A2) se arregló con los módulos de un sobremesa con Gentoo.
* `spd.py` · media · `decode` revienta si el chip devuelve menos de 384 bytes,
  y se pierden todos los módulos, no solo el corto.
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

* `ui/pages/caches.py` · baja · en «Quién comparte qué», un bloque cuya
  etiqueta no cabe sale vacío: en un híbrido, la L2 de 1.25 MiB de cada
  núcleo P y la L1 de cada núcleo E (volcado `i7-12700kf`, a 1200 px). El
  dato está en la tabla de debajo, pero el bloque no dice nada.
* `ui/pages/storage.py` · baja · con Silux abierto como root, «Vida
  restante» de un pendrive se enseña y se esconde entre dos fotos iguales
  (`test_nada_se_mueve` como root, en el contenedor de
  `tools/probar_en_minimo.py`).

* **La terminal, solo en español** · menor · `cli.py` escribe el volcado
  con literales en español («Núcleo», «Reloj de memoria», «de N W»), sin
  pasar por `_()`. `tests/test_interface_language.py` mira la ventana, no la
  terminal.

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
* **F-M8 · `benchmark.py`** · media · el nombre y la descripción de cada
  carga del benchmark están escritos en español en `WORKLOADS` y se pintan
  tal cual con la interfaz en inglés. Deberían ser claves que se traducen al
  pintar, como ya lo son el tipo de firmware y los motivos de freno.
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

* `privileged/helper.py` · baja · aplazado por el autor: el TDP de fábrica
  de un Intel está en `MSR_PKG_POWER_INFO` (0x614), que el ayudante no tiene
  en su lista. Con él, un portátil cuya BIOS sube el PL1 por encima del TDP
  (un i5-5200U de 15 W con PL1 y PL2 en 25 W) lo diría al lado del límite.

* `privileged/helper.py`, `privileged/client.py` · media · los topes de
  tamaño del protocolo se comprueban después de reservar la memoria (F-M24),
  y el `timeout` de `request()` no acota la lectura (F-M25).
* **F-M26 · `privileged/client.py`** · media · tras una respuesta ilegible no
  se cierra el canal, y desde ahí cada respuesta llega con una de retraso.
* **F-M27 · `privileged/helper.py`** · media-baja · la lista blanca de MSR
  tiene nueve registros que no se usan. Va como propuesta antes que código.
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

* `tools/probar_en_minimo.py` · media · pasa la suite como root dentro del
  contenedor y sin `.git`, y el CI como usuario normal y con el repositorio:
  en `master` da 147 fallos que el CI no tiene (avisos y candados de
  permisos, `git ls-files`). No puede salir en verde; hasta arreglarlo, sirve
  comparando con lo que da sobre `master`.
* `tools/build_appimage.py` · baja · `--container` se traga `--keep` y
  `--appdir-only`; `appimagetool` se descarga en cada construcción sin fijar
  su hash.
* `.github/workflows/appimage.yml` · baja · `contents: write` para todo el
  flujo; las acciones van por etiqueta y no por SHA; comprobar que el
  AppImage arranca es un `--help`, que no carga el plugin de plataforma ni
  mira si pinta sus iconos.
* **F-M37 · `tools/probar_en_minimo.py`** · media · cualquier fallo del
  contenedor se anuncia como «la suite no pasa», y dentro corre como root.
  Como root no hay candados ni avisos de permisos, y `/proc/self/mounts` es
  el del contenedor: el 22 de noviembre de 2026 dio 88 fallos y 6 errores en
  `master`, los mismos test a test que con la zona 8 del inglés, y un
  `Segmentation fault` al salir. El CI, que no corre como root, pasa en 3.10.
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

* **La presión del sistema (PSI) para «¿Qué frena tu equipo?»** (idea, sin
  escribir). `/proc/pressure/{cpu,memory,io}` dicen qué parte del tiempo hubo
  tareas esperando CPU, memoria o disco: `some` y `full`, medias de 10, 60 y
  300 s y un total en µs, que es un contador y va por `providers/counters.py`.
  - Se lee sin permisos desde que existe (4.20, modo 0444; 0666 desde 5.13,
    y escribir pide CAP_SYS_RESOURCE salvo los avisos de 2 s desde 6.5).
  - Lo que cambia es si existe. Lo traen encendido Debian 12 y 13, Ubuntu
    22.04 y 24.04 (y Mint, que usa su kernel), Fedora, Arch, `gentoo-kernel`
    y Tumbleweed. Lo compilan apagado (`CONFIG_PSI_DEFAULT_DISABLED=y`)
    RHEL y CentOS Stream 9 y 10, openSUSE Leap 15.x y 16.0 y el kernel de
    antiX: sin `psi=1` en el arranque no hay `/proc/pressure` (desde 5.6;
    antes el archivo estaba y leerlo daba EOPNOTSUPP). Un kernel de Gentoo
    hecho a mano lo tiene si se activó (Kconfig: «Say N if unsure»).
  - La línea `full` de `cpu` no significa nada para todo el sistema: de 5.13
    a 5.18 da números, desde 5.19 ceros. `irq` (6.1, con
    `IRQ_TIME_ACCOUNTING`) solo está en Fedora, Arch, `gentoo-kernel` y
    CentOS Stream.
  - En un contenedor es la de todo el sistema, salvo con LXCFS (LXC,
    Incus), que pone la del contenedor.
  - Si falta, la nota dice que el kernel no lo publica, y que se enciende con
    `psi=1` cuando la configuración del kernel (`/proc/config.gz` o
    `/boot/config-*`) dice que está compilado y apagado.
  - Fuentes: `kernel/sched/psi.c` en cada etiqueta y la configuración de cada
    distribución; la tabla con sus enlaces, en las notas
    (`propuestas/propuesta-psi.md`).
  - Cómo, con las ideas de Felix Lara (su `psi_cpu_verdict.py`, con su
    permiso y su crédito en el código y en Acerca de): la presión de un
    intervalo es lo que avanza `some_total` (y `full_total`) dividido por el
    tiempo, por `providers/counters.py`, no las medias `avg10`/`avg60`. Si la
    presión de CPU coincide con la de memoria o la de disco, el cuello de
    botella probablemente es la RAM o el disco. Y su límite, dicho en la
    interfaz: PSI mide espera, no lentitud por hilo. En Python puro, sin
    pandas ni numpy.
  - El objetivo, de Felix Lara: ver con el tiempo cuándo el procesador se
    queda corto para lo que se le pide, para saber cuándo cambiar de equipo.
    Solo cuenta el tiempo con el equipo en uso, no el reposo; se guarda
    cuánto rato hubo espera alta, no solo la media; se enseña la tendencia
    de semanas o meses, y una carga larga (renderizar, compilar) sale tal
    cual, no como fallo.
  - Más adelante, con historial o bandeja: «¿Te hace falta más RAM?», con
    los días de presión de memoria de todo el sistema (`/proc/pressure/memory`)
    y los zócalos libres. Nada por programa: Silux no es un administrador de
    tareas.

* **Tendencias con el historial** (idea, a largo plazo). Con meses de
  medidas, ver si algo empeora: Mann-Kendall sobre una prueba térmica fija
  (la misma carga y la misma duración; la temperatura y la frecuencia
  sostenida del final) diría si la pasta térmica o el polvo empeoran el
  equipo. No supone ninguna distribución y aguanta huecos, pero pide bastantes
  medidas espaciadas. La temperatura de la habitación influye y no se lee: el
  resultado lo dice, y medir la subida sobre el reposo de antes de la prueba
  la compensa en parte.

* **El informe con permisos donde no hay polkit** (propuesta, sin escribir:
  toca privilegios). En antiX y otros sistemas sin systemd lo correcto es
  instalar `pkexec`, `libpam-elogind` y un agente de polkit
  ([dependencias.md](dependencias.md)). `sudo silux --report` funcionaría,
  pero corre el programa entero como root (Qt, los analizadores de SMBIOS,
  SPD y EDID, los hijos que preguntan a OpenGL y Vulkan), justo lo que el
  ayudante mínimo evita. La alternativa segura sería que `--report` lanzase el
  mismo ayudante con `sudo` en vez de `pkexec` cuando falta polkit: el resto
  seguiría sin privilegios. Falta el visto bueno del autor.

* **La frecuencia media de una Intel por el ayudante** (propuesta, sin
  escribir: toca su lista blanca). Sin permisos, la frecuencia es la media de
  las lecturas de `act_freq` que pillan despierta a la gráfica, cada 250 ms;
  con un video 4K60 (despierta el 18 % del tiempo) uno de cada tres segundos
  no la pilla ninguna y sale la pedida. El PMU de i915 publica
  `actual-frequency` y `requested-frequency` acumuladas por el kernel: dos
  eventos más en `PMU_EVENT`, del mismo PMU que ya se abre. Falta medirlo en
  el T14 contra `intel_gpu_top` y el visto bueno del autor.

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
  AppIndicator) y KDE. Donde no hay bandeja (un gestor de ventanas sin ella;
  `QSystemTrayIcon.isSystemTrayAvailable()`), la opción no se ofrece y Silux
  funciona como siempre. Y con eso, alertas opcionales por notificación del
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
    ya lee `tools/gen_memory_limits.py` para el máximo de memoria. Hoy 160
    de los 411 procesadores de referencia no tienen encapsulado en la tabla:
    casi todos anteriores a 2011, y los portátiles con zócalo (rPGA), que
    comparten nombre en clave con los soldados y solo se separan por el
    número de modelo.
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
