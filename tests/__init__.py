"""La suite corre en una caja: nada de lo que escribe cae en la carpeta personal.

El programa guarda preferencias en `XDG_CONFIG_HOME`, el historial de pruebas
y los registros en `XDG_DATA_HOME` y las copias del ayudante en
`XDG_CACHE_HOME`. La ventana guarda sus preferencias al cerrarse, así que un
test que la monta sin aislar reescribía las de quien ejecuta la suite, y los
que montan la página de Rendimiento leían su historial real. Se aísla aquí, al
importar el paquete, para que valga para todos los tests sin que cada uno
tenga que acordarse: `unittest` importa este archivo antes que cualquier
módulo de `tests/`, se lance la suite entera o uno suelto.

Los tests que necesitan un directorio propio lo siguen poniendo con
`mock.patch.dict(os.environ, …)`, que se apila encima de este.
"""

import atexit
import os
import shutil
import tempfile

CAJA = tempfile.mkdtemp(prefix="silux-tests-")
atexit.register(shutil.rmtree, CAJA, ignore_errors=True)

for _variable, _carpeta in (("XDG_CONFIG_HOME", "config"),
                            ("XDG_DATA_HOME", "data"),
                            ("XDG_CACHE_HOME", "cache")):
    os.makedirs(os.path.join(CAJA, _carpeta))
    os.environ[_variable] = os.path.join(CAJA, _carpeta)
