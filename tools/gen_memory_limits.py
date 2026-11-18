#!/usr/bin/env python3
"""Genera `silux/db/memory_limits.json`: el máximo oficial de memoria de cada
procesador de sobremesa, con la página del fabricante de donde sale cada fila.

    python3 tools/gen_memory_limits.py            # descarga y escribe
    python3 tools/gen_memory_limits.py --cache D  # guarda lo descargado en D

Como `gen_cpu_db.py`: la tabla no se escribe a mano, se genera desde la
fuente, y cada fila dice cuál.

**AMD** (Ryzen 3000 a 9000 de sobremesa, PRO incluidos). La lista sale de la
tabla de especificaciones de amd.com, que lleva un JSON con cada procesador.
Los antiguos dan ahí una cifra plana («3200»). Los nuevos la dejan vacía: su
máximo depende de los módulos —dos o cuatro, de uno o dos rangos— y está en
la ficha de cada modelo, «Max Memory Speed», con una línea por disposición
(«2x1R DDR4-3200», «4x2R DDR4-2667»). La fila guarda eso tal cual.

**Intel** no se descarga: intel.com rechaza a los clientes que no son un
navegador (403), y esta herramienta no intenta saltárselo. Sus filas salen
de `tools/memory_limits_intel.json`, escrito a mano con la página de Intel de
cada una, hasta que se decida de dónde generarlas. Lo dice cada fila
(`"origin": "manual"`).

Pide cerca de un minuto: una petición a la tabla y otra por cada ficha que
haga falta, con un segundo entre una y otra.
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
import time
import urllib.request
from typing import Optional

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from silux.db import normalize_cpu_model  # noqa: E402

DESTINO = RAIZ / "silux" / "db" / "memory_limits.json"
INTEL = RAIZ / "tools" / "memory_limits_intel.json"

TABLA_AMD = "https://www.amd.com/en/products/specifications/processors.html"
# Quién pregunta, dicho sin disfrazarse de navegador.
AGENTE = "silux-gen-memory-limits/1"
PAUSA = 1.0

SERIES_AMD = re.compile(r"^Ryzen (PRO )?[345789]000 Series$")
DISPOSICION = re.compile(r"^[124]x[12]R$")
VELOCIDAD = re.compile(r"^(DDR[45])-(\d{4})$")


def descargar(url: str, cache: Optional[pathlib.Path]) -> str:
    if cache is not None:
        archivo = cache / re.sub(r"[^a-zA-Z0-9.]+", "_", url)[-180:]
        if archivo.is_file():
            return archivo.read_text(encoding="utf-8")
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(pedido, timeout=60) as respuesta:
        texto = respuesta.read().decode("utf-8", errors="replace")
    time.sleep(PAUSA)
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)
        archivo.write_text(texto, encoding="utf-8")
    return texto


def _valor(item: dict, clave: str):
    campo = item.get("elements", {}).get(clave)
    if campo is None:
        return None
    return campo.get("value", campo.get("values"))


def productos_amd(tabla_html: str) -> list[dict]:
    """Los Ryzen de sobremesa de la tabla: nombre, tipos de memoria, la cifra
    plana si la hay y la página de su ficha."""
    crudo = re.search(r'data-json="([^"]*)"', tabla_html)
    if crudo is None:
        raise SystemExit("la tabla de AMD no trae el JSON de siempre: ha cambiado de forma")
    salida = []
    for item in json.loads(html.unescape(crudo.group(1)))["items"]:
        serie = (_valor(item, "series") or [""])
        serie = serie[0] if isinstance(serie, list) else serie
        formato = _valor(item, "formFactor") or []
        formato = formato if isinstance(formato, list) else [formato]
        if not SERIES_AMD.match(serie or "") or "Desktops" not in formato or "Laptops" in formato:
            continue
        nombre = _valor(item, "name")
        nombre = nombre[0] if isinstance(nombre, list) else nombre
        tipos = _valor(item, "systemMemoryType") or []
        plana = _valor(item, "systemMemorySpecification") or []
        plana = plana[0] if isinstance(plana, list) and plana else plana
        salida.append({
            "name": nombre,
            "types": tipos if isinstance(tipos, list) else [tipos],
            "flat": int(float(plana)) if plana and re.fullmatch(r"[\d.]+", str(plana)) else None,
            "page": (item.get("productPages") or {}).get("en"),
        })
    return salida


def disposiciones(ficha_html: str) -> dict[str, dict[str, int]]:
    """«Max Memory Speed» de una ficha: {tipo: {disposición: MT/s}}.

    La ficha lo pinta como una lista de pares, disposición y velocidad, uno
    debajo de otro. Se lee el texto en orden a partir del título.
    """
    texto = html.unescape(re.sub(r"<[^>]+>", "\n", ficha_html))
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    try:
        inicio = lineas.index("Max Memory Speed")
    except ValueError:
        return {}
    salida: dict[str, dict[str, int]] = {}
    pendiente = None
    for linea in lineas[inicio + 1:inicio + 40]:
        if DISPOSICION.match(linea):
            pendiente = linea
        elif (encaje := VELOCIDAD.match(linea)) and pendiente:
            salida.setdefault(encaje.group(1), {})[pendiente] = int(encaje.group(2))
            pendiente = None
        elif salida and not pendiente:
            break
    return salida


def filas_amd(cache: Optional[pathlib.Path]) -> tuple[list[dict], list[str]]:
    filas, fuera = [], []
    for producto in productos_amd(descargar(TABLA_AMD, cache)):
        modelo = normalize_cpu_model(producto["name"])
        tipos: dict = {}
        fuente = TABLA_AMD
        pagina = producto["page"]
        if pagina and "/products/processors/" in pagina:
            tipos = disposiciones(descargar(pagina, cache))
            fuente = pagina if tipos else fuente
        if not tipos and producto["flat"]:
            tipos = {t: producto["flat"] for t in producto["types"]}
        if not tipos:
            fuera.append(f"{modelo}: ni la tabla ni su ficha dan el máximo")
            continue
        filas.append({"vendor": "AMD", "models": [modelo], "types": tipos,
                      "source": fuente, "origin": "generated"})
    return filas, fuera


def filas_intel() -> list[dict]:
    datos = json.loads(INTEL.read_text(encoding="utf-8"))
    return [{"vendor": "Intel", **fila, "origin": "manual"} for fila in datos["cpus"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=pathlib.Path,
                        help="carpeta donde guardar lo descargado y reutilizarlo")
    args = parser.parse_args()

    amd, fuera = filas_amd(args.cache)
    intel = filas_intel()
    datos = {
        "schema": 2,
        "_": ("Generado por tools/gen_memory_limits.py; no se edita a mano. "
              "El máximo oficial de memoria de cada procesador de sobremesa, por tipo de "
              "memoria; en AMD, por disposición de módulos («2x1R»: dos módulos de un "
              "rango). Cada fila dice de qué página sale y si se generó o se escribió "
              "a mano."),
        "cpus": intel + amd,
    }
    DESTINO.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    modelos_amd = sum(len(f["models"]) for f in amd)
    por_ficha = sum(1 for f in amd if "/products/processors/" in f["source"])
    print(f"AMD:   {modelos_amd} modelos ({por_ficha} con disposición de módulos, "
          f"{modelos_amd - por_ficha} con la cifra plana de la tabla)")
    print(f"Intel: {sum(len(f['models']) for f in intel)} modelos, a mano")
    for linea in fuera:
        print(f"fuera: {linea}")
    print(f"escrito {DESTINO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
