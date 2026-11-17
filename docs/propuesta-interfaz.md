# Propuesta: una interfaz más ordenada y más refinada

## Pendiente para seguir en casa

Decidido y **hecho** en la rama `interfaz`: el logo `5-chaflan-ambar`,
Gráficos con el bloque «Ahora mismo», el estilo A y la tabla de códecs con
«✓» y «✗».

Por hacer, nada de esto está empezado:

- **Gráficos de la iGPU**: queda un hueco entre Frecuencia y Consumo por la
  ficha de Temperatura que falta. Que la rejilla se ajuste a las fichas que
  hay, o que la ficha diga «no publica temperatura».
- **Inicio, tarjeta de Red**: el nombre largo de la tarjeta se corta en la
  segunda línea, en claro y también en oscuro. Arreglarlo en los dos temas.
- **Raya bajo la cabecera de las tablas**: no se ve. El commit `03ef40b` dice
  que la lleva y no es verdad: corregir el código (o, si se quita, decirlo
  en el commit que lo haga; el mensaje ya empujado no se reescribe).
- **Sensores**: plegar por defecto las interfaces de red sin tráfico
  (`interfaz1`, `tailscale0`).
- **Textos**: «Núcleo 0 MHz» con la gráfica en reposo → «en reposo»; «Uso de
  video» en «Consumo y temperaturas» → «Uso del motor de video», sin tilde.
- **AppImage con el logo y los iconos nuevos**: sin construir. Comprobar en
  el CI de `interfaz` que los iconos de la barra lateral salen dentro del
  paquete.
- **Lo que ya había sin hacer**: los estados vacíos de una ficha, los
  identificadores en monoespaciada y medir el contraste de la paleta. (La
  coma decimal no se toca: está en `docs/convenciones.md`.)

El CI de `interfaz` no se ha lanzado: `gh workflow run appimage.yml --ref
interfaz`. Las capturas están en `~/Imágenes/silux-test/interfaz/` de la
oficina y no van al repositorio.

---

Sin código todavía. Lo que sigue sale de recorrer las trece páginas con este
equipo (i5-10400, Fedora) y con el volcado del 5800X3D, en oscuro a 1440×900 y
en compacto a 900×680, sobre la rama `ui-permisos` con la tercera tanda ya
hecha. Las capturas de partida están en `~/Imágenes/silux-test/tanda-3/despues/`
y las maquetas, en `~/Imágenes/silux-test/propuesta-interfaz/` (oficina).

Lo que no se toca: silux es un todo en uno. Los mejores núcleos, las
temporizaciones de la RAM, los relojes de la gráfica, los sensores y el
benchmark se quedan. Lo que se propone es ordenarlo mejor, no enseñar menos.

## Estado (17 de noviembre de 2026, última vuelta)

Todo esto vive en la rama **`interfaz`**, que sale de `master`. Nada de aquí
está en `master`.

Decidido por el autor:

- **Dirección A, «instrumento», con menos color.** Un solo acento, el ámbar,
  para lo seleccionado, el botón principal y las curvas. Barras en tonos del
  acento y grises. Iconos de la barra lateral grises, y el seleccionado en
  ámbar; sin color por sección.
- **Lo accionable y los candados, en azul**; lo que es así, en gris; un
  fallo, en rojo. El ámbar es la marca y no puede ser también un aviso
  (está en `docs/lecciones.md`).
- **La estructura de las nueve páginas**, aprobada para las cuatro primeras
  y hecha igual para las otras cinco.
- **Logo: la traza.** Falta elegir entre cinco variantes.

Hecho en la rama, un commit por cambio y con su test:

| Commit | Qué |
|---|---|
| `2eb9a28` | refactor(ui/graphics): cuatro fichas, la memoria en su tarjeta y los identificadores plegados |
| `4a405a3` | fix(ui/widgets): la barra de memoria va en tonos del acento, no en azul y amarillo |
| `7bf9f62` | refactor(ui/inicio): el equipo primero, el aviso al pie y nada repetido |
| `e5da48b` | refactor(ui/cpu): la identificación CPUID plegada y la leyenda de los núcleos en una frase |
| `662d81e` | refactor(ui/memory): los módulos y sus temporizaciones primero, lo que falta al final |
| `baf53cd` | chore(i18n): fuera las cinco claves que la estructura nueva dejó sin uso |
| `ea44b96` | fix(ui): la tarjeta de permisos de Memoria y Almacenamiento, sin «No volver a pedirla» |
| `8e39b85` | feat(ui/app): --samples, para capturar con las gráficas llenas |
| `7bb4ac0` | feat(ui/theme): lo accionable y los candados en azul; el ámbar, acento por omisión |
| `63aa648` | refactor(ui/system): Sistema empieza por lo suyo, y el uso de la memoria vive en Memoria |
| `6ece4b9` | refactor(ui/board): sin columnas de guiones ni la tarjeta de un equipo que no hay |
| `8689d1f` | refactor(ui/network): el titular es la conexión, y una interfaz sin enlace no enseña guiones |
| `180c3fd` | refactor(ui/storage): en la ficha de un disco, la salud arriba y lo del kernel plegado |
| `c6405b9` | refactor(sensores): lo que se mira primero, cada chip junto y las ramas largas plegadas |
| `03ef40b` | feat(ui/graphics): el bloque «Ahora mismo», y la tabla de códecs con su sí y su no |
| `927cb8b` | feat(ui): el estilo «instrumento» y el logo nuevo |
| `c96ffb9` | feat(ui): el logo, también en la imagen para compartir y en el README |

Cada página, en una línea:

- **Gráficos**: cuatro fichas; la VRAM entera en su tarjeta, con «Bus en
  uso»; «Consumo y temperaturas» sin repetir la del núcleo; identificadores
  plegados.
- **Inicio**: el equipo primero, el aviso de permisos al pie, sin frase fija
  ni arquitectura; «8.9 GB de 31.3 GB»; la tarjeta de la placa dice el
  chipset; la de Red, la interfaz y su dirección.
- **CPU**: identificación CPUID plegada; leyenda de los mejores núcleos en
  una frase.
- **Memoria**: módulos y temporizaciones antes de lo que pide permisos; el
  desglose del uso (el que estaba en Sistema), plegado bajo la barra.
- **Sistema**: sin la memoria repetida; lo que la distribución no declara se
  esconde y se nombra.
- **Placa base**: sin la tarjeta «Equipo» en una placa suelta; lo que el
  firmware no rellena, al pie.
- **Red**: titular con la interfaz y su dirección; una tarjeta sin cable no
  enseña cinco guiones.
- **Almacenamiento**: en la ficha de cada disco, la salud arriba y firmware
  y sectores plegados; sin «Enlace —» en un SATA.
- **Sensores**: temperaturas, ventiladores y consumo antes que tensiones y
  relojes; cada chip junto; las ramas de más de doce filas nacen plegadas y
  dicen cuántas llevan.

`Plegable` es la primitiva nueva de `ui/widgets.py`; la usan Gráficos, CPU,
Memoria y Almacenamiento.

Lo que **no** se hizo de lo que este documento proponía, y por qué:

- La fila «Frecuencia» de «Relojes» (CPU) se queda: en un híbrido hay una
  por tipo de núcleo.
- En Almacenamiento, la tabla de unidades y las fichas siguen repitiendo
  modelo, tipo y capacidad: la tabla es para comparar y la ficha para leer.
- En Sensores no se han agrupado visualmente los chips con un subtítulo:
  van juntos y con su nombre entre paréntesis cuando se repite la etiqueta.
- En Placa base no se tocaron «Firmware» ni «Chipset».

Lo último decidido, ya en la rama (los tres commits más recientes de la
tabla):

1. **Logo: `5-chaflan-ambar`.** Es el icono del paquete
   (`silux/ui/assets/silux.svg`), y con él el de la ventana, la entrada de
   menú y el AppImage; la marca suelta va en la barra lateral y en la imagen
   para compartir, y el README lo enseña junto al título. El emoji ya no
   existe. Las otras cuatro variantes siguen en
   `~/Imágenes/silux-test/interfaz/logo/` por si hay que volver.
2. **Gráficos, con el bloque «Ahora mismo»** debajo de las cuatro fichas:
   memoria de video, consumo y bus, cada barra con su nombre, su cifra y su
   porcentaje. Las tarjetas de abajo pierden su barra y las filas que decían
   lo mismo.
3. **El estilo de la dirección A, aplicado**: tarjetas con filo y no con
   borde, títulos en minúscula y tenues, cifras en la letra de la interfaz
   con números de ancho fijo, insignias sin borde, botón principal relleno,
   y la barra lateral con un icono por sección y la versión al pie.
4. **La tabla de códecs**, y con ella todas las tablas: sin el bloque negro
   de fondo, con raya bajo la cabecera, «✓» en verde para lo que la tarjeta
   acelera y «✗» en rojo suave para lo que no, cada uno con su texto al
   pasar el ratón.

Lo que queda de este documento sin hacer:

- **Los decimales de las temperaturas** en las cifras grandes: son de
  `render.py` y de sus tests, no del estilo. **La coma decimal, decidido
  que no**: el punto se queda (`docs/convenciones.md`, «El idioma»); lo que
  más abajo la propone ya no vale.
- **Los estados vacíos de una ficha** (una raya y un hueco donde no hay
  dato): piden tocar `StatTile`, que tiene dos fallos abiertos (F-M2).
- **Los valores que son identificadores** (`0000:0c:00.0`, `0xa201213`) van
  en la misma letra que el resto: la propuesta los quería en monoespaciada,
  y separarlos pide que cada página diga cuál es cuál.
- **El contraste** de la paleta nueva no está medido contra WCAG.
- **El tema claro** lleva la misma paleta de las maquetas, pero se ha
  mirado menos que el oscuro.

Capturas de antes y después de las nueve páginas, en los dos equipos, en
`~/Imágenes/silux-test/interfaz/estructura/`. Las del i5-10400 son de la
máquina, tras 65 muestras reales a un segundo. Las del 5800X3D salen de su
volcado, que es una foto fija: para que las gráficas tengan forma se le da
**movimiento simulado** a uso, temperaturas, consumo y frecuencias. Los
datos fijos (qué pieza es, sus tablas) son los del volcado.

**El logo, construido** (`interfaz/logo/traza.py`): rejilla de 96 unidades,
un solo grosor de pista, giros todos a 45° o todos del mismo radio, vías
como círculos concéntricos con el final de la pista, y tres correcciones
ópticas (anillo un 12 % más fino que la pista, la pista muere dentro del
anillo, la marca sube una unidad en la ficha). Cada variante trae icono con
ficha (degradado, canto inferior y filo de luz), la marca suelta, versiones
de 24 y 16 px en su rejilla de píxeles, la simbólica monocroma y su hoja.

| Variante | Qué cambia |
|---|---|
| `1-chaflan` | Giros a 45°, vías en anillo, ámbar arriba, ficha grafito |
| `2-curva` | Los mismos puntos con giros de radio 10 |
| `3-compacta` | Pista más gruesa, vías macizas, ámbar abajo, ficha clara |
| `4-ambar` | La curva en blanco sobre ficha ámbar |
| `5-chaflan-ambar` | La forma de la 1 sobre la ficha de la 4 |

## La propuesta, en corto

1. **Un solo orden para todas las páginas**: qué pieza es, cómo está ahora, su
   ficha, y lo técnico al final y plegado. Hoy cada página tiene el suyo.
2. **Cada dato en un solo sitio**, y los demás enlazan. Hoy la memoria del
   sistema se pinta entera tres veces.
3. **Una sola forma de cada cosa**: una ficha de cifra, un aviso, un botón de
   permisos, una tabla. Hoy hay dos o tres de cada.
4. **Una dirección visual** con menos cajas y más jerarquía. Hay dos maquetadas
   para elegir: «instrumento» y «tablero». Recomiendo la primera.
5. **Un logo**, uno solo, en lugar del emoji de la barra y del icono naranja.
   Cuatro conceptos en `propuesta-interfaz/logo/`.

Elegir dirección y logo es lo único que hace falta para empezar. El resto de
este documento es el porqué y el orden de trabajo.

## 1. Lo que sobra o está repetido

| Qué | Dónde sale | Qué haría |
|---|---|---|
| La barra de memoria del sistema, con su leyenda | Inicio, cabecera de Memoria y tarjeta «Memoria» de Sistema, que además repite la tabla entera (total, usada, caché, intercambio…) | Se queda en Memoria. Sistema pierde la tarjeta y gana un renglón que lleva allí |
| El nombre de la placa | En Inicio, dos veces en la misma pantalla: es el titular de arriba y otra vez el de la tarjeta «Placa base» | El titular de Inicio es el equipo; la tarjeta de la placa enseña BIOS, chipset y arranque, que es lo que no está arriba |
| `x86_64` | Insignia en Inicio, en CPU y en Sistema, y fila «Arquitectura» en CPU y en Sistema | Una vez, en CPU. En Sistema es del kernel y se queda como fila |
| El resumen de cachés | Insignias de la cabecera de Cachés («L1 datos 256 KB…») y, justo debajo, la tabla que dice lo mismo | Las insignias dicen lo que no dice la tabla: «3D V-Cache», «100.5 MB en total» |
| La frecuencia del procesador | Ficha «Frecuencia», primera fila de «Relojes» y, a medias, cada celda de núcleos | La ficha manda; «Relojes» empieza por el multiplicador |
| Dos formas de pedir permisos | El aviso de Inicio («Dar permisos», «Qué hace esto») y la tarjeta «Lo que falta necesita permisos» de Memoria, Almacenamiento y Gráficos («Leer con permisos de administrador», «No volver a pedirla»), cada una con su texto | Una sola pieza, la de Inicio, con el texto de cada página. Con el candado ya en cada dato, en las páginas puede ser un renglón |
| Cuatro maneras de apartar un aviso | «Ahora no», «No volver a mostrar» y, en la misma tarjeta de Memoria, «No volver a pedirla» | Las dos primeras, en todas partes |
| Las explicaciones fijas | «Vías y conjuntos» y «Línea» en Cachés, la frase de Inicio («Qué hardware llevas dentro…»), la nota de «Tráfico por interfaz» | A un «¿Qué es esto?» plegado o al tooltip del título. Ocupan lo mismo el primer día que el día cien |
| La versión y el identificador de la copia | Dos renglones bajo el nombre, en lo alto de la barra lateral | A la barra de estado y a Ajustes. Arriba compiten con la navegación |
| Filas que no existen en este equipo | «Enlace —» en un disco SATA, «Versión —» y «Variante —» en una distribución que no las tiene | Regla 5: lo que no existe se esconde y se nombra al pie. Está hecha en Gráficos y no en Almacenamiento ni en Sistema |

## 2. Lo que está mal ordenado

Lo importante primero, lo técnico más abajo o plegado. Página a página:

- **Inicio.** Lo primero que se ve es un aviso de permisos de 130 px, antes
  que el equipo. Va debajo del titular, en un renglón, o al pie. Las tres
  tarjetas de abajo (Temperaturas, Red, Placa base) quedan cortadas a 900 de
  alto en las dos densidades: o suben las temperaturas a la primera fila, que
  es lo que se mira, o la cabecera pierde su renglón de explicación.
- **CPU.** Bien arriba (cabecera, cuatro fichas, núcleos). Debajo, «Procesador»
  mezcla lo que se busca (núcleos, hilos, encapsulado) con lo que casi nadie
  mira (familia, modelo, stepping, firma CPUID, microcódigo). Lo segundo, a un
  bloque «Identificación» plegado. La leyenda de los mejores núcleos son dos
  renglones de letra pequeña a todo el ancho: mejor una frase corta y el resto
  al pasar el ratón por la estrella.
- **Memoria.** Sin permisos, la página es: cabecera, una tarjeta que pide
  permisos, una que ofrece medir, un aviso del SMBus y otro de lo que el
  equipo no publica. No hay un dato hasta el tercer bloque. El orden bueno:
  cabecera con lo que sí se sabe (total, tipo y velocidad catalogada si hay
  SPD), los zócalos, la medida, y al final lo que falta y por qué. En la
  maqueta ya va así.
- **Gráficos.** Seis fichas de cifra, y dos de ellas («VRAM ocupada», «Bus de
  memoria») son de memoria y tienen debajo su tarjeta. Cuatro fichas (uso,
  temperatura, consumo, frecuencia) y la VRAM en su tarjeta, con la barra.
  «Tarjeta» mezcla identidad (fabricante, ensamblador, driver) con inventario
  (ranura PCI, nodo DRM, identificadores): lo segundo, plegado. «Sensores» es
  en realidad «Consumo y temperaturas», y repite la temperatura de la ficha.
- **Sensores.** La página más densa y la que mejor está. Le falta poder
  plegar un aparato entero de un vistazo (ya se puede, pero abre todo) y que
  los dieciséis relojes del procesador no sean lo primero: temperaturas y
  consumo antes que relojes, que es el orden de `CATEGORY_ORDER` solo a
  medias. Los canales de `gigabyte_wmi` y de `it8688`, que son las mismas
  sondas por dos caminos, salen intercalados: agrupados por chip se leen.
- **Almacenamiento.** Fichas, tabla de unidades, tabla de particiones y luego
  una tarjeta por disco con catorce filas. Las tarjetas repiten modelo, tipo y
  capacidad de la tabla. Cada tarjeta: salud y temperatura arriba, y sector
  lógico, físico y planificador plegados.
- **Red.** La cabecera es el nombre del chip («RTL8125 2.5GbE Controller»); lo
  que identifica la conexión es la interfaz y su dirección. Bien resuelto lo
  de las virtuales.
- **Sistema.** Empieza por la memoria, que no es suya (ver arriba). Debería
  empezar por distribución, kernel y escritorio, que hoy están en el segundo
  bloque.
- **Placa base, Cachés, Rendimiento, Ajustes.** Orden correcto. En Placa base,
  cuatro tarjetas de cinco filas con mucha celda vacía en un sobremesa
  montado («Equipo»: fabricante, modelo, versión, familia y SKU, casi todo
  guiones): la tarjeta «Equipo» solo si dice algo.

## 3. Incoherencias entre páginas

| Qué | Cómo sale hoy | Lo que propongo |
|---|---|---|
| La cifra grande | En CPU y Gráficos, monoespaciada, con la unidad pequeña al lado («3.09 GHz»). En Red y Almacenamiento, monoespaciada con la unidad pegada y del mismo tamaño («0 B/s», «3.4 GB»). En Inicio, de palo seco | Una: cifra en la letra de la interfaz con números de ancho fijo, unidad pequeña |
| Los valores de las fichas | Monoespaciados siempre, también «activado», «auto», «PowerColor» o «sin límites» | Monoespaciado solo para lo que es un identificador o se copia: `0000:0c:00.0`, `1002:7550`, `0xa201213`. Lo demás, texto normal |
| Los decimales | «51.0 °C» en Inicio y en las fichas de la gráfica; «48 °C» en la ficha de CPU con el mismo dato a «47.6» en Inicio | Temperaturas sin decimal en las cifras grandes, con uno en tablas y sensores. Lo decide `render`, no cada página |
| El separador decimal | Punto en todas partes («31.3 GB») y, en Red, punto de millares («3.124.273 paquetes») | Uno. Con la interfaz en español, coma decimal; es un cambio de `render` y de sus tests |
| Las insignias de la cabecera | La primera va resaltada porque es la primera, no porque signifique algo: «equipo», «Navi 48», «enp6s0», «Linux 7.3.4» | Sin resaltar ninguna, o resaltar solo un estado («principal», «por debajo de su velocidad») |
| Los títulos de tarjeta | Mayúsculas con espaciado y peso 700; compiten con el titular de la página | Minúscula, tamaño pequeño, color tenue: el título nombra, no manda |
| Las tablas | Sobre un bloque más oscuro que la tarjeta, que no tiene ningún otro contenido; las fichas no lo llevan | Mismo fondo que la tarjeta, una raya bajo la cabecera |
| Los avisos | Banda a la izquierda en `Notice`; tarjeta entera con título en mayúsculas para permisos; pie en gris para lo que no existe | Tres piezas, una por estado: se arregla (ámbar), es así (gris), fallo (rojo). Ya es la regla; falta que la tarjeta de permisos sea un `Notice` |
| Las gráficas de las fichas | Con dos muestras, una raya en la esquina; en Sensores, la del árbol ocupa todo el ancho con las mismas dos muestras | La misma geometría en las dos |
| Los colores de las barras | El tramo «Caché» es azul fijo aunque el acento sea otro (se ve en la maqueta «instrumento») | Tonos del acento, o grises: ningún color fuera de la paleta |
| Los espaciados | Tarjetas de la misma fila con alturas distintas y hueco abajo (CPU: «Uso» y «Consumo» vacías junto a dos con gráfica) | Las fichas sin dato enseñan su candado o su motivo centrado, no un hueco |

## 4. Lo que hace falta para que se vea más moderno

- **Jerarquía.** Hoy todo es una caja con borde del mismo peso: cabecera,
  fichas, tarjetas, tablas dentro de tarjetas. Tres niveles bastan: la página
  (titular grande, sin caja), los bloques (superficie sin borde o con uno casi
  invisible) y los datos.
- **Tipografía.** Una familia para todo y números de ancho fijo donde hay
  columnas (`tnum`), con la monoespaciada para identificadores. Es el cambio
  que más quita el aire de terminal. Cuatro tamaños: titular, cifra, texto,
  nota.
- **Color.** Un acento con significado: es lo seleccionado y lo que se puede
  pulsar. Ámbar, rojo y gris quedan para los estados. Los datos van en tinta.
- **Iconos.** La barra lateral no tiene ninguno y trece nombres seguidos se
  leen, no se reconocen. Un icono de trazo por sección, del mismo grosor.
  También para candado, copiar y plegar, que hoy son de tres estilos.
- **La barra lateral.** La selección es un recuadro con borde; mejor un fondo
  suave sin borde. La versión, fuera de ahí.
- **El logo.** Ver el apartado 6.
- **Estados vacíos.** Una ficha sin dato es una raya y un hueco; debería decir
  en una línea por qué, o llevar su candado.
- **Tema claro.** Existe, pero está menos cuidado: el acento naranja tostado
  sobre blanco y los bordes grises lo hacen parecer un formulario. En las
  maquetas hay versión clara de las dos direcciones.

## 5. Dos direcciones, maquetadas

Las maquetas están hechas con la ventana de verdad: `maquetas.py` monta
`MainWindow` con el volcado del 5800X3D y le cambia desde fuera la paleta, la
hoja de estilos, la letra de las cifras, la barra lateral y el orden de la
página de Memoria. No hay un píxel dibujado a mano, así que lo que se ve es lo
que se puede conseguir sin reescribir las páginas. Por lo mismo, **no enseñan
los cambios de estructura** de los apartados 1 y 2 (bloques plegados, tarjetas
que se quitan): esos piden tocar cada página.

Cada dirección tiene veinte imágenes: Inicio, CPU, Memoria, Gráficos y
Sensores, en oscuro y en claro, a 1440×900 y en compacto a 900×680.

```
propuesta-interfaz/
├─ a-instrumento/{oscuro,claro}-{1440x900,compacto-900x680}/
├─ b-tablero/{oscuro,claro}-{1440x900,compacto-900x680}/
├─ logo/{1-oblea,2-traza,3-pulso,4-medida}/
├─ maquetas.py
└─ logos.py
```

### A. «Instrumento»

Un aparato de medida: sobrio, con mucho aire, y un solo color.

- Superficies sin apenas borde, esquinas de 12 px, más margen entre bloques.
- Cifras en la letra de la interfaz con números de ancho fijo; la
  monoespaciada desaparece de los valores.
- Títulos de tarjeta en minúscula y tenues.
- Un acento, el ámbar de la marca, para lo seleccionado, el botón principal y
  las curvas.
- Barra lateral con iconos de trazo y la selección como una pastilla suave.
- Insignias sin borde.

A favor: es la que más ordena con menos, envejece bien y deja que el dato sea
lo que destaca. En contra: todas las páginas se parecen, y quien salta entre
CPU y Gráficos no tiene una pista de color de dónde está.

### B. «Tablero»

Un panel de control: más contraste y un color por sección.

- Fondo más oscuro, tarjetas con borde y un filo de color arriba.
- Cada sección tiene su color (CPU azul, Memoria verde, Gráficos violeta,
  Almacenamiento ámbar, Red cian, Sensores coral) en los iconos de la barra,
  los títulos, las cifras y las curvas de su página.
- Cifras monoespaciadas y más grandes; títulos en mayúsculas.
- Selección de la barra con una banda a la izquierda.

A favor: se sabe dónde se está de un vistazo y tiene más carácter. En contra:
trece colores que mantener en dos temas, con contraste suficiente en cada uno;
el color deja de significar «esto se pulsa» o «esto va mal»; y los avisos en
ámbar chocan con la sección ámbar.

### Recomendación

**La A**, con una cosa de la B: el color por sección solo en el icono de la
barra lateral. Da la pista de lugar sin gastar el color dentro de la página.

Lo que cualquiera de las dos pide decidir aparte:

- **El acento por omisión.** Hoy es azul en las preferencias y naranja en el
  icono. Propongo el ámbar de la marca; los otros cinco siguen en Ajustes.
- **La coma decimal.** No es de estilo, es de `render` y de sus tests.

## 6. Un logo, uno solo

Hoy hay dos: el icono del programa (un cuadrado naranja con un chip blanco) y
el emoji de la barra lateral. Cuatro conceptos, cada uno con su idea, hechos
en SVG por `logos.py`:

| Concepto | La idea | Lo mejor | Lo peor |
|---|---|---|---|
| `1-oblea` | Silicio: la oblea con su chaflán y un dado encendido | Es el único que dice «silicio», que es de donde sale el nombre | A 16 px la rejilla desaparece y queda un aro con un punto |
| `2-traza` | La «S» de silux, dibujada como una pista de circuito entre dos vías | Se lee a cualquier tamaño, es una letra y es un circuito, y en monocromo no pierde nada | Una «S» sola dice poco del programa a quien no lo conoce |
| `3-pulso` | Chip y sensores: el encapsulado y la medida saliendo de él | Cuenta las dos mitades del programa | Es el más parecido a lo que ya existe: un recuadro con una onda es el icono de medio monitor de sistema |
| `4-medida` | Un dado en el centro de un indicador | Muy limpio, aguanta bien los 16 px | Genérico: podría ser un botón de encendido o un cargador |

Cada carpeta lleva la marca a color sobre oscuro y sobre claro, la variante
gruesa para 16 y 24 px, el monocromo para la bandeja (`currentColor`), el icono
de aplicación (la marca sobre su ficha, para el menú y el AppImage), los PNG a
16, 24, 48 y 256 px y una `hoja.png` con todo junto y en contexto: barra
lateral, lanzador y cabecera del README, en los dos temas.

Ninguno parte de un logo existente; están dibujados desde cero con cuatro
trazos cada uno. No he hecho una búsqueda de marcas registradas: antes de
publicar el elegido conviene mirarlo.

**Mi orden: `2-traza`, y `1-oblea` si se prefiere la idea al reconocimiento.**
Las maquetas llevan `2-traza` en la barra lateral solo para tener uno puesto.

El elegido se aplicaría, en un solo cambio, en: la barra lateral
(`ui/app.py`), `silux/ui/assets/` y la entrada de menú
(`tools/install_desktop.py`), el AppImage (`tools/build_appimage.py`), la
cabecera del README y la imagen para compartir (`ui/tarjeta.py`).

## 7. Qué va antes y qué después de partir `widgets.py`

`ui/widgets.py` tiene 1700 líneas y la fase 3 lo parte. Lo que toca sus
primitivas conviene hacerlo después, una vez; lo que no, puede ir ya.

**Antes, en `ui-permisos` o en una rama propia (no toca primitivas):**

1. El logo: assets, barra lateral, `.desktop`, AppImage, README, imagen.
2. La paleta y la hoja de estilos de la dirección elegida (`ui/theme.py`):
   bordes, radios, títulos, insignias, selección de la barra.
3. Los iconos de la barra lateral, y la versión fuera de ella.
4. El orden de los bloques de cada página (apartado 2): es mover llamadas a
   `addWidget`, con su test de orden.
5. Quitar lo repetido (apartado 1): la memoria de Sistema, la placa de
   Inicio, las insignias que duplican la tabla.
6. Esconder y nombrar lo que no existe en Almacenamiento y Sistema.

**Después de partir `widgets.py`:**

7. La ficha de cifra única (`StatTile`): unidad pequeña, estado vacío con su
   motivo, candado. Hoy tiene dos fallos abiertos (F-M2).
8. `InfoGrid` con bloques plegables («Identificación», «Inventario»).
9. `Table` sin su fondo, con celdas que admitan un candado (pendiente de la
   tercera tanda) y cabecera con raya.
10. Un solo `Notice` para los tres estados, y la tarjeta de permisos de las
    páginas convertida en uno.
11. La letra de las cifras: hoy `mono_font` se pide desde veinte sitios;
    separar «cifra» de «identificador» es un cambio de las primitivas.
12. La misma geometría para `Sparkline` y la curva del árbol de sensores.

**Aparte, porque no es de la interfaz:** la coma decimal y los decimales de
las temperaturas, que son de `render.py`.

Cada paso, un commit con su test montando la página. Las capturas de antes y
después, en `~/Imágenes/silux-test/`, como hasta ahora.

## 8. Lo que no he comprobado

- Las maquetas son del volcado del 5800X3D sin permisos, con muestras
  inventadas para que las curvas tengan forma. No hay maquetas del i5-10400.
- El contraste de los colores nuevos no está medido contra WCAG; los de la
  dirección B, menos todavía.
- Los números de ancho fijo (`tnum`) dependen de la tipografía del sistema: en
  Noto Sans funcionan; con otra letra habría que mirarlo.
- La memoria: los iconos y el logo son unos pocos píxeles, pero no he medido
  la ventana con ellos contra el presupuesto de 300 MB.
- No he probado nada de esto con la letra al máximo ni en inglés.
