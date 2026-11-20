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
con un mensaje genérico en vez del nuestro.

## La ventana de la contraseña

La pide polkit, y lo que dice depende de qué se ejecute:

| Caso | Orden | Lo que dice la ventana |
|---|---|---|
| «Dar permisos esta vez» | `/usr/bin/pkexec /usr/bin/python3 -I -c …` | la frase genérica de polkit, con la orden: «… run `/usr/bin/python3 -I -c import linecache…` as the super user» |
| «Instalar el ayudante», al instalar | `/usr/bin/pkexec /usr/bin/python3 -I -c … instalar.py` | la misma |
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
permisos», que dice lo que enseñará la ventana y ofrece instalar el ayudante
como lo recomendado. Con la regla al día se piden sin más.

**Instalar el ayudante no quita la contraseña.** La regla es
`auth_admin_keep`: polkit la recuerda unos minutos y para ese proceso, así
que cada vez que se abre Silux y se dan permisos se vuelve a pedir. Lo que se
gana es que la ventana diga en el idioma de la sesión qué se lee, y que no
salga el aviso previo. Quitarla para la sesión local (`allow_active = yes`)
se estudió el 20 de noviembre de 2026 y no se hizo: daría root sin
contraseña a cualquier proceso de esa sesión. El análisis, en
[pendientes.md](pendientes.md#propuestas-sin-aplicar).

**Un ayudante instalado de otra versión no se usa** (el cliente solo usa el
instalado si es exactamente el suyo), y lo dicen Inicio, los avisos, los
candados y la barra de abajo: lo que lo arregla es «Actualizar el ayudante»,
que lo sustituye.

El texto de la regla va en `instalar.MENSAJES`, en español y en inglés, porque
la escribe root sin poder leer el AppImage; `tests/test_privileged.py` lo
compara con `perm.polkit.message` de `es.json` y `en.json`. polkit elige el
`<message>` por el idioma de la sesión, y sin uno de ese idioma usa el que no
lleva `xml:lang`, el español. `PrivilegedClient.al_dia()` compara también la
regla instalada, así que cambiar el texto ofrece actualizar el ayudante a
quien ya lo tenía.

Para cuando haya paquetes de distribución, su regla y su ayudante van dentro
del paquete y nunca se pasa por `python3 -c`.

## La revisión de seguridad del 20 de noviembre de 2026

Todo lo que pasa por root, antes de la 0.4-prueba1. Lo que salió y no era
grave está en [pendientes.md](pendientes.md#privilegios-y-privacidad) con su
gravedad.

- **Qué ejecuta root.** Tres órdenes, siempre por `/usr/bin/pkexec` con la
  ruta absoluta (antes `pkexec` a secas, que se busca en el `PATH` del
  usuario): el ayudante instalado, de root y con su shebang
  `#!/usr/bin/python3 -I`; o un guion entero por `argv` a un Python del
  sistema con `-I` (sin `PYTHONPATH`, `PYTHONSTARTUP`, `site-packages` del
  usuario ni la carpeta actual en `sys.path`), sea el ayudante, el
  instalador o el cargador de módulos. pkexec ya limpia el entorno y entra en
  la carpeta de root; `-I` hace que no dependa de eso. Root no lee ni ejecuta
  nada que el usuario pueda cambiar: lo vigila `tests/test_pkexec.py`, que
  descubre leyendo el código cada sitio que monta una orden.
- **El ayudante** solo hace lo de su lista: la tabla SMBIOS y su punto de
  entrada (rutas fijas), los MSR de una lista blanca en una CPU que es un
  entero con tope, el diagnóstico SMART de un disco cuyo nombre casa con un
  patrón fijo (comandos de solo lectura escritos en el código), los
  contadores de la gráfica y del controlador de memoria que admite por
  nombre, y la energía de RAPL. No acepta rutas ni órdenes, y una petición
  mal formada (JSON roto, que no es un objeto, demasiado larga, acción
  desconocida, tipos raros) recibe un error y no hace nada.
- **El instalador** comprueba que la carpeta del ayudante es una carpeta de
  verdad, de root y que solo root puede escribir, y que las de encima son de
  root y no las puede escribir cualquiera (salvo con el bit pegajoso, como
  `/tmp`). Escribe cada archivo en un temporal nuevo de la misma carpeta
  (`O_EXCL`, `O_NOFOLLOW`), le pone dueño y modo antes de que tenga nombre y
  lo cambia por el viejo con un `rename`, que sustituye un enlace en vez de
  seguirlo. Antes escribía a través de lo que hubiera en esa ruta.
- **Cargar un módulo**: el nombre, contra una forma fija y una lista cerrada;
  `modprobe` por su ruta absoluta, sin shell; `/etc/modules-load.d/silux.conf`
  escrito igual que el instalador. Y se confirma antes con su propio aviso,
  porque sí cambia el sistema.
- **El actualizador**: solo HTTPS, con verificación del certificado y
  redirecciones solo a HTTPS; topes de tamaño; el SHA-256 del
  `SHA256SUMS` de la release se comprueba antes de tocar nada; el temporal
  va en la misma carpeta y se cambia con `os.replace`; nada descargado se
  ejecuta antes de comprobarlo.
- **En general**: ningún `shell=True`, `os.system`, `eval` ni `pickle`; el
  único `exec` es el que ejecuta, como root, el guion que viaja por `argv`.
  Un `settings.json` raro (vacío, `null`, tipos cambiados, `NaN`, `1e999`,
  binario, 5000 llaves) no impide arrancar. Los iconos que se dibujan van a
  la carpeta de ejecución del usuario y no a un nombre fijo de `/tmp`.
- **Nada se queda corriendo.** Ni servicios, ni arranque automático, ni
  `fork`. El ayudante termina al final de la tubería con Silux, que el
  kernel cierra con el proceso: al cerrar la ventana y también si Silux se
  mata con `SIGKILL` (`tests/test_helper_lifecycle.py`).

## Lo que este modelo no cierra

Desde el código fuente, el guion que viaja por `argv` a `pkexec` se lee del
árbol de trabajo del usuario: quien pueda editar `helper.py`,
`instalar.py` o `cargar_modulo.py` decide qué corre como root después de la
contraseña. No tiene arreglo dentro de este modelo y no hay que venderlo
como cerrado. Desde el AppImage no pasa: el montaje es de solo lectura.
