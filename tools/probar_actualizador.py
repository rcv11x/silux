#!/usr/bin/env python3
"""Prueba el actualizador de punta a punta, sin publicar ninguna release.

    python3 tools/probar_actualizador.py VIEJO.AppImage NUEVO.AppImage

VIEJO es el AppImage que se actualiza (uno con el actualizador: el de
`build_appimage.py --container` o el del CI); NUEVO, cualquier otro AppImage
de silux, que se publica como una v0.4.0 de mentira. Hace falta mitmproxy
(`uv tool install mitmproxy`), que hace de GitHub (`actualizador/github_falso.py`):
contesta la lista de releases, el SHA256SUMS y la descarga, la pasa por una
redirección a objects.githubusercontent.com como GitHub, y corta con un 403
todo lo demás. Nada sale a la red de verdad.

Para cada caso, una copia de VIEJO en una carpeta temporal, con su entrada
de menú, y la ventana sin pantalla dentro del Python del propio AppImage
(`actualizador/conductor.py`): «Buscar ahora», «Actualizar» y «Reiniciar»,
contestando que sí. Los casos:

- bien: queda NUEVO en la misma ruta, ejecutable, y es lo que corre tras
  reiniciar; la entrada de menú sigue apuntando ahí;
- sha-mal: el SHA256SUMS no casa: se avisa y VIEJO no se toca;
- http: la descarga se redirige a http://: se corta y VIEJO no se toca;
- solo-lectura: la carpeta no se puede escribir: solo se da el enlace.

Sale con código 1 si algún caso no da lo que debe.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

AQUI = pathlib.Path(__file__).resolve().parent / "actualizador"
PUERTO = 8089


def version(appimage: pathlib.Path) -> str:
    salida = subprocess.run([str(appimage), "--version"], capture_output=True, text=True)
    return salida.stdout.strip().splitlines()[-1] if salida.stdout.strip() else ""


def caso(nombre: str, viejo: pathlib.Path, nuevo: pathlib.Path, raiz: pathlib.Path,
         confdir: pathlib.Path) -> tuple[bool, str]:
    modo = "bien" if nombre == "solo-lectura" else nombre
    base = pathlib.Path(tempfile.mkdtemp(prefix=f"silux-actualizar-{nombre}-"))
    app = base / "app"
    app.mkdir()
    destino = app / "silux-x86_64.AppImage"
    shutil.copy2(viejo, destino)
    antes = hashlib.sha256(destino.read_bytes()).hexdigest()
    if nombre == "solo-lectura":
        app.chmod(0o555)
    proxy = subprocess.Popen(
        ["mitmdump", "--set", f"confdir={confdir}", "-p", str(PUERTO), "-s",
         str(AQUI / "github_falso.py"), "--set", f"modo={modo}", "--set", f"nuevo={nuevo}"],
        stdout=open(base / "proxy.log", "w"), stderr=subprocess.STDOUT)
    time.sleep(3)
    usr = raiz / "usr"
    entorno = dict(
        os.environ, PYTHONHOME=str(usr), PYTHONPATH=str(usr / "lib" / "python"),
        LD_LIBRARY_PATH=f"{usr / 'lib'}:{usr / 'lib' / 'python' / 'PySide6' / 'Qt' / 'lib'}",
        QT_PLUGIN_PATH=str(usr / "lib" / "qt" / "plugins"),
        QT_QPA_PLATFORM_PLUGIN_PATH=str(usr / "lib" / "qt" / "plugins" / "platforms"),
        QT_QPA_PLATFORM="offscreen", APPIMAGE=str(destino),
        XDG_CONFIG_HOME=str(base / "conf"), XDG_DATA_HOME=str(base / "datos"),
        https_proxy=f"http://127.0.0.1:{PUERTO}", HTTPS_PROXY=f"http://127.0.0.1:{PUERTO}",
        no_proxy="", SSL_CERT_FILE=str(confdir / "mitmproxy-ca-cert.pem"))
    conductor = subprocess.Popen([str(usr / "bin" / "python3"), str(AQUI / "conductor.py")],
                                 env=entorno, stdout=open(base / "conductor.log", "w"),
                                 stderr=subprocess.STDOUT)
    time.sleep(40)
    corre = subprocess.run(["pgrep", "-f", str(destino)], capture_output=True, text=True).stdout.split()
    registro = (base / "conductor.log").read_text(errors="replace")
    conductor.kill()
    for pid in corre:
        subprocess.run(["kill", pid])
    proxy.terminate()
    proxy.wait()
    app.chmod(0o755)

    despues = hashlib.sha256(destino.read_bytes()).hexdigest()
    restos = [p.name for p in app.iterdir() if p.name != destino.name]
    dialogos = [l for l in registro.splitlines() if l.startswith("DIÁLOGO")]
    entrada = (base / "datos" / "applications" / "silux.desktop")
    exec_ = next((l for l in entrada.read_text().splitlines() if l.startswith("Exec=")), "") \
        if entrada.is_file() else ""
    nuevo_sha = hashlib.sha256(nuevo.read_bytes()).hexdigest()
    if nombre == "bien":
        bien = (despues == nuevo_sha and os.access(destino, os.X_OK) and not restos
                and bool(corre) and str(destino) in exec_)
        detalle = (f"{version(destino)}; reinicia: {'sí' if corre else 'no'}; "
                   f"entrada: {'apunta ahí' if str(destino) in exec_ else exec_}")
    else:
        # Con su motivo de verdad: un corte a http:// salía como «no hay
        # conexión», y eso no es lo que pasa.
        motivo = {"sha-mal": "SHA-256", "http": "HTTPS", "solo-lectura": "/releases/tag/"}[nombre]
        bien = despues == antes and not restos and any(motivo in d for d in dialogos)
        detalle = (dialogos[-1] if dialogos else "sin aviso") + f"; AppImage {'intacto' if despues == antes else 'CAMBIADO'}"
    if restos:
        detalle += f"; quedan {restos}"
    shutil.rmtree(base, ignore_errors=True)
    return bien, detalle


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("viejo", type=pathlib.Path)
    parser.add_argument("nuevo", type=pathlib.Path)
    parser.add_argument("--casos", default="bien,sha-mal,http,solo-lectura")
    args = parser.parse_args(argv)
    if shutil.which("mitmdump") is None:
        print("falta mitmproxy: uv tool install mitmproxy", file=sys.stderr)
        return 2
    trabajo = pathlib.Path(tempfile.mkdtemp(prefix="silux-actualizador-"))
    confdir = trabajo / "mitm"
    # El primer arranque de mitmproxy crea su certificado, que solo se le da a
    # este proceso por SSL_CERT_FILE: no se instala en ningún sitio.
    subprocess.run(["timeout", "6", "mitmdump", "--set", f"confdir={confdir}", "-p", str(PUERTO)],
                   capture_output=True)
    subprocess.run([str(args.viejo.resolve()), "--appimage-extract"], cwd=trabajo,
                   capture_output=True)
    raiz = trabajo / "squashfs-root"
    print(f"viejo: {version(args.viejo)}   nuevo (como v0.4.0): {version(args.nuevo)}")
    fallos = 0
    for nombre in args.casos.split(","):
        bien, detalle = caso(nombre, args.viejo.resolve(), args.nuevo.resolve(), raiz, confdir)
        fallos += not bien
        print(f"{'bien ' if bien else 'MAL  '} {nombre:13} {detalle}")
    shutil.rmtree(trabajo, ignore_errors=True)
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
