# Cambios

Lo que cambia en cada versión, contado para quien usa el programa: qué se ve
distinto y qué deja de funcionar como funcionaba. El detalle técnico (por qué
se hizo así y qué se probó antes) vive en los mensajes de commit y en
`CLAUDE.md`, que son otra cosa y otro lector.

Cada copia dice de qué versión y de qué commit salió: `silux --version`, la
barra lateral y la cabecera del informe. Al pedir ayuda, ese par es lo primero
que hace falta.

---

## 0.4-prueba1 (sin publicar)

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
- El ayudante de permisos permanentes se quita desde Ajustes, con «Quitar
  el ayudante…», y sirve también si usas el AppImage.
- Dar los permisos para siempre ya no tiene botón propio en Memoria y
  Almacenamiento («No volver a pedirla»): se ofrece dentro de «Qué hace
  esto».
- La página Sistema ya no enseña el uso de la memoria: está entero en
  Memoria, en «Desglose del uso».
- «Encendido desde», en Sistema, y el campo `boot_time` del JSON pasan a
  año-mes-día («2026-11-17 18:15»), como la fecha de la BIOS.
- En Sensores, las ramas que nunca abriste o cerraste a mano vuelven a
  seguir la regla: una rama larga que tuvieras abierta («Relojes · 16») nace
  cerrada otra vez hasta que la abras.

### Permisos

- Cambiado: «Qué pasa al dar permisos» dice lo mismo en cuatro frases cortas.
- Nuevo: «Quitar el ayudante…» en Ajustes, si lo instalaste para siempre.
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
  ejecutar `python3` como administrador, y recomienda «Para siempre».
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

### Gráficos

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

### Privacidad

- Nuevo: de lo enchufado por USB no se lee nunca el número de serie, ni la
  dirección del adaptador Bluetooth. Con `--anonymous` y en el informe, cada
  dispositivo dice qué clase de cosa es y a qué velocidad va, no su marca.
- Arreglado: con `--anonymous`, dos tarjetas de red distintas salían con la
  misma dirección física.

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
