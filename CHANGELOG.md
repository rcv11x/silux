# Cambios

Lo que cambia en cada versión, contado para quien usa el programa: qué se ve
distinto y qué deja de funcionar como funcionaba. El porqué técnico va en los
mensajes de commit y en [docs/](docs/), que tienen otro lector.

Cada copia dice de qué versión y de qué commit salió: `silux --version`, la
barra lateral y la cabecera del informe. Al pedir ayuda, ese par es lo primero
que hace falta.

---

## Sin publicar

### Mejoras

- Las pruebas de disco y de memoria se comparten como imagen: «Copiar como imagen» y «Guardar…» bajo su resultado, sin la carpeta donde se hizo ni el nombre del equipo
- La imagen del equipo, con el diseño de las de las pruebas: el procesador y la gráfica de título, y al pie la versión y dónde está Silux
- La barra lateral se encoge a solo los iconos con el botón de su panel, junto al logo; al pasar el ratón dice el nombre de cada sección, y se queda como la dejaste
- La marca de la sección abierta se desliza por la barra lateral hasta la nueva en vez de saltar; se quita en Ajustes → Apariencia
- Cambiar de tema, de densidad o de letra tarda la mitad: menos de un segundo en un sobremesa
- Color de acento en Ajustes → Apariencia: ámbar, azul, verde, rojo o morado, cada uno legible en claro y en oscuro; cambia todo a la vez, sin reiniciar, y con el azul lo que tiene arreglo y los candados pasan a morado
- El ámbar del tema claro, un poco más oscuro: el texto de los botones principales y de las etiquetas se lee mejor
- En Almacenamiento, las fichas de lectura, escritura y temperatura pueden enseñar una sola unidad: se elige en el desplegable «Unidad», encima de ellas, o pulsando su fila en «Unidades», con su gráfica desde que se abrió Silux, y se recuerda
- En Sensores, clic derecho en un sensor para fijarlo arriba, en su propia rama con el nombre de su aparato; se recuerda
- La salud de cada disco de un vistazo, en su tarjeta de Almacenamiento (que lo nombra por su dispositivo y su modelo): «Bien», «Vigilar» o «Haz copia ya», con el porqué una sola vez y arriba un resumen de los que piden atención, solo con lo que declara el propio disco o la especificación de NVMe; en SATA llega como mucho a «Vigilar»
- Dispositivos lista lo que no tiene driver del kernel (una wifi, un controlador USB, el sonido, algo enchufado por USB) con su ID y qué se puede hacer, y de los que se conocen, el driver y el paquete que les faltan (la wifi Broadcom BCM43142); un driver que se carga se ve al momento
- En una Radeon, Gráficos calcula las unidades de sombreado y de texturas, los TFLOPS en FP32 y los rellenos de píxeles y texturas, cada cifra marcada como calculada, con el reloj al que se calculó («41.3 TFLOPS (calculado a 2.52 GHz)») y su fórmula al pasar el ratón
- La prueba de disco tiene un perfil «Personalizado»: patrón, bloque y cola a elegir, con un hilo; su comparación con la vez anterior y su historial van solo con pruebas iguales
- Los botones, desplegables y casillas llevan la letra del resto del programa en todas las páginas y crecen con el tamaño de letra de Ajustes; un botón que no cabe parte su texto en dos líneas
- Los desplegables miden lo que su opción más larga, con un mínimo y un tope, y no se estiran a todo el ancho
- El informe y su anexo llevan el nombre y el ID de lo enchufado por USB y de las cámaras (nunca su número de serie), para reconocer un lector de huellas o una cámara de infrarrojos

### Arreglos

- En una ventana estrecha, el selector de secciones («Almacenam…») y el texto de la barra de estado ya no se cortan
- En la prueba de disco, «Dónde» mide lo que su texto pide, con un tope, y no todo el ancho de la ventana
- En Rendimiento, los desplegables, sus etiquetas, «Medir también la escritura» y los botones del historial iban con una letra más pequeña que el resto
- Con la letra más grande de Ajustes, los botones y los desplegables se quedaban del tamaño de siempre
- En Sensores, el globo del consumo del procesador decía «intel-rapl · rapl/package_w», también en un Ryzen: ahora dice «RAPL del kernel (powercap)»
- En Gráficos, la línea bajo el uso o la frecuencia de una integrada de Intel aparecía y desaparecía al pasar por 0, y la página se movía
- Un Ryzen con el turbo apagado en la BIOS salía como «Este procesador no tiene turbo»: ahora dice que está desactivado
- Con la base cambiada a mano en la BIOS, CPU y la imagen del equipo daban como máxima la que el kernel calcula sobre esa base (5.36 GHz en un Ryzen 7 5800X que llega a 4.7): ahora no la dan, y dicen la base de fábrica y el turbo de AMD
- Con nouveau, una GeForce que no publica ningún sensor (una RTX 3070) salía con «Temperatura: —» y un aviso que prometía la temperatura: ahora dice que nouveau no la publica en esa tarjeta
- Inicio dice por qué una gráfica sale sin ninguna cifra cuando es cosa de su driver (nouveau), en vez de enseñar solo su nombre
- En la terminal, las categorías de Sensores salían como claves («cat.temperature») y quién montó la gráfica con su razón social («Micro-Star International Co., Ltd. [MSI]»)
- Una wifi Atheros AR242x salía como «Ethernet» en los dispositivos PCIe de Placa base: declara esa clase, pero es inalámbrica
- En Sensores, los sensores del firmware de un portátil salían como un aparato con el nombre del kernel («dell_smm», «thinkpad», «hp»), con dos «CPU (dell_smm)» iguales: ahora van con el equipo, numerados si se llaman igual, y el chip se nombra en palabras («ACPI», «Dell») solo cuando hace falta
- El ventilador de un portátil salía como «cpu_fan»: ahora «Ventilador del procesador»
- Placa base decía «Chip de sensores: ASUS» en placas sin driver de Super I/O: era el firmware de la placa
- Una batería que no da su tensión, o da una imposible, salía en Sensores con «0.000 V» o esa tensión, mientras Batería decía que no la da
- Una GeForce de la revisión «Lite Hash Rate» llevaba eso en el nombre: ahora «GeForce RTX 3070 LHR», como la vende NVIDIA
- Los frenos por temperatura salían sin separador de miles y con «(0.0 s)» cuando el kernel los cuenta sin su tiempo: ahora «128 753 en los núcleos»
- En el diagnóstico de un disco SATA, la temperatura del atributo 194 (y la del aire, 190) salía como un número enorme («en crudo 176 094 576 668»): ahora como smartctl, «28 °C, mín 14, máx 41»; y el 192 tiene su nombre, «Apagados sin cerrar bien»
- Un SSD que no publica su desgaste como manda el estándar (un KIOXIA EXCERIA, con su atributo 173 al 141 %) decía «Vida restante —»: ahora dice que el disco no lo publica

## 0.4-prueba14 (27 de noviembre de 2026)

### Lo destacado

- Una versión de arreglos, con lo que salió en los informes de la prueba13
- La página de Rendimiento ya no se queda en blanco después de la prueba de procesador
- El informe lleva enteras tus últimas pruebas de memoria y de disco

### Mejoras

- La cabecera del informe dice qué valores son de ejemplo: el nombre del equipo, las direcciones IP y MAC, las carpetas de los discos
- La vista previa del informe y la terminal ya no dicen que esos datos se quitan: se cambian por otros de ejemplo
- Sin permisos, Memoria dice cuánta memoria suman los módulos leídos cuando no es toda la del equipo
- El anexo del informe ya no toma por dormida una gráfica que el sistema tiene para una máquina virtual, y dice que es suya
- El anexo guarda dónde empieza cada partición, para saber en qué parte del plato se hizo una prueba de disco
- `--json` dice a qué velocidad va cada módulo de memoria
- Rendimiento ocupa todo el ancho de la ventana, como las demás páginas: en una pantalla ancha dejaba mucho hueco a los lados
- En Rendimiento, la tabla de pruebas anteriores usa el ancho, la descripción se lee a un ancho cómodo y «Renombrar» y «Borrar» son botones como los demás

### Arreglos

- La página de Rendimiento se quedaba en blanco tras una prueba de procesador, también la rápida
- El informe no llevaba las pruebas de memoria y de disco, aunque la prueba13 decía que sí
- En el informe corto, la carpeta de la prueba de disco salía sin tapar: en una memoria USB, con tu usuario y su etiqueta
- Con dos gráficas dedicadas, Inicio enseñaba la que no tiene el monitor (la que se reserva para una máquina virtual)
- Inicio decía la velocidad de catálogo de la memoria y no a la que va («DDR5-4800» con un perfil EXPO a 6000)
- Dos discos del mismo modelo salían juntos en Sensores, con cada temperatura dos veces y «(nvme)» detrás
- La versión del driver de Vulkan de NVK salía como «Mesa 26.0.128»
- Los chips de memoria de una Radeon salían en minúscula («hynix», «samsung»): ahora con su marca (SK Hynix, Samsung)
- El reloj del núcleo de una Radeon saltaba entre «en reposo» y cifras como 41 MHz: ahora es la media del segundo, y «en reposo» solo cuando el núcleo estuvo apagado todo ese tiempo
- Sensores da el mismo reloj del núcleo de una Radeon que Gráficos, y «en reposo» en vez de «0.0 MHz»
- Con el núcleo de una Radeon en sueño profundo, la fila de escalones decía «en reposo»: ahora dice a qué reloj está
- El voltaje del núcleo de una Radeon salía «en reposo» por debajo de 0,1 V aunque el driver diera una cifra: ahora sale la cifra (como «0.006 V»), y «en reposo» solo cuando el driver da 0
- Ctrl+C en la terminal no cerraba Silux, y SIGTERM lo mataba sin parar las pruebas en marcha: los dos lo cierran ya como el botón de cerrar
- En un sistema que arranca sin initramfs, Almacenamiento no decía dónde está montada la raíz, y una prueba de disco en ella no enseñaba su resultado
- En Sensores, la media de una lectura que no cambia podía salir una décima por encima del máximo (75.9 frente a 75.8 en un NVMe)
- En una ventana estrecha, la tabla de pruebas anteriores de Rendimiento ensanchaba la página y cortaba el texto por la derecha: ahora se desplaza por dentro
- La pestaña abierta de Rendimiento, en negrita, se cortaba por los bordes («Memoria», «Disco»)

### Problemas conocidos

- En btrfs, la escritura aleatoria 4K con 32 peticiones sale un 12-15 % por debajo de fio
- En btrfs, la lectura secuencial con 8 peticiones por io_uring sale un 5 % por debajo de fio
- En procesadores con dos tipos de núcleo o dos CCD, la prueba de memoria mide solo uno
- El camino AVX-512 de la prueba de memoria funciona, pero aún no se ha comparado con otras herramientas
- Que una NVIDIA de portátil se quede dormida solo se ha probado en un modelo
- En KDE, Dolphin puede no enseñar el icono del AppImage

## 0.4-prueba13 (26 de noviembre de 2026)

### Lo destacado

- Nueva prueba de disco, escrita desde cero en Rust (experimental)
- Secuencial y aleatoria 4K, con muchas peticiones a la vez y de una en una, en lectura y, si quieres, en escritura
- Comparada con fio en dos NVMe: dentro del 1 % en secuencial y del 2,5 % en aleatoria 4K, en ext4
- Probada en un SSD SATA, un disco de platos y unidades USB, con ext4, btrfs, exFAT y FAT32
- Nueva prueba de memoria, escrita en Rust (experimental): la latencia de cada nivel de caché y de la RAM, y el ancho de banda leyendo, escribiendo y copiando
- Comparada con multichase, lmbench, STREAM e Intel MLC
- Sustituye a la medida antigua en Python, que queda solo como reserva al ejecutarlo desde el código sin el módulo nativo
- Portátiles con NVIDIA: Silux ya no mantiene despierta la gráfica

### Mejoras

- Los resultados de disco se comparan con tu prueba anterior del mismo disco y perfil («▲ 8 %», «▼ 12 %»)
- Los cambios de menos del 3 % se toman como ruido y no se enseñan
- Mientras mide, la prueba en marcha se resalta y su barra crece suave
- La tabla del resultado de disco lleva las cifras más grandes, en negrita y junto a su barra
- En pantallas anchas, la petición suelta, el uso del enlace y la temperatura van en una sola fila
- Antes de empezar, la prueba de disco dice cuánto va a tardar y cuánto va a escribir
- Al acabar, dice cuánto escribió de verdad
- El perfil «Uso real» hace solo las pruebas de una petición cada vez, en la mitad de tiempo
- En FAT32, avisa antes de empezar si el archivo no cabe y ofrece el más grande que cabe
- En memorias USB lentas, dice cuánto tardará en crear el archivo de la prueba, antes y durante la prueba
- Mientras FAT32 reserva el espacio del archivo, la barra de progreso sigue avanzando y dice qué está haciendo
- Si el sistema de archivos pasa la prueba por la RAM (FAT32, exFAT o NTFS), la prueba se para y te lo dice
- Si el disco se desconecta a mitad, la prueba lo dice así
- En un disco de platos, el resultado dice en qué parte del plato estaba el archivo de la prueba
- Sin io_uring (en un contenedor, por ejemplo), mide con hilos y llama a cada prueba por lo que hizo de verdad
- El archivo temporal de la prueba nunca se queda, aunque Silux se cierre a mitad
- Cuando más de dos cifras varían entre vueltas, el aviso ya no las nombra todas: las marcas «*» dicen cuáles
- El globo del código de cada prueba (SEQ1M Q8T1…) ya no tapa la fila de abajo
- Almacenamiento enseña la velocidad del enlace de cada disco (SATA a 6 Gb/s, USB a 5 Gb/s)
- Almacenamiento enseña el último resultado de cada disco; al pulsarlo se abre la prueba
- Con permisos de administrador, la prueba de memoria dice qué porcentaje del máximo teórico de tu memoria alcanza
- El informe lleva enteras tus últimas pruebas de memoria y de disco
- Si Silux se cierra a mitad, la prueba de memoria se para y suelta su memoria
- Textos más claros en las pestañas de Disco y Memoria
- Las cabeceras de Disco y Memoria tienen más aire, con el progreso en su propio bloque y una barra más gruesa y redondeada
- En ventanas estrechas, los títulos de las tablas ocupan dos líneas como mucho y se acortan si hace falta
- Los avisos se ponen al día cuando cambia su texto, sin salir de la página
- Una NVIDIA sin sensor de consumo (como la RTX 4060 de sobremesa) enseña lo que estima su driver en su propia fila, con ese nombre
- Una gráfica apagada dice ahora «Dormida» en vez de «En reposo»
- El informe dice qué devolvió cada forma de leer el consumo de una NVIDIA
- El pie de los sensores ya no llama «GeForce» a una tarjeta profesional
- Cuando no se puede leer el consumo de una integrada de Intel, Gráficos explica por qué
- En un contenedor, el aviso de RAPL culpa al contenedor, no a la CPU
- `--report` en un sistema sin las bibliotecas gráficas escribe el informe corto en vez de fallar
- El informe escribe el tamaño de cada caché con sus decimales («1.25 MiB»)
- Las casillas marcadas enseñan su marca en los temas claro y oscuro
- Los botones desactivados se ven desactivados
- En el tema oscuro, la parte vacía de una barra enseña dónde está el 100 %
- El aviso de «Copiado» sale junto al valor

### Arreglos

- Gráficas integradas con su nombre en clave en vez de su nombre («AlderLake-S GT1» en vez de «UHD Graphics 770»)
- Integradas de AMD sin nombre conocido, tituladas con el nombre en clave del procesador («Raphael»)
- Ventiladores de gráfica que salían parados mientras giraban
- El voltaje del núcleo de una Radeon en reposo, como «0.006 V»
- Temperaturas de la memoria y los reguladores de una Radeon que no las mide, como 0 °C
- Sensores de la placa sin nada conectado (0 °C y −1 °C en los chips nct67xx), como si fueran lecturas
- Lectores de tarjetas vacíos, como unidades «SSD · 0 B»
- El escritorio como «X-Cinnamon» o «ubuntu:GNOME»
- Una sesión gráfica arrancada desde la consola, como «tty»
- La marca de un monitor, dos veces («LG LG HDR 4K», «Hewlett Packard HP 27wm»)
- La OpenCL de ROCm con la versión de Mesa
- Chipsets de Intel sin reconocer con un pci.ids antiguo cuando el modelo va al final del nombre («H670»)
- El USB y el sonido de los procesadores AMD con gráfica integrada, en la gráfica
- Lecturas de consumo imposibles de una NVIDIA de portátil al despertar (588 W)

### Problemas conocidos

- En btrfs, la escritura aleatoria 4K con 32 peticiones sale un 12-15 % por debajo de fio
- En btrfs, la lectura secuencial con 8 peticiones por io_uring sale un 5 % por debajo de fio
- En procesadores con dos tipos de núcleo o dos CCD, la prueba de memoria mide solo uno
- El camino AVX-512 de la prueba de memoria funciona, pero aún no se ha comparado con otras herramientas
- Que una NVIDIA de portátil se quede dormida solo se ha probado en un modelo
- En KDE, Dolphin puede no enseñar el icono del AppImage

## 0.4-prueba12 (24 de noviembre de 2026)

Con informes de Anianin27, Erziok, Felix Lara, jwpitr y widecoocaa23_.

El AppImage compatible ya no pide un sistema más nuevo que el normal (glibc
2.30); los Intel híbridos, con sus núcleos P y E como secciones, la máxima
de todas sus CPUs y los núcleos favoritos; los módulos del kernel que faltan
se cargan desde Silux (cambia el ayudante), y lo que trajeron los informes de
la prueba11: el disco SATA en una caja USB, los AMD anteriores a Zen y las
NVIDIA cuyo driver no da el consumo.

- Gráficos: sin consumo medido, la ficha de Consumo dice el límite por su
  nombre («límite 115 W») bajo el guion, y no «de 115 W», que se leía como
  una cifra sobre 115.
- Inicio y Gráficos: en una integrada de Intel, lo que falta por permisos
  se dice tal cual. Donde el consumo ya se lee sin permisos (RAPL legible,
  como en Fedora), la ficha dice «El uso, con permisos» y el aviso habla
  solo del uso; «El uso y el consumo» queda para cuando faltan los dos.
- Gráficos: una integrada ya no se llama como el equipo en el que va («HP
  EliteDesk 800 G1» en vez de «HD Graphics 4600»): el nombre que pci.ids da
  al subsistema solo cuenta si es el de la tarjeta. Sin pci.ids en el
  sistema, una gráfica de Intel se llama por la tabla de Mesa que lleva
  Silux, y otra sin nombre, por su marca («AMD, gráfica integrada») en vez
  de «Gráfica 0».
- CPU: si el procesador no publica su reloj base por ninguna vía (los AMD
  anteriores a Zen), la fila «Base» ya no sale con un guion: lo dice el
  aviso de la página.
- Ajustes → Acerca de: entre los datos de terceros salen también
  smartmontools y Mesa, de donde salen las unidades del SMART y el nombre de
  las gráficas de Intel; sus avisos ya iban en el programa.
- Cachés: en «Quién comparte qué», un bloque estrecho ya no se queda en
  blanco: lleva su tamaño corto («48K», «1.25M»), o una vez por cada tramo
  de bloques iguales («4 × 32K») si ni eso cabe, y al pasar el ratón cada
  bloque dice su nivel, su tamaño y qué CPUs lo comparten.
- CPU: la máxima de cada tipo de núcleo es la de todas sus CPUs, no la de
  la primera. Con núcleos favoritos (Turbo Boost Max 3.0, los preferidos de
  AMD), Relojes dice cuáles llegan más alto, en vez de «El kernel limita a
  4.90 GHz de los 5.00 GHz del silicio».
- CPU: un límite de potencia de 4095 W, lo máximo que cabe en el registro,
  es la forma del firmware de no poner ninguno: sale como «sin límite»
  (el PL2 de muchas placas de sobremesa), y ya no cuenta como umbral
  crítico del consumo en Sensores.
- CPU: en un procesador híbrido, «Núcleos P (rendimiento)» y «Núcleos E
  (eficiencia)» son el título de su grupo de tarjetas, con una raya hasta el
  borde; antes eran una línea gris y pequeña entre tarjetas. En el informe
  corto son encabezados, como cada gráfica.
- AppImage compatible: arranca en sistemas más antiguos. Pide glibc 2.30
  (Ubuntu 20.04, Debian 11 y posteriores) en vez de 2.35, que era más de lo
  que pide el normal.
- AppImage: el archivo lleva el logo (`.DirIcon`, en PNG de 256 px), que es lo
  que enseñan los gestores de archivos con vista previa de AppImage.
- Placa base: un chipset que la base de datos PCI del sistema no conoce ya no
  sale con dos guiones: lo dice al pie.
- Informe: un aparato USB que se llama solo por lo que es («Controller», el
  nombre de muchos mandos) ya no se toma por un dato de la persona: el anexo
  quitaba el modelo de cada nombre PCI que llevara esa palabra.
- CPU: el voltaje del núcleo de los AMD anteriores a Zen (y de Zen 5) ya no se
  lee con el formato de los Ryzen, que daba una cifra falsa (1.550 V en un
  FX-8150): el aviso dice que esta versión no sabe leer ese formato.
- AppImage: si el normal no puede arrancar en ese procesador, lo primero que
  dice es qué descargar y de dónde, también como notificación del escritorio
  cuando se abre con doble clic. La lista de procesadores de cada AppImage
  está comprobada familia a familia: los Atom anteriores a 2013 y los AMD
  Llano y Bobcat, aunque sean de 2011, necesitan el compatible.
- CPU: en los AMD con `fam15h_power` (de Bulldozer a Puma), lo que el driver
  publica como potencia «crítica» es el TDP: sale como «TDP» en Potencia y
  reposo, y pasarlo un rato con el turbo ya no da «1 sensor en crítico».
- Almacenamiento y Memoria: con el ayudante desfasado, «Actualizar el
  ayudante» sale como en Inicio: naranja, el primero y con «Ahora no»;
  antes salía gris, debajo de «Qué hace esto».
- Sensores: un disco SATA con drivetemp se llama por su modelo («KIOXIA-EXCERIA
  S»), sin el «ATA» de relleno delante.
- Interfaz: en las tablas de etiqueta y valor, un valor largo baja de línea
  en vez de cortarse con «…» («Linux 7.…», la compilación, la línea de
  arranque). Y en una tarjeta estrecha con letra grande, cada etiqueta
  va encima de su valor, que ocupa el ancho entero.
- Discos: un SATA en una caja USB que deja pasar los comandos ATA sale con
  su propio modelo, firmware y tipo (SSD o de platos, y a cuántas rpm),
  que udev ya le preguntó al disco; la caja va aparte («Adaptador USB:
  JMicron»). «Por USB no se sabe…» solo queda cuando el disco no contesta.
- Discos: «Escrito en total» ya no sale cuando no se sabe la unidad de ese
  disco (sin su modelo, detrás de una caja USB), ni cuando la cifra es más
  de lo que el enlace pudo mover en sus horas encendido. Un Kingston A400
  con 9630 GiB salía con 4.9 MB.
- CPU: con el driver acpi-cpufreq y el turbo activo, la máxima que publica
  el kernel es la de sin turbo: ya no sale como techo («2.26 GHz (1.00 –
  2.00 GHz)») y un aviso dice que no se sabe hasta dónde sube.
- AppImage compatible: en un procesador que puede con el normal, Ajustes →
  Acerca de lo dice en una línea, con el nombre del archivo que conviene.
- Inicio: si la placa es el propio equipo y no hay chipset que nombrar, la
  ficha de la placa lleva de titular el tipo de firmware («BIOS heredada»,
  «UEFI (64 bits)») y debajo la versión de la BIOS. Una versión larga
  sin espacios sacaba la página por la derecha con la letra más grande.
- Placa base: un equipo cuyo nombre ya lleva la marca no la repite
  («Lenovo B50-45», no «Lenovo Lenovo B50-45»), y «Not Defined» ya no
  sale como revisión.
- Bienvenida: es una ventana de diálogo del programa, con su barra de
  título: sale centrada encima de Silux (en Wayland la coloca el
  escritorio, y antes podía salir en una esquina con la ventana grande) y
  se puede mover y cerrar.
- Interfaz: el nombre de una versión de prueba es el de su release en
  cualquier idioma: «0.4-prueba11», no «0.4-test11» en inglés.
- Informe: el anexo ya no se queda fuera con un disco en una caja USB cuyo
  adaptador rellena el número de serie con bytes nulos (ese número sí se
  tapaba; la comprobación lo tomaba por otro). Y si algo lo deja fuera, el
  informe dice de qué archivo salía, sin enseñarlo.
- Sistema: la descripción más larga de una vulnerabilidad sale entera con la
  letra grande, en vez de cortada con «…».
- CPU: sin el módulo `msr`, el aviso del voltaje (y de la frecuencia base en
  los AMD que la necesitan) tiene «Cargar ahora», como el de la temperatura
  de los discos: lo carga hasta que se apague el equipo, sin escribir nada,
  y deja la línea para copiar si se quiere siempre. Si el ayudante falla por
  otra cosa, ya no culpa al módulo.
- Interfaz: con una letra ancha (DejaVu Sans, la de Debian y Ubuntu), los
  títulos largos de las tarjetas y los avisos bajan de línea en vez de sacar
  la página por la derecha con la letra más grande. Y en Inicio las cifras ya
  no saltan a una segunda línea moviendo la fila: cada ficha reserva lo que
  su pieza puede llegar a decir (el reloj hasta su máxima, la temperatura
  hasta su límite) y, si eso no cabe en una línea, ocupa dos desde el
  principio. Las columnas siguen siendo iguales.
- Interfaz: «Calculando…» y las demás palabras que van en lugar de una cifra
  («con el cargador») caben enteras en las fichas grandes: bajan de tamaño
  lo justo cuando no hay sitio, también con la letra más grande. Antes salía
  «Calculandc» en CPU.
- Textos: con una sola cosa, en singular («1 módulo», «1 núcleo · 1 hilo»,
  «1 de 1 activa», «1 ciclo»…). La imagen para compartir ya no deja un «—»
  donde falta un dato: lo quita.
- Discos: un SATA ya no suma en «datos que no se pudieron leer» tres
  contadores distintos. El aviso dice cuántos sectores hay sustituidos por
  otros de reserva, cuántos no se pueden leer ahora y cuántos no pudo leer su
  revisión interna, cada uno con su atributo SMART (5, 197 y 198).
- CPU: sin driver de frecuencia, la ficha ya no dice que la frecuencia es
  fija (dice hasta dónde llega), y se explica que la de cada hilo es la
  efectiva que mide el procesador (APERF/MPERF) mientras trabaja, y la
  nominal en reposo.
- Gráficos: una gráfica integrada dice dónde va, «en el procesador» o «en el
  chipset» (las Intel anteriores a Clarkdale), en su cabecera y en la lista
  de la placa. La de una APU de AMD ya no enseña su enlace PCIe interno como
  si fuera una ranura, ni una Resizable BAR, e Inicio dice que su
  temperatura es compartida con la CPU.
- Gráficos: los ROPs de una AMD salen de contar cuatro por cada «render
  backend», y ocho desde RDNA2: una RX 550 tiene 16 (salían 8) y una Vega 3,
  4 (salía 1). Y un ROP es una unidad de salida de render, no de
  rasterizado.
- Memoria: la tabla de perfiles tiene la latencia de cada uno en
  nanosegundos, el tAA que declara el chip SPD (en DDR2, su CL por el ciclo
  que da el chip para él). Es la del chip, no la de todo el camino, y nunca
  sale de la velocidad que ha puesto la BIOS.
- Anexo del informe: cada tarjeta de red lleva su propia dirección física
  sustituta, la misma que arriba; antes todas salían con una sola.
- Batería: «Retenida en el tope» solo cuando está llena. Enchufada y sin
  cargar por debajo, dice eso, o «En modo conservación» cuando el portátil lo
  tiene puesto (el de Lenovo, y el Long_Life del kernel), que además sale en
  sus límites de carga.
- Informe: cada tipo de núcleo de un procesador híbrido y cada gráfica son
  un apartado con su encabezado, y lo de dentro baja un nivel; antes su
  nombre era una línea suelta que parecía del texto de arriba.
- Informe: la cifra fija de una zona térmica que no mide (un acpitz a 27,8 °C)
  dice en el árbol de sensores que no es una medida; en la ventana ya salía
  en gris, pero el informe no tiene color.
- Memoria: el fabricante y la referencia de un módulo dicen «según la BIOS»
  cuando salen de la tabla del firmware y no de su chip SPD, igual que la
  velocidad y el voltaje, y en todos los módulos por igual. En una DDR5 de
  la que solo se lee la primera página del chip, los dos salen de la BIOS.
- Memoria: la temperatura de cada módulo sale en ámbar o rojo según los
  límites que declara su chip (el de DDR5 da 55 y 85 °C), como en Sensores,
  y al pasar el ratón dice cuáles son.
- Temperaturas: un Ryzen de Zen 2 en adelante, que no declara sus límites,
  avisa en ámbar desde el Tjmax de su ficha en amd.com (90 °C un 5800X3D),
  y nunca en rojo: la ficha no dice dónde se apaga el equipo. Al pasar el
  ratón se dice de dónde sale. Antes de Zen 2 no se usa: la cifra de la
  ficha no se compara con lo que se lee.
- Módulos del kernel: «Cargar ahora» carga el que falta (la temperatura de
  los discos SATA, el chip SPD de la memoria) solo hasta que se apague el
  equipo, y sale en Sensores, Almacenamiento y Memoria. Para que se cargue
  siempre, el aviso deja la orden para copiar: Silux ya no escribe en
  `/etc/modules-load.d/`. Los permisos instalados piden actualizarse.
- Interfaz: con la letra más grande y la ventana estrecha, ninguna página se
  sale ya por la derecha: los títulos y las cifras bajan de línea, las filas
  de botones se ponen en columna y el título de un plegable largo se
  recorta (entero al pasar el ratón). Antes se cortaba casi todo a 760 px.
- Sensores: dos discos del mismo driver (dos NVMe) compartían una fila, y
  con ella el mínimo, el máximo y la media, que mezclaban los dos discos.
  Ahora cada uno tiene la suya.
- Temperaturas: el color sale solo de los límites que declara la propia
  pieza: normal, ámbar desde su máximo y rojo desde su crítica (si son la
  misma cifra, directo a rojo). Silux ya no se inventa límites para lo que no
  los da (un Ryzen se ponía amarillo hacia los 80 °C, y un disco SATA sin
  SCT lo hacía desde 55 °C), ni tiñe poco a poco al acercarse. Los valores
  de relleno que dejan algunos chips (0, −273,15 o 65261,85 °C) no cuentan
  como límite.
- Temperaturas: el mismo color en Sensores, en el aviso y las tarjetas de
  Inicio, en la pestaña CPU, en la de la gráfica y en los discos (la tabla de
  unidades, «Más caliente» y la ficha de cada disco, que dice sus límites).
- Temperaturas: los límites salen sin decimales, como los da la pieza (un
  NVMe los declara en kelvin enteros: 358 K son 85 °C).
- Fahrenheit: toda temperatura pasa por las mismas funciones. Ya no se
  quedan en °C los límites que se ven al pasar el ratón en Sensores, la
  gráfica de temperaturas de Inicio (que guardaba cifras en Celsius) ni
  «Más caliente» cuando ningún disco da temperatura; en °F, la diferencia de
  la deriva térmica del benchmark es ×1,8, sin sumar 32.
- Gráficos: una NVIDIA cuyo driver no da el consumo (`nvidia-smi` lo da como
  N/A) sale sin consumo, con su aviso, y no con la media de su búfer de
  muestras, que el driver no da como su consumo: una RTX 4060 sin consumo
  marcaba 53 W.
- Memoria: un valor marcado «según la BIOS» o «según la BIOS, no coincide»
  baja de línea en vez de cortarse con puntos suspensivos, que escondían
  justo la marca.
- Memoria: sin permisos, la cabecera ya no dice que el resto de la memoria
  no tiene chip SPD, que no se sabe (el kernel puede no haberlo registrado):
  dice que no se ha podido leer.
- Memoria: un voltaje que sale del chip SPD y no de la BIOS dice «nominal
  del SPD»: es para el que está hecho el módulo, no el que tiene puesto.
- Gráficos: si no se ha podido preguntar a qué resolución va cada monitor,
  la columna se llama «Resolución preferida» (en dos líneas, para que la
  tabla quepa como antes), no solo el pie; el resumen de la terminal y del
  informe dice «(la preferida)».
- `--json`: `resolution` de un monitor es solo la que tiene puesta, y
  `voltage_mv` de un módulo, solo la de la BIOS; lo que sale del EDID y del
  SPD va en `preferred_resolution` y en `nominal_voltage_mv`.
- Batería: una que no da su potencia ni su corriente, solo su energía, ya no
  se queda en «Calculando…»: la potencia sale de cuánto baja o sube la
  energía entre dos puestas al día del firmware, y lo dice al pasar el
  ratón.
- Informe: el anexo dice qué llamada de NVML dio el consumo de una NVIDIA,
  para saber de dónde sale una cifra que no cuadra con `nvidia-smi`.

## 0.4-prueba11 (23 de noviembre de 2026)

Con informes de Felix Lara.

La bienvenida de la primera vez y los accesos directos con un interruptor
cada uno; el tráfico de la memoria en los Intel de Tiger Lake y Alder Lake
(cambia el ayudante), y lo que trajeron los informes de la prueba9 y la
prueba10: la memoria y la batería de un portátil con DDR2, la gráfica
dedicada dormida de un Optimus y el nombre de los portátiles HP.

- Memoria: el tráfico de la memoria se lee también en los Intel cuyo
  controlador escribe sus contadores con dos campos (Tiger Lake y Alder
  Lake), que el ayudante no sabía abrir y daba por inexistentes. Cambia el
  ayudante: Ajustes pedirá actualizarlo.

### Privacidad

- El anexo del informe lleva una segunda lectura de los contadores del
  equipo (el uso de cada hilo, el reposo, la frecuencia, el tráfico de la
  red y los discos, los sensores), un segundo después de la primera: con ella
  se reproduce lo que sale de restar dos. Son unos 10 KB, y solo números.
- El anexo del informe lleva el EDID de cada monitor con solo su número de
  serie tapado (y su suma de control al día). Antes, una tele que escribe
  «01 01 01 01» como número de serie, que en EDID quiere decir «sin número»,
  se quedaba sin EDID.
- De lo enchufado por USB, el anexo lleva ahora sus identificadores
  (vendor:product), que dicen el modelo y no la persona. Lo que escribe el
  propio aparato (su nombre y su fabricante) y su número de serie siguen sin
  ir.

### Bienvenida

- Nuevo: la primera vez que se abre Silux sale una bienvenida de dos
  pantallas. Trae marcados el idioma del sistema y el tema del escritorio, y
  deja elegir idioma, tema y tamaño de letra mientras la ventana de detrás
  cambia al momento; ofrece añadir Silux al menú de aplicaciones y dice en
  una frase qué son los permisos. Se salta con un botón, no pide contraseña
  ni toca nada del sistema sin que se pulse, y se vuelve a ver desde Ajustes.

### Ajustes y escritorio

- Cambiado: «Integración con el escritorio» se llama ahora «Accesos
  directos», con un interruptor para cada uno, «En el menú de aplicaciones»
  y «En el escritorio», que se aplica al momento. Ya no hay botón «Añadir»
  aparte, y la ruta del AppImage sale en pequeño debajo.
- Nuevo: al poner un acceso directo desde un AppImage que no está en
  ~/AppImages, Silux ofrece moverse allí para que el acceso no se rompa el
  día que se vacíe Descargas: «Mover y añadir» lo mueve (sin pisar otro
  archivo del mismo nombre) y vuelve a abrir Silux desde allí. Si no se puede
  mover, lo copia y te dice que el de antes ya se puede borrar. Si lo dejas
  donde está, Ajustes avisa de que el acceso dejará de funcionar si mueves o
  borras el archivo.
- Nuevo: si mueves el AppImage a otra carpeta, al abrirlo desde allí sus
  accesos directos pasan a apuntar a la ruta nueva, sin preguntar. Si en la
  ruta de antes sigue habiendo una copia, no se tocan.
- Arreglado: un acceso directo borrado a mano, desde la terminal o desde el
  editor de menús de KDE, sale en Ajustes como no añadido. Volver a ponerlo
  desde Ajustes deshace también el borrado del editor de KDE.
- Nuevo: la entrada del menú lleva `TryExec`: si el AppImage ya no existe,
  el menú deja de enseñarla la próxima vez que se pone al día.

### Arreglos

- Batería: si el firmware da una tensión que una batería de esa nominal no
  puede tener (20,48 V en una de 14,8 V), no se enseña. Sin capacidad ni
  carga, sale «Batería sin datos» diciendo esa tensión, y no una ficha con el
  modelo vacío y «Carga: — (0.0 Wh)».
- Memoria: «Hynix/Hyundai», como lo escribe alguna BIOS, sale «SK Hynix»,
  igual que el módulo leído de su chip.
- Memoria: con permisos, la fila «Rangos» de un módulo sale de su chip SPD
  cuando la tabla de la BIOS no los trae, en vez de un guion.
- Memoria: con permisos, lo que la BIOS dice de un módulo cuyo chip SPD no se
  pudo leer y contradice al chip del otro (el tipo, el formato o la velocidad
  a la que va) sale marcado «según la BIOS, no coincide», y no cuenta en la
  cabecera. Un portátil con dos DDR2 decía «DDR · DDR2 · 667 MT/s ·
  800 MT/s».
- Sistema: el aviso de un kernel anterior al mínimo lleva su propio
  encabezado, «Kernel anterior a 5.15», y no el de un dato concreto.
- Memoria: con permisos, cuando el kernel no ha registrado el chip SPD del
  segundo módulo (con dos zócalos solo lo busca en 0x50 y 0x51, y muchos
  portátiles lo ponen en 0x52), Silux lo explica y da la orden para
  registrarlo a mano, para copiarla. Silux no la ejecuta.
- Memoria: con permisos y un módulo leído de su chip SPD, el pie dice de qué
  módulo no se pudo leer el chip («y el del módulo 2 no se ha podido leer»),
  en vez de decirlo de todos con el primero leído al lado.
- Gráficos: una tarjeta en reposo (la dedicada de un portátil con Optimus)
  ya no enseña 35 filas con guion: queda una ficha corta con lo que se sabe
  sin despertarla (nombre, fabricante, driver, identificadores) y un aviso
  «En reposo» que dice por qué no se le pregunta nada.
- Gráficos: mientras la otra tarjeta duerme, la integrada ya no dice «Ni
  Vulkan ni OpenGL usan esta tarjeta» ni «Sin bibliotecas gráficas»: dice
  que todavía no se les ha preguntado, para no despertar a la otra.
- Placa base: un portátil HP ya no se llama «HP Type1ProductConfigId», que
  es un relleno de su BIOS, sino por su nombre («HP Laptop 15-dw3xxx»).
- Informe: una cifra que necesita permisos dice «(necesita permisos)» una
  vez, y no «(necesita permisos) (con permisos)».

## 0.4-prueba10 (22 de noviembre de 2026)

Las temporizaciones de una DDR5 con su chip SPD legible salían mal en la
prueba9 y antes: el CL y los tiempos se leían de otro sitio.

- Memoria: las temporizaciones de una DDR5 se leían dos bytes antes de donde
  están, de la lista de latencias que admite el chip: una DDR5-4800 CL40
  salía con CL9. Ahora salen como las da JEDEC: 40-39-39-77-116.
- Memoria: con solo la primera página del SPD de una DDR5, la referencia, la
  capacidad y los rangos ya no salen con guion: se esconden y se nombran al
  pie, y con permisos los da la tabla del firmware.

## 0.4-prueba9 (22 de noviembre de 2026)

Letra más legible y unidades coherentes: memoria en GiB, discos y red en GB
decimales como `df -H`, y «Calculando…» en la primera lectura. Y lo que
trajeron dos informes de la prueba8: la resolución que tiene puesta cada
monitor, el SPD de una DDR5 que bloquea el cambio de página, los paquetes de
una Wi-Fi USB que no cuadran y los núcleos P y E en Sensores.

### Legibilidad y unidades

- Un punto más de letra en la densidad normal, y los valores en seminegrita
  junto a sus etiquetas en gris.
- La memoria, la memoria de video y las cachés llevan su símbolo binario:
  «15.9 GiB», «8 × 32 KiB».
- Los discos, las particiones y lo que pasa por la red van en decimal, como
  los vende el fabricante y como escribe `df -H`: un disco de 1 TB dice
  «1.0 TB», no «931.5 GB», y lo ocupado y lo libre suman lo que dice. Los GiB,
  al pasar el ratón. Ninguna tarjeta mezcla ya las dos familias.
- Sensores dice lo mismo que las páginas: la memoria de video en MiB, y la
  red, tasas y totales, en decimal («kB/s», «MB») bajo una sola rama.
- En la primera lectura, lo que sale de restar dos (el uso y el consumo de la
  CPU, el uso de la gráfica, lo que leen y escriben los discos, lo que baja y
  sube la red) dice «Calculando…» en vez de un guion.

### De los informes de la prueba8

- Memoria: el chip SPD de una DDR5 se lee página a página. Donde el equipo
  bloquea el cambio de página, la página 0 ya se lee (antes se pedía de una
  vez más de lo que cabe en ella, y fallaba entera).
- Memoria: el sensor de temperatura de cada módulo DDR5 dice de qué módulo
  es, por su dirección en el bus, y sale en la ficha de ese módulo. El
  formato del módulo es el mismo con permisos y sin ellos («UDIMM»).
- Gráficos: la resolución de cada monitor es la que tiene puesta, no la que
  prefiere; la preferida va aparte cuando es otra. Una tele que escribe su
  proporción (160 × 90 cm) donde va su tamaño ya no sale de 72".
- Gráficos: la versión de Mesa de una Intel dice «Mesa» aunque OpenGL sea de
  la NVIDIA; la cabecera ya no repite el nombre en clave en sus etiquetas.
  Al pasar el ratón por la memoria de video se explica por qué una tarjeta de
  «16 GB» da 15.9 GiB: lleva 16 GiB y su firmware se queda una parte.
- Gráficos y Sensores: en un Intel con gráfica integrada, la zona de RAPL que
  el kernel llama «uncore» es la de la gráfica: se llama así, y Gráficos da
  la misma cifra. Por debajo de 10 W, los vatios llevan un decimal en todas
  partes.
- CPU: un procesador sin turbo ya no dice «Turbo desactivado».
- Sensores: en un procesador híbrido, cada núcleo dice si es P o E.
- Red: una tarjeta cuyo driver cuenta más bytes por paquete de los que caben
  en su MTU no enseña sus paquetes como dato, y dice por qué. Una tarjeta USB
  saca su modelo de `usb.ids` y dice su puerto USB, no una «ranura PCI».
- Placa base: «Rev X.0x» y otros rellenos del firmware ya no salen como
  revisión, y la cabecera no repite el chipset y el firmware.
- Sistema: un módulo de licencia no compatible con la GPL (ZFS) ya no se
  llama «propietario».
- En Debian, `pnp.ids` se pide con `hwdata`, que lo trae en Debian 12 y 13.

## 0.4-prueba8 (22 de noviembre de 2026)

Con informes de Felix Lara.

El primer DDR2, leído de su chip; el anexo ya no lleva el número de serie de
los módulos DDR2 y DDR3; con pkexec sin agente de polkit se dice cuál
instalar; las gráficas de Intel con su nombre comercial y todas las del bus a
la vista, y sin conexión ya no se toma el bucle local por la red.

### Privacidad

- El anexo del informe ya no lleva el número de serie de los módulos DDR2 y
  DDR3 (la prueba7 lo dejaba en su chip SPD; los de DDR4 y DDR5 ya se
  borraban), ni la lista de bibliotecas del sistema (`ld.so.cache`). Con
  Silux abierto como root, tampoco la tabla SMBIOS en crudo.

### Informe

- El informe completo sale entero en el idioma elegido: la cabecera, el
  diagnóstico, el tipo de firmware («BIOS heredada») y los motivos por los
  que se frena una gráfica iban en español. Lo que no se sabe ya no sale
  como «?».
- Con pkexec instalado pero sin agente de polkit en la sesión (Hyprland,
  Sway, i3…), Silux ya no dice que se canceló la contraseña: dice que falta
  el agente y cuál instalar según el escritorio. El diagnóstico del informe
  dice el paquete de todo lo que falta por un paquete.
- Sin systemd, el aviso de que falta pkexec dice también lo que polkit
  necesita (en Debian y derivadas, libpam-elogind y un agente como lxpolkit),
  y Ajustes lo repite junto a «No disponible».
- Sin logind (runit, sysvinit) el escritorio y la sesión salen de lo que
  deja el gestor de sesiones y de la pantalla; si aun así no se saben, la
  página Sistema lo dice en vez de enseñar un guion.

### Procesador

- La base de la ficha y la del TDP configurado salen en dos filas: un
  portátil configurado con menos TDP enseñaba «Base 900 MHz» con «@ 2.40GHz»
  en el nombre. En un híbrido, cada tipo de núcleo sigue con su base.
- PL1 y PL2 son los que se aplican: el procesador guarda cada límite en sus
  registros y en los del controlador de memoria, y aplica el más bajo. Si
  difieren, se dice el otro. Y se leen en cada muestra: muchos portátiles
  los cambian al enchufar o quitar el cargador.
- El tamaño de cada caché sale con los decimales que hacen falta para que la
  cuenta cuadre: «4 × 1.25 MB», no «4 × 1.2 MB» para 5 MB.
- El encapsulado de los Intel de sobremesa de la segunda a la séptima
  generación (LGA 1155, 1150 y 1151), y «soldado» en los portátiles U e Y y
  en los Atom, Celeron y Pentium de bajo consumo. Si la tabla no lo tiene,
  con permisos se lee de la tabla del firmware.
- Lo que el procesador no publica (el reloj de referencia, el multiplicador,
  la máxima de fábrica) y la preferencia de energía que el driver no ofrece
  ya no salen con guion: se esconden y se dice por qué. Tampoco el consumo
  de un procesador sin contador de energía (un Core 2) ni el chipset de un
  portátil del que solo se conoce el nombre en clave.
- Un procesador anterior a Sandy Bridge (un Core 2) dice que no publica su
  voltaje, en vez de pedir permisos para leerlo.
- Uno de un solo núcleo dice «1 núcleo · 1 hilo», y su reposo ya no sale
  «entre el 77 % y el 77 %».

### Memoria

- La DDR2 se lee de su chip SPD: capacidad, velocidad, temporizaciones,
  fabricante y fecha. Y el tipo lo dice el chip: una BIOS de la época que
  declara DDR para módulos DDR2 ya no los llama DDR.
- Si la BIOS da una velocidad distinta a cada módulo, el aviso dice la del
  más lento, que es a la que van todos.
- Un fabricante que la BIOS escribe con su código JEDEC en hexadecimal
  («80CE») sale con su nombre.
- Dos módulos en dos controladores ya no se llaman los dos «Canal A»: el
  zócalo dice su controlador cuando es lo que los distingue.
- Un voltaje que el SPD confirma ya no dice «según la BIOS».
- La DDR3 se lee de su chip SPD: capacidad, velocidad, temporizaciones,
  voltaje y fabricante, y «DDR3L» cuando el módulo admite 1,35 V. Si los
  módulos están catalogados a velocidades distintas, se dice que van todos a
  la del más lento, también sin permisos.
- Lo que el chip SPD de un módulo no declara se dice al pie de su ficha, sin
  guiones, y la explicación de los perfiles es una frase: el resto, al pasar
  el ratón.
- La ficha de un módulo soldado dice «Soldada a la placa» y por qué se sabe,
  en vez del formato que declara la BIOS.

### Red y Placa base

- El nombre del equipo ya no sale de la versión de la BIOS ni del código de
  plataforma («Acer V1.13»): si hace falta, se toma el nombre del producto.
  Ni de la letra de la serie: «ASUS X550JK», no «ASUS X».
- Sin conexión, Inicio y Red dicen «Sin conexión» en vez de tomar el bucle
  local («lo · 127.0.0.1») por la interfaz principal.
- Una interfaz virtual ya no enseña dirección física, driver, modelo y ranura
  PCI con guiones: se dice al pie de su tarjeta que no tiene tarjeta detrás.
- Los paquetes que el kernel descarta se llaman descartados, no perdidos, y
  los que llegan con error salen aparte.
- La explicación de bytes y bits ya no da cifras que no son las del equipo.
- El chipset de un portátil que lo lleva en el encapsulado del procesador
  sale como tal, y la versión de la BIOS sin los espacios que deja el
  firmware.

### Gráficos

- Las integradas de Intel se llaman por su nombre comercial («HD Graphics
  4600»), de las tablas de Mesa, donde pci.ids solo daba la familia; las
  más antiguas, sin «(primary)».
- Una gráfica que está en el bus PCI sale siempre, también sin driver o con
  uno que no la ofrece como gráfica (vfio-pci), y dice por qué no da datos.
  Inicio nombra también la otra gráfica de un portátil híbrido, aunque
  duerma.
- Lo que una gráfica o su driver no da ya no sale con guion: se esconde y se
  dice al pie de cada tarjeta. Una integrada de Intel no tiene BIOS de video
  propia; una NVIDIA con nouveau no publica relojes, memoria ni sensores, y
  sus fichas de uso, frecuencia y consumo se van.
- La versión del driver de una gráfica con driver libre es la de Mesa, y se
  dice: «amdgpu · Mesa 26.2.6». Cada biblioteca nombra el suyo («radv (Mesa
  26.2.6)», «radeonsi», «rusticl») y la versión del cargador de Vulkan, que
  no es de la tarjeta, ya no sale.
- Una Radeon RDNA 3 o posterior enseña su caché L2 y su Infinity Cache, y
  cada Radeon su juego de instrucciones (gfx1201).
- El límite de potencia dice el que aplica y el de fábrica («340 W · de
  fábrica 330 W»); el rango que admite, al pasar el ratón.
- La BIOS de video de una Radeon dice su versión y su fecha, y bajo
  «Relojes y enlace» hay una sección plegada para expertos: los escalones de
  cada reloj con el que está en uso, el perfil de energía y si OverDrive
  está activado, con cómo activarlo.
- Un ventilador parado dice «parado (0 RPM)» y por qué es normal; las
  unidades de rasterizado se llaman ROPs y la memoria que la gráfica toma
  del sistema, GTT. «Memoria (efectiva)», que repetía el reloj de memoria
  junto a la tasa de datos, ya no sale.

### Batería

- Una batería entre sus dos límites de carga dice «En pausa por su límite de
  carga», no «Retenida en el tope», que solo es cuando ha llegado al de
  parada.
- Una batería que el firmware declara sin nada dentro lo dice en una frase,
  en vez de una página de guiones.

### Almacenamiento

- La vida restante de un pendrive lleva candado sin permisos, como el resto
  de su diagnóstico, en vez de un guion.
- Un disco que no dice su fabricante lo dice al pie de su tarjeta.
- Una partición de intercambio sale como «Intercambio» en la barra, no como
  espacio sin montar.
- Las cabeceras cuentan todas las unidades: un SSD por USB se reconoce por su
  modelo, y la que no dice su tipo se cuenta como «sin tipo conocido».

## 0.4-prueba7 (21 de noviembre de 2026)

Con los informes de la prueba5 y de la prueba6: la memoria dice lo que solo
sabe la BIOS y por qué no se lee el SPD, sin recomendar drivers de más; una
Radeon sin telemetría del firmware ya no se llena de rayas; un pendrive ya
no es un disco duro, y un procesador sin turbo no enseña el suyo.

### Memoria

- Sin el chip SPD, «Catalogado a» y «Voltaje» dicen «según la BIOS» cuando
  solo los da la tabla del firmware: muchas BIOS dejan ahí el voltaje de
  serie aunque un perfil XMP o EXPO suba el real. Y si la memoria va por
  encima de la velocidad más alta de JEDEC de su tipo, se avisa de que su
  voltaje real puede ser otro.
- El motivo de que no se lea el SPD sale una vez, al pie de los módulos, y
  no dos.
- Arreglado: con los permisos dados, lo que faltaba por un driver salía como
  «(necesita permisos)». Ahora se dice que falta el driver, y cuál.
- Arreglado: se recomendaba cargar `ee1004` en equipos sin ningún chip SPD a
  la vista, porque contaban como bus de la memoria los del touchpad. Ahora
  solo cuenta el bus que cuelga del controlador SMBus, el driver que se
  recomienda es el del chip que hay, y sin chip se dice así.
- Una DDR5 de la que solo se puede leer la primera página del SPD (cuando el
  equipo bloquea las escrituras que hacen falta para pasar a las demás)
  enseña lo que hay en ella: el tipo, la velocidad y las temporizaciones de
  JEDEC. El resto se dice bloqueado, y la tabla de la BIOS completa lo que
  puede.

### Procesador

- Un procesador sin turbo ya no enseña «Turbo: —» ni «Máxima (silicio): —»:
  esas filas se esconden y el pie lo dice. Cuando el kernel no lo sabe, lo
  dice la ficha oficial de AMD.
- Los errores de la instrucción que identifica el procesador ya no salen en
  español con la interfaz en inglés.

### Gráficos

- En una AMD, lo que su driver no publica en esa tarjeta (el punto caliente,
  los reguladores, los voltajes del SoC y de la memoria; en una Polaris, casi
  todo eso) ya no sale con raya: se esconde y el pie lo nombra.
- Si el enlace PCIe va a toda velocidad pero con menos líneas de las que
  admiten la tarjeta y la ranura, ya no se atribuye al reposo.
- Inicio nombra cada gráfica por el enlace al que llega, como la cabecera de
  Gráficos: en reposo una NVIDIA de portátil salía «PCIe 1.0 × 8».
- Un límite de potencia con un mínimo de 0 W ya no se presenta como un rango.

### Almacenamiento

- Arreglado: un pendrive salía como disco duro. Por USB el kernel marca casi
  todo como si girara: un dispositivo USB extraíble es memoria flash, y lo
  que no publica (temperatura, horas, escrito) se esconde y se dice.

### Empaquetado

- El AppImage usa el fontconfig y el freetype del sistema: en una
  distribución al día ya no llena la terminal de avisos al arrancar.

### Inicio y Placa base

- Arreglado: al dar permisos con Inicio abierto, la temperatura que
  encabezaba podía quedarse en la de antes en vez de pasar a la más alta.
- «x.x» como versión de la placa, que dejan algunas Gigabyte, es un relleno
  del firmware y no se enseña.

### Idioma

- Con la interfaz en inglés, dos palabras salían en español: la «y» que une
  los tipos de memoria del aviso del SPD y la «instancia» de la fila de
  Vulkan.

### Permisos

- El ayudante con permisos lee cada petición con un tope, en vez de leerla
  entera y mirar después cuánto ocupa. Quien lo tenga instalado verá que hay
  que actualizarlo.

## 0.4-prueba6 (21 de noviembre de 2026)

Con los informes de la prueba5: las gráficas Intel integradas sin saltos ni
ceros, ningún dato de una ventana de tiempo imposible, la interfaz en inglés
sin una palabra en español, y lo que los informes del LOQ y del sobremesa
con Gentoo dejaron por arreglar.

### Cambio que rompe: la salida JSON (`--json`)

Para quien la lee desde un script. Lo que era texto en español pasa a ser
el número o el código que da el propio estándar; el texto se pone al pintar,
en el idioma de quien lee.

- `spd.manufactured` («semana 32 de 2021») pasa a ser `manufactured_year`
  y `manufactured_week`.
- `Edid.made` ya no sale: la fecha va en `year` y `week`.
- `MemoryModule.form_factor` y `MemoryArray.error_correction` son el código
  de SMBIOS (`13` es SODIMM, `11` una fila de chips, `5` ECC de bit único),
  no su nombre. `details` son los números de bit de la tabla 77.
- `MemoryModule.type` ya no vale «Otro» ni «Desconocido» (sale `null`), y
  el tipo 1Fh es `logical-non-volatile`.
- Campos nuevos: `Note.key` y `Note.detail`; `Sensor.device_key`,
  `chip_label`, `group` y `plausible`; `Gpu.package_temp_c`;
  `MemoryModule.in_a_slot`; `Snapshot.failures`, los fallos del propio
  Silux con su traza.

### Consumo

- Arreglado: un consumo imposible entraba en la gráfica, en el máximo y en la
  media (una Iris Xe que gastaba 9 W tuvo un pico de 1336648637.3 W). Ahora
  un vatio negativo o por encima de lo que puede dar la pieza (su PL4, o lo
  que declara RAPL) se descarta, y el informe dice cuántos y con qué números.
  Vale para el procesador y para la gráfica integrada de Intel.
- Arreglado: el consumo del procesador leído con permisos se cronometraba
  antes de leerse, y el ayudante puede esperar hasta 100 ms: con el
  intervalo de un segundo, algún segundo salía hasta un 10 % alto o bajo.
  Ahora se cronometra donde se lee, y no se resta una lectura de sysfs a
  otra del ayudante.
- Arreglado de raíz: todo lo que sale de restar dos lecturas (el consumo
  del procesador y de la gráfica, el uso de cada uno, la red, los discos, el
  tráfico de la memoria y los estados de reposo) pasa por la misma regla. Si
  entre las dos lecturas no ha pasado al menos la mitad del intervalo, o el
  contador ha ido hacia atrás, esa vuelta no da cifra y empieza otra. El
  techo de los vatios imposibles queda detrás, de red.
- Arreglado: la gráfica de la tarjeta de la gráfica en Inicio enseña el uso
  o, sin él, la frecuencia. Una muestra sin uso pintaba megahercios encima
  de los porcentajes; ahora empieza de cero cuando cambia lo que enseña.
- Arreglado de raíz: cada gráfica dibuja una sola serie, con su clave y su
  unidad. Si cambia lo que enseña (otra tarjeta, otro disco, otra interfaz,
  °C o °F, quién encabeza las temperaturas en Inicio) empieza de cero, y un
  valor que no cabe en su unidad (un contador en bruto, milésimas de grado,
  más bytes de los que da el enlace) no entra, ni en la curva de cada
  sensor ni en su mínimo, máximo y media.

### Gráficos

- Arreglado: la frecuencia de una gráfica Intel saltaba cada segundo
  (0, 1050, 0, 450, 1100 MHz con un video 4K60) porque era una lectura
  suelta, y con la gráfica dormida en RC6 se lee 0. Ahora es la media de lo
  que leyó despierta durante el intervalo, y debajo dice cuánto tiempo estuvo
  en reposo.
- Una gráfica dormida dice «en reposo» en la ficha, en la gráfica y en el
  informe, no «0 MHz».
- Una gráfica integrada de Intel no tiene sensor de temperatura propio (i915
  y xe solo lo dan en las dedicadas). Ahora Gráficos enseña la del paquete,
  como «Temperatura del paquete, compartida con la CPU»; nunca como la de la
  gráfica, ni en Sensores ni en el informe. Sin sensor del paquete, como
  antes.
- Los avisos dicen las cosas en lenguaje normal: ni nodos, ni hwmon, ni
  rutas en pantalla. El detalle técnico va al informe, junto a cada dato que
  falta.
- Arreglado: una NVIDIA sin el «modesetting» de nvidia-drm decía «Sin salidas
  de video», y sus salidas funcionan. Ahora dice que el driver no las publica.
- Arreglado: una integrada que ni Vulkan ni OpenGL usan, con otra gráfica que
  sí, decía «Sin bibliotecas gráficas». Ahora dice que no la usan.
- La cabecera de cada gráfica dice el enlace al que llega («PCIe 4.0 × 8»), no
  el del momento: en reposo el enlace baja para gastar menos y se leía como
  una avería. La fila «Enlace» sigue con el de ahora y, al pasar el ratón,
  dice que en reposo es lo normal.
- Arreglado: una NVIDIA sin consumo enseñaba un guion sin motivo. Ahora una
  nota dice que el driver no lo da, y el informe lleva lo que contestó NVML a
  cada forma de pedirlo.

- Una NVIDIA cuyo driver no da el consumo por las vías normales lo saca
  ahora de las muestras de potencia que el driver toma siempre, con su media
  en cada intervalo, como hace `nvidia-smi`. Y enseña su límite de potencia de fábrica y el rango que
  admite.
- Con un driver de NVIDIA que ya no traiga las llamadas antiguas de la
  temperatura y de los motivos de recorte, se usan las que las sustituyen.
- Cuando el driver de Vulkan está instalado y rechaza una gráfica, la fila de
  Vulkan lo dice, con el motivo que dio el driver, en vez de «ni Vulkan ni
  OpenGL la usan».

### Batería

- Justo después de enchufar o desenchufar el cargador, el portátil tarda
  unos segundos en dar la potencia. Mientras, Potencia y Autonomía dicen
  «Calculando…», no un guion ni «0».
- La capacidad sale con la misma cifra en todos los sitios: arriba ponía
  «50 Wh» y debajo «50.5 Wh».
- Con la batería llena o retenida en su tope, Autonomía dice «con el
  cargador», no un guion.
- Arreglado: un portátil con una sola batería, que el kernel llama BAT1, la
  enseñaba como «Batería 2» en Sensores.

### Memoria

- Arreglado: el formato de cada módulo, la corrección de errores y el tipo
  que da la tabla del firmware se guardaban como textos en español y la
  lógica decidía sobre ellos (lo soldado, por «Fila de chips»). Ahora son
  los códigos de la especificación y se nombran al pintar: en inglés ya no
  salen «Fila de chips» ni «ECC de bit único».
- La memoria soldada se reconoce primero por su formato en la tabla del
  firmware («Fila de chips»), aunque su zócalo se llame «ChannelA-DIMM0».
  Con otro formato manda el nombre del zócalo: el T14 declara «SODIMM» su
  memoria soldada.
- Arreglado: el fabricante de un módulo de memoria y el de sus chips salen
  de la lista entera de JEDEC (JEP106BP, más de 2300 fabricantes, de la copia
  de OpenOCD). La de antes tenía 15, y Kingston, Infineon, Elpida y Transcend
  estaban en el sitio equivocado. Un código sin nombre en la lista se dice
  como tal.
- Arreglado: sin permisos, un portátil con memoria soldada decía «8 GB
  instalados · 15.3 GB utilizables»: la soldada no tiene chip SPD y no
  contaba. Ahora no dice cuánta hay instalada, y sí que el resto se sabe con
  permisos.
- Arreglado: con memoria soldada, la nota decía que sus chips, sus perfiles y
  su fecha «no se han podido leer». La soldada no lleva chip SPD, y lo dice.
- Arreglado: el aviso de cargar `spd5118` salía con el módulo ya cargado, y
  hablaba de «los 1 módulos». Si el chip ya tiene su driver no se propone
  nada, y con uno va en singular.
- Arreglado: el tráfico de la memoria decía «este equipo no lo publica»
  cuando el controlador sí publica sus contadores y no se pudieron abrir.
  Ahora sale como error, y el informe lleva el motivo.

- Si el chip SPD de la DDR5 está y leerlo falla, se dice así, con el error
  exacto en el informe: pasa cuando el equipo bloquea las escrituras al SPD
  o cuando el driver no se recupera de una suspensión. Antes solo decía que
  no se había podido leer.

### Procesador

- Arreglado: las cachés de un núcleo sin SMT decían «1 hilos».
- En un híbrido, las cachés de cada nivel van con los núcleos P antes que
  los E.

### Almacenamiento

- Un NVMe cuyo modelo empieza por «SKHynix» es de SK hynix.
- Un disco de platos cuyo SMART no lleva la cuenta de lo escrito ya no
  enseña «Escrito en total: —»: la fila se esconde y el pie lo dice.

### Sensores

- Arreglado: el árbol agrupaba cada aparato por su nombre traducido y
  guardaba así las ramas que se dejan plegadas. Ahora va por una clave del
  aparato que no cambia con el idioma. Las ramas plegadas a mano que tenían
  un nombre traducido (la red, la memoria, la batería) se abren una vez.
- Los nombres del tráfico de red en Sensores («Bajada», «Subida»…) salen en
  el idioma de la interfaz.

### Red

- Arreglado: con la interfaz en inglés, las cabeceras del tráfico y las
  cuatro fichas de arriba salían en español.
- Arreglado: más textos que salían en español con la interfaz en inglés: un
  ventilador parado, la fecha de fabricación de un monitor y de un módulo de
  memoria («semana 16 de 2024»), la frecuencia fija de un procesador, un
  sistema sin nombre y un disco sin particiones montadas. Las dos fechas se
  guardaban ya escritas; ahora son números y se escriben al pintar.

### Sistema

- Con un kernel anterior a Linux 5.15, el mínimo, la página Sistema avisa de
  que puede faltar algún dato sin que se diga por qué. Sistema enseña ya sus
  avisos, también el de un `systemctl`, `kmod` o `xdg-open` que falte.
- En Gentoo, el paquete que falta se nombra con el de Gentoo
  (`dev-libs/opencl-icd-loader` para OpenCL), no con el de las otras cuatro
  familias.

### Informe

- Arreglado: el informe no decía nada de las interfaces virtuales (un túnel
  de WireGuard, los puentes de Docker), que Red enseña plegadas: ahora van
  desplegadas. Y el bucle local conserva su dirección, 127.0.0.1, que no
  identifica a nadie.
- Arreglado: un fallo del propio Silux (un archivo suyo que no está, un
  error al leer entre muestras) salía como «este equipo no lo publica», o
  no salía. Ahora es un error, y el informe lo lista con su traza, sin la
  carpeta personal.
- Arreglado: en el anexo, un disco montado en una ruta con el nombre del
  usuario dentro salía con dos nombres distintos, y al reproducirlo se
  quedaba sin cifras.
- Un espacio de más en «sostenida  · la medida de referencia».

---

## 0.4-prueba5 (21 de noviembre de 2026)

Con lo que trajeron los primeros informes con sus datos en crudo: el XMP de
DDR4, la NVIDIA en Sensores, el SPD de los portátiles con memoria soldada, y
la lista de lo que Silux usa del sistema, que ahora se dice cuando falta.

### Procesador

- Arreglado: con los estados de reposo de la tabla ACPI de la placa (un
  Comet Lake, un Tiger Lake), «C2 es el reposo más hondo de este procesador»
  no era cierto: dice que son los de la placa, con su número de ACPI.
- Arreglado: un procesador sin driver de frecuencia (cpufreq) salía con
  «Frecuencia: —» en todas partes. Ahora la da `/proc/cpuinfo` y, con
  permisos, en los Ryzen y Athlon (Zen), el propio procesador: su P-state,
  y el P0 es el reloj base. Las filas que solo da ese driver se esconden y
  se dice por qué.
- Cambiado: el aviso de que falta la frecuencia ya no dice «Falta un módulo
  del kernel»: puede ser la BIOS (Cool'n'Quiet desactivado) o que el driver
  no haya cargado, y dice eso.
- Arreglado: «Turbo: —» en un procesador sin turbo. Dice que no tiene.
- Arreglado: donde el consumo del procesador pide permisos (casi todos los
  AMD y algunos portátiles Intel), su candado decía «Pulsa el candado» y no
  hacía nada.
- Arreglado: con permisos, en un Intel cuyo kernel guarda el consumo para
  root, solo llegaba el del paquete. Llegan también el de los núcleos, el del
  uncore y el de la memoria.

### Memoria

- Arreglado: el perfil XMP de los DDR4 se leía un byte desplazado y con el
  voltaje mal: unos Team Group de 3200 salían «CL 18, tRP 4, 0,81 V». Se lee
  como lo vende el fabricante (16-18-18-38 a 1,35 V), comprobado con los
  módulos de un probador.
- Arreglado: en un portátil con memoria soldada y un módulo en la ranura, los
  datos del chip SPD del módulo de la ranura (fabricante de los chips, fecha,
  temporizaciones) salían pegados a la memoria soldada, que no tiene ese
  chip.
- Arreglado (se rompió en la prueba2): unos DDR4-3200 con un XMP que esta
  versión no sabe leer salían «Catalogado a 2400» y perdían el aviso de que
  van al máximo del procesador. La velocidad del perfil se lee bien y vuelve a
  contar.
- Arreglado: el chip SPD de un módulo Kingston no daba fabricante: la tabla
  ponía a Kingston en otro banco de códigos JEDEC. Lo enseñó el módulo del
  ThinkPad del autor.

### Gráficos

- Arreglado: el consumo de una NVIDIA con los drivers recientes (595) salía
  «—»: se pide también como lo indica la documentación de NVML.
- Arreglado: la NVIDIA de un portátil enseñaba «Ventilador: —». Su ventilador
  es del portátil y lo lleva su controlador: no se enseña, y se dice al pie.
- Arreglado: con permisos, una Intel cuyo uso por motor no se pudo leer decía
  que ese uso «ya se está leyendo». Ahora dice lo que pasa con esa gráfica:
  que el kernel no publica sus contadores, o que los publica y no se han
  podido abrir.
  Y si el ayudante se cierra, vuelve a pedir permisos en vez de seguir
  diciendo que el uso se lee.

### Almacenamiento

- Nuevo: al pasar el ratón por «Reservado», en Almacenamiento y en Inicio,
  dice qué es: lo que ext4 guarda para root y las tablas del sistema de
  archivos.
- Arreglado (a medias en la prueba2): lo que ext4 guarda para root (el 5 %)
  contaba como ocupado, y «Reservado» eran solo las tablas del sistema de
  archivos. Un portátil decía «Ocupado 40.6 GB» de unos 17. Ahora va en
  «Reservado», como lo cuenta `df`.

### Sensores

- Arreglado: una NVIDIA con el driver propietario no tenía temperatura,
  consumo ni relojes en Sensores, aunque sí en Gráficos.

### Ajustes y escritorio

- Nuevo: «Gracias a» en Ajustes → Acerca de y en el README, con quien manda
  informes y ha dado permiso para salir.

### Sistema

- Nuevo: si falta algo del sistema que este equipo necesita (`pci.ids`,
  NVML, las bibliotecas gráficas, pkexec, el Python del sistema…), se dice
  en Diagnóstico y en su página, con el paquete de su distribución. La lista
  entera, con lo que da cada cosa, en `docs/dependencias.md`.
- Arreglado: en Debian no se proponía cargar `drivetemp` ni el driver del
  chip SPD: se buscaba `modinfo` en el `PATH` del usuario, y Debian lo deja
  fuera.
- Arreglado: sin los certificados del sistema, buscar una versión nueva
  decía «no hay conexión con GitHub»; ahora dice que faltan los certificados
  y qué paquete los trae.

### Permisos

- El ayudante lee la energía y los contadores de la gráfica y de la memoria
  como mucho cada 100 ms, pida lo que pida el programa: leídos más deprisa
  dejan ver lo que calculan otros procesos (CVE-2020-8694). No cambia nada de
  lo que se ve. Al actualizar, Silux pide actualizar el ayudante.

---

## 0.4-prueba4 (20 de noviembre de 2026)

La prueba3 con un arreglo más, para que la pruebe también quien usa un
sistema sin systemd.

### Sistema

- Arreglado (se rompió en la prueba2): en un sistema sin systemd cuyo
  proceso 1 es `init` (Gentoo con OpenRC, sysvinit) salían con «?» la
  distribución, el kernel, la arquitectura, el escritorio y el sistema de
  inicio. Y si alguno de esos datos no se puede leer, falta ese solo.

---

## 0.4-prueba3 (20 de noviembre de 2026)

Una prueba corta, para que el anexo del informe salga en los equipos de la
gente: en la prueba2 no salió en ninguno de los tres primeros.

### Informe

- Arreglado: el anexo no salió en ninguno de los tres primeros equipos de la
  prueba2. Tomaba por datos tuyos cosas que no lo son o que ya estaban
  tapadas: una puerta de enlace 192.168.1.1, el modelo de un pendrive, el
  identificador de una NVIDIA o un equipo llamado como su marca o como un
  driver («thinkpad»). Ahora solo busca lo que es tuyo, y como palabra entera.
  Si algo no se puede tapar, quita ese archivo y el informe dice cuál y qué
  llevaba; si aun así no puede escribirse, dice qué dato quedaba por tapar,
  nunca el dato.
- Arreglado: un adaptador de red USB se llama como su dirección física
  («enx…»), y esa dirección salía en el informe. Ahora va tapada, como las
  demás.
- Arreglado: la nota que va debajo de una lista («Iris Xe Graphics: no
  publica su temperatura.», «Un disco de platos…») salía pegada a la última
  línea de la lista.

### Sensores

- Arreglado: un portátil con dos puertos USB-C los llamaba igual, y en
  Sensores cada lectura llevaba el nombre del kernel
  («ucsi-source-psy-USBC000:001»). Ahora son «Puerto USB-C 1» y «2», y un
  puerto sin nada enchufado no enseña sus lecturas a cero.

---

## 0.4-prueba2 (20 de noviembre de 2026)

Segunda versión de prueba de la 0.4: lo que se ha arreglado con los primeros
informes de la prueba1, y un informe que acaba con los datos en crudo del
equipo.

### Procesador

- Arreglado: un procesador que no está en la tabla salía con el nombre en
  clave, la tecnología y el encapsulado de otro solo porque coincidía la
  familia. El virtual de QEMU salía «Xeon (Cranford) · 90 nm».
- Cambiado: en una máquina virtual el procesador no se busca en la tabla: lo
  que declara lo decide el hipervisor. No salen nombre en clave, tecnología
  ni encapsulado, la ficha dice por qué y no se pide el informe para
  completarlo.
- Arreglado: en un procesador híbrido (Intel de 12.ª en adelante), la L3 que
  comparten los núcleos P y E se contaba dos veces: un i5-12450H decía
  31.7 MB de caché en total en vez de 19.7.
- Arreglado: en un híbrido, «núcleos» debajo de la temperatura era la media
  de los núcleos P solos; ahora es la de todos.

### Máquinas virtuales

- Cambiado: dentro de una máquina virtual no se pide permiso para nada que
  no tiene: el voltaje del procesador, los módulos de memoria o la salud de
  los discos, que el hipervisor se inventa. Tampoco se culpa a la placa del
  SMBus, del chipset o del controlador de memoria.
- Arreglado: el disco virtual de QEMU salía «HDD» y «disco SMR». Es
  «Virtual», sin temperatura, horas ni desgaste que enseñar.
- Arreglado: la VGA de QEMU se llamaba «Gráfica 0» y su ficha era una lista
  de rayas. Se llama «QEMU Standard VGA» y dice al pie lo que una gráfica
  emulada no tiene; del monitor virtual no salen tamaño ni fecha.
- Arreglado: el título de Placa base decía «Placa base» cuando el firmware
  no la nombra. Sale el equipo («QEMU Standard PC (i440FX + PIIX, 1996)»), y
  la página dice que es una máquina virtual. Los dispositivos PCI salen
  «emulados», no «en el procesador» ni «en la placa».
- Arreglado: con BIOS heredada, el arranque seguro decía «no se puede leer»;
  no existe, y se dice al pie.
- Nuevo: Cachés avisa de que las cachés de un procesador virtual las declara
  el hipervisor.

### Actualizaciones

- Nuevo: en Ajustes, el canal: «Estable» o «Pruebas». Con «Pruebas» se
  ofrecen también las versiones de prueba; sin elegir, una versión de prueba
  sigue las pruebas (quien tiene la prueba2 recibe la prueba3 con «Buscar
  ahora») y una final, las finales. Una prueba recibe su final en los dos.
  La prueba1 no tiene canal y no ve la prueba2: esta se descarga a mano.

### Textos

- Arreglado: textos en inglés o en crudo de los primeros informes: el chasis
  «Notebook», el sensor «Composite» de un NVMe, los aparatos de Sensores
  «spd5118», «Red (iwlwifi_1)» y «Alimentación · ucsi-source-psy-…» (que
  además repetía el «Puerto USB-C»), «QEMU Virtual version 2.5+» por QEMU
  Virtual CPU, «Cargando (Super I/O)» y «1 paquetes perdidos».
- Arreglado: en Sensores, los núcleos de un procesador con más de nueve
  canales salían desordenados («Núcleo 8, 12, Paquete, 20…, 0, 4»).
- Cambiado: a un portátil ya no se le propone `sensors-detect` para buscar un
  Super I/O: sus ventiladores los lleva el controlador del equipo.

### Informe

- Nuevo: el informe completo acaba con un anexo, los datos en crudo que Silux
  ha leído del equipo para escribirlo, con lo mismo tapado que el resto. Con
  él, lo que falla en tu equipo se puede reproducir en las pruebas de Silux
  sin pedirte nada más. Desde la ventana tarda un par de segundos en
  prepararse, y «Guardar…» espera a que esté. Lleva lo que se lee sin
  permisos; `--short` y `--sections` no lo llevan.
- Arreglado: el volcado de un equipo para las pruebas (el de
  `tools/volcar_equipo.py`, que es el del anexo) no se escribía si había
  enchufado un aparato USB de fabricante «Generic» o «Realtek»: tomaba el
  nombre por un dato tuyo y luego lo encontraba en el sonido y en la red.
- Arreglado: con el AppImage compat (Python 3.10), ese volcado no recogía lo
  que se lee de cierta manera (entre otras cosas, dónde están los chips de la
  memoria) y podía despertar la gráfica dedicada dormida de un portátil al
  hacerlo.
- Arreglado: en un equipo llamado como su marca («lenovo» en un Lenovo), el
  informe anónimo cambiaba la marca por «silux-pc» en los nombres de los
  sensores. El nombre del equipo se sigue tapando.
- Arreglado: el informe hecho desde la ventana justo después de «Dar
  permisos» salía sin el consumo del procesador, aunque el equipo lo diera:
  se quedaba con la primera lectura, y ese dato sale de restar dos. Ahora se
  rehace también con la segunda.

### Sistema

- Arreglado: con OpenRC (Gentoo) el sistema de inicio salía «init», y el pie
  de Arranque decía que systemd «no ha contestado» en un sistema sin
  systemd. Sale «openrc», y el pie dice que esos tiempos los mide systemd.
- Arreglado: sin gestor de arranque conocido, el pie decía «Gestor de
  arranque no lo publica».
- Cambiado: «Revisión SMBIOS» se llama «Revisión de la BIOS», que es lo que
  es, y el «0.0» de relleno de SeaBIOS no se enseña.
- Arreglado: la lista de vulnerabilidades se titulaba «Las mitigadas» y traía
  también las que no lo están; y las que ni el kernel sabe («Unknown») no
  se contaban en ningún lado. Se cuentan aparte, «Sin saber».
- Arreglado: con el AppImage, los programas del sistema que lanza Silux
  heredaban sus bibliotecas. En Debian 13, con el compat, `systemctl` no
  arrancaba y faltaban los tiempos de arranque; y abrir la carpeta de las
  pruebas podía abrir el gestor de archivos con el Qt del AppImage.

### Memoria

- Arreglado: la cabecera decía «3200 MT/s · al máximo del procesador» de una
  memoria que iba a 2933: ahora dice a cuánto va.
- Arreglado: el fabricante de unos módulos Team Group salía «04EF», el código
  que escribe la BIOS de MSI. Se traduce, y Team Group entra en la tabla.
- Arreglado: con un perfil XMP en la tabla, la nota decía «Estos módulos no
  traen perfiles rápidos». Y un perfil con un voltaje imposible (0,81 V en
  una DDR4) no se enseña: la nota dice que el módulo trae XMP y que esta
  versión no sabe leerlo con seguridad.

### Almacenamiento

- Arreglado: un Kingston A400 decía «Escrito en total: 33.4 MB» tras casi
  diez mil horas: cuenta en GiB, y se leía como si contara sectores. La
  unidad de cada contador sale ahora de la base de datos de discos de
  smartmontools, con el modelo entero del disco (el del sistema viene
  cortado a 16 letras).
- Cambiado: si lo escrito en total da menos de lo que el disco tiene
  guardado, no se enseña ni eso ni lo leído, y se dice por qué.
- Arreglado: «Sin montar» contaba lo que el sistema de archivos se reserva en
  las particiones montadas (el 5 % de ext4 para el administrador): un
  portátil con todo montado decía «Sin montar 8.6 GB». Va aparte, como
  «Reservado»; la barra de cada disco reparte igual que la de arriba, y lo
  que no llega al 1 % no se cuenta.

### Gráficos

- Arreglado: una gráfica cuyo driver no da versión decía «i915 None» en la
  cabecera.
- Arreglado: el monitor virtual de QEMU se llamaba «Red Hat, Inc. QEMU
  Monitor»: un fabricante que no está en la lista también pierde la forma
  jurídica.
- Arreglado: la dedicada de un portátil, dormida, decía «Falta un driver» y
  salía «en el procesador» en la tabla PCI. Dice que está en reposo.
- Arreglado: la ficha de una NVIDIA tenía una veintena de rayas. Lo que NVML
  no publica en una GeForce, o lo que una NVIDIA no tiene, se esconde y se
  dice al pie.
- Arreglado: una RTX 4060 de 8 GB salía con 8.2 GB: Vulkan suma la ventana
  de la BAR a la memoria, y manda la cifra de NVML.
- Arreglado: la versión del driver de NVIDIA perdía un cero («595.104.2» en
  vez de 595.104.02), y la fila de OpenGL no la decía.
- Arreglado: el OpenGL por software (llvmpipe) daba su versión de Mesa como
  la del driver de la tarjeta; ahora dice que dibuja el procesador.

---

## 0.4-prueba1 (20 de noviembre de 2026)

Versión de prueba de la 0.4: lo que sigue es lo que traerá, para probarlo antes.


La versión de los permisos y del aspecto nuevo. Un candado donde falta un
dato por permisos, y un aviso que explica qué se gana al darlos antes de
pedir la contraseña. Una sección nueva, Dispositivos; Placa base y Sistema
ganan datos nuevos, y las páginas se ordenan para que cada dato salga una
vez.
Funciona con Linux 5.15 o posterior, y lo que un kernel más antiguo no
publica se dice con la versión que lo trae.

### Antes de actualizar

- En Sensores, los relojes y el uso de cada hilo se llaman «CPU 0», «CPU 1»…
  como en la página del procesador, y no «Core #0». Si tienes guiones que
  leen el CSV grabado o `--sensors` por esos nombres, hay que cambiarlos.
- `--page` con una sección que tu equipo no tiene (Batería en un sobremesa)
  termina con código 2 en vez de guardar la captura de otra página.
- Lo que se fuerza por la línea de órdenes (tema, densidad, tamaño de letra,
  tamaño de ventana) vale solo para esa vez: ya no se queda guardado en tus
  preferencias.
- El color de acento es uno solo, el ámbar de la marca, y deja de estar en
  Ajustes. Si habías elegido otro, la interfaz vuelve al ámbar. La opción
  `--accent` desaparece: un guion que la pase termina con error.
- El ayudante instalado se quita desde Ajustes, con «Quitar el
  ayudante…», y sirve también si usas el AppImage.
- Instalar el ayudante ya no tiene botón propio en Memoria y Almacenamiento
  («No volver a pedirla»): se ofrece dentro de «Qué hace esto».
- La página Sistema ya no enseña el uso de la memoria: está entero en
  Memoria, en «Desglose del uso».
- «Encendido desde», en Sistema, y el campo `boot_time` del JSON pasan a
  año-mes-día («2026-11-17 18:15»), como la fecha de la BIOS.
- En Sensores, las ramas que nunca abriste o cerraste a mano vuelven a
  seguir la regla: una rama larga que tuvieras abierta («Relojes · 16») nace
  cerrada otra vez hasta que la abras.
- La cabecera de `--report` es una lista («- **Kernel:** …») y no una
  tabla: si un guion la leía como tabla, hay que cambiarlo.

### Permisos

- Cambiado: «Qué pasa al dar permisos» dice lo mismo en cuatro frases cortas.
- Nuevo: «Quitar el ayudante…» en Ajustes, si lo instalaste.
  Antes había que copiar una orden `sudo rm`.
- Nuevo: un candado donde falta un dato por permisos, en vez del mismo guion
  que lleva lo que no se sabe. Pulsarlo los pide.
- Nuevo: Inicio avisa de lo que falta por permisos, con nombre («Salud de
  los discos», «Voltaje del procesador»), y con cuatro salidas: «Dar
  permisos», «Qué hace esto», «Ahora no» y «No volver a mostrar».
- Nuevo: «Qué hace esto» cuenta, antes de pedir la contraseña, qué lee el
  ayudante, que solo lee, cuánto dura y quién pide la contraseña.
- Nuevo: sin el ayudante instalado, dar permisos abre antes «Qué pasa al dar
  permisos», que avisa de que la ventana de la contraseña dirá que se va a
  ejecutar `python3` como administrador, y recomienda instalar el ayudante.
- Cambiado: con el ayudante instalado, la ventana de la contraseña dice
  «Silux necesita permiso para leer datos del hardware reservados al
  administrador: memoria, discos, voltaje, consumo y uso de la gráfica. Solo
  lee, no cambia nada.», en español o en inglés. Si lo instalaste antes, el
  programa ofrece actualizarlo.
- Arreglado: la ventana se quedaba congelada mientras el sistema pedía la
  contraseña.
- Arreglado: la página abierta se pone al día sola cuando cambian los
  permisos o se enchufa o se quita algo.
- Arreglado: un dato que falta por otro motivo ya no dice «requiere
  permisos», y ningún texto culpa al equipo de lo que es un permiso.
- Arreglado: «Cancelar» en la ventana de la contraseña cancela. Antes salía
  otra vez, y no se vuelve a pedir hasta que pulses tú.
- Arreglado: tras cancelar, los botones de permisos de Gráficos se quedaban
  en «Esperando autorización…».
- Cambiado: «Instalar el ayudante (recomendado)» no promete que deje de
  pedirse la contraseña. Con él, la ventana de la contraseña dice
  en tu idioma qué se lee y no sale el aviso previo; la contraseña se sigue
  pidiendo al dar permisos.
- Nuevo: con un ayudante instalado de otra versión, Inicio, los avisos, los
  candados y la barra de abajo lo dicen, con «Actualizar el ayudante».
- Cambiado: Ajustes, con el ayudante instalado y leyendo, dice «Ayudante
  instalado y leyendo».

### Inicio

- Nuevo: tres tarjetas más: Temperaturas, con cada cifra junto a lo que
  mide, Red y Placa base. Cada una lleva a su sección.
- Arreglado: Inicio y la página CPU daban dos temperaturas distintas del
  mismo procesador en el mismo momento (33 °C y 30 °C).
- Arreglado: el titular de Temperaturas cambiaba de pieza por décimas de
  grado.
- Arreglado: con permisos, la tarjeta de Memoria decía «31.3 GB ·
  Desconocido» si el primer zócalo de la placa estaba vacío.
- Arreglado: decía que una gráfica integrada «usa 11.6 GB de la RAM».
- Arreglado: el nombre de la tarjeta de red salía cortado por abajo cuando
  ocupaba dos líneas.
- Arreglado: la tarjeta Gráfica enseña la que está trabajando (la dedicada
  en un equipo para jugar) y no la primera de la lista, que en un portátil
  suele ser la integrada. Lo mismo la temperatura y la imagen para compartir.

### Procesador

- Nuevo: cuánto descansa el procesador: qué parte del tiempo pasan sus hilos
  en cada estado de reposo (C1, C2, C6…).
- Nuevo: en Intel, los límites de potencia PL1 y PL2 a la vista, también sin
  permisos.
- Nuevo: sin permisos, el voltaje lleva un candado en vez de un guion.
- Nuevo: el nodo de fabricación de los procesadores que las demás tablas
  nombran sin nodo (un Panther Lake, «Intel 18A») sale de las tablas del
  programa `cpuid` de Todd Allen.
- Nuevo: el nombre en clave, el nodo y el encapsulado de los AMD que libcpuid
  no tiene salen de la tabla oficial de amd.com (744 modelos), y de ahí
  también el nodo o el encapsulado que libcpuid no sabe.
- Arreglado: el encapsulado de algunos AMD salía mal: un Ryzen 5 2400G o un
  Ryzen 7 8700G de sobremesa salían con uno de portátil, y los Threadripper
  con el del servidor. Ahora manda la ficha de AMD de ese modelo.
- Nuevo: los Intel que la tabla de libcpuid todavía no tiene (Panther Lake,
  Wildcat Lake, Nova Lake, Diamond Rapids) salen con su nombre en clave, que
  se toma del kernel Linux. El nodo y el encapsulado siguen diciendo que no
  están en la tabla de esta versión.
- Arreglado: un procesador nuevo podía salir con el nombre de uno antiguo
  que solo compartía la familia y el modelo base: un Panther Lake salía
  «Atom (Cedarview)».
- Cambiado: con un procesador que la tabla de esta versión no conoce, el
  nombre en clave, el nodo y el encapsulado dicen «no está en la tabla de
  esta versión» en vez de un guion, y el aviso pide el informe en vez de
  mandar a regenerar la base de datos. Todo lo que da el propio procesador
  sale igual.
- Arreglado: la frecuencia de cada hilo es la que el procesador ha dado de
  verdad en el último intervalo, no la última que pidió el sistema.
- Arreglado: la gráfica de frecuencia se medía contra un techo equivocado y
  se quedaba en una barra vertical o recortaba las muestras.
- Arreglado: con el contador de energía parado, el consumo salía «0 W». Ahora
  se explica por qué no hay cifra.
- Arreglado: en AMD salía «núcleos 3,7 W» con el paquete a 64 W: ese contador
  es de un solo núcleo. No se enseña, y se dice.
- Arreglado: en los Ryzen que publican dos temperaturas (Tctl y Tdie) se
  enseñaba la que lleva sumado un margen para los ventiladores; ahora, Tdie.
- Arreglado: en AMD sin `amd-pstate`, «Máxima (silicio)» daba una frecuencia
  que no era un techo de nada. Sale sin dato y con su aviso, que con un
  kernel anterior al 5.17 dice que es por el kernel.
- Arreglado: la ficha de temperatura decía «núcleos» en procesadores que solo
  tienen un sensor para todo el encapsulado.
- Arreglado: sin sensor propio del procesador, su temperatura se tomaba de
  una zona del firmware que marca siempre lo mismo (27.8 °C).
- Arreglado: en una ventana estrecha, la especificación del procesador pasa
  a dos líneas en vez de cortarse.
- Nuevo: en los Intel, la ventana de tiempo de PL1 y PL2 («65.0 W · ventana
  de 28.0 s») y cuántas veces se frenó por temperatura desde el arranque.
- Cambiado: un procesador que no está en la tabla ya no repite «no está en la
  tabla de esta versión» en tres filas: lo dice el aviso de abajo.
- Arreglado: en un Ryzen de dos chiplets con V-Cache en uno (7950X3D,
  9950X3D), la página CPU enseñaba una sola L3 de 32 MB; ahora «96 MB +
  32 MB», con qué CPU lleva cada una al pasar el ratón.

### Cachés

- Nuevo: la latencia de cada nivel, después de medirla en Memoria.
- Arreglado: la página no se pintaba.

### Memoria

- Nuevo: el título dice la memoria instalada y la utilizable: «16 GB
  instalados · 15.4 GB utilizables». La instalada sale de los módulos; sin
  permisos, de su SPD si se lee.
- Nuevo: si los módulos van al máximo oficial de memoria del procesador, no
  se avisa de que van «por debajo de su velocidad» ni se sugiere activar
  XMP. El máximo sale de las fichas de AMD (de los Ryzen 3000 a los 9000,
  según cuántos módulos y de cuántos rangos) y de las de Intel que hay en la
  tabla (ver «Limitaciones conocidas»).
- Nuevo: en un procesador anterior a Nehalem (2008), la página dice que la
  velocidad de la memoria la decide el chipset.
- Nuevo: sin permisos, la velocidad real, el banco y el zócalo de cada módulo
  llevan un candado: están, y se ven al dar permisos.
- Cambiado: las fichas se llaman «Módulo 1», «Módulo 2», con permisos y sin
  ellos; el zócalo va en su campo. Y no se dice cuántos zócalos tiene la
  placa ni cuántos quedan libres: el firmware de muchas placas declara
  zócalos que no existen.
- Arreglado: una velocidad de memoria sale con el nombre de su grado en todas
  las generaciones: un DDR2-667 ya no sale «666 MT/s», ni una LPDDR5-5500
  «5466 MT/s».
- Arreglado: algunas latencias de DDR4 y de los perfiles XMP salían un ciclo
  por debajo de la real (un CL23 como CL22).
- Arreglado: sin permisos, la cabecera decía «a 3200 MT/s» como si fuera la
  velocidad a la que va la memoria; es la del catálogo del módulo, y ahora lo
  dice: «catalogados a 3200 MT/s».
- Arreglado: cuando el SPD no se lee, se dice por qué: si es la placa, con
  su motivo; si falta un driver, con candado, porque se arregla dando
  permisos.
- Arreglado: el aviso que proponía `acpi_enforce_resources=lax` para leer los
  módulos no decía el riesgo. Ahora lo dice, y que no merece la pena solo por
  ese dato.
- Arreglado: el fabricante del módulo se llama igual venga del SPD o de la
  tabla del firmware («Crucial», no «Crucial Technology»).
- Arreglado: que los módulos no traen perfiles rápidos se decía tres veces.
- Arreglado: en una placa que repite el nombre de sus zócalos (Gigabyte),
  dos módulos salían como «DIMM 1» y dos huecos como «DIMM 0». Ahora «Canal
  A · DIMM 1», «Canal B · DIMM 1».
- Arreglado: al dar permisos desde Memoria, las tarjetas de los módulos no
  aparecían hasta cambiar de página y volver.
- Arreglado: la medida de la memoria pedía páginas grandes y en Fedora no
  las tenía: la latencia de la RAM salía unos 10 ns más alta.

### Gráficos

- Nuevo: en «Relojes y enlace», los errores que ha contado el enlace PCIe de
  la tarjeta desde el arranque (AER): corregidos, no fatales y fatales.
- Nuevo: en «Consumo y temperaturas», el límite de consumo de fábrica de la
  tarjeta y entre qué valores se puede poner (amdgpu); si el de ahora está
  por encima, el globo dice que alguien lo ha subido.
- Arreglado: en una integrada de Intel, «Tomada del sistema 11.6 GB» era lo
  que el driver podría tomar, no lo que toma. Ahora dice «hasta 11.6 GB».
- Nuevo: el bloque «Ahora mismo» junta en tres barras la memoria de video
  ocupada, el consumo y el uso del bus, cada una con su cifra.
- Nuevo: en una integrada de Intel, las frecuencias del silicio (máxima y
  mínima), el reposo RC6, el uso de cada motor y, en las generaciones que lo
  publican, por qué se frena.
- Nuevo: la tabla de códecs de video marca lo que la tarjeta acelera y lo
  que no, sin depender del color.
- Nuevo: en «Ahora mismo», cada gráfica tiene una barra por motor que deja
  medir, integrada o dedicada: «Render / 3D» y el video. En AMD el video es
  una sola barra, «Video (codificar y decodificar)», porque ver y grabar van
  por el mismo motor y el driver da una cifra; en NVIDIA, decodificar y
  codificar van aparte; en Intel, además, mejora de video y copia, con un
  candado sin permisos. Lo que el driver de tu gráfica no publica se dice
  al pie.
- Cambiado: la dedicada de un portátil que está en reposo no se despierta
  para leerla. Gráficos dice «En reposo» y lo último que se supo, y no se le
  pregunta nada (ni su enlace, ni sus sensores, ni NVML) hasta que algo la
  use.
- Nuevo: sin permisos, el uso y el consumo de una gráfica Intel, y el uso de
  cada motor, llevan un candado.
- Cambiado: lo que una integrada no tiene (memoria propia, reguladores,
  ventilador) no sale con guion: se esconde y se nombra al pie en una frase.
  Si a una integrada de Intel no le queda nada propio en «Consumo y
  temperaturas», esa tarjeta se va.
- Arreglado: la temperatura de una gráfica que no la publica salía con un
  guion en Gráficos, en Sensores y en Inicio.
- Arreglado: el monitor se llama por su marca («Gigabyte AORUS FO27Q2») y no
  por la razón social del fabricante, que además cortaba la resolución en la
  tabla de pantallas. Su tamaño sale de sus milímetros: uno de 27 pulgadas ya
  no dice 26.6" ni 27.2".
- Arreglado: el ensamblador de la tarjeta sale por su marca: «PowerColor» y
  no «Tul Corporation / PowerColor».
- Arreglado: un identificador único todo a ceros ya no se enseña.
- Arreglado: «en reposo» en vez de «0 MHz» cuando el motor gráfico duerme.
- Arreglado: en una APU de AMD, el consumo de todo el procesador salía
  como el de la gráfica, y la temperatura del SoC como «Punto caliente».
  Ahora no se enseñan, y se dice por qué al pie.
- Arreglado: en una APU de AMD con un kernel anterior al 6.10, el uso del
  video salía cien veces mayor (0,45 % como 45 %).
- Arreglado: cualquier Arc decía «PCIe 1.0 × 1». Su enlace no se puede leer
  con seguridad y no se enseña.
- Arreglado: una Arc con el driver `i915` junto a una integrada enseñaba el
  uso de la integrada. Con `xe`, decía que no publica su temperatura, y la
  publica.
- Arreglado: en «Ahora mismo», el fondo de las barras cambiaba de largo
  según las cifras de la derecha. Ahora cada cifra tiene reservado el ancho
  de lo más largo que puede decir, y nada se mueve.
- Arreglado: la página parpadeaba cada segundo y se movía todo lo que hay
  por debajo de «Relojes y enlace»: unas filas que no tocan se enseñaban y
  se volvían a esconder con cada muestra. Ahora una muestra nueva solo
  cambia las cifras, y la página gasta menos de la mitad al recibirla.
- Arreglado: el uso de una gráfica AMD saltaba de un segundo a otro (de 85 %
  a 42 % jugando a lo mismo) porque era una lectura suelta. Ahora es la
  media del intervalo, como la que da MangoHud.
- Arreglado: la telemetría de AMD en su formato 1.0 se leía con las
  posiciones de otro, y salían cifras creíbles y falsas. Ahora se dice que
  ese formato no se interpreta.

### Almacenamiento

- Nuevo: lo que se ve del TRIM de cada unidad y, con permisos, el
  diagnóstico completo de cada disco.
- Nuevo: sin permisos, la temperatura de los discos SATA, las horas, lo
  escrito y la vida restante llevan un candado.
- Arreglado: un disco de platos ya no enseña «Vida restante».
- Arreglado: un NVMe decía «Conexión: NVME».
- Arreglado: en una ventana estrecha, la tabla de unidades se salía por la
  derecha; ahora recorta el modelo del disco y deja las cifras.

### Red

- Arreglado: la tarjeta de red empieza por su marca («Realtek RTL8111…»),
  también en Inicio y en Placa base.
- Arreglado: el tipo de interfaz sale traducido; la tabla dice 0 perdidos en
  vez de un guion; y se ve cuál de MB/s y Mb/s está elegido.
- Nuevo: las interfaces virtuales (Docker, máquinas virtuales, VPN) van
  plegadas debajo de las físicas.
- Arreglado: el dúplex salía «full».

### Dispositivos

- Arreglado: el micrófono de una cámara se llama así en Sonido, en vez de
  ser un «Audio USB» más.
- Arreglado: la cabecera del árbol USB es como la de las demás tablas.
- Arreglado: la cabecera dice cuántas tarjetas de sonido hay en total, no
  «de sonido» al lado de los dispositivos USB; y el árbol USB no enseña
  columnas vacías cuando no se saben marcas ni modelos (con `--anonymous`).
- Nuevo: sección nueva con lo enchufado por USB (en árbol, colgando de su
  concentrador, con su velocidad), las tarjetas de sonido, las cámaras y el
  adaptador Bluetooth.
- Arreglado: enchufar o quitar un USB con la página abierta podía cerrar el
  programa.

### Placa base

- Nuevo: los dispositivos PCIe, con su enlace actual y máximo, y lo que la
  plataforma tiene activado: IOMMU, virtualización, Above 4G Decoding, chip
  de sensores y códec de sonido.
- Nuevo: un dispositivo que `pci.ids` aún no conoce se nombra por su marca,
  su clase y su identificador: «Intel, audio HD (8086:f0c8)».
- Arreglado: en una placa AMD, el chipset salía «FCH LPC Bridge». Ahora,
  «AMD X570».
- Arreglado: una placa Gigabyte suelta se titulaba «Gigabyte -CF».
- Arreglado: la fecha de la BIOS salía en el orden del firmware, mes/día/año;
  ahora «2025-10-28».
- Arreglado: los fabricantes salen por su marca («MSI», «Gigabyte») y no por
  su razón social, y ningún «Desconocido» del firmware llega a la pantalla.

### Sistema

- Nuevo: si el kernel está «contaminado» (tainted) y por qué: un módulo de
  fuera del kernel, uno sin firmar, un aviso, un OOPS…
- Nuevo: la línea de arranque del kernel, con lo que identifica al equipo
  tapado (los UUID de los discos, los volúmenes cifrados, el nombre o la
  dirección): no llega ni a la ventana, ni al informe, ni a un volcado.
- Nuevo: las vulnerabilidades del procesador y sus mitigaciones, el
  intercambio (con lo que comprime zram), el gestor de arranque y la versión
  de Mesa.
- Nuevo: cuánto tarda cada fase del arranque (firmware, cargador, kernel,
  initrd y espacio de usuario) y el total, con cualquier gestor de arranque:
  con GRUB, el firmware y el cargador salen de la tabla del firmware y el
  resto de systemd.
- Nuevo: lo que falta porque el kernel es anterior al dato se dice así: «Tu
  kernel (5.15) no publica esto; existe desde Linux 6.11».
- Arreglado: los miles se separan con un espacio fino, igual en español que
  en inglés: las horas de un disco ya no salen «4.136 h», que parecían
  cuatro horas con decimales.
- Nuevo: «Kernel contaminado» dice qué módulos lo contaminan.

### Sensores

- Nuevo: lo que no tiene actividad nace plegado: los ventiladores a 0 RPM
  («Ventiladores parados · 3») y las interfaces de red sin tráfico.
- Nuevo: lo que dos drivers leen del mismo chip sale una vez. En una
  Gigabyte, seis temperaturas de placa en vez de doce.
- Nuevo: la curva del último minuto ocupa todo el ancho.
- Arreglado: las tensiones y temperaturas que el chip de la placa numera sin
  decir qué miden lo dicen al pie, en vez de parecer nombres; y las zonas del
  firmware que marcan siempre 16.8 °C o 27.8 °C van apagadas y dicen que no
  son una medida.
- Arreglado: «Paquete» y «Núcleo N», no «Package id 0» y «Core N».
- Arreglado: en una ventana estrecha, la cabecera se salía por la derecha.
- Nuevo: «Cargar el módulo» avisa antes de que eso sí cambia el sistema, qué
  módulo carga y cómo deshacerlo.

### Rendimiento

- Arreglado: «Renombrar» y «Borrar» del historial son pequeños y van a la
  altura de su fila.
- Nuevo: botón «Borrar las de otra escala», para quitar de una vez las
  pruebas que ya no se pueden comparar con las de ahora.
- Arreglado: una prueba medida con otra escala decía «—» donde va la
  puntuación; ahora dice con qué escala se midió y por qué no puntúa.
- Arreglado: «Borrar el historial» borraba el archivo y dejaba las pruebas a
  la vista hasta reabrir el programa.
- Arreglado: un historial estropeado impedía abrir la ventana y generar el
  informe.
- Arreglado: «mejor o peor que la vez anterior» comparaba la suma de las
  medidas en crudo, no la puntuación que se ve.
- Arreglado: dos pruebas de la misma duración podían darse por distintas,
  según cuánto tardara en acabar la última operación.

### Ajustes y escritorio

- Nuevo: «Ver y guardar el informe…» en Ajustes enseña el informe completo
  antes de guardarlo, el mismo que `--report`, y pide ahí los permisos que
  falten; el texto se pone al día al darlos. Antes guardaba el corto, sin
  enseñarlo. Y en GitHub, la plantilla de issue «Mi CPU y placa» para
  mandarlo.
- Cambiado: la primera vez Silux sale en el idioma del sistema: en español
  si el sistema está en español, y en inglés en cualquier otro caso. Antes
  salía siempre en español. Lo elegido en Ajustes sigue mandando.
- Nuevo: el AppImage se actualiza solo, con un clic. Apagado de serie: Silux
  no se conecta a nada si no lo pides. En Ajustes, «Buscar ahora» o «Buscar
  actualizaciones al iniciar»; si hay una versión nueva, el botón «Actualizar
  a …» la baja de GitHub, comprueba su suma SHA-256 y sustituye el AppImage.
  Solo ofrece versiones publicadas, no las de prueba: quien tenga la
  0.4-prueba1 recibirá la 0.4.
- Arreglado: un `settings.json` que no es un objeto JSON impedía abrir la
  ventana, y un solo campo con un valor raro devolvía todas las
  preferencias a las de serie. `"fluid_charts": "false"` encendía el
  movimiento fluido.
- Nuevo: Ajustes reordenado en grupos (General, Apariencia, Muestreo,
  Permisos, Integración con el escritorio, Compartir e informes, Acerca de),
  con interruptores en vez de casillas.
- Cambiado: la versión se enseña «0.4»; el tercer número sale solo en una
  versión de arreglos («0.4.1»). `--version` y el informe la siguen dando
  entera.
- Nuevo: «Integración con el escritorio» pone Silux en el menú de
  aplicaciones con su icono, y si quieres un acceso en el escritorio, sin
  pedir permisos. Desde el AppImage, la entrada apunta al AppImage; desde el
  código, va aparte, como «Silux (desarrollo)», para no pisar la otra.
- Arreglado: la ventana se presentaba con el icono del tema y no con el del
  programa.
- Arreglado: Ajustes hablaba de «las 53» banderas cuando la página CPU
  cuenta las de tu procesador.
- Arreglado: «Buscar ahora», y cualquier botón que se queda esperando,
  movían la página.
- Cambiado: con una versión de prueba, la búsqueda dice «No hay ninguna
  versión más nueva» y no «Tienes la última versión (0.4.0rc1)».
- Cambiado: «Acerca de» dice de dónde sale cada cifra de la tabla de
  procesadores y con qué Python y qué Qt corre esta copia.
- Cambiado: «Ver y guardar el informe…» lo enseña formateado.

### Aspecto

- Cambiado: el nombre es siempre «Silux», con mayúscula.
- Cambiado: la cifra de las fichas grandes empieza a la izquierda, donde su
  etiqueta, con la unidad pegada detrás.
- Nuevo: aspecto renovado. Tarjetas más limpias, títulos discretos, cifras en
  la misma letra que el resto y una barra lateral con un icono por sección.
- Nuevo: logo propio, una «S» dibujada como una pista de circuito sobre una
  ficha ámbar. Es el icono de la ventana, del menú y del AppImage, y
  sustituye al dibujo de lupa de la barra lateral.
- Nuevo: las páginas están reordenadas para que lo que se mira vaya arriba y
  cada dato salga una vez. Lo que se consulta una vez va plegado y a un clic:
  los identificadores de la gráfica, la identificación CPUID, el firmware y
  los sectores de cada disco, el desglose del uso de memoria.
- Nuevo: con «Movimiento fluido» (Ajustes › Apariencia), también las
  barras se mueven en vez de saltar: la de cada motor, la memoria, los
  discos, el uso de cada hilo. Llegan a su dato en menos de dos décimas de
  segundo desde donde estén, y la cifra de al lado cambia en el acto.
- Nuevo: lo que tiene arreglo (un permiso, un módulo por cargar) y sus
  candados van en azul; el ámbar queda para lo seleccionado y lo que se
  pulsa.
- Nuevo: en una ventana grande, las tablas reparten sus columnas y Placa
  base y Sistema ponen sus tarjetas en una fila.
- Arreglado: las filas que no existen en tu equipo ya no salen con guion: el
  enlace PCIe de un disco SATA, la versión de una distribución que no la
  tiene, la dirección de una tarjeta de red sin cable. Se dice al pie cuáles
  son.
- Arreglado: en las barras de Inicio, Memoria y Almacenamiento no se sabía
  qué color era cada cosa, y la caché no se distinguía del fondo; usaban azul
  y amarillo, que parecían avisos, y ahora son tonos del acento.
- Arreglado: las tablas se veían como un bloque negro dentro de su tarjeta,
  cortaban con puntos suspensivos textos que cabían y sus títulos quedaban
  lejos de las filas.
- Arreglado: las gráficas de las fichas tienen su eje de lado a lado desde
  que se abren, y la cifra del punto más alto ya no se monta sobre la curva.
- Arreglado: la explicación que sale al pasar el ratón por un dato se perdía
  al cambiar la ventana de tamaño.
- Arreglado: en las fichas grandes, la unidad saltaba a un lado cada vez que
  la cifra ganaba o perdía un dígito («9 %» a «10 %»), y a veces la fila de
  fichas entera. Ahora cada cifra tiene reservado su ancho y va pegada a su
  unidad.
- Arreglado: en Almacenamiento, los candados de lo que falta por permisos se
  quitaban y se volvían a poner cada segundo.
- Arreglado: la barra de estado decía una lista de fuentes internas y un
  número de datos sin permisos que no coincidía con el de Inicio.
- Arreglado: la barra lateral cortaba «Almacenamiento» en compacto, y «Qué
  pasa al dar permisos» abría demasiado pequeño.
- Arreglado: con un ayudante de permisos de una versión anterior instalado,
  Memoria y Almacenamiento salían cortadas por la derecha en una ventana
  estrecha.
- Arreglado: el contorno de los interruptores salía borroso.

### Línea de órdenes

- Arreglado: el informe se lee mejor: los avisos van como cita con su título,
  los valores de los sensores dicen de qué columna son, las notas de varias
  líneas no se pegan, los desplegables dicen su valor y no se cuelan las
  columnas que la ventana esconde («Concentrador · concentrador»).
- Arreglado: `--report ''` y una sección de `--sections` que no existe dan
  un error que dice qué pasa, en vez de seguir sin avisar.
- Nuevo: `--report` escribe el informe completo: todo lo que enseña cada
  página, tal y como lo enseña, sin el nombre del equipo, ni direcciones, ni
  números de serie. Pide los permisos al empezar (`--without-permissions`
  para no pedirlos). `--sections cpu,board` lo limita a esas páginas y
  `--short` da el corto de antes. En un procesador donde Qt no arranca sale
  el corto, y lo dice.
- Nuevo: `--help` en el idioma de la interfaz, con ejemplos. Con el AppImage,
  `--help` explica también cómo usar la terminal y el informe.
- Cambiado: las opciones van en inglés, cada una con su versión en español
  que también vale (`--informe`, `--sensores`, `--anonimo`…). La de la
  ventana `--anonimo` se llama ahora `--anonymous`, y los tamaños de letra
  de `--font-scale` son normal, large, larger y largest.
- Nuevo: `--samples N`, para que `--screenshot` capture con las gráficas
  llenas.
- Cambiado: el informe empieza con la versión como la dice la ventana
  («0.4-prueba1») y una lista, no una tabla sin cabecera.

### Privacidad

- Nuevo: de lo enchufado por USB no se lee nunca el número de serie, ni la
  dirección del adaptador Bluetooth. Con `--anonymous` y en el informe, cada
  dispositivo dice qué clase de cosa es y a qué velocidad va, no su marca.
- Arreglado: con `--anonymous`, dos tarjetas de red distintas salían con la
  misma dirección física.
- Cambiado: tu carpeta personal sale como «~» (los ajustes, la copia de
  desarrollo, el informe guardado): una captura ya no lleva tu nombre de
  usuario.
- Arreglado: lo que corre como administrador se busca por su ruta absoluta
  y corre con un Python aislado, y el instalador nunca escribe a través de un
  enlace ni en una carpeta que no sea solo de root.
- Arreglado: los iconos que dibuja Silux ya no van a una carpeta de nombre
  fijo en /tmp, donde otro usuario del equipo podía dejar los suyos.

### AppImage y paquete

- Arreglado: con el AppImage de la 0.3, la ventana podía cerrarse sola al
  cambiar de forma (al dar permisos, al conectar un disco o un USB). Era Qt
  6.11 con Python 3.10, y ninguno de los dos AppImage lo lleva ya. Si
  instalas desde el código con Python 3.10 o 3.11, se pide Qt 6.10 o
  anterior.
- Cambiado: el AppImage normal lleva Python 3.14 y Qt 6.12 (antes, 3.10 y
  6.11). Funciona también con glibc 2.34, así que entran RHEL 9, Rocky 9 y
  Alma 9. Pesa 53 MB en vez de 43 y arranca antes: la ventana, un 15 %. El
  `-compat` sigue con Python 3.10 y Qt 6.9.
- Cambiado: los dos AppImage dejan fuera el plugin de Qt para servir la
  ventana por VNC, que se llevaba dentro una pieza de glibc (`libresolv`).
  Pesan 1,4 MB menos.
- Arreglado: los AppImage y el paquete llevan la licencia de Silux y los
  avisos de libcpuid y CPU-X, de donde sale la tabla de procesadores, como
  piden sus licencias. En Ajustes, «Acerca de» dice qué datos son de cada uno
  y el botón «Avisos de licencia» los enseña enteros.
- Arreglado: el AppImage salía sin los iconos de la barra lateral ni la
  marca.
- Arreglado: fuera del AppImage, instalado con pip, el programa salía sin sus
  textos: la interfaz enseñaba claves como `cpu.card.clocks`.
- Nuevo: el README también en inglés.

### Limitaciones conocidas

- El máximo oficial de memoria de cada procesador cubre los Ryzen de las
  series 3000 a 9000 (salvo once que AMD no publica en ninguna ficha) y, de
  Intel, solo las generaciones 10.ª y 11.ª y el i7-12700K. En los demás no se
  compara la velocidad de la memoria con el máximo.
- Los límites de potencia de AMD (PPT, TDC y EDC) no se leen.
- Gráficos está probado con una Radeon dedicada (amdgpu) y una integrada
  Intel (i915). NVIDIA, el driver `xe` de Intel, nouveau y `radeon` están
  escritos sin haberlos visto en un equipo real.
- Una Arc no enseña su enlace PCIe y, con `i915`, tampoco su uso: leer su
  contador pide un cambio en el ayudante de permisos que está propuesto.
- Que la dedicada de un portátil no se despierte está escrito con el código
  del kernel, sin un portátil con dos gráficas delante.
- En un procesador ARM, la página CPU está escrita sin haberla probado.
- El perfil XMP de un módulo DDR4 puede salir un grado por debajo del suyo
  (un DDR4-3600 como 3200).
- Dos discos del mismo modelo pueden mezclar su temperatura en Sensores.
- No hay navegación por teclado.

## 0.3 (16 de noviembre de 2026)

### Antes de actualizar

- Las pruebas de rendimiento guardadas con la 0.2.0 se quedan sin puntuación,
  porque la escala cambia (v6). Siguen en el historial; para tener cifra hay
  que repetirlas.
- La puntuación sale ahora de dos de las cinco cargas: el resumen
  criptográfico y la compresión pesada. Las otras tres dependían de la zlib de
  cada distribución; se siguen enseñando, pero no puntúan.
- Si diste permisos permanentes con la 0.2.0, pulsa «Actualizar el ayudante
  del sistema»: el de la 0.2.0 se instalaba por un camino que otro programa
  podía aprovechar para colar algo como administrador.
- La sección «Benchmark» se llama «Rendimiento»: en los guiones,
  `--page Benchmark` pasa a ser `--page Rendimiento`.

### Memoria

- Nuevo: ancho de banda de la RAM y latencia de cada nivel de caché, con el
  botón «Medir».
- Nuevo: cuánto tráfico mueve la memoria en este momento, en los Intel (con
  permisos).
- Arreglado: velocidades que no existen, como «2700 MT/s» en un DDR4-2666, y
  el aviso falso de «por debajo de su velocidad» que encendían.
- Arreglado: con módulos de dos velocidades, el consejo para la BIOS pedía
  algo imposible.
- Arreglado: zócalos con el mismo nombre, zócalos vacíos con tarjeta propia y,
  sin permisos, numerados con un número que no era el de la placa.
- Arreglado: un ThinkPad con dos módulos bien repartidos decía «canal único».

### Procesador

- Nuevo: el voltaje del núcleo en la ficha de CPU, en AMD e Intel (con
  permisos).
- Nuevo: dentro de una máquina virtual, el programa lo dice y nombra el
  hipervisor.
- Arreglado: el consumo seguía pidiendo permisos después de darlos.

### Gráficos

- Nuevo: punto caliente, voltajes y motivos de recorte en las Radeon
  integradas recientes, como la 740M.
- Nuevo: si la telemetría de una tarjeta viene en un formato que aún no se
  sabe leer, se dice cuál es y va al informe.
- Arreglado: una RTX 3050 decía tener 16 núcleos CUDA.
- Arreglado: una gráfica integrada enseñaba la memoria del sistema como si
  fuera VRAM propia.

### Batería

- Nuevo: sección de Batería en los portátiles, con salud, ciclos, autonomía y
  topes de carga.
- Arreglado: la batería salía dos veces en el árbol de sensores, y un rango de
  0 a 100 % se enseñaba como un tope puesto.

### Rendimiento

- Nuevo: la prueba vigila lo que hace el resto del equipo mientras mide, no
  solo antes de empezar.
- Arreglado: la puntuación premiaba tener poca caché.

### Interfaz

- Nuevo: una imagen del equipo para pegar en un chat, desde Inicio o Ajustes.
- Nuevo: el aviso de que falta un permiso lleva el botón para darlo, y lo que
  no tiene arreglo va en gris en todas las páginas.
- Arreglado: un equipo de marca se titulaba con un código interno de placa,
  como «Lenovo 316C» en un ThinkCentre M80q.
- Arreglado: en los Intel, el árbol de sensores empezaba por el disco.
- Arreglado: Rendimiento y Ajustes se cortaban por la derecha en una ventana
  estrecha.
- Arreglado: `--page` con un nombre de sección que no existe guardaba la
  captura de otra página; ahora da error.

### Privacidad

- Arreglado: el informe anónimo y las capturas con `--anonimo` dejaban ver el
  nombre del equipo dentro de los nombres de red y de sensores, y las
  interfaces con un nombre puesto a mano; ahora salen como «interfaz1»,
  «interfaz2»…
- Arreglado: las capturas anónimas enseñaban los números de serie de monitores
  y batería y los puntos de montaje de las memorias USB.

### AppImage

- Arreglado: el de la 0.2.0 no arrancaba en algunos escritorios X11; le
  faltaban siete bibliotecas gráficas.
- Arreglado: en un procesador demasiado antiguo, explica qué pasa y qué versión
  descargar en vez de cerrarse con «Instrucción ilegal».
- Arreglado: en ese mismo caso, `--report` funciona; el aviso salía en inglés
  con el sistema en español y mandaba a una ruta que no existía.
- Arreglado: fuera del AppImage, instalado con pip en Python 3.10 o 3.11, el
  programa se cerraba con PySide6 6.12.0.

---

## 0.2 (30 de agosto de 2026)

Primera versión con número propio. Hasta aquí todo se llamó 0.1.0, así que
esta entrada recoge lo que ha cambiado desde entonces.

### Ojo al actualizar

- **Las puntuaciones guardadas antes de esta versión se quedan sin cifra.** La
  escala con la que se calculan cambió, y una puntuación medida con la anterior
  no significa lo mismo que una de ahora: ponerlas en la misma tabla enseñaría
  una diferencia que no existe. Las pruebas siguen en el historial con sus
  medidas y sus condiciones; lo que no sale es su puntuación. Para volver a
  tenerla hay que repetir la prueba.

### Nuevo

- **Una puntuación que se puede comparar con la de otro equipo.** Cada carga se
  mide contra lo que da en una pieza de referencia, así que las cinco pesan lo
  mismo. Antes la cifra la decidía una sola carga y no servía fuera del propio
  equipo.
- **El programa dice si tu equipo rinde como se espera de esa pieza**, cuando
  hay medidas suficientes de ese mismo procesador.
- **La interfaz habla inglés**, y se cambia de idioma sin reiniciar.
- **Un clic en un valor lo copia**, en las fichas y en las tablas. Se copia el
  texto entero, no el recortado con puntos suspensivos.
- **Se puede grabar la sesión a un CSV**, fila a fila.
- **Buscador en el árbol de sensores**, y las ramas abiertas se recuerdan.
- **Los mejores núcleos salen marcados**: el firmware publica lo bien que salió
  cada núcleo de la oblea y hasta ahora no lo enseñaba nadie en Linux.
- **Los recortes de la gráfica dicen desde cuándo**: medio segundo contra el
  límite de potencia es normal; un minuto contra el térmico, no.
- **El informe lleva la puntuación** y las condiciones en que se midió.
- **El informe se ha completado** y ahora sirve para revisar casi todo sin
  necesidad de capturas: los discos con sus contadores de salud (faltaban
  enteros), los sensores con su nombre y su valor uno a uno, el SPD de la
  memoria con sus perfiles XMP, las ranuras de la placa y con qué compilador se
  hizo el kernel. Sigue sin publicar el nombre del equipo, las IP, las MAC, los
  números de serie ni las rutas de las particiones.
- **El AppImage se reparte en dos**: el normal y uno compatible con
  procesadores anteriores a 2008 (Intel) o 2011 (AMD).
- **Cada copia dice de qué commit salió**, para que una captura se pueda situar
  en el tiempo.

### Arreglado

- **La prueba de rendimiento daba cifras que bailaban un 5 % sin motivo.** Era
  una de las cinco cargas, que alternaba entre dos velocidades según cómo le
  cayera la memoria. Cambiada por otra que mide lo mismo sin ese sorteo: ahora
  dos pruebas seguidas del mismo equipo se llevan un 1 %.
- **La medida de un solo hilo salía penalizada**, y con ella la comparación
  entre un núcleo y todos: un procesador de ocho núcleos decía escalar catorce
  veces, que no es posible.
- Un **Ryzen 5 5600G** se identificaba como un Ryzen 9 PRO.
- Una **RTX 4060** decía tener 24 núcleos CUDA en vez de los que tiene.
- Las **fichas de disco** enseñaban los nombres de los campos y ningún dato.
- La **ficha de la gráfica** salía entera a guiones cuando el driver no
  contestaba, incluso sin el nombre de la tarjeta.
- Las **salidas de vídeo que la carcasa no trae** ocupaban una fila cada una,
  todas a guiones.
- Los **dos chiplets de un Ryzen X3D** se contaban como uno, y enseñaban la
  caché grande como si fuera la de todo el procesador.
- El **AppImage no arrancaba en procesadores anteriores a 2008**.
- El **AppImage se llevaba módulos de Python sin sus bibliotecas**, así que dos
  de las cargas de la prueba reventaban en muchas distribuciones.
- Los **colores de los sensores** no llegaban a la pantalla: el árbol salía
  entero del mismo gris, sin el rojo de lo que se pasa de vueltas.
- **Dejó de pedir la contraseña en cada arranque.**
- Varias cosas seguían **en español con la interfaz en inglés**.
- El **informe** enseñaba nombres internos en la lista de sensores
  (`cat.temperature`) en vez de «temperaturas».
