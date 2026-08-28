"""Carga un módulo de sensores del kernel y lo deja puesto para el arranque.

El programa ya detecta qué módulo daría datos que faltan y lo dice: «cargando
drivetemp tendrías la temperatura de los discos SATA». Eso deja al usuario con
una orden que copiar a una terminal, y a la mayoría ahí se le acaba el camino.

Hace dos cosas: `modprobe` para ahora y una línea en `/etc/modules-load.d/`
para los arranques siguientes. Lo segundo es la mitad que importa —un
`modprobe` suelto se pierde al reiniciar— y es también la que nadie recuerda.

**El nombre del módulo no viene de fuera.** Se comprueba contra la lista de
abajo antes de tocar nada: un ayudante que corre como root y carga el módulo
que le digan es un ayudante que carga cualquier módulo del sistema, y eso no
es lo que hace falta aquí. La lista son los que el propio programa llega a
sugerir, y solo leen sensores.

    sudo python3 -m silux.privileged.cargar_modulo drivetemp

Vive dentro del paquete y no importa nada de `silux` por lo mismo que
`instalar.py`: desde un AppImage se copia como archivo suelto fuera del punto
de montaje, donde el resto del paquete no está.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys

# Los que el programa sugiere, y nada más. Todos son de solo lectura: leen un
# chip de sensores o el SPD de la memoria, y ninguno cambia configuración.
PERMITIDOS = frozenset({
    # temperatura de los discos SATA
    "drivetemp",
    # el chip de identificación de la memoria
    "spd5118", "ee1004", "at24",
    # los buses por los que se llega a ese chip
    "i2c-piix4", "i2c-i801", "i2c-dev",
    # Super I/O de las placas más comunes, por si algún día se sugieren
    "nct6775", "nct6683", "it87", "w83627ehf", "f71882fg",
})

DESTINO = pathlib.Path("/etc/modules-load.d/silux.conf")

# Un nombre de módulo del kernel no lleva nada más que esto. La comprobación
# va antes de la lista blanca y no en su lugar: si algún día alguien amplía la
# lista con una variable, el nombre sigue sin poder ser una orden de shell.
NOMBRE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def se_puede(modulo: str) -> bool:
    """Si este ayudante sabe cargar ese módulo.

    Lo pregunta la interfaz para decidir si pone el botón: un aviso con un
    botón que va a fallar es peor que un aviso con una orden que copiar.
    """
    return bool(NOMBRE.match(modulo)) and modulo in PERMITIDOS


def cargar(modulo: str) -> None:
    if not NOMBRE.match(modulo):
        raise SystemExit(f"«{modulo}» no tiene forma de módulo del kernel.")
    if modulo not in PERMITIDOS:
        raise SystemExit(
            f"«{modulo}» no está en la lista de módulos que este ayudante carga.\n"
            "Solo carga los que el programa sugiere, y todos son de solo lectura."
        )

    resultado = subprocess.run(["modprobe", modulo],
                               capture_output=True, text=True)
    if resultado.returncode != 0:
        detalle = (resultado.stderr or "").strip().splitlines()
        raise SystemExit(f"modprobe {modulo}: {detalle[-1] if detalle else 'falló'}")

    _fijar(modulo)
    print(f"{modulo} cargado y anotado en {DESTINO}")


def _fijar(modulo: str) -> None:
    """Deja el módulo en la lista de los que se cargan al arrancar.

    Se conserva lo que ya hubiera en el archivo: puede haber otro módulo
    puesto por una sesión anterior, y reescribirlo entero lo perdería.
    """
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    puestos = []
    if DESTINO.exists():
        puestos = [linea.strip() for linea in
                   DESTINO.read_text(encoding="utf-8").splitlines()
                   if linea.strip() and not linea.startswith("#")]
    if modulo in puestos:
        return
    puestos.append(modulo)
    DESTINO.write_text(
        "# Módulos de sensores que pidió silux. Borrar una línea basta para\n"
        "# que deje de cargarse en el arranque siguiente.\n"
        + "\n".join(puestos) + "\n",
        encoding="utf-8")
    os.chmod(DESTINO, 0o644)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("modulo", help="el módulo que cargar")
    args = parser.parse_args(argv)

    if os.geteuid() != 0:
        raise SystemExit(
            "Hay que ejecutarlo como root: carga un módulo y escribe en "
            "/etc/modules-load.d.\n"
            f"  sudo python3 -m silux.privileged.cargar_modulo {args.modulo}"
        )
    cargar(args.modulo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
