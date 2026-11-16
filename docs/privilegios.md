# Privilegios

Qué necesita permisos, cómo se piden y por qué así. Las lecciones de esta
zona —sobre todo las de pkexec y la copia instalada— están en
[lecciones.md](lecciones.md#privilegios), y lo que queda por arreglar, en el
índice de pendientes de `CLAUDE.md`.

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

## Lo que este modelo no cierra

Desde el código fuente, el guion que viaja por `argv` a `pkexec` se lee del
árbol de trabajo del usuario: quien pueda editar `helper.py`,
`instalar.py` o `cargar_modulo.py` decide qué corre como root después de la
contraseña. No tiene arreglo dentro de este modelo y no hay que venderlo
como cerrado. Desde el AppImage no pasa: el montaje es de solo lectura.
