"""Un GitHub de mentira para probar el actualizador sin publicar nada.

Lo lanza tools/probar_actualizador.py; a mano:
mitmdump -s github_falso.py --set modo=bien|sha-mal|http --set nuevo=RUTA

Contesta a la lista de releases de rcv11x/silux con una v0.4.0 cuyos
adjuntos son el AppImage de `nuevo` y su SHA256SUMS, y
pasa la descarga por una redirección a objects.githubusercontent.com, como
GitHub. Todo lo demás se corta con un 403: nada sale a la red de verdad.

- `bien`: todo en orden.
- `sha-mal`: el SHA256SUMS no casa con el archivo.
- `http`: la redirección de la descarga va a http://, que se tiene que cortar.
"""

import hashlib
import json
import pathlib

from mitmproxy import ctx, http

# Los dos tipos con el mismo archivo: así se prueba también el `-compat`,
# que busca el suyo y no el normal.
NOMBRES = ("silux-x86_64.AppImage", "silux-x86_64-compat.AppImage")
# La final de la prueba1 (0.4.0rc1): es justo el salto que se quiere probar.
ETIQUETA = "v0.4.0"
DESCARGA = f"https://github.com/rcv11x/silux/releases/download/{ETIQUETA}"
OBJETOS = "https://objects.githubusercontent.com/github-production-release-asset/silux"


def load(loader):
    loader.add_option("modo", str, "bien", "bien, sha-mal o http")
    loader.add_option("nuevo", str, "", "el AppImage que se publica como v0.4.0")


def request(flow: http.HTTPFlow) -> None:
    url = flow.request.pretty_url
    ctx.log.info(f"pide: {flow.request.method} {url}  UA={flow.request.headers.get('User-Agent')}")
    modo = ctx.options.modo
    if url.startswith("https://api.github.com/repos/rcv11x/silux/releases"):
        lista = [{
            "tag_name": ETIQUETA, "draft": False, "prerelease": False,
            "html_url": f"https://github.com/rcv11x/silux/releases/tag/{ETIQUETA}",
            "assets": [{"name": n, "browser_download_url": f"{DESCARGA}/{n}"}
                       for n in (*NOMBRES, "SHA256SUMS")],
        }]
        flow.response = http.Response.make(200, json.dumps(lista).encode(),
                                           {"Content-Type": "application/json"})
    elif url == f"{DESCARGA}/SHA256SUMS":
        suma = hashlib.sha256(pathlib.Path(ctx.options.nuevo).read_bytes()).hexdigest()
        if modo == "sha-mal":
            suma = "0" * 64
        flow.response = http.Response.make(
            200, "".join(f"{suma}  {n}\n" for n in NOMBRES).encode())
    elif url in {f"{DESCARGA}/{n}" for n in NOMBRES}:
        nombre = url.rsplit("/", 1)[1]
        destino = (OBJETOS.replace("https://", "http://") if modo == "http" else OBJETOS) + "/" + nombre
        flow.response = http.Response.make(302, b"", {"Location": destino})
    elif url in {f"{OBJETOS}/{n}" for n in NOMBRES}:
        flow.response = http.Response.make(200, pathlib.Path(ctx.options.nuevo).read_bytes(),
                                           {"Content-Type": "application/octet-stream"})
    else:
        flow.response = http.Response.make(403, b"cortado por la prueba")
