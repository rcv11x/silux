# Cambios

Lo que cambia en cada versión, contado para quien usa el programa: qué se ve
distinto y qué deja de funcionar como funcionaba. El detalle técnico —por qué
se hizo así y qué se probó antes— vive en los mensajes de commit y en
`CLAUDE.md`, que son otra cosa y otro lector.

Cada copia dice de qué versión y de qué commit salió: `silux --version`, la
barra lateral y la cabecera del informe. Al pedir ayuda, ese par es lo primero
que hace falta.

---

## 0.2.0 — 30 de agosto de 2026

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
