# El ayudante privilegiado es una lista cerrada

**Decisión.** Lo que solo lee root lo lee un ayudante que entiende siete
peticiones y nada más: sin rutas, sin órdenes, sin argumentos. Los registros
MSR, los nombres de disco y los PMU que abre están fijados en él. Se lanza con
`pkexec`, de una de dos formas: «esta vez» (el código viaja por argv a un
Python del sistema y la contraseña se pide cada vez) o instalado en
`/usr/local/libexec/silux/`, de root, con su propia acción de polkit.

**Por qué.** Lo que corre como root tiene que poder leerse entero. Instalado,
además, el código que corre con permisos es un archivo que solo cambia el
administrador.

**Descartado.** Copiar el ayudante a `~/.cache` y pasarle la ruta a pkexec:
entre la copia y la apertura, el usuario (o cualquier programa suyo) podía
cambiar el archivo, y lo que quedaba instalado era lo que hubiera ahí. Y
apuntar la acción de polkit al intérprete: valdría para cualquier guion de
Python de la máquina.

**Dónde vive.** `silux/privileged/`. El detalle, en
[privilegios.md](../privilegios.md).
