#!/usr/bin/env python3
"""Instala el ayudante privilegiado con su propia acción de polkit.

Sin esto, silux lanza el ayudante con `pkexec python3 .../helper.py`, y eso cae
en la acción genérica de polkit, que pide la contraseña **cada vez**. Con una
acción propia se pide una vez y polkit la recuerda el resto de la sesión, que
es lo que hacen los demás programas que necesitan leer hardware.

Hay un motivo de seguridad para copiar el ayudante en vez de apuntar a donde
está: `pkexec` asocia la autorización a la ruta del programa que ejecuta y **no
mira los argumentos**. Con el ayudante en el directorio del usuario, una regla
permanente daría root sin contraseña a cualquier proceso que corra como ese
usuario y sepa reescribir el archivo antes de que silux lo lance. Copiado a un
sitio que solo root puede escribir, esa puerta no existe.

Por lo mismo se instala como un ejecutable con shebang y no como un argumento
de `python3`: si la acción apuntara al intérprete, la autorización valdría para
cualquier script de Python de la máquina.

    sudo python3 -m silux.privileged.instalar
    sudo python3 -m silux.privileged.instalar --uninstall

La interfaz lo llama por su cuenta desde el aviso de permisos; a mano solo hace
falta para instalarlo en un equipo sin entorno gráfico.

Vive dentro del paquete y no en `tools/` porque lo ejecuta el usuario final,
no quien desarrolla: `tools/` no entra en el AppImage, y allí el botón de la
interfaz se quedaba sin instalador que lanzar. Por lo mismo no importa nada de
`silux`: se copia como archivo suelto fuera del punto de montaje, donde el
resto del paquete no está.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

ORIGEN = pathlib.Path(__file__).resolve().parent / "helper.py"

DESTINO = pathlib.Path("/usr/local/libexec/silux/silux-helper")
POLITICA = pathlib.Path("/usr/share/polkit-1/actions/org.silux.helper.policy")

ACCION = "org.silux.helper"

# `auth_admin_keep` y no `yes`: se pide una vez y polkit la recuerda mientras
# dure la sesión, en vez de dejar la puerta abierta para siempre. Es lo que
# hacen LACT y kdiskmark, que necesitan lo mismo que esto.
#
# `allow_inactive` a `no` porque una sesión que no está delante del equipo no
# tiene por qué leer sus sensores: eso incluye las sesiones por SSH.
PLANTILLA = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1.0/policyconfig.dtd">
<policyconfig>
  <vendor>silux</vendor>
  <vendor_url>https://github.com/rcv11x/silux</vendor_url>

  <action id="{accion}">
    <description>Leer la identificación y los sensores del hardware</description>
    <description xml:lang="en">Read hardware identification and sensors</description>
    <message>Se necesita autorización para leer los módulos de memoria y el diagnóstico de los discos</message>
    <message xml:lang="en">Authentication is required to read memory modules and disk health</message>
    <defaults>
      <allow_any>auth_admin</allow_any>
      <allow_inactive>no</allow_inactive>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">{destino}</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
"""


def instalado() -> bool:
    """Si el ayudante y su acción están puestos y son utilizables."""
    return DESTINO.is_file() and os.access(DESTINO, os.X_OK) and POLITICA.is_file()


def _interprete() -> str:
    """Un Python del sistema para el shebang.

    El de un AppImage no vale: su punto de montaje va con `nosuid` y pertenece
    al usuario, así que pkexec se niega a ejecutar nada de ahí y root ni
    siquiera puede leerlo.
    """
    for ruta in ("/usr/bin/python3", "/bin/python3", "/usr/local/bin/python3"):
        if os.path.exists(ruta):
            return ruta
    raise SystemExit("No hay ningún Python del sistema con el que ejecutar el ayudante.")


def del_paquete() -> str:
    """El ayudante que viene al lado, para cuando esto se ejecuta a mano."""
    if not ORIGEN.is_file():
        raise SystemExit(f"No encuentro el ayudante en {ORIGEN}")
    return ORIGEN.read_text(encoding="utf-8")


def instalar(cuerpo: str) -> None:
    """Deja el ayudante en el sistema con su acción de polkit.

    Recibe el **texto** del ayudante y no una ruta, y eso es una decisión de
    seguridad y no de estilo. Antes la interfaz le pasaba `--from` con una ruta
    de ~/.cache, que escribe el usuario: cualquier proceso suyo podía cambiar
    ese archivo mientras el usuario tecleaba la contraseña —segundos, no una
    carrera— y lo que quedaba instalado, de root y con la acción de polkit
    apuntándole, era lo del atacante. Un texto que llega por una tubería no
    tiene nombre que sustituir.
    """
    if not cuerpo.strip():
        raise SystemExit("No me han pasado ningún ayudante que instalar.")
    # El shebang que trae el archivo es `/usr/bin/env python3`, que resuelve
    # contra el PATH de quien lo ejecute. Aquí lo ejecuta root a través de
    # pkexec, así que se clava el intérprete y se deja de depender del entorno.
    if cuerpo.startswith("#!"):
        cuerpo = cuerpo.split("\n", 1)[1]
    cuerpo = f"#!{_interprete()}\n" + cuerpo

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(DESTINO.parent, 0o755)
    DESTINO.write_text(cuerpo, encoding="utf-8")
    # 0755 y de root: cualquiera puede ejecutarlo (pkexec decide si se le deja),
    # nadie más que root puede cambiar lo que hace.
    os.chown(DESTINO, 0, 0)
    os.chmod(DESTINO, 0o755)

    POLITICA.write_text(
        PLANTILLA.format(accion=ACCION, destino=DESTINO), encoding="utf-8")
    os.chown(POLITICA, 0, 0)
    os.chmod(POLITICA, 0o644)

    print(f"ayudante:  {DESTINO}")
    print(f"política:  {POLITICA}")
    print("Listo. La contraseña se pedirá una vez por sesión, no en cada arranque.")


def desinstalar() -> None:
    for ruta in (POLITICA, DESTINO):
        if ruta.exists():
            ruta.unlink()
            print(f"borrado: {ruta}")
    if DESTINO.parent.is_dir() and not any(DESTINO.parent.iterdir()):
        DESTINO.parent.rmdir()
    print("Se vuelve a pedir la contraseña en cada arranque.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--uninstall", action="store_true",
                        help="quita el ayudante y su acción de polkit")
    parser.add_argument("--check", action="store_true",
                        help="dice si están instalados y sale")
    parser.add_argument("--from-stdin", action="store_true",
                        help="lee el ayudante de la entrada estándar en vez de "
                             "usar el del paquete. Es como lo instala la "
                             "interfaz desde un AppImage, donde root no puede "
                             "leer dentro del punto de montaje. No se acepta "
                             "una ruta a propósito: la que había que dar era "
                             "de una carpeta del usuario, y eso deja instalar "
                             "como root lo que otro proceso ponga ahí")
    args = parser.parse_args(argv)

    if args.check:
        print("instalado" if instalado() else "no instalado")
        return 0 if instalado() else 1

    if os.geteuid() != 0:
        raise SystemExit(
            "Hay que ejecutarlo como root: escribe en /usr/local/libexec y en "
            "/usr/share/polkit-1/actions.\n"
            "  sudo python3 -m silux.privileged.instalar"
        )

    if args.uninstall:
        desinstalar()
    else:
        instalar(sys.stdin.read() if args.from_stdin else del_paquete())
    return 0


if __name__ == "__main__":
    sys.exit(main())
