# Cambios

Lo que cambia en cada versión, contado para quien usa el programa: qué se ve
distinto y qué deja de funcionar como funcionaba. El detalle técnico (por qué
se hizo así y qué se probó antes) vive en los mensajes de commit y en
`CLAUDE.md`, que son otra cosa y otro lector.

Cada copia dice de qué versión y de qué commit salió: `silux --version`, la
barra lateral y la cabecera del informe. Al pedir ayuda, ese par es lo primero
que hace falta.

---

## 0.3.0 (16 de noviembre de 2026)

### Ojo al actualizar

- **Las pruebas de rendimiento guardadas con la 0.2.0 se quedan sin
  puntuación.** La escala cambia otra vez (es la v6), así que su cifra no
  diría lo mismo que una de ahora. Las pruebas siguen en el historial con sus
  medidas y sus condiciones; para volver a tener puntuación hay que repetir la
  prueba.
- **La puntuación sale ahora de dos de las cinco cargas**: el resumen
  criptográfico y la compresión pesada. Las otras tres dependen de qué versión
  de zlib trae cada distribución —la misma pieza daba casi diez veces más en
  Fedora que en Ubuntu— y medían la biblioteca, no el procesador. Se siguen
  midiendo y enseñando, con la biblioteca que las midió al lado, pero no
  cuentan para comparar equipos.
- **Si diste permisos permanentes con la 0.2.0, pulsa «Actualizar el
  ayudante del sistema».** El ayudante que se instala en el sistema no se
  actualiza solo, y el de la 0.2.0 se instalaba por un camino que otro programa
  del propio usuario podía aprovechar para colar algo como administrador. El
  programa ya no usa esa copia y el botón la sustituye.
- **La sección «Benchmark» se llama «Rendimiento».** Si tenías un guion con
  `--page Benchmark`, cámbialo; ahora, un nombre de sección que no existe da
  un error en vez de guardar en silencio la captura de otra página.

### Nuevo

- **El ancho de banda y la latencia de la memoria, medidos de verdad.** En
  Memoria, el botón «Medir» da cuánto lee la RAM y lo que tarda en contestar
  cada nivel de caché y la propia RAM, con cifras muy parecidas a las de
  AIDA64 en la misma pieza.
- **Cuánto tráfico mueve la memoria en este momento**, en los Intel: en la
  ficha de Memoria, en el árbol de sensores y en el informe. Necesita permisos.
- **El voltaje del núcleo** en la ficha de CPU, en AMD y en Intel, leído del
  propio procesador. Necesita permisos.
- **Una sección de Batería** en los portátiles: salud, ciclos, autonomía y los
  topes de carga que algunos fabricantes permiten poner. En un sobremesa no
  aparece.
- **Una imagen del equipo para pegar en un chat**, desde Inicio o Ajustes, sin
  el nombre del equipo, las direcciones ni los números de serie.
- **Dentro de una máquina virtual, el programa lo dice**, con el nombre del
  hipervisor, al lado de los datos que lo delatan y en el informe. Antes
  enseñaba los núcleos y la placa virtuales como si fueran los de verdad.
- **Más datos de las Radeon integradas recientes**, como la 740M: punto
  caliente, voltajes y motivos de recorte, que salían a guiones. Si una tarjeta usa un
  formato de telemetría que todavía no se sabe leer, ahora se dice cuál y va
  al informe.
- **El aviso de que falta un permiso lleva el botón para darlo**, en la misma
  página. Y los avisos de lo que no tiene arreglo van en gris en todas las
  páginas, no solo en Gráficos.
- **La prueba de rendimiento vigila lo que hace el resto del equipo mientras
  mide**, no solo antes de empezar, y lo dice si algo se despertó a mitad.
- **El AppImage normal, en un procesador demasiado antiguo para él, explica
  qué pasa** y qué versión descargar, en vez de cerrarse con «Instrucción
  ilegal».

### Arreglado

- **El AppImage de la 0.2.0 no arrancaba en algunos escritorios X11**: le
  faltaban siete bibliotecas gráficas (`libxcb-cursor` y otras) que muchas
  distribuciones no traen instaladas. Ahora los dos paquetes se construyen en
  el mismo entorno en que se prueban, y la construcción falla si falta algo en
  vez de publicarlo así.
- **Instalado con pip en Python 3.10 o 3.11, el programa se cerraba** al
  pintar la primera gráfica con la versión más reciente de PySide6, la 6.12.0.
  Ahora se instala la anterior en esas versiones de Python.
- **En un procesador antiguo, el AppImage bloqueaba también `--report`**, que
  es justo lo que su aviso recomendaba usar mientras tanto. El aviso además
  mandaba a una ruta temporal que ya no existía y salía en inglés aunque el
  sistema estuviera en español.
- **La puntuación premiaba tener poca caché**: con la misma memoria, un
  procesador con menos caché sacaba más de un 40 % de ventaja.
- **Un equipo de marca se titulaba con un código interno de placa**: un
  ThinkCentre M80q salía como «Lenovo 316C».
- **La memoria salía con velocidades que no existen**, como «2700 MT/s» en un
  módulo DDR4-2666, y eso encendía el aviso de que iba «por debajo de su
  velocidad» sin ser cierto. Con módulos de dos velocidades, el consejo de
  activar el perfil rápido en la BIOS pedía algo imposible.
- **Los zócalos de memoria se titulaban mal**: dos módulos podían llamarse
  igual («DIMM 0»), un zócalo vacío ocupaba una tarjeta entera, y sin permisos
  se numeraban con un número que no era el de la placa.
- **Un ThinkPad con dos módulos bien repartidos decía «canal único»** y
  aconsejaba repartirlos.
- **En los Intel, el árbol de sensores empezaba por el disco** en vez de por el
  procesador.
- **En los portátiles, la batería salía dos veces** en el árbol de sensores, y
  un rango de carga de 0 a 100 % se enseñaba como si alguien hubiera puesto un
  tope.
- **Una RTX 3050 decía tener 16 núcleos CUDA**, y una gráfica integrada
  enseñaba la memoria del sistema como si fuera VRAM propia.
- **El consumo del procesador seguía pidiendo permisos después de darlos** en
  los kernels que lo reservan al administrador.
- **El informe anónimo y las capturas con `--anonimo` dejaban ver más de lo
  que prometían.** El nombre del equipo se colaba cuando una interfaz de red o
  un sensor lo llevaba dentro, aunque fuera en mayúsculas, y una interfaz con
  un nombre puesto a mano —una de WireGuard con el nombre de alguien, por
  ejemplo— salía tal cual. Ahora las interfaces cuyo nombre no lo pone el
  sistema salen como «interfaz1», «interfaz2»… en los dos sitios. En las
  capturas, además, se veían los números de serie de los monitores y de la
  batería y los puntos de montaje de las memorias USB, que llevan el nombre
  del usuario; ahora se tapan.
- **Rendimiento y Ajustes se cortaban por la derecha** en una ventana
  estrecha.

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
