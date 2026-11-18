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
navegador (403), y esta herramienta no intenta saltárselo. Las fichas de
ark.intel.com se guardan desde el navegador en una carpeta y se leen de ahí:

    python3 tools/gen_memory_limits.py --intel-desde ~/Descargas/intel-ark

De cada ficha sale el modelo (del título), «Memory Types» y la dirección
de la página (la canónica que lleva dentro), que es la fuente de la fila.
Lo que no venga en una ficha guardada sale de `tools/memory_limits_intel.json`,
escrito a mano con la ficha oficial de cada fila (`"origin": "manual"`).

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


_TITULO = re.compile(r"<title>(.*?)</title>", re.S | re.I)
# La dirección de la ficha: la canónica, y si no, la de `og:url`, que en ARK
# va antes en la página y con http.
_CANONICA = re.compile(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', re.I)
_OG_URL = re.compile(r'<meta[^>]+property="og:url"[^>]+content="([^"]+)"', re.I)
# «DDR4-2666» en las fichas hasta la 11.ª; «Up to DDR5 4800 MT/s» desde la
# 12.ª. DDR3L es DDR3 de bajo voltaje: la tabla del firmware de un módulo
# DDR3L dice «DDR3», y así se guarda.
_MEMORIA_INTEL = re.compile(r"\b(LPDDR[345]X?|DDR[345]L?)[- ](\d{3,4})\b")


def _tipos_de_memoria(texto: str, tipos: Optional[dict] = None) -> dict[str, int]:
    """{tipo: MT/s} de un texto de ARK; con varios grados del mismo tipo,
    el más alto, que es el máximo."""
    tipos = {} if tipos is None else tipos
    for tipo, mts in _MEMORIA_INTEL.findall(texto):
        tipo = "DDR3" if tipo == "DDR3L" else tipo
        tipos[tipo] = max(tipos.get(tipo, 0), int(mts))
    return tipos
# Las etiquetas que vienen después de «Memory Types» en la ficha: donde
# empiezan, se acabó el valor.
_SIGUIENTE = re.compile(r"^(Max # of Memory Channels|Max Memory Bandwidth|ECC Memory"
                        r"|Max Memory Size)", re.I)


def ficha_intel(texto_html: str) -> Optional[dict]:
    """Una ficha de ark.intel.com guardada: modelo, memoria por tipo y fuente.

    Se lee el texto, no el marcado: el marcado de ARK cambia y el texto que
    enseña («Memory Types», «DDR4-2666») es lo que la página promete. Con
    varios grados del mismo tipo («DDR4-2933, DDR4-2666», según el modelo de
    placa o de configuración) se queda el más alto, que es el máximo.
    """
    from silux.db import normalize_cpu_model

    titulo = _TITULO.search(texto_html)
    if not titulo:
        return None
    modelo = normalize_cpu_model(html.unescape(titulo.group(1)))
    texto = html.unescape(re.sub(r"<[^>]+>", "\n", texto_html))
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    try:
        inicio = next(i for i, l in enumerate(lineas) if l.lower() == "memory types")
    except StopIteration:
        return None
    tipos: dict[str, int] = {}
    for linea in lineas[inicio + 1:inicio + 8]:
        if _SIGUIENTE.match(linea):
            break
        _tipos_de_memoria(linea, tipos)
    encaje = _CANONICA.search(texto_html) or _OG_URL.search(texto_html)
    fuente = re.sub(r"^http://", "https://", encaje.group(1)) if encaje else None
    if not tipos or not fuente or "intel.com" not in fuente:
        return None
    return {"vendor": "Intel", "models": [modelo], "types": tipos,
            "source": fuente, "origin": "saved-page"}


_ENLACE_DE_MODELO = re.compile(
    r'<a[^>]+href="([^"]*/products/sku/(\d+)/[^"]*)"[^>]*>(.*?)</a>', re.S)


def comparacion_intel(texto_html: str) -> list[dict]:
    """Las filas de una comparación de ARK guardada: una por modelo.

    Es la forma corta de cubrir una serie entera: desde su página se marcan
    todos los modelos y «Compare», y la comparación lleva la fila «Memory
    Types» de cada uno, en el orden de sus enlaces de cabecera. Cada fila
    toma como fuente la ficha de su modelo.
    """
    from silux.db import normalize_cpu_model

    modelos: list[tuple[str, str]] = []
    vistos = set()
    for url, sku, nombre in _ENLACE_DE_MODELO.findall(texto_html):
        if sku not in vistos:
            vistos.add(sku)
            modelos.append((url, html.unescape(re.sub(r"<[^>]+>", "", nombre)).strip()))
    for inicio in (m.start() for m in re.finditer(r'<tr class="MemoryTypes"', texto_html)):
        fila = texto_html[inicio:texto_html.find("</tr>", inicio)]
        celdas = [html.unescape(re.sub(r"<[^>]+>", " ", c))
                  for c in re.findall(r"<td[^>]*>(.*?)</td>", fila, re.S)][1:]
        if len(celdas) == len(modelos) and modelos:
            break
    else:
        return []
    salida = []
    for (url, nombre), celda in zip(modelos, celdas):
        tipos = _tipos_de_memoria(celda)
        if tipos:
            fuente = url if url.startswith("http") else f"https://www.intel.com{url}"
            salida.append({"vendor": "Intel", "models": [normalize_cpu_model(nombre)],
                           "types": tipos, "source": fuente, "origin": "saved-page"})
    return salida


def filas_intel(carpeta: Optional[pathlib.Path]) -> tuple[list[dict], list[str]]:
    """Las de las fichas guardadas, y para lo demás las escritas a mano."""
    guardadas, ilegibles = {}, []
    if carpeta is not None:
        for archivo in sorted(carpeta.rglob("*.htm*")):
            texto = archivo.read_text(encoding="utf-8", errors="replace")
            filas = comparacion_intel(texto) if 'class="MemoryTypes"' in texto \
                else [f for f in [ficha_intel(texto)] if f]
            if not filas:
                ilegibles.append(archivo.name)
            for fila in filas:
                guardadas[fila["models"][0]] = fila
    datos = json.loads(INTEL.read_text(encoding="utf-8"))
    manuales = []
    for fila in datos["cpus"]:
        resto = [m for m in fila["models"] if m not in guardadas]
        if resto:
            manuales.append({"vendor": "Intel", **fila, "models": resto, "origin": "manual"})
    return list(guardadas.values()) + manuales, ilegibles


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=pathlib.Path,
                        help="carpeta donde guardar lo descargado y reutilizarlo")
    parser.add_argument("--intel-desde", type=pathlib.Path, metavar="CARPETA",
                        help="fichas de ark.intel.com guardadas desde el navegador")
    args = parser.parse_args()

    amd, fuera = filas_amd(args.cache)
    intel, ilegibles = filas_intel(args.intel_desde)
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
    de_fichas = sum(len(f["models"]) for f in intel if f["origin"] == "saved-page")
    print(f"Intel: {de_fichas} modelos de fichas guardadas, "
          f"{sum(len(f['models']) for f in intel) - de_fichas} a mano")
    for nombre in ilegibles:
        print(f"sin memoria: {nombre} (no lleva «Memory Types»: una página de serie no la "
              f"trae, hace falta su comparación)")
    for linea in fuera:
        print(f"fuera: {linea}")
    print(f"escrito {DESTINO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
