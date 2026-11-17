# Convenciones, con su porqué

`CLAUDE.md` las resume en una línea cada una; aquí está el motivo de cada
una, que casi siempre es algo que salió mal.

## Al trabajar en este repositorio

**Los commits siguen Conventional Commits, en español.** La primera línea es
`tipo(zona): descripción`: el tipo es uno de los del estándar, sin traducir
—`fix`, `feat`, `test`, `docs`, `refactor`, `perf`, `build`, `ci`, `chore`—,
la zona es el módulo o la carpeta que se toca —`spd`, `providers/hwmon`,
`ui/widgets`, `privileged`, `bench`, `report`, `cli`, `i18n`, `appimage`, `ci`,
`tests`, `claude`— y la descripción va en minúscula y sin punto final. El
cuerpo explica el porqué del cambio: qué fallaba, cómo se vio y qué se
comprobó, incluido que el test se vio fallar antes del arreglo. El autor es el
del repositorio, y cuando el commit se escribe con Claude lleva al final la
línea `Co-Authored-By: Claude …` que corresponda al modelo.

```
fix(ui/widgets): la ficha que nace sin dato pinta el guion pequeño

Cuerpo: el porqué.

Co-Authored-By: <el modelo de la sesión> <noreply@anthropic.com>
```

**Nunca se empuja sin preguntar.** Commitear en local es reversible; publicar
no, y menos con el CI atado a cada empujón a master. Se pregunta siempre,
aunque el commit anterior se haya empujado hace un minuto.

**Lo que toca privilegios se propone antes de escribirlo.** Si el cambio roza
los permisos, la seguridad o un estado que sobrevive entre máquinas o entre
versiones, primero va la propuesta —medida, con lo que se ha comprobado— y se
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
intermedio: hoy se hizo en `096ace0` y el commit siguiente lo dejó atrasado
otra vez, con una fila de la ficha de procesador que el archivo no mencionaba
y dos cifras que ya no cuadraban. Se escribe cuando ya no va a entrar nada más.

**Un dato nuevo no está terminado hasta que hay un test que lo ve en pantalla**,
montando la página de verdad y comprobando la celda. Los 1352 tests pasaban con
el voltaje del núcleo medido, guardado en el modelo y sin ninguna fila donde
pintarlo: probaban el proveedor, la interpretación de los bits y el reparto de
avisos, y ninguno miraba si eso se veía. Probar la fuente no es probar que se
ve, y lo que no se ve no está hecho.

**Un commit por cambio lógico.** Un cambio lógico es una causa, no un archivo
ni un arreglo: cuatro correcciones que salen de la misma causa son un commit,
no cuatro. El arreglo y el test que lo vigila van en el mismo commit, y lo que
solo mueve código va en uno propio, para que `git log --follow` siga sirviendo.
La suite queda en verde entre uno y otro.

## El CHANGELOG

Cada versión es una entrada `## X.Y.Z (día de mes de año)`, de la más nueva a
la más vieja, contada para quien usa el programa y no commit a commit. Dentro,
un apartado por zona del programa y en este orden, omitiendo los vacíos:

1. **Antes de actualizar**: lo que hay que saber antes de dar el paso (lo que
   deja de valer, lo que hay que hacer a mano). Sin prefijo: no son cambios.
2. **Memoria**, **Procesador**, **Gráficos**, **Batería**, **Rendimiento**,
   **Interfaz**, **Privacidad** y **AppImage**.

En cada zona, una línea por cambio, corta, que empieza por «Nuevo:» o
«Arreglado:». Sin emojis. Lo que no encaja en ninguna zona va a la más
cercana, no a una nueva: la lista corta es lo que deja encontrar lo suyo de un
vistazo. La entrada se escribe como «sin publicar» y la fecha se pone al
etiquetar; la de arriba tiene que ser la versión que declara el paquete, y
hay un test que lo vigila.

## El idioma

La interfaz va en **español neutro**: `video` y no «vídeo», `archivo` y no
«fichero», `dispositivo` y no «aparato», `equipo` y no «ordenador». Nueve de
cada diez hispanohablantes están al otro lado del Atlántico y no hay motivo
para cerrarles la puerta por una tilde.

Los comentarios del código no siguen esa regla y van en el español del autor:
no los ve nadie desde la ventana y no se traducen.

**Las claves son símbolos** —`cpu.card.clocks`—, así que el español es un
idioma más y vive en `db/lang/es.json`. Retocar una frase en castellano es
cambiar un valor, no una clave: la traducción inglesa no se descuelga.

Lo malo conocido de las claves simbólicas —que una traducción incompleta
enseñe `cpu.card.clocks` en pantalla— aquí no pasa, porque `_()` tiene tres
escalones: el idioma pedido, el español y por último la clave. Un `en.json` a
medias enseña español entre inglés, que se lee; la clave solo asoma cuando la
frase no está escrita en ninguna de las dos lenguas, y entonces es justo lo
que hace falta ver.

Las categorías del árbol de sensores también son claves. Esos nombres
—«Temperaturas», «Ventiladores»— los inventa el programa para agrupar y no
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
que explica por qué falta un dato, el nombre que le ponen a un sensor —«Punto
caliente» donde amdgpu dice `junction`—, la función de un motor gráfico. Lo
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
`_()`: el informe es castellano fijo —«Procesador», «Placa base»—, así que con
la función normal, el de alguien con la interfaz en inglés mezclaría los dos
idiomas en la misma página.

**Nada de `_()` en una constante de módulo.** Se resuelve al importar, cuando
todavía no se sabe qué idioma quiere nadie, así que se queda con el castellano
para toda la sesión; y como quien monta la ficha vuelve a pasar cada entrada
por `_()`, la segunda llamada recibe «Uso» —que no es una clave— y devuelve
«Uso». Así salía la columna «LEYENDO» en medio de una tabla de discos en
inglés: la tupla llevaba once claves y una traducción ya hecha, y era la única
que no cambiaba de idioma. Hay un test que lo vigila.

La interfaz está entera en los dos idiomas: 1022 claves, ninguna sin traducir,
y trece de ellas ya no las usa nadie (`gen_lang.py` solo ve cinco, ver lo
pendiente).
Hay un test que recorre el árbol de sintaxis de cada página buscando
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
