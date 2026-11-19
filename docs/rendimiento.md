# Rendimiento: lo que gasta silux y cómo se mide

Lo que cuesta tener silux abierto, en % de un núcleo, en el 5800X3D (CachyOS,
KDE Plasma en Wayland, RX 9070 XT, dos monitores a 240 y 144 Hz). Los
objetivos están en CLAUDE.md, junto a los 300 MB de memoria, y los comprueba
`tools/medir_consumo.py`.

## Los objetivos

En este equipo, para la página que más gasta y con el muestreo a un segundo,
medidos con `tools/medir_consumo.py` (sin pantalla):

| | Objetivo | Medido el 18 de noviembre |
|---|---|---|
| A la vista, sin movimiento fluido | 7 % | 5,7 % (Gráficos) |
| A la vista, con movimiento fluido | 9 % | 7,2 % (Gráficos) |
| Minimizada o en otro escritorio | 5,5 % | 4,5 % |
| Memoria (RSS) | 300 MB | 159 MB (176 MB en la pantalla) |

```bash
python3 tools/medir_consumo.py                 # unos 6 minutos; código 1 si algo se pasa
python3 tools/medir_consumo.py --paginas Inicio,CPU --segundos 6
```

No va en la suite: medir CPU en un runner compartido es ruido. Las cifras
dependen del equipo; en uno más lento, mirar la tabla más que el código de
salida. El margen sobre lo medido es para el ruido, que ronda el medio punto.

## Cómo se mide

**Sin pantalla** (`tools/medir_consumo.py`): la ventana con
`QT_QPA_PLATFORM=offscreen`, unas preferencias aisladas y el hardware de
verdad. Qt pinta igual, en memoria; lo que no cuenta es el compositor.

**En la pantalla**, para los tres estados de verdad: un guion de la sesión
(no está en el repositorio) que abre la ventana y la mueve con un guion de
KWin por D-Bus (`org.kde.kwin.Scripting`): siempre encima en un monitor, en
un escritorio virtual temporal que se crea y se quita, y minimizada. Por
página: 3 s para asentarse y 8 s midiendo CPU del proceso
(`time.process_time`, todos los hilos), RSS, fotogramas entregados al
compositor (`UpdateRequest` de la ventana) y pintados por clase de widget.
Con la pantalla apagada o la sesión bloqueada no sirve: no se pinta nada.

**Dónde se va el tiempo**: py-spy, que con `ptrace_scope` a 1 tiene que
lanzar él el proceso:

```bash
uv tool install py-spy
py-spy record --nonblocking --threads -r 200 -f raw -o perfil.txt -- .venv/bin/python -m silux.ui.app
```

El formato `raw` son pilas plegadas, una por línea: se suman por función
(propio e inclusivo) y por hilo.

**El coste en la gráfica**: silux no dibuja con la gráfica: Qt pinta los
widgets en memoria, con el procesador, y KWin compone (el proceso no tiene
abierto ningún nodo DRM; los ioctl de amdgpu abren y cierran el suyo, y
OpenGL y Vulkan se preguntan en un hijo). Lo que le cuesta a la
gráfica son los fotogramas que le manda, que es lo que mide la columna de
fotogramas. KWin no deja leer su `fdinfo`, y su CPU es demasiado ruidosa con
el escritorio en uso para atribuirle nada.

## Antes y después, en la pantalla

«Mañana» es `41dab81` (el código con que se midió en un i5-10400: Inicio, 5,9
y 16,5 %); «antes», `e0f83c8`, con las barras de las 17:00 ya arregladas;
«después», `39df74e`, con todo lo de esta pasada. Medido el 18 por la noche
en el monitor de 240 Hz, con nadie tocándolo. Memoria máxima, 176 MB.

| | Sin fluido, antes → después | Con fluido, antes → después |
|---|---|---|
| A la vista, la que más gasta / la media | 9,3 / 7,6 → **6,2 / 4,3** | 31,3 / 13,0 → **9,4 / 5,3** |
| En otro escritorio | 8,4 / 7,2 → **4,2 / 3,8** | 8,8 / 7,8 → **4,1 / 3,7** |
| Minimizada | 8,3 / 7,4 → **4,6 / 4,1** | 8,7 / 8,2 → **4,8 / 4,2** |

| Estado | Página | Sin fluido: mañana · antes · después | Con fluido: mañana · antes · después | Fotogramas/s con fluido: antes · después |
|---|---|---|---|---|
| a la vista | Inicio | 6,4 · 7,1 · **4,6** | 13,8 · 15,3 · **6,6** | 47 · 40 |
| a la vista | CPU | 7,9 · 8,0 · **5,2** | 40,5 · 31,3 · **8,5** | 42 · 36 |
| a la vista | Cachés | 7,5 · 7,7 · **4,0** | 7,1 · 9,0 · **3,5** | 1 · 0 |
| a la vista | Placa base | 7,6 · 7,1 · **4,0** | 6,9 · 8,9 · **4,1** | 0 · 0 |
| a la vista | Memoria | 7,2 · 7,5 · **4,0** | 10,2 · 9,4 · **4,8** | 24 · 26 |
| a la vista | Gráficos | 7,5 · 9,3 · **6,2** | 23,9 · 25,9 · **9,4** | 48 · 34 |
| a la vista | Almacenamiento | 7,2 · 7,7 · **4,8** | 19,6 · 18,8 · **5,6** | 34 · 10 |
| a la vista | Red | 7,5 · 7,4 · **4,4** | 21,6 · 17,6 · **6,1** | 33 · 12 |
| a la vista | Dispositivos | 6,4 · 8,1 · **3,4** | 7,6 · 7,9 · **3,6** | 0 · 0 |
| a la vista | Batería | 7,7 · 6,9 · **3,8** | 7,1 · 7,5 · **4,0** | 0 · 0 |
| a la vista | Sistema | 6,5 · 7,3 · **3,6** | 7,2 · 7,5 · **4,0** | 1 · 1 |
| a la vista | Rendimiento | 6,5 · 7,2 · **3,9** | 7,1 · 7,3 · **3,9** | 0 · 0 |
| a la vista | Sensores | 7,1 · 7,7 · **4,6** | 7,9 · 8,1 · **5,9** | 1 · 1 |
| a la vista | Ajustes | 6,5 · 7,5 · **3,8** | 7,5 · 7,4 · **4,0** | 0 · 0 |
| otro escritorio | Inicio | — · 7,4 · **3,6** | — · 8,0 · **3,6** | 0 · 0 |
| otro escritorio | CPU | — · 7,3 · **4,0** | — · 7,6 · **3,9** | 0 · 0 |
| otro escritorio | Cachés | — · 6,9 · **3,4** | — · 7,4 · **3,8** | 0 · 0 |
| otro escritorio | Placa base | — · 6,9 · **3,9** | — · 7,3 · **3,4** | 0 · 0 |
| otro escritorio | Memoria | — · 7,1 · **3,5** | — · 7,3 · **3,8** | 0 · 0 |
| otro escritorio | Gráficos | — · 7,2 · **4,2** | — · 8,2 · **3,7** | 0 · 0 |
| otro escritorio | Almacenamiento | — · 8,4 · **3,4** | — · 8,8 · **3,9** | 0 · 0 |
| otro escritorio | Red | — · 7,0 · **3,9** | — · 7,5 · **3,5** | 0 · 0 |
| otro escritorio | Dispositivos | — · 6,9 · **3,4** | — · 7,5 · **3,9** | 0 · 0 |
| otro escritorio | Batería | — · 6,8 · **4,1** | — · 7,4 · **3,5** | 0 · 0 |
| otro escritorio | Sistema | — · 6,9 · **3,5** | — · 8,1 · **4,0** | 0 · 0 |
| otro escritorio | Rendimiento | — · 6,9 · **4,0** | — · 7,7 · **3,5** | 0 · 0 |
| otro escritorio | Sensores | — · 7,8 · **3,7** | — · 8,3 · **4,1** | 0 · 0 |
| otro escritorio | Ajustes | — · 7,0 · **4,1** | — · 7,8 · **3,5** | 0 · 0 |
| minimizada | Inicio | — · 6,8 · **4,0** | — · 8,4 · **3,9** | 0 · 0 |
| minimizada | CPU | — · 7,2 · **4,3** | — · 8,5 · **3,6** | 0 · 0 |
| minimizada | Cachés | — · 6,9 · **4,4** | — · 8,4 · **4,5** | 0 · 0 |
| minimizada | Placa base | — · 6,7 · **3,9** | — · 8,7 · **4,0** | 0 · 0 |
| minimizada | Memoria | — · 7,7 · **4,4** | — · 7,9 · **4,6** | 0 · 0 |
| minimizada | Gráficos | — · 7,2 · **4,2** | — · 8,2 · **4,8** | 0 · 0 |
| minimizada | Almacenamiento | — · 7,4 · **4,4** | — · 8,6 · **4,1** | 0 · 0 |
| minimizada | Red | — · 7,4 · **3,8** | — · 7,8 · **4,5** | 0 · 0 |
| minimizada | Dispositivos | — · 7,0 · **4,6** | — · 8,5 · **3,9** | 0 · 0 |
| minimizada | Batería | — · 7,8 · **4,0** | — · 7,7 · **4,4** | 0 · 0 |
| minimizada | Sistema | — · 7,8 · **4,0** | — · 7,7 · **3,8** | 0 · 0 |
| minimizada | Rendimiento | — · 7,5 · **4,0** | — · 8,3 · **4,3** | 0 · 0 |
| minimizada | Sensores | — · 8,3 · **3,8** | — · 7,6 · **3,8** | 0 · 0 |
| minimizada | Ajustes | — · 7,4 · **3,8** | — · 8,2 · **4,5** | 0 · 0 |

## Antes y después, sin pantalla

Con `tools/medir_consumo.py`, `e0f83c8` frente a `4443931`:

| Estado | Página | Sin fluido: antes · después | Con fluido: antes · después |
|---|---|---|---|
| a la vista | Inicio | 7,4 · **4,4** | 13,0 · **6,0** |
| a la vista | CPU | 8,4 · **5,0** | 22,8 · **6,5** |
| a la vista | Cachés | 7,6 · **4,5** | 8,3 · **4,4** |
| a la vista | Placa base | 7,7 · **3,9** | 8,2 · **4,0** |
| a la vista | Memoria | 7,5 · **4,5** | 8,3 · **4,9** |
| a la vista | Gráficos | 9,4 · **5,7** | 21,9 · **7,2** |
| a la vista | Almacenamiento | 8,2 · **5,3** | 18,1 · **6,8** |
| a la vista | Red | 7,9 · **4,8** | 20,5 · **6,3** |
| a la vista | Dispositivos | 7,6 · **3,9** | 7,9 · **3,9** |
| a la vista | Batería | 8,0 · **4,4** | 7,7 · **4,4** |
| a la vista | Sistema | 7,3 · **4,1** | 8,2 · **3,8** |
| a la vista | Rendimiento | 7,3 · **4,6** | 7,7 · **4,6** |
| a la vista | Sensores | 8,0 · **5,2** | 8,9 · **5,1** |
| a la vista | Ajustes | 7,4 · **4,5** | 8,2 · **4,5** |
| escondida | Inicio | 8,2 · **4,5** | 8,1 · **4,1** |
| escondida | CPU | 7,3 · **4,0** | 7,9 · **4,4** |

## Qué se arregló, por orden de peso

Cada uno en su commit, con lo medido en el mensaje:

| Commit | Qué | Dónde se veía |
|---|---|---|
| `bf74fd0` | `pci.ids` se recorría entero en cada muestreo para nombrar la tarjeta de red | 7 % del suelo |
| `62dd137` | USB y sonido se releen solo si algo se enchufa (`codec#N` es el volcado entero del códec) | 10 % del suelo |
| `1989671` | El enlace PCIe resuelve su cadena de puentes una vez y no relee el máximo | 4,5 % del suelo |
| `2ef786c` | Los contadores de las 41 interfaces de red, de `/proc/net/dev` de una vez | 31 % del muestreo |
| `9420e27` | Las lecturas de uso de AMD, a 4 por segundo (0,24 puntos; a 10, 0,56) | — |
| `244073b` | La gráfica de líneas calcula su curva con cada muestra y la mueve con `translate` | 30 % con fluido |
| `c4e8cc4`, `2f353ee` | La matriz de núcleos: curvas guardadas y lo fijo desde una imagen | 21 % y 32 % en CPU con fluido |
| `f174d5d` | La barra apilada repinta su franja y no su leyenda | ~100 insignias/s en Inicio |
| `b3ccf00` | El temporizador late solo si hay algo que mover y la ventana se ve | 1,8 puntos en Placa base con fluido |
| `648a417` | La foto entera, solo a la página que se ve; las demás guardan su historia (`record`) | 35 % del suelo |
| `4443931` | Lo que se mueve se busca solo en la página abierta (3 ms → 0,04 ms por muestreo) | 0,7 puntos escondida con fluido |
| `4bf4ca5` | Una muestra con los mismos campos no enseña ni esconde nada | Gráficos, de 18,3 a 6-8 ms por muestra |
| `61d98f4` | Las fichas grandes reservan el ancho de su cifra | la unidad y la fila de fichas se movían |

## Lo que se recoloca con cada muestra

Lo que cuesta al hilo de la interfaz recibir una muestra con la página
abierta, sin pantalla y con letra grande y la ventana a
1607×942, en el 5800X3D: CPU del hilo (`time.thread_time`), mediana de diez
muestras. «Aplicar» es `apply`; «después», lo que Qt hace a continuación
(recolocar y pintar).

| Página | Aplicar | Después | Pintados | Show/Hide |
|---|---|---|---|---|
| Gráficos, antes | 5,8 ms | 12,5 ms | 297 | 20 |
| Gráficos, después | 3,4-3,6 ms | 2,5-4,1 ms | 31-45 | 0 |
| Almacenamiento, antes | 10,0 ms | 3,9 ms | 38 | 74 |
| Almacenamiento, después | 4,7-5,0 ms | 3,0-3,7 ms | 25-35 | 0 |

Antes había además ~10 Show/Hide por muestra en cualquier otra página: los
de Gráficos, que recibe la muestra entera aunque no se vea. Las
recolocaciones que quedan (de 4 a 19 por muestra, de `setText`) no mueven
nada y cuestan de 0,2 a 1,8 ms por muestra.

## Lo que queda

- **El suelo es el muestreo**: con la ventana escondida, el 65 % de lo que
  gasta silux es leer el equipo cada segundo (sensores, discos, red, la
  gráfica). Hace falta para las gráficas y los mínimos y máximos.
- **Los fotogramas de las barras**: mientras una barra va hacia su dato
  (180 ms), el temporizador va al ritmo de la pantalla, hasta uno cada
  7 ms. En una pantalla de 240 Hz son 143 por segundo durante ese rato.
- **Cada `setText` recoloca hacia arriba**: `ElidingLabel` toma su tamaño
  del texto, y Qt recoloca la tarjeta y la página aunque nada cambie de
  sitio. Son de 0,2 a 1,8 ms por muestra (CPU, la que más); quitarlo pide
  cambiar cómo mide esa etiqueta en toda la aplicación.
- **Pintar CPU después de cada muestra**: 11,5 ms, frente a 2-4 en las
  demás. Sin mirar todavía de qué.
- **Lo que hay detrás de una gráfica transparente**: al repintarla, Qt
  repinta también la tarjeta y la página de detrás (en Inicio, ~145 widgets
  por segundo). Pintarla opaca con el color de su tarjeta lo quitaría.
