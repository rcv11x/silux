# Privilegios

Qué necesita permisos, cómo se piden y por qué así. Lo que queda por
arreglar está en [pendientes.md](pendientes.md).

## El ayudante privilegiado

Dos cosas necesitan root y no hay forma de evitarlo: la tabla SMBIOS completa
(donde están los módulos de memoria) y los registros MSR del procesador. El
programa **nunca corre como root**. Cuando el usuario pide esos datos, lanza
por polkit un ayudante mínimo y le habla por una tubería.

El ayudante está escrito para poder leerse de una sentada, y de ahí sus tres
reglas:

- **No importa nada del propio programa**, solo la biblioteca estándar. Un
  fallo en cualquier otro módulo no puede llegar hasta él.
- **No interpreta lo que lee.** Devuelve los bytes crudos de la tabla SMBIOS
  y el análisis se hace sin privilegios. Analizar formatos binarios es de
  donde salen la mayoría de los fallos de memoria, y hacerlo como root sería
  regalar el problema.
- **No acepta rutas ni órdenes.** Las dos rutas que abre son constantes en su
  código, y los registros MSR admitidos son una lista cerrada de diez.

Hay tests que comprueban que el ayudante no contiene `subprocess`, `eval`,
`exec` ni importaciones del paquete, y que las dos listas blancas de MSR (la
del contrato y la suya) no se han separado.

Tampoco se pide nada al arrancar: la pestaña de Memoria enseña lo que sabe,
explica qué falta y pone un botón. Un programa de diagnóstico que abre un
diálogo de contraseña nada más abrirse es un programa que se desinstala.

`data/org.silux.helper.policy.in` es la política de polkit para quien empaquete
el programa. Es opcional: sin ella pkexec pide la contraseña igual, solo que
con un mensaje genérico y sin recordar la autorización durante la sesión.

## La ventana de la contraseña

La pide polkit, y lo que dice depende de qué se ejecute:

| Caso | Orden | Lo que dice la ventana |
|---|---|---|
| «Dar permisos esta vez» | `pkexec /usr/bin/python3 -c …` | la frase genérica de polkit, con la orden: «… run `/usr/bin/python3 -c import linecache…` as the super user» |
| «Para siempre», al instalar | `pkexec python3 -c … instalar.py` | la misma |
| Con el ayudante instalado | `pkexec /usr/local/libexec/silux/silux-helper` | la nuestra: «Silux necesita permiso para leer datos del hardware reservados al administrador: memoria, discos, voltaje, consumo y uso de la gráfica. Solo lee, no cambia nada.» |

Los dos primeros no se pueden cambiar. pkexec elige la acción por la ruta del
programa y quien llama no puede pasarle un texto. Una acción con nuestro texto
tiene que estar en `/usr/share/polkit-1/actions`, que es de root. Apuntarla a
`/usr/bin/python3` serviría para cualquier script del equipo. Lanzar un archivo
en vez de `python3 -c` reabre el agujero de la copia sustituible, y desde el
AppImage root ni siquiera puede leerlo. `run0` y `systemd-run` piden
«gestionar servicios del sistema», que asusta más.

Así que se avisa antes: sin la regla
puesta y al día, cualquier botón de dar permisos abre primero «Qué pasa al dar
permisos», que dice lo que enseñará la ventana y ofrece «Para siempre» como lo
recomendado. Con la regla al día se piden sin más.

El texto de la regla va en `instalar.MENSAJES`, en español y en inglés, porque
la escribe root sin poder leer el AppImage; `tests/test_privileged.py` lo
compara con `perm.polkit.message` de `es.json` y `en.json`. polkit elige el
`<message>` por el idioma de la sesión, y sin uno de ese idioma usa el que no
lleva `xml:lang`, el español. `PrivilegedClient.al_dia()` compara también la
regla instalada, así que cambiar el texto ofrece actualizar el ayudante a
quien ya lo tenía.

Para cuando haya paquetes de distribución, su regla y su ayudante van dentro
del paquete y nunca se pasa por `python3 -c`.

## Lo que este modelo no cierra

Desde el código fuente, el guion que viaja por `argv` a `pkexec` se lee del
árbol de trabajo del usuario: quien pueda editar `helper.py`,
`instalar.py` o `cargar_modulo.py` decide qué corre como root después de la
contraseña. No tiene arreglo dentro de este modelo y no hay que venderlo
como cerrado. Desde el AppImage no pasa: el montaje es de solo lectura.
