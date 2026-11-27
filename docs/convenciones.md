# Cómo contribuir

Lo que hace falta para trabajar en Silux y las convenciones del repositorio,
con el motivo de cada una, que casi siempre es algo que salió mal. `CLAUDE.md`
las resume en una línea cada una.

## Antes de empezar

El entorno se monta con [uv](https://docs.astral.sh/uv/), y la suite corre
sin pantalla:

```bash
uv sync --extra gui
QT_QPA_PLATFORM=offscreen uv run pytest -n 4 -m "not a_solas"
QT_QPA_PLATFORM=offscreen uv run pytest -m a_solas
```

Son unos 4700 y tardan cerca de una hora en paralelo con ocho núcleos, casi
toda en las de anchura, que abren cada página de cada volcado con cada letra.
Cómo se ejecuta todo lo demás, en
[arquitectura.md](arquitectura.md#cómo-se-ejecuta-cada-cosa). El suelo es
Python 3.10: lo que pasa en un Python reciente no dice que pase en 3.10, y
`tools/probar_en_minimo.py --container` pasa la suite en el del suelo.

Un fallo se reporta con el informe (`--report informe.md`) en un
[issue](https://github.com/rcv11x/silux/issues). Un cambio, con un pull
request desde una rama que sale de `master`, una por tema.

Lo que toca privilegios (el ayudante, polkit, lo que se lee como root) se
propone en un issue antes de escribirlo.

## Al trabajar en este repositorio

**Los commits siguen Conventional Commits, en inglés y cortos** (desde el 20
de noviembre de 2026; los de antes, en español, no se reescriben). La primera
línea es `type(area): description`: el tipo es uno de los del estándar (`fix`,
`feat`, `test`, `docs`, `refactor`, `perf`, `build`, `ci`, `chore`), la zona
es el módulo o la carpeta que se toca (`spd`, `providers/hwmon`, `ui/widgets`,
`privileged`, `bench`, `report`, `cli`, `i18n`, `appimage`, `ci`, `tests`,
`claude`) y la descripción va en minúscula y sin punto final. El cuerpo, solo
si el título no basta para entender el porqué. El autor es el del
repositorio, y cuando el commit se escribe con Claude lleva al final la línea
`Co-Authored-By: Claude …` que corresponda al modelo. En inglés porque el
historial lo lee quien contribuye, como el código; lo que lee quien usa el
programa (la interfaz, el README, el CHANGELOG y las notas de cada versión)
sigue en español, y el README tiene además su versión en inglés.

```
fix(ui/widgets): small dash when a tile is born without data

Co-Authored-By: <el modelo de la sesión> <noreply@anthropic.com>
```

**Nunca se empuja sin preguntar.** Commitear en local es reversible; publicar
no, y menos con el CI atado a cada empujón a master. Se pregunta siempre,
aunque el commit anterior se haya empujado hace un minuto.

**Lo que toca privilegios se propone antes de escribirlo.** Si el cambio roza
los permisos, la seguridad o un estado que sobrevive entre máquinas o entre
versiones, primero va la propuesta (medida, con lo que se ha comprobado) y se
espera respuesta. No se escribe código y luego se pregunta: para cuando hay un
parche delante, la conversación ya empieza discutiendo el parche en vez de si
el enfoque es el correcto.

**Una comprobación que nadie ha visto fallar no es una comprobación.** Toda
guarda nueva se ejecuta contra el caso concreto que pretende cazar, y se
enseña que lo caza. Vale para los tests y vale para las validaciones del
programa: si solo se ha visto pasar, lo único demostrado es que no estorba.

**Y si depende de que alguien se acuerde de subir un número, tampoco lo es.**
El ayudante privilegiado llevaba su `VERSION` para que el cliente detectara una
copia instalada que se hubiera quedado atrás, y habría dejado pasar los tres
arreglos de escalada de privilegios del 31 de agosto de 2026: ninguno de los
tres tocó ese número, porque ninguno cambiaba el contrato. Se compara el
contenido, que no se olvida de cambiar. Un número hay que acordarse de subirlo
justo el día que más prisa hay.

**El commit del CLAUDE.md es el último antes de empujar.** Nunca uno
intermedio: el commit siguiente lo deja atrasado otra vez, con una fila que
el archivo no menciona y cifras que ya no cuadran. Se escribe cuando ya no va
a entrar nada más.

**Una rama solo para lo que tiene riesgo, y se borra al pasar a `master`.**
Con una rama por tema para todo, hasta un cambio de una línea en la
documentación esperaba a su CI, y en noviembre de 2026 había veintiuna ramas
en el remoto, todas ya en `master`, que nadie se atrevía a borrar. Lo que no
puede romper el programa (documentación, notas, textos, arreglos pequeños)
va directo a `master` con la suite pasada; lo que sí puede, en su rama hasta
que su CI sale en verde, y entonces se pasa y se borra.

**Un dato nuevo no está terminado hasta que hay un test que lo ve en pantalla**,
montando la página de verdad y comprobando la celda. Más de mil tests pasaban
con el voltaje del núcleo medido, guardado en el modelo y sin ninguna fila donde
pintarlo: probaban el proveedor, la interpretación de los bits y el reparto de
avisos, y ninguno miraba si eso se veía. Probar la fuente no es probar que se
ve, y lo que no se ve no está hecho.

**Ningún cambio visual se da por hecho sin comprobarlo en la captura.** Un
commit dijo una vez que la tabla llevaba una raya bajo la cabecera y la tabla
no la llevaba: la regla estaba escrita en la hoja de estilos, el test miraba
la hoja y nadie miró la imagen. Lo que se ve se comprueba donde se ve: se saca
la captura de después, se abre y se busca en ella lo que el cambio promete. Y
**el mensaje del commit dice solo lo que se ve en esa captura**, no lo que el
código pretende: un mensaje ya empujado no se reescribe, así que el que afirma
algo que no pasa se queda mintiendo en el historial.

**Un commit por cambio lógico.** Un cambio lógico es una causa, no un archivo
ni un arreglo: cuatro correcciones que salen de la misma causa son un commit,
no cuatro. El arreglo y el test que lo vigila van en el mismo commit, y lo que
solo mueve código va en uno propio, para que `git log --follow` siga sirviendo.
La suite queda en verde entre uno y otro.

## El CHANGELOG

Silux es rolling release: cada versión se llama por el día en que se publica,
`AAAA.M.D` sin ceros delante (`2026.11.28`), y es una entrada `## 2026.11.28`,
de la más nueva a la más vieja. Las de antes (`## 0.4-prueba14 (…)` y
anteriores) se quedan como están. Dentro, Lo destacado, Mejoras, Arreglos y
Problemas conocidos, contado para quien usa el programa y no commit a commit:
una línea por cambio, corta, sin emojis.

La entrada se escribe como «Sin publicar» y la versión se pone al publicar,
con `__version__`, en el mismo commit; la de arriba tiene que ser la versión
que declara el paquete, y hay un test que lo vigila. Como mucho una versión
al día: la versión es la fecha y no hay formato para dos.

Se publica como release normal, no *prerelease*, con la versión como
etiqueta y como título: así sale como «Latest» en GitHub y la encuentran las
copias de las pruebas, en cualquier canal (`docs/arquitectura.md`).

Debajo del título de cada versión, una línea «Con informes de Ana, Luis y
Marta.» con quien mandó los informes que la arreglaron, si ha dado permiso
para salir. Los nombres salen de `silux/db/thanks.json`, que rellena el autor
con los que cada uno le autoriza, y en ningún sitio se nombra a nadie que no
esté ahí: la misma lista sale en Ajustes → Acerca de y en el apartado
«Gracias» de los dos README (`tests/test_thanks.py`). Sin nadie que nombrar,
la línea no se pone.

Las notas de cada release en GitHub no repiten el CHANGELOG: la tabla de qué
AppImage descargar y una lista corta de lo que cambia, con el enlace a su
entrada del CHANGELOG para el resto. Las lee quien va a descargar y quiere
saber qué archivo y qué trae; las peticiones y las instrucciones para mandar
un informe se quedaban ahí, versión tras versión, tapando lo que cambiaba.
Eso va en el README, que es el mismo para todas.

## El idioma

La interfaz va en **español neutro**: `video` y no «vídeo», `archivo` y no
«fichero», `dispositivo` y no «aparato», `equipo` y no «ordenador». Nueve de
cada diez hispanohablantes están al otro lado del Atlántico y no hay motivo
para cerrarles la puerta por una tilde.

**El separador decimal es el punto y no se toca**: «31.3 GB», «4.55 GHz».
No es un descuido que quede por arreglar. Si algún día se cambia, no será por
una coma fija: seguirá el idioma del sistema, que es quien sabe cómo escribe
los números quien está delante.

El código va aparte. Lo nuevo se escribe en inglés y con el estilo de PEP 8
(`snake_case` para funciones, variables y módulos, `CamelCase` solo para
clases, constantes en mayúsculas), con comentarios en inglés que dicen el
porqué y no repiten el código. Un porqué que no cabe en una o dos líneas va
a [decisiones/](decisiones/), con sus datos y lo descartado, y el comentario
lo enlaza. Gran parte del código de antes está en español y se pasa por
zonas, cada una en su rama: hasta entonces no se renombra nada al pasar, pero
tampoco se añade nada nuevo en español. Mezclar las dos lenguas en un mismo
nombre no vale nunca.

**Las claves son símbolos** (`cpu.card.clocks`), así que el español es un
idioma más y vive en `db/lang/es.json`. Retocar una frase en castellano es
cambiar un valor, no una clave: la traducción inglesa no se descuelga.

Lo malo conocido de las claves simbólicas (que una traducción incompleta
enseñe `cpu.card.clocks` en pantalla) aquí no pasa, porque `_()` tiene tres
escalones: el idioma pedido, el español y por último la clave. Un `en.json` a
medias enseña español entre inglés, que se lee; la clave solo asoma cuando la
frase no está escrita en ninguna de las dos lenguas, y entonces es justo lo
que hace falta ver.

Las categorías del árbol de sensores también son claves. Esos nombres
(«Temperaturas», «Ventiladores») los inventa el programa para agrupar y no
salen del kernel, así que son interfaz: la frontera no está en de dónde viene
el dato sino en quién escribió la palabra.

Los nombres de sección son claves (`nav.sensors`), así que `select_section`
acepta tres cosas: lo que se ve, la clave y el nombre en español. Sin lo
tercero, `--page Sensores` dejaría de funcionar en cuanto alguien se pusiera
la interfaz en inglés.

Se eligió JSON sobre gettext por quién escribe los archivos: un `.po` hay que
compilarlo a binario antes de que sirva, y esto se corrige desde el navegador
de GitHub y se lee en el diff línea a línea.

**Los proveedores también traducen, pero solo lo que se inventan**: el aviso
que explica por qué falta un dato, el nombre que le ponen a un sensor («Punto
caliente» donde amdgpu dice `junction`), la función de un motor gráfico. Lo
que leen del equipo pasa entero y sin tocar. La línea se comprueba sin
ejecutar nada: a `_()` solo puede llegar un literal escrito en el archivo o
una variable que se rastree hasta una tabla declarada ahí mismo. Un
`_(entry["label"])` traduciría un dato, y eso rompe la detección de una
gráfica en cuanto alguien se pone la interfaz en inglés.

**Fuera de la interfaz, las claves no se traducen solas.** El informe agrupa
los sensores por categoría, y esas categorías son claves porque el nombre lo
inventa el programa. Como `report.py` no importaba nada de `i18n`, salían
crudas: «cat.temperature (2), cat.power (2)» en el archivo que se le pide a
quien reporta un fallo. Y la traducción que necesita ahí es `en_español` y no
`_()`: el informe es castellano fijo («Procesador», «Placa base»), así que con
la función normal, el de alguien con la interfaz en inglés mezclaría los dos
idiomas en la misma página.

**Nada de `_()` en una constante de módulo.** Se resuelve al importar, cuando
todavía no se sabe qué idioma quiere nadie, así que se queda con el castellano
para toda la sesión; y como quien monta la ficha vuelve a pasar cada entrada
por `_()`, la segunda llamada recibe «Uso» (que no es una clave) y devuelve
«Uso». Así salía la columna «LEYENDO» en medio de una tabla de discos en
inglés: la tupla llevaba once claves y una traducción ya hecha, y era la única
que no cambiaba de idioma. Hay un test que lo vigila.

La interfaz está entera en los dos idiomas, y un test vigila que no quede
ninguna clave sin traducir. Hay otro que recorre el árbol de sintaxis de cada página buscando
constructores de widget con una cadena española a pelo, porque eso es lo que
no se ve hasta abrir la pantalla en el otro idioma y ningún test normal lo
nota. **Descubre los archivos solo**: con la lista escrita a mano se quedaron
cinco páginas enteras sin traducir y el test seguía en verde, porque no las
miraba.

**`_` no se puede usar de descarte.** `for _ in range(10)` o `ruta, _ =
dialogo()` es lo idiomático en Python para decir «esto no me importa», y aquí
sustituye la función de traducción dentro de esa función: la siguiente llamada
revienta con «'int' object is not callable», un error que no menciona ni el
idioma ni la traducción. Y lo hace meses después, cuando alguien añade una
cadena traducible en ese mismo método. Hay un test que lo vigila.

`tools/gen_lang.py` los mantiene al día. Solo recoge lo que ya está envuelto
en `_()`: adivinar qué cadena del código es texto de interfaz sale mal en
silencio, y un `"amdgpu"` traducido rompe la detección de la gráfica sin que
nadie lo relacione con el idioma. **Nada de `providers/` se traduce**: lo que
sale de ahí es el dato del equipo, no una frase del programa.
