# Cambios

Lo que cambia en cada versión, contado para quien usa el programa: qué se ve
distinto y qué deja de funcionar como funcionaba. El detalle técnico (por qué
se hizo así y qué se probó antes) vive en los mensajes de commit y en
`CLAUDE.md`, que son otra cosa y otro lector.

Cada copia dice de qué versión y de qué commit salió: `silux --version`, la
barra lateral y la cabecera del informe. Al pedir ayuda, ese par es lo primero
que hace falta.

---

## 0.4.0 (sin publicar)

### Antes de actualizar

- En Sensores, los relojes y el uso de cada hilo se llaman «CPU 0», «CPU 1»…
  como en la página del procesador, y no «Core #0». Si tienes guiones que
  leen el CSV grabado o `--sensors` por esos nombres, hay que cambiarlos.
- `--page` con una sección que tu equipo no tiene (Batería en un sobremesa)
  termina con código 2 en vez de guardar la captura de otra página.
- Lo que se fuerza por la línea de órdenes (tema, densidad, tamaño de letra,
  acento, tamaño de ventana) vale solo para esa vez: ya no se queda guardado
  en tus preferencias.
- La orden para quitar el ayudante de permisos permanentes ha cambiado: es
  borrar sus dos archivos, y sirve también si usas el AppImage. Está en
  «Qué hace esto», lista para copiar.

### Memoria

- Nuevo: sin permisos, la velocidad real y el banco de cada módulo llevan un
  candado en vez de un guion: están, y se ven al dar permisos.
- Arreglado: con permisos, la tarjeta de Memoria de Inicio decía «31.3 GB ·
  Desconocido» si el primer zócalo de la placa estaba vacío. Ahora dice el
  tipo de los módulos puestos («DDR4-3200») o, si el firmware no lo da, nada.
- Arreglado: algunas latencias de DDR4 y de los perfiles XMP salían un ciclo
  por debajo de la real (un CL23 como CL22).
- Arreglado: sin permisos, la cabecera decía «a 3200 MT/s» como si fuera la
  velocidad a la que va la memoria; es la del catálogo del módulo, y ahora lo
  dice: «catalogados a 3200 MT/s».
- Arreglado: el aviso que proponía `acpi_enforce_resources=lax` para leer los
  módulos no decía el riesgo. Ahora lo dice, y que no merece la pena solo por
  ese dato.

### Procesador

- Nuevo: sin permisos, el voltaje lleva un candado en vez de un guion.
- Arreglado: la frecuencia de cada hilo es la que el procesador ha dado de
  verdad en el último intervalo, no la última que pidió el sistema.
- Arreglado: la gráfica de frecuencia se medía contra un techo equivocado y
  se quedaba en una barra vertical o recortaba las muestras.
- Arreglado: Inicio y la página CPU daban dos temperaturas distintas del
  mismo procesador en el mismo momento (33 °C y 30 °C).
- Arreglado: con el contador de energía parado, el consumo salía «0 W». Ahora
  se explica por qué no hay cifra.
- Arreglado: en AMD salía «núcleos 3,7 W» con el paquete a 64 W: ese contador
  es de un solo núcleo. No se enseña, y se dice.
- Arreglado: en los Ryzen que publican dos temperaturas (Tctl y Tdie) se
  enseñaba la que lleva sumado un margen para los ventiladores; ahora, Tdie.
- Arreglado: en AMD sin `amd-pstate`, «Máxima (silicio)» daba una frecuencia
  que no era un techo de nada. Sale sin dato y con su aviso.
- Arreglado: la ficha de temperatura decía «núcleos» en procesadores que solo
  tienen un sensor para todo el encapsulado.
- Arreglado: sin sensor propio del procesador, su temperatura se tomaba de
  una zona del firmware que marca siempre lo mismo (27.8 °C).

### Gráficos

- Nuevo: sin permisos, el uso y el consumo de una gráfica Intel llevan un
  candado, y pulsarlo pide los permisos.
- Arreglado: la temperatura de una gráfica que no la publica salía con un
  guion en Gráficos, en Sensores y en Inicio. Ahora se esconde y se dice al
  pie que esa gráfica no la da.
- Arreglado: Inicio decía que una gráfica integrada «usa 11.6 GB de la RAM».
- Arreglado: el monitor se llama por su marca («Gigabyte AORUS FO27Q2») y no
  por la razón social del fabricante, que además cortaba la resolución en la
  tabla de pantallas.
- Arreglado: el ensamblador de la tarjeta sale por su marca: «PowerColor» y
  no «Tul Corporation / PowerColor».
- Arreglado: un identificador único todo a ceros ya no se enseña.

### Rendimiento

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

### Interfaz

- Nuevo: Inicio avisa de lo que falta por permisos, con nombre («Salud de
  los discos», «Voltaje del procesador»), y con cuatro salidas: «Dar
  permisos», «Qué hace esto», «Ahora no» y «No volver a mostrar».
- Nuevo: «Qué hace esto» cuenta, antes de pedir la contraseña, qué lee el
  ayudante, que solo lee, cuánto dura y quién pide la contraseña.
- Nuevo: un candado donde falta un dato por permisos, en vez del mismo guion
  que lleva lo que no se sabe. Pulsarlo los pide. En Almacenamiento: la
  temperatura de los discos SATA, las horas, lo escrito y la vida restante.
- Nuevo: Inicio tiene tres tarjetas más: Temperaturas, con cada cifra junto a
  lo que mide, Red y Placa base. Cada una lleva a su sección.
- Nuevo: en Red, las interfaces virtuales (Docker, máquinas virtuales, VPN)
  van plegadas debajo de las físicas.
- Arreglado: la ventana se quedaba congelada mientras el sistema pedía la
  contraseña.
- Arreglado: la barra de estado decía una lista de fuentes internas y un
  número de datos sin permisos que no coincidía con el de Inicio.
- Arreglado: en las barras de Inicio, Memoria y Almacenamiento no se sabía
  qué color era cada cosa, y la caché no se distinguía del fondo.
- Arreglado: en una placa AMD, el chipset salía «FCH LPC Bridge». Ahora,
  «AMD X570».
- Arreglado: una placa Gigabyte suelta se titulaba «Gigabyte -CF».
- Arreglado: la fecha de la BIOS salía en el orden del firmware, mes/día/año;
  ahora «2025-10-28».
- Arreglado: los fabricantes salen por su marca («MSI», «Gigabyte») y no por
  su razón social, y ningún «Desconocido» del firmware llega a la pantalla.
- Arreglado: en Sensores, las tensiones y temperaturas que el chip de la
  placa numera sin decir qué miden lo dicen al pie, en vez de parecer
  nombres; y las zonas del firmware que marcan siempre 16.8 °C o 27.8 °C van
  apagadas y dicen que no son una medida.
- Arreglado: en Red, el dúplex salía «full».
- Arreglado: un NVMe decía «Conexión: NVME».
- Arreglado: el titular de Temperaturas de Inicio cambiaba de pieza por
  décimas de grado.
- Arreglado: las gráficas de las fichas tienen su eje de lado a lado desde
  que se abren, y la cifra del punto más alto ya no se monta sobre la curva.
- Arreglado: las tablas cortaban con puntos suspensivos textos que cabían, y
  sus títulos quedaban lejos de las filas.
- Arreglado: la explicación que sale al pasar el ratón por un dato se perdía
  al cambiar la ventana de tamaño.
- Arreglado: en una ventana estrecha, la cabecera de Sensores se salía por la
  derecha.

### Privacidad

- Arreglado: con `--anonimo`, dos tarjetas de red distintas salían con la
  misma dirección física.

### AppImage

- Arreglado: fuera del AppImage, instalado con pip, el programa salía sin sus
  textos: la interfaz enseñaba claves como `cpu.card.clocks`.

---

## 0.3.0 (16 de noviembre de 2026)

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

## 0.2.0 (30 de agosto de 2026)

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
