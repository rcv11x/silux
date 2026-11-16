# Empaquetado: el suelo, el AppImage y las guardas

Qué exige el programa desde el código fuente, qué exige la copia que se
reparte y por qué, y cómo se comprueba. Las lecciones de esta zona están en
[lecciones.md](lecciones.md#empaquetado).

Que pasen aquí no dice que pasen en el mínimo. El suelo declarado es Python
3.10 y aquí se desarrolla en 3.14: `self.enterContext` es de 3.11 y se llevó
once tests por delante en el CI estando todo verde en local, y el mismo día un
traceback perdía el texto de la línea porque hasta 3.12 quien pinta las
excepciones no atrapadas es el escritor en C. Ninguna de las dos se ve leyendo
el código —se probó `vermin -t=3.10` y ni siquiera cazaba la primera—, así que
la única comprobación que vale es ejecutar, y para eso está
`probar_en_minimo.py --container`. El CI lleva matriz con las dos puntas.

`--container` no es opcional para repartir: sin él se construye contra el
Python y el Qt de la máquina, y sale un AppImage que exige el juego de
instrucciones y la glibc de quien lo compiló. Con contenedor sale
`x86-64` a secas —cualquier procesador de 64 bits, de 2003 en adelante— y
glibc **2.35**, que es la de Ubuntu 22.04, la base del contenedor. Eso deja
fuera Ubuntu 20.04, Debian 11, Mint 20 y RHEL 9, que se quedan en 2.31-2.34.
El símbolo que más alto pide es `hypot@GLIBC_2.35` del propio intérprete: para
bajar el suelo hay que construir sobre una base más antigua con Python 3.10
puesto a mano, no basta con tocar una opción. El paso final de comprobación recorre el
AppDir y avisa de lo que resuelve fuera. Si avisa de algo, hay que mirarlo:
lo que sale ahí es una biblioteca que el programa espera encontrar puesta en
la máquina ajena. Después mira el juego de instrucciones, por lo mismo: que
no se cuele un requisito de procesador que aquí no se nota.

**Ese suelo es el del AppImage y no el del programa**, y conviene no juntarlos
porque el `pyproject.toml` parece decir otra cosa. Su clasificador
`Operating System :: POSIX :: Linux` es la casilla donde PyPI archiva Linux,
taxonomía y no una promesa: ni dice que esto corra sobre cualquier POSIX —un
BSD o un macOS son POSIX y ahí no hay sysfs, ni hwmon, ni ioctl de DRM que
leer— ni sabe nada de glibc, que ni siquiera es lo que ese campo describe.
Desde el código fuente los requisitos son los del README: Python 3.10, un
kernel Linux y PySide6 para la ventana. La glibc 2.35 y el juego de
instrucciones son de la copia que se reparte, porque se los lleva dentro. Así
que estrechar el clasificador no arreglaría nada —no hay dónde escribir ahí
una versión de glibc— y perderlo sí cuesta: es por lo que se encuentra el
paquete.

**PySide6 lleva dos techos en el empaquetador, y cada uno es por otra cosa.**
El `<6.10` es del AppImage `--compat`, y de nadie más. Qt 6.10 pasó a compilarse con `-march=x86-64-v2`, y no en rutas aparte que se
eligen mirando la CPU, sino dentro de funciones normales: `QString`,
`QUtf8::convertToUnicode`, `QPainterPath::quadTo`. En un procesador sin
SSE4.1 eso es «Instrucción ilegal» y un volcado antes de pintar nada; Qt trae
un aviso para ese caso —«Incompatible processor»— y ni siquiera llega a
salir, porque revienta antes de imprimirlo. x86-64-v2 es Nehalem (2008) en
Intel y Bulldozer (2011) en AMD, así que deja fuera los Core 2, los Athlon II
y los Phenom II: justo la clase de equipo cuyo dueño quiere saber qué lleva
dentro. Lo descubrió un Athlon II X2 250u ajeno, no una prueba de aquí.

Quién lo pone y quién no: `RANGO_PYSIDE`, en el empaquetador, se lo pone al
`--compat`. El normal se lleva la última serie que funciona a propósito —los
arreglos de Qt, y sobre todo los de Wayland, están ahí—, y por eso su techo
es otro y por otro motivo: **`<6.12`, porque PySide6 6.12.0 tumba Python 3.10
y 3.11.** Resta una referencia a `None` en cada método que devuelve `void`
(`lineTo`, `setY`…); desde 3.12 `None` es inmortal y no se nota, pero en el
3.10 que va dentro del AppImage el proceso muere con «Fatal Python error:
none_dealloc» al pintar la primera gráfica. Se quita cuando una 6.12.x lo
corrija y la suite pase en 3.10 con ella. Como el CI pregunta el rango a
`--pyside-range`, ese techo alcanza también a sus tests.

`pyproject.toml` no le pone techo a PySide6: no es su trabajo decidir qué Qt
corre en la máquina de otro, y quien instala desde el código fuente casi
siempre usa el PySide6 de su distribución, que no lee los extras del
`pyproject`. **Con una excepción, y es un cierre reproducido, no una
preferencia de Qt:** el extra `gui` pide `PySide6<6.12` solo con
`python_version < '3.12'`. Ahí la 6.12.0 tumba el proceso —lo de `None` de
arriba, medido con 2000 llamadas a `lineTo`: −2001 con 6.12.0 y 0 con 6.11.3—,
y quien hace `pip install silux[gui]` en un 3.10 recibiría un programa que se
cae al pintar la primera gráfica. Desde 3.12 la 6.12 funciona y no se le quita
a nadie. Un techo aquí solo entra con ese criterio: una versión concreta que se
cae, reproducida, y limitado a donde se cae; el `<6.10` del `--compat`, que es
de procesador y no de cierre, no entra. Este repositorio se desarrolla con
6.11.

Lo que sí hay en todas partes es la guarda, en dos versiones porque la
pregunta se responde distinto según de dónde se arranque. En el AppImage está
en el AppRun, en shell, y es **exacta**: el empaquetador lee el desensamblado
de lo que acaba de meter y le pasa las banderas que encontró. Desde el código
fuente está en `ui/guarda.py`, corre antes de importar Qt y es **una regla**,
no una medida: de 6.10 en adelante se pide x86-64-v2, porque leer el ELF del
Qt del sistema en cada arranque costaría más que arrancar. Como es una regla
puede equivocarse —una distribución es libre de compilar su 6.10 para x86-64
a secas—, así que `SILUX_SIN_GUARDA=1` la desactiva: equivocarse aquí tiene
que costar una variable de entorno y no un programa que no abre. Las dos
miran la misma lista de cinco banderas y hay un test que no las deja
separarse.

Cada copia lleva dentro de qué commit salió: debajo de la versión, en
`--version` y en la cabecera del informe. Lo escribe el empaquetador en
`silux/_build.txt` —dentro del AppImage no hay repositorio al que preguntar— y
desde el código fuente se lee de git en vivo. Un `+` al final avisa de que esa
copia tenía cambios sin guardar. Nace de que las capturas que manda la gente no
decían de qué versión eran, y un fallo ya corregido se investigaba dos veces.
