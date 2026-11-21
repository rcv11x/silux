# Un fallo nuestro es un error, nunca «no lo tiene»

**Decisión.** Solo es del equipo lo que falta bajo `/sys`, `/proc`, `/dev`,
`/etc` o `/run`. Cualquier otro `FileNotFoundError`, y cualquier otra
excepción de un proveedor, es un fallo de Silux: sale como error en su
página y el informe lo lista con su traza, sin la carpeta personal. Lo que
falla entre muestras también se apunta, aunque la página no pierda nada.

**Por qué.** La regla 5: un dato que falta se explica, y «este equipo no lo
publica» explica algo falso cuando el que falla es nuestro código. Nadie
reporta un «no lo tiene».

**Descartado.** Un registro global de errores: los tests que rompen un
proveedor a propósito ensuciarían el informe de otros. Cada `Collector`
lleva el suyo (`silux/failures.py`) y la foto los trae en
`Snapshot.failures`.

**Dónde vive.** `Collector._our_failure`, `collector.is_the_systems` y
`tests/test_collector.py`.
