"""silux: perfilador de hardware para Linux.

Copyright (C) 2026 rcv11x

Este programa es software libre: puede redistribuirlo y modificarlo bajo los
términos de la Licencia Pública General de GNU, versión 3 o posterior, tal y
como la publica la Free Software Foundation. Se distribuye con la esperanza de
que resulte útil, pero SIN NINGUNA GARANTÍA. El texto completo está en el
fichero LICENSE.

La licencia es la GPL porque la base de datos de identificación incluye la
tabla de encapsulados que hereda de CPU-X, que es GPL-3.0.

La regla que sostiene todo el paquete: los proveedores leen *valores*
(enteros en hercios, bytes, grados) y el modelo los guarda tal cual.
El texto que ve el usuario se produce en `silux.render`, nunca antes.
"""

# Sube cuando hay algo que el usuario nota. El número menor —de 0.1 a 0.2— se
# reserva para cuando algo le cambia de verdad: una sección nueva, un dato que
# antes no salía, o algo que deja de funcionar como funcionaba. El último
# dígito, para arreglos que no obligan a leer nada.
#
# No es cosmético: sin esto, la única forma que tiene alguien de saber si va
# atrasado es el identificador de construcción, y un hash no se compara de un
# vistazo. Lo que cambia en cada versión está en CHANGELOG.md, y hay un test
# que no deja subir este número sin escribirlo allí.
__version__ = "0.2.0"


def build_id() -> str:
    """Qué copia exacta es esta: «20260829.c22e689», o vacío si no se sabe.

    Se llama `build_id` y no `build` porque `report.build()` ya existe y es
    otra cosa —construye el informe—: importarla suelta la habría pisado
    dentro de ese módulo, que es el error del guion bajo otra vez.

    Nace de un problema concreto: la gente manda capturas de lo que le sale, y
    entre una y otra pasan arreglos. Sin esto, una captura de anteayer con un
    fallo ya corregido se investiga otra vez desde cero, y la versión sola no
    basta: entre dos publicaciones hay decenas de commits y todos dicen lo
    mismo.

    No sustituye a `__version__` ni al revés, porque contestan a dos personas
    distintas. Esto es para quien mantiene el programa: de qué commit exacto
    salió esa copia. La versión es para quien lo usa: si va atrasado o no, que
    es algo que un hash no dice.

    Tres sitios, en este orden. El archivo que escribe el empaquetador, que es
    el caso que importa porque el AppImage viaja sin repositorio. El propio git
    si estamos sobre el código fuente. Y si no hay ninguno —un tarball suelto,
    una copia por FTP—, nada: es preferible el hueco a inventar un número.
    """
    global _build
    if _build is None:
        _build = _leer_build() or _preguntar_a_git() or ""
    return _build


_build = None


def _leer_build() -> str:
    """Lo que dejó escrito el empaquetador dentro del paquete."""
    try:
        import pathlib
        texto = (pathlib.Path(__file__).parent / "_build.txt").read_text(
            encoding="utf-8").strip()
    except OSError:
        return ""
    # Un archivo a medio escribir no vale más que no tenerlo.
    return texto if texto and len(texto) < 64 else ""


def _preguntar_a_git() -> str:
    """La fecha y el commit de la copia de trabajo, si esto es un repositorio.

    La marca `+` al final avisa de que hay cambios sin guardar: una captura de
    una copia tocada a mano no se corresponde con ningún commit, y saberlo
    ahorra buscar en el historial algo que no está.
    """
    import subprocess
    raiz = __file__.rsplit("/", 2)[0]
    try:
        commit = subprocess.run(
            ["git", "-C", raiz, "log", "-1", "--format=%cd.%h", "--date=format:%Y%m%d"],
            capture_output=True, text=True, timeout=5)
        if commit.returncode != 0:
            return ""
        sucio = subprocess.run(["git", "-C", raiz, "status", "--porcelain"],
                               capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    marca = commit.stdout.strip()
    return f"{marca}+" if marca and sucio.stdout.strip() else marca

# El emoji del rótulo. Uno solo y en un sitio: en un programa que ya usa el
# color para señalar lo importante, más de uno compite con los datos.
EMOJI = "🔎"
