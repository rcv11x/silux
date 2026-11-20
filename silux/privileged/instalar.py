#!/usr/bin/env python3
"""Instala el ayudante privilegiado con su propia acción de polkit.

Sin esto, Silux lanza el ayudante con `pkexec python3 -c …`, y eso cae en la
acción genérica de polkit, cuya ventana enseña la orden y no qué se lee. Con
una acción propia la ventana lo dice con nuestras palabras. La contraseña se
sigue pidiendo al dar permisos (`auth_admin_keep`).

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
import stat
import sys
import tempfile

ORIGEN = pathlib.Path(__file__).resolve().parent / "helper.py"

DESTINO = pathlib.Path("/usr/local/libexec/silux/silux-helper")
POLITICA = pathlib.Path("/usr/share/polkit-1/actions/org.silux.helper.policy")

ACCION = "org.silux.helper"

# Lo que dice la ventana de la contraseña con la regla puesta, en cada idioma
# de la interfaz: todo lo que abre el permiso, ni más ni menos. Va copiado
# aquí y no leído de `db/lang` porque la regla la escribe root, y root no
# puede leer dentro del AppImage del usuario. `tests/test_privileged.py` lo
# compara con la clave `perm.polkit.message` de `es.json` y `en.json`.
MENSAJES = {
    "es": ("Silux necesita permiso para leer datos del hardware reservados al "
           "administrador: memoria, discos, voltaje, consumo y uso de la "
           "gráfica. Solo lee, no cambia nada."),
    "en": ("Silux needs permission to read hardware data reserved to the "
           "administrator: memory, disks, voltage, power and graphics usage. "
           "It only reads; it changes nothing."),
}

# `auth_admin_keep` y no `yes`: la contraseña se pide al dar permisos (polkit
# la recuerda unos minutos y solo para ese proceso), en vez de dejar la puerta
# abierta a cualquier proceso de la sesión. Lo que se gana instalando es que la
# ventana diga qué se lee, no dejar de pedirla (docs/privilegios.md).
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
    <message>{mensaje_es}</message>
    <message xml:lang="en">{mensaje_en}</message>
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


def politica() -> str:
    """La regla tal y como se escribe, para instalarla y para compararla.

    El cliente la compara con la instalada: cambiar el texto de la ventana
    tiene que llegar también a quien ya la tenía puesta.
    """
    return PLANTILLA.format(accion=ACCION, destino=DESTINO,
                            mensaje_es=MENSAJES["es"], mensaje_en=MENSAJES["en"])


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


# Who has to own what the installer writes into. A constant so the tests,
# which cannot be root, can say «me».
DUENO = 0


def _comprobar_carpetas(carpeta: pathlib.Path) -> None:
    """Root's and nobody else's, all the way up.

    Whoever can write a folder can swap what is inside it, file and checks
    included. The folder of its own must be a real folder owned by root and
    writable only by root; the ones above are followed to where they really
    are (on Silverblue /usr/local is a link to /var/usrlocal) and must be
    root's and not writable by everyone. A group may write them: on older
    Debian /usr/local belongs to `staff`, which the distribution counts as
    root.
    """
    info = os.lstat(carpeta)
    if not stat.S_ISDIR(info.st_mode):
        raise SystemExit(f"{carpeta} no es una carpeta: no instalo nada ahí.")
    if info.st_uid != DUENO or info.st_mode & 0o022:
        raise SystemExit(f"{carpeta} la puede cambiar alguien que no es root: no instalo nada ahí.")
    for parte in pathlib.Path(os.path.realpath(carpeta.parent)).joinpath("x").parents:
        info = os.stat(parte)
        # Writable by everyone only with the sticky bit, like /tmp: then nobody
        # can rename or delete what belongs to someone else.
        abierta = info.st_mode & 0o002 and not info.st_mode & stat.S_ISVTX
        if info.st_uid not in (DUENO, 0) or abierta:
            raise SystemExit(f"{parte} la puede cambiar alguien que no es root: no instalo nada ahí.")


def _escribir(destino: pathlib.Path, texto: str, modo: int) -> None:
    """Writes the file whole and atomically, and never through a link.

    A temporary file created new in the same folder (`mkstemp` opens it with
    O_EXCL and O_NOFOLLOW), owned and moded before it has its name, and then
    renamed over the old one: a rename replaces a link, it does not follow it.
    Writing in place followed whatever was at that path.
    """
    descriptor, temporal = tempfile.mkstemp(prefix=f".{destino.name}.", dir=destino.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            archivo.write(texto)
            archivo.flush()
            os.fsync(archivo.fileno())
            os.fchown(archivo.fileno(), DUENO, DUENO)
            os.fchmod(archivo.fileno(), modo)
        os.replace(temporal, destino)
    except BaseException:
        try:
            os.unlink(temporal)
        except OSError:
            pass
        raise


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
    # `-I`: as root, no PYTHONPATH, PYTHONSTARTUP or user site-packages.
    if cuerpo.startswith("#!"):
        cuerpo = cuerpo.split("\n", 1)[1]
    cuerpo = f"#!{_interprete()} -I\n" + cuerpo

    DESTINO.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    _comprobar_carpetas(DESTINO.parent)
    _comprobar_carpetas(POLITICA.parent)
    # 0755 y de root: cualquiera puede ejecutarlo (pkexec decide si se le deja),
    # nadie más que root puede cambiar lo que hace.
    _escribir(DESTINO, cuerpo, 0o755)
    _escribir(POLITICA, politica(), 0o644)

    print(f"ayudante:  {DESTINO}")
    print(f"política:  {POLITICA}")
    print("Listo. La ventana de la contraseña dirá qué se lee.")


def orden_de_desinstalar() -> str:
    """La orden que quita el ayudante, valga como valga instalado silux.

    Son dos archivos y se borran. `python3 -m silux.privileged.instalar
    --uninstall` hace lo mismo, pero solo existe donde silux está instalado
    como paquete: quien lo usa desde el AppImage no tiene ese módulo en su
    Python, y es justo quien instaló el ayudante desde la ventana.
    """
    return f"sudo rm {DESTINO} {POLITICA}"


def desinstalar() -> None:
    for ruta in (POLITICA, DESTINO):
        if ruta.exists():
            ruta.unlink()
            print(f"borrado: {ruta}")
    if DESTINO.parent.is_dir() and not any(DESTINO.parent.iterdir()):
        DESTINO.parent.rmdir()
    print("Al dar permisos vuelve a salir el aviso.")


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
