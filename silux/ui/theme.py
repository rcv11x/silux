"""Paleta, métricas y hoja de estilos.

Se define un juego de tokens propio en vez de heredar los colores del sistema
tal cual: una aplicación de datos densos necesita jerarquía (superficie,
línea, tinta, tinta apagada) y las paletas de escritorio solo garantizan un
puñado de roles. Del sistema sí se hereda, si el usuario no dice otra cosa,
la decisión de claro u oscuro y la tipografía.

Los neutros tiran a frío y el acento es cobre: el color de las pistas de una
placa y de los disipadores, que contrasta con los grises azulados sin
pelearse con ellos.

`METRICS` es una variable de módulo a propósito. Los widgets la leen al
construirse, y cambiar de densidad reconstruye las páginas, así que nunca hay
dos densidades vivas a la vez. La alternativa (pasar las métricas por el
constructor de cada widget) añadía un parámetro a doce clases sin ganar nada.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QApplication

from .. import thermal

# --------------------------------------------------------------------------
# color
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    bg: str
    surface: str
    surface_alt: str
    line: str
    line_soft: str
    ink: str
    ink_dim: str
    muted: str
    accent: str
    accent_soft: str
    accent_wash: str
    ok: str
    warn: str
    crit: str
    info: str
    disabled: str
    # The second and third series of a chart beside the accent, apart from
    # the status colours: a bar in amber or red reads as a warning.
    series_b: str = "#6A47C8"
    series_c: str = "#0E8077"
    # The empty part of a bar, up to its 100 %: seen on its card, and far
    # below the bar's own colour.
    track: str = "#ECEEF2"

    def q(self, name: str, alpha: float = 1.0) -> QColor:
        color = QColor(getattr(self, name))
        if alpha < 1.0:
            color.setAlphaF(alpha)
        return color

    def for_level(self, level: str) -> "str | None":
        """The colour of a `thermal.level`, or None for its own."""
        key = LEVEL_COLOURS.get(level)
        return getattr(self, key) if key else None


# A temperature's level and its colour, here and nowhere else: the style
# sheet below and what paints by hand (the sensors' tree, Home's line) read
# it, so a reading is the same colour wherever it's shown.
LEVEL_COLOURS = {thermal.HIGH: "warn", thermal.CRITICAL: "crit"}
# The value of a label's «level» property for each one, which the style sheet
# matches (`widgets.paint_level`).
LEVEL_PROPERTY = {thermal.HIGH: "high", thermal.CRITICAL: "critical"}


# Las superficies casi no llevan borde: lo que separa una tarjeta del fondo es
# su tono, y `line_soft` es apenas un filo. Con un borde del mismo peso en
# cada caja —cabecera, fichas, tarjetas, tablas— la página era una rejilla de
# recuadros y no se veía qué mandaba. El acento es el ámbar del logo.
LIGHT = Palette(
    bg="#F4F5F7", surface="#FFFFFF", surface_alt="#F0F2F5",
    line="#E2E5EA", line_soft="#ECEEF2",
    ink="#1B2028", ink_dim="#3A4250", muted="#667080",
    accent="#C2570C", accent_soft="#D46A1C", accent_wash="#FBEBDD",
    ok="#2A6E52", warn="#8A6408", crit="#93362E", info="#245F9E",
    disabled="#A7AEBA", series_b="#6A47C8", series_c="#0E8077",
)

DARK = Palette(
    bg="#0F1318", surface="#171C24", surface_alt="#1E242E",
    line="#252C37", line_soft="#1D232C",
    ink="#E8EBF0", ink_dim="#C2C8D2", muted="#8792A2",
    accent="#F2994A", accent_soft="#F7B77D", accent_wash="#2B2017",
    ok="#6FBF9A", warn="#D6AF4E", crit="#E0857D", info="#7FB2E5",
    disabled="#525C6A", series_b="#B49CFF", series_c="#47C1B6",
    # Its `line_soft` was nearly the card's: where the 100 % was didn't show.
    track="#2F3744",
)



def icon_cache() -> pathlib.Path:
    """Where the drawn icons are kept: the user's own runtime folder, which
    nobody else can write. Not a fixed name in /tmp, where another user could
    have left the files that Qt then loads."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base and os.path.isdir(base) and os.stat(base).st_uid == os.getuid():
        return pathlib.Path(base) / "silux-icons"
    cache = os.environ.get("XDG_CACHE_HOME") or str(pathlib.Path.home() / ".cache")
    return pathlib.Path(cache) / "silux" / "icons"

def con_alfa(color: str, alfa: float) -> str:
    """El mismo color, translúcido, en la forma que entiende Qt.

    Los lavados de la paleta están escritos a mano, y añadir uno por cada color que alguna vez necesite fondo suave sería una tabla que
    mantener. Para un tinte sobre el fondo que ya hay, esto basta y no puede
    desincronizarse de su color.
    """
    crudo = color.lstrip("#")
    if len(crudo) != 6:
        return color
    r, g, b = (int(crudo[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alfa:.2f})"


# --------------------------------------------------------------------------
# densidad
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Metrics:
    page_margin: int
    section_gap: int
    card_pad_h: int
    card_pad_v: int
    card_gap: int
    grid_vspace: int
    grid_hspace: int
    base_pt: int
    small_pt: int
    mono_pt: int
    headline_px: int
    tile_value_pt: int
    chart_height: int
    cell_w: int
    cell_h: int
    nav_width: int
    # Suelo de la ventana. No es el mínimo técnico (el contenido cabe en unos
    # 230 px) sino el punto por debajo del cual la aplicación deja de leerse
    # bien: los nombres de campo se recortan tanto que dejan de identificar
    # nada. Mejor que el usuario tope aquí a que la encoja hasta lo inútil.
    min_window_w: int
    min_window_h: int


SPACIOUS = Metrics(
    page_margin=18, section_gap=14, card_pad_h=18, card_pad_v=15, card_gap=11,
    grid_vspace=8, grid_hspace=22, base_pt=10, small_pt=10, mono_pt=10,
    headline_px=22, tile_value_pt=20, chart_height=38, cell_w=176, cell_h=50,
    nav_width=164, min_window_w=520, min_window_h=430,
)

NORMAL = Metrics(
    page_margin=14, section_gap=10, card_pad_h=15, card_pad_v=12, card_gap=8,
    grid_vspace=5, grid_hspace=16, base_pt=11, small_pt=10, mono_pt=10,
    headline_px=23, tile_value_pt=20, chart_height=30, cell_w=166, cell_h=42,
    nav_width=166, min_window_w=480, min_window_h=380,
)

# La barra lateral es más ancha que antes en las tres densidades: cada
# sección lleva su icono delante del nombre.
COMPACT = Metrics(
    page_margin=8, section_gap=6, card_pad_h=10, card_pad_v=8, card_gap=4,
    grid_vspace=2, grid_hspace=11, base_pt=9, small_pt=8, mono_pt=8,
    headline_px=18, tile_value_pt=15, chart_height=22, cell_w=132, cell_h=34,
    nav_width=140, min_window_w=410, min_window_h=330,
)

METRICS: Metrics = NORMAL

# El relleno de la lista de secciones. Lo usan la hoja de estilos y quien
# mide el ancho de la barra lateral: escrito en los dos sitios, se separan.
NAV_PADDING = 4


# Lo que el árbol de sensores deja a cada lado del texto de una celda. Vive
# aquí y no dentro de la hoja de estilos porque hay que contarlo al medir si
# una cifra cabe: escrito en los dos sitios, subirlo en uno dejó los relojes
# de núcleo como «4374.4 …» hasta que alguien arrastraba la columna.
RELLENO_DE_CELDA = 10

DENSITIES: dict[str, Metrics] = {
    "spacious": SPACIOUS,
    "normal": NORMAL,
    "compact": COMPACT,
}


# Cuánto se agranda la letra. Los pasos son los que se notan de verdad: por
# debajo de un 15 % el cambio no compensa volver a Ajustes.
FONT_SCALES: dict[str, float] = {
    "normal": 1.0, "grande": 1.15, "mayor": 1.3, "máximo": 1.5,
}


def _escalar(base: Metrics, factor: float) -> Metrics:
    """Agranda la letra, y con ella lo que tiene que seguirla.

    Los tamaños de texto van al factor entero. Las celdas y los anchos fijos
    también, o el texto grande se saldría de ellos. Los márgenes y separaciones
    crecen a la mitad de ritmo: si se agrandan igual, la pantalla se llena de
    aire justo cuando el usuario está pidiendo que quepa mejor lo que lee.
    """
    if factor == 1.0:
        return base
    entero = lambda valor: max(1, round(valor * factor))
    suave = lambda valor: max(1, round(valor * (1 + (factor - 1) / 2)))
    return dataclasses.replace(
        base,
        base_pt=entero(base.base_pt), small_pt=entero(base.small_pt),
        mono_pt=entero(base.mono_pt), headline_px=entero(base.headline_px),
        tile_value_pt=entero(base.tile_value_pt),
        cell_w=entero(base.cell_w), cell_h=entero(base.cell_h),
        nav_width=entero(base.nav_width), chart_height=entero(base.chart_height),
        min_window_w=entero(base.min_window_w), min_window_h=entero(base.min_window_h),
        page_margin=suave(base.page_margin), section_gap=suave(base.section_gap),
        card_pad_h=suave(base.card_pad_h), card_pad_v=suave(base.card_pad_v),
        card_gap=suave(base.card_gap),
        grid_vspace=suave(base.grid_vspace), grid_hspace=suave(base.grid_hspace),
    )


def set_density(name: str, font_scale: str = "normal") -> Metrics:
    global METRICS
    METRICS = _escalar(DENSITIES.get(name, NORMAL),
                       FONT_SCALES.get(font_scale, 1.0))
    return METRICS


# --------------------------------------------------------------------------
# tipografía
# --------------------------------------------------------------------------


def mono_font(size: int | None = None, bold: bool = False) -> QFont:
    """La monoespaciada de verdad: para una orden que se copia a un terminal.

    Los valores de las fichas y las tablas no van aquí sino en `value_font`.
    """
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(size if size is not None else METRICS.mono_pt)
    font.setBold(bold)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def value_font(size: int | None = None, bold: bool = False) -> QFont:
    """La letra de las cifras y los valores: la de la interfaz, con los
    números de ancho fijo.

    Con todos los valores en monoespaciada —también «activado», «PowerColor»
    o «sin límites»— la ventana tenía aire de terminal. Lo que hace falta de
    una monoespaciada es que las columnas de números no bailen al refrescar,
    y eso lo dan las cifras tabulares (`tnum`) de la letra normal.
    """
    font = QFont()
    font.setPointSize(size if size is not None else METRICS.mono_pt)
    # Values a step heavier than their grey labels: the figure is what's read.
    font.setWeight(QFont.Weight.Bold if bold else QFont.Weight.DemiBold)
    # `setFeature` existe desde Qt 6.7. Sin ella las cifras son las
    # proporcionales de la tipografía, que en las del sistema ya suelen medir
    # todas lo mismo.
    if hasattr(font, "setFeature"):
        font.setFeature(QFont.Tag("tnum"), 1)
    return font


def ui_font(size: int | None = None, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setPointSize(size if size is not None else METRICS.base_pt)
    font.setWeight(weight)
    return font


# --------------------------------------------------------------------------
# resolución del tema
# --------------------------------------------------------------------------


def system_prefers_dark(app: QApplication) -> bool:
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def resolve(app: QApplication, choice: str) -> Palette:
    if choice == "dark":
        return DARK
    if choice == "light":
        return LIGHT
    return DARK if system_prefers_dark(app) else LIGHT


# --------------------------------------------------------------------------
# hoja de estilos
# --------------------------------------------------------------------------


def _arrow_icon(color: str, direction: str) -> str:
    """Dibuja una flechita y devuelve su ruta, cacheada por color y sentido.

    Qt deja de pintar la flecha nativa de un desplegable en cuanto se le
    aplica una hoja de estilos, y no sabe construirla con bordes CSS: hay que
    darle una imagen. Se genera aquí para que siga el color del tema en vez
    de arrastrar un PNG por el repositorio.
    """
    # El triángulo ocupa diez de los dieciséis píxeles: con ocho, el selector
    # de «Refrescar cada» enseñaba dos flechas de tres píxeles. Su forma va
    # en el nombre del archivo, o la caché seguiría sirviendo la anterior.
    size, scale = 16, 2                    # x2 para que no se vea dentado
    half, height = 5.0, 3.2
    cache = icon_cache()
    target = cache / f"arrow-{color.lstrip('#')}-{direction}-{half:g}x{height:g}.png"
    if target.exists():
        return target.as_posix()

    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))

    half, mid, height = half * scale, size * scale / 2, height * scale
    if direction == "right":
        points = [QPointF(mid - height, mid - half), QPointF(mid - height, mid + half),
                  QPointF(mid + height, mid)]
    else:
        tip_y = mid + height if direction == "down" else mid - height
        base_y = mid - height if direction == "down" else mid + height
        points = [QPointF(mid - half, base_y), QPointF(mid + half, base_y),
                  QPointF(mid, tip_y)]
    painter.drawPolygon(QPolygonF(points))
    painter.end()

    cache.mkdir(parents=True, exist_ok=True)
    pixmap.save(target.as_posix(), "PNG")
    return target.as_posix()


def _check_icon(color: str) -> str:
    """Draw a tick for a checked box and return its path, cached by colour.

    With the sheet, a checked box was only filled with the accent: nothing
    in it said it was ticked. As the arrows, made here to follow the theme.
    """
    size, scale = 15, 4
    cache = icon_cache()
    target = cache / f"check-{color.lstrip('#')}-{size}.png"
    if target.exists():
        return target.as_posix()

    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 2.0 * scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    tick = QPainterPath(QPointF(3.6 * scale, 7.8 * scale))
    tick.lineTo(QPointF(6.4 * scale, 10.6 * scale))
    tick.lineTo(QPointF(11.6 * scale, 4.6 * scale))
    painter.drawPath(tick)
    painter.end()

    cache.mkdir(parents=True, exist_ok=True)
    pixmap.save(target.as_posix(), "PNG")
    return target.as_posix()


def stylesheet(p: Palette, m: Metrics | None = None) -> str:
    m = m or METRICS
    try:
        arrow_down = _arrow_icon(p.muted, "down")
        arrow_up = _arrow_icon(p.muted, "up")
        arrow_right = _arrow_icon(p.muted, "right")
        arrow_down_hot = _arrow_icon(p.accent, "down")
        # In the colour a primary button writes on the accent.
        check = _check_icon(p.bg)
        arrows = f"""
    QCheckBox::indicator:checked {{{{ image: url({check}); }}}}
    QComboBox::down-arrow {{{{
        image: url({arrow_down}); width: 14px; height: 14px; margin-right: 4px;
    }}}}
    QComboBox::down-arrow:on, QComboBox::down-arrow:hover {{{{
        image: url({arrow_down_hot});
    }}}}
    QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {{{{
        image: url({arrow_up}); width: 14px; height: 14px;
    }}}}
    QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {{{{
        image: url({arrow_down}); width: 14px; height: 14px;
    }}}}
    QTreeView::branch:has-children:closed {{{{
        image: url({arrow_right}); width: 9px; height: 9px;
    }}}}
    QTreeView::branch:has-children:open {{{{
        image: url({arrow_down}); width: 9px; height: 9px;
    }}}}
""".format()
    except Exception:                       # sin QGuiApplication todavía
        arrows = ""
    # El rojo de peligro, apenas insinuado en el fondo al pasar el ratón y un
    # poco más al pulsar. Sale del propio color y no de la paleta para que no
    # haya que declarar un lavado por cada tema.
    crit_wash = con_alfa(p.crit, 0.13)
    crit_press = con_alfa(p.crit, 0.22)

    card_radius = max(8, m.card_pad_v)

    return f"""
    QMainWindow, QWidget#Root {{ background: {p.bg}; }}
    QWidget {{ color: {p.ink}; }}

    QFrame#Card {{
        background: {p.surface};
        border: 1px solid {p.line_soft};
        border-radius: {card_radius}px;
    }}
    QFrame#WelcomePanel {{ background: {p.surface}; border: none; }}
    QFrame#CardFlat {{
        background: {p.surface_alt};
        border: none;
        border-radius: {max(6, m.card_pad_v - 3)}px;
    }}

    /* El título de una tarjeta nombra, no manda: pequeño, tenue y en
       minúscula. En mayúsculas espaciadas y a peso 700 competía con el
       titular de la página y con las cifras. */
    QLabel#CardTitle {{
        color: {p.muted};
        font-size: {m.small_pt + 4}px;
        font-weight: 600;
        padding-bottom: 3px;
    }}
    /* La cabecera de una columna no es el título de una tarjeta: nombra un
       dato de la fila de abajo y tiene que quedarse por detrás de él. */
    QLabel#ColumnTitle {{
        color: {p.muted};
        font-size: {m.small_pt}px;
        font-weight: 600;
        letter-spacing: 1.1px;
    }}
    QWidget#TableBody {{ background: transparent; }}
    /* La raya bajo la cabecera de una tabla: una, de lado a lado. */
    QFrame#TableRule {{ background: {p.line}; border: none; }}
    /* Un sí y un no en una tabla. Verde y un rojo suave: que una tarjeta no
       codifique AV1 no es una avería, así que no lleva el rojo de un fallo
       ni el amarillo de un estado del equipo. El símbolo es distinto en cada
       caso; el color solo acompaña. */
    QLabel#FieldName[tone="yes"], QLabel#FieldValue[tone="yes"] {{
        color: {p.ok}; font-weight: 700;
    }}
    QLabel#FieldName[tone="no"], QLabel#FieldValue[tone="no"] {{
        color: {con_alfa(p.crit, 0.78)};
    }}
    QLabel#FieldName  {{ color: {p.muted}; }}
    QLabel#FieldValue {{ color: {p.ink}; }}
    QLabel#Muted      {{ color: {p.muted}; }}
    QLabel#WarnText   {{ color: {p.warn}; }}
    QLabel#Accent     {{ color: {p.accent}; }}

    /* El «copiado» que aparece un momento junto al valor. Va con el color de
       acento porque confirma una acción del usuario, no un estado del
       equipo, y esos dos no deben confundirse. */
    QLabel#Toast {{
        color: {p.accent};
        background: {p.surface};
        border: 1px solid {p.accent};
        border-radius: 4px;
        padding: 1px 6px;
    }}

    QLabel#Headline {{ color: {p.ink}; font-size: {m.headline_px}px; font-weight: 650; }}
    QLabel#Subhead  {{ color: {p.ink_dim}; font-size: {m.small_pt + 3}px; }}
    /* The heading of a group of cards, such as each core type of a hybrid:
       below the page's headline and above a card's title. */
    QLabel#SectionTitle {{ color: {p.ink}; font-size: {m.headline_px - 5}px; font-weight: 650; }}

    /* Pastillas sin borde: el borde las hacía parecer botones. */
    QLabel#Badge {{
        background: {p.accent_wash};
        color: {p.accent};
        border: none;
        border-radius: 9px;
        padding: 3px 10px;
        font-size: {m.small_pt + 1}px;
        font-weight: 600;
    }}
    QLabel#BadgeQuiet {{
        background: {p.surface_alt};
        color: {p.ink_dim};
        border: none;
        border-radius: 9px;
        padding: 3px 10px;
        font-size: {m.small_pt + 1}px;
    }}

    QLabel#TileValue {{ color: {p.ink}; font-weight: 650; }}
    /* A temperature by the limits its part declares (`thermal`): amber from
       its max, red from its crit. Last, so it wins over each one's colour. */
    QLabel#TileValue[level="high"], QLabel#FieldValue[level="high"],
    QLabel#FieldName[level="high"], QLabel#Headline[level="high"] {{ color: {p.warn}; }}
    QLabel#TileValue[level="critical"], QLabel#FieldValue[level="critical"],
    QLabel#FieldName[level="critical"], QLabel#Headline[level="critical"] {{ color: {p.crit}; }}
    QLabel#TileUnit  {{ color: {p.muted}; font-size: {m.small_pt + 3}px; }}
    QLabel#TileLabel {{
        color: {p.muted}; font-size: {m.small_pt + 3}px;
        font-weight: 500;
    }}

    QFrame#Notice {{
        background: {p.surface};
        border: 1px solid {p.line_soft};
        border-left: 3px solid {p.warn};
        border-radius: 8px;
    }}
    /* Lo que el usuario puede arreglar va en azul; lo que es un hecho del
       hardware, en gris; un fallo, en rojo. Con el mismo color, «esta gráfica
       no trae sensor de temperatura» se lee como una avería permanente. Y no
       en ámbar: el ámbar es la marca y el acento, y un aviso del color de un
       botón no avisa. El amarillo queda para un estado del equipo: un disco
       que avisa de algo, una lectura cerca de su límite. */
    QFrame#Notice[tone="action"] {{ border-left-color: {p.info}; }}
    QFrame#Notice[tone="idle"] {{ border-left-color: {p.muted}; }}
    QFrame#Notice[tone="bad"]  {{ border-left-color: {p.crit}; }}
    QLabel#NoticeTitle {{ color: {p.ink}; font-weight: 600; }}
    QLabel#NoticeBody  {{ color: {p.ink_dim}; }}
    QLabel#NoticeHint  {{ color: {p.muted}; font-size: {m.small_pt + 2}px; }}

    /* El aviso de la barra de estado. Va en azul por lo mismo que la banda
       de un Notice: es de lo que el usuario puede arreglar. Y con el subrayado
       puesto, que en una barra llena de texto apagado nada dice que se pueda
       pulsar salvo que se note. The same for a permissions link inside a
       page's text (LinkAction). */
    QPushButton#StatusAction, QPushButton#LinkAction {{
        background: transparent;
        border: none;
        padding: 0 6px;
        color: {p.info};
        text-decoration: underline;
        /* Al tamaño del texto normal y no al de la letra pequeña del resto de
           la barra: es lo único de ahí que se puede pulsar, y con `small_pt`
           se quedaba en diez píxeles, que en un 27 pulgadas a 1440p se lee
           con esfuerzo. Sube y baja con la escala que el usuario elija, como
           todo lo demás. */
        font-size: {m.base_pt}px;
        font-weight: 600;
    }}
    QPushButton#StatusAction:hover, QPushButton#LinkAction:hover {{ color: {p.ink}; }}

    QFrame#Divider {{ background: {p.line_soft}; max-height: 1px; border: none; }}

    QListWidget#Nav {{
        background: transparent; border: none; outline: none;
        padding: {NAV_PADDING}px {NAV_PADDING}px;
    }}
    QListWidget#Nav::item {{
        color: {p.ink_dim};
        padding: {max(5, m.card_pad_v - 6)}px 9px;
        border-radius: 8px;
        margin-bottom: 1px;
    }}
    /* La sección abierta, sobre una pastilla del color de acento y con su
       icono en ámbar: en una lista de trece se encuentra sin leer. Sin
       borde, que la convertía en un recuadro más. */
    QListWidget#Nav::item:selected {{
        background: {p.accent_wash};
        color: {p.ink};
        border: none;
        font-weight: 600;
    }}
    QListWidget#Nav::item:hover:!selected {{ background: {p.surface_alt}; color: {p.ink_dim}; }}
    QListWidget#Nav::item:disabled {{ color: {p.disabled}; }}

    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
    QProgressBar {{ background: {p.track}; border: none; border-radius: 3px; }}
    QProgressBar::chunk {{ background: {p.accent}; border-radius: 3px; }}
    QScrollBar::handle:vertical {{ background: {p.line}; border-radius: 4px; min-height: 28px; }}
    QScrollBar::handle:vertical:hover {{ background: {p.muted}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* --- controles de la página de ajustes --- */

    /* El borde de un control en reposo es `muted` y no `line`: es lo único
       que dice dónde acaba, porque su relleno apenas se separa de la tarjeta
       (1.1:1). Con `line` el contorno quedaba en 1.2:1 en oscuro y no se
       veía; `muted` da 5.4:1 en oscuro y 5.0:1 en claro, por encima del 3:1
       que pide un control (WCAG 1.4.11). Al pasar el ratón sube a `ink_dim`. */
    QComboBox, QDoubleSpinBox, QSpinBox {{
        background: {p.surface_alt};
        color: {p.ink};
        border: 1px solid {p.muted};
        border-radius: 5px;
        padding: 4px 8px;
        min-height: 20px;
    }}
    QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover {{ border-color: {p.ink_dim}; }}
    QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{ border-color: {p.accent}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {p.surface};
        color: {p.ink};
        border: 1px solid {p.line};
        selection-background-color: {p.accent_wash};
        selection-color: {p.accent};
        outline: none;
        padding: 3px;
    }}
    QDoubleSpinBox::up-button, QSpinBox::up-button,
    QDoubleSpinBox::down-button, QSpinBox::down-button {{
        background: transparent; border: none; width: 20px;
    }}

    QCheckBox {{ color: {p.ink}; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 15px; height: 15px;
        border: 1px solid {p.muted};
        border-radius: 4px;
        background: {p.surface_alt};
    }}
    QCheckBox::indicator:hover {{ border-color: {p.ink_dim}; }}
    QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}

    QPushButton {{
        background: {p.surface_alt};
        color: {p.ink_dim};
        border: 1px solid {p.muted};
        border-radius: 8px;
        padding: 5px 13px;
    }}
    /* Para lo que interrumpe o descarta: se tiene que distinguir del botón
       que empieza algo, sin gritar más que el contenido. */
    QPushButton#Danger {{
        color: {p.crit};
        border-color: {p.crit};
    }}
    /* Estos dos hover van escritos aparte y no les vale el de abajo. Un
       selector con id gana a uno con pseudo-clase, así que `QPushButton#Danger`
       le ganaba el color y el borde a `QPushButton:hover` y estos botones se
       quedaban sin reaccionar al ratón. El único hover que tenían ponía el
       fondo que ya tenían puesto, o sea, nada. */
    QPushButton#Danger:hover {{
        background: {crit_wash};
        color: {p.crit};
        border-color: {p.crit};
    }}
    QPushButton#Danger:pressed {{ background: {crit_press}; }}
    /* La acción a la que lleva un aviso: la única rellena con el acento,
       para que sea lo primero que se vea al lado de los botones que solo lo
       apartan. Es el único sitio, con la sección abierta y las curvas, donde
       el ámbar ocupa superficie. */
    QPushButton#Primary {{
        background: {p.accent};
        color: {p.bg};
        border: 1px solid {p.accent};
        font-weight: 600;
    }}
    QPushButton#Primary:hover {{
        background: {p.accent_soft};
        color: {p.bg};
        border-color: {p.accent_soft};
    }}
    QPushButton#Primary:disabled {{
        background: {p.surface_alt}; color: {p.disabled}; border-color: {p.line};
    }}
    /* Un botón que es solo su texto: para apartar un aviso sin que el gesto
       pese lo mismo que atenderlo. */
    QPushButton#TextButton {{
        background: transparent;
        border: none;
        padding: 5px 8px;
        color: {p.muted};
    }}
    QPushButton#TextButton:hover {{ color: {p.ink}; text-decoration: underline; }}
    /* A tab of a page (Performance's tests): its name, and a line of the
       accent under the one shown. Not Qt's tab bar, whose frame doesn't
       match the cards. */
    QPushButton#Tab {{
        background: transparent;
        border: none;
        border-bottom: 2px solid transparent;
        border-radius: 0;
        padding: 6px 12px;
        color: {p.muted};
    }}
    QPushButton#Tab:hover {{ color: {p.ink}; }}
    QPushButton#Tab:checked {{
        background: transparent;
        color: {p.ink};
        border-bottom: 2px solid {p.accent};
        font-weight: 600;
    }}
    /* Para lo que acompaña a la acción principal sin competir con ella: el
       de al lado es el que la gente ha venido a pulsar. */
    QPushButton#GhostButton {{
        color: {p.muted};
        border-color: {p.muted};
    }}
    QPushButton#GhostButton:hover {{
        border-color: {p.accent};
        color: {p.accent};
    }}
    QPushButton#GhostButton:pressed {{ background: {p.accent_wash}; }}
    QPushButton:hover {{ border-color: {p.accent}; color: {p.accent}; }}
    QPushButton:pressed {{ background: {p.accent_wash}; }}
    /* A sheet colour overrides the palette's disabled one, so without this a
       button that can't be pressed looks like one that can. After the hover:
       of two rules that weigh the same, the later wins. */
    QPushButton:disabled, QPushButton#Danger:disabled, QPushButton#GhostButton:disabled {{
        background: {p.surface_alt}; color: {p.disabled}; border-color: {p.line};
    }}
    /* Los de una fila de una tabla (Renombrar y Borrar en Rendimiento): del
       alto del texto de la fila, no del de un botón suelto. */
    QPushButton[compacto="true"] {{
        padding: 1px 8px;
        border-radius: 6px;
    }}
    /* El que se queda pulsado (MB/s o Mb/s en Red): el elegido, con el
       acento, para que se vea cuál está puesto sin tener que pulsar. */
    QPushButton:checked {{
        background: {p.accent_wash};
        border-color: {p.accent};
        color: {p.accent};
        font-weight: 600;
    }}

    /* --- árbol de sensores --- */

    QTreeWidget {{
        background: {p.surface};
        alternate-background-color: {p.surface_alt};
        border: 1px solid {p.line_soft};
        border-radius: 8px;
        outline: none;
        padding: 2px;
    }}
    /* Sin `color` a propósito. Una hoja de estilos que lo declara aquí pisa
       el que cada celda pide por su cuenta, y con él puesto no se veían ni el
       rojo de un sensor pasado de vueltas ni el ámbar del que se está
       acercando: el árbol salía entero del mismo gris. El color base lo pone
       el propio árbol al montar cada fila. */
    /* El árbol de dispositivos USB va siempre abierto: sin flechas. */
    QTreeWidget#DeviceTree::branch {{ image: none; border-image: none; }}
    QTreeWidget::item {{
        padding: {max(3, m.grid_vspace)}px {RELLENO_DE_CELDA}px;
        border: none;
        border-radius: 5px;
    }}
    QTreeWidget::item:selected {{ background: {p.accent_wash}; color: {p.accent}; }}
    QTreeWidget::item:hover {{ background: {p.surface_alt}; }}
    QHeaderView::section {{
        background: {p.surface_alt};
        color: {p.muted};
        border: none;
        border-bottom: 1px solid {p.line};
        /* El horizontal es generoso a propósito: las columnas de cifras van
           alineadas a la derecha, así que el texto termina siempre pegado al
           borde donde el propio widget dibuja la marca de arrastre. Ensanchar
           la columna no lo arregla —ese hueco cae por la izquierda—, y solo el
           relleno mete aire donde hace falta. */
        padding: 7px {RELLENO_DE_CELDA}px;
        font-size: {m.small_pt + 1}px;
        font-weight: 600;
        letter-spacing: 0.8px;
    }}
    QHeaderView::section:first {{ padding-left: 8px; }}
    /* El árbol de Dispositivos va entre tablas, y su cabecera tiene que ser
       como la de ellas (`QLabel#ColumnTitle`): sin fondo, pequeña y con la
       raya debajo. La del árbol de sensores sí lleva fondo: es una lista
       que se ordena y se redimensiona. */
    QTreeWidget#DeviceTree {{
        background: transparent;
        border: none;
        padding: 0;
    }}
    QTreeWidget#DeviceTree QHeaderView {{ background: transparent; border: none; }}
    QTreeWidget#DeviceTree QHeaderView::section {{
        background: transparent;
        color: {p.muted};
        border: none;
        border-bottom: 1px solid {p.line};
        padding: 0 {RELLENO_DE_CELDA}px 3px {RELLENO_DE_CELDA}px;
        font-size: {m.small_pt}px;
        font-weight: 600;
        letter-spacing: 1.1px;
    }}
    QTreeWidget#DeviceTree::item:hover {{ background: transparent; }}

    QToolTip {{
        background: {p.surface}; color: {p.ink};
        border: 1px solid {p.line}; padding: 4px 6px;
    }}
    """ + arrows


# --------------------------------------------------------------------------
# aplicación del tema
# --------------------------------------------------------------------------


def qt_palette(p: Palette) -> QPalette:
    """Traduce los tokens a la QPalette que usa Qt para dibujar por su cuenta.

    Hace falta porque hay cosas que Qt no dibuja desde la hoja de estilos: las
    flechas de los desplegables, el cursor de texto, el color de selección.
    Intentar hacerlas con bordes CSS produce cuadrados, no triángulos.
    """
    role = QPalette.ColorRole
    group = QPalette.ColorGroup
    palette = QPalette()

    pairs = {
        role.Window: p.bg,
        role.WindowText: p.ink,
        role.Base: p.surface,
        role.AlternateBase: p.surface_alt,
        role.Text: p.ink,
        role.Button: p.surface_alt,
        role.ButtonText: p.ink,
        role.BrightText: p.accent,
        role.Highlight: p.accent,
        role.HighlightedText: p.surface,
        role.ToolTipBase: p.surface,
        role.ToolTipText: p.ink,
        role.PlaceholderText: p.muted,
        role.Light: p.line_soft,
        role.Mid: p.line,
        role.Dark: p.muted,
        role.Shadow: p.line,
    }
    for key, value in pairs.items():
        palette.setColor(key, QColor(value))

    for key in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(group.Disabled, key, QColor(p.disabled))

    return palette


# --------------------------------------------------------------------------
# iconos de los sensores
# --------------------------------------------------------------------------

# Cada magnitud con su color y su silueta. A 12 píxeles el color hace la mitad
# del trabajo y la forma la otra mitad; es lo que permite recorrer una lista
# de cuarenta sensores sin leer una sola etiqueta.
SENSOR_COLORS: dict[str, str] = {
    "temperature": "crit",
    "voltage": "warn",
    "fan": "info",
    "power": "accent",
    "current": "warn",
    "energy": "accent",
    "clock": "info",
    "usage": "ok",
    "other": "muted",
}


def sensor_icon(kind: str, palette: Palette):
    """Devuelve la ruta de un icono de 16 px para una magnitud."""
    color = getattr(palette, SENSOR_COLORS.get(kind, "muted"))
    cache = icon_cache()
    target = cache / f"sensor-{kind}-{color.lstrip('#')}.png"
    if target.exists():
        return target.as_posix()

    size, scale = 16, 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _draw_sensor_glyph(painter, kind, QColor(color), size * scale)
    painter.end()

    cache.mkdir(parents=True, exist_ok=True)
    pixmap.save(target.as_posix(), "PNG")
    return target.as_posix()


def _draw_sensor_glyph(painter: QPainter, kind: str, color: QColor, box: float) -> None:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPen

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    unit = box / 16.0                       # trabajar en una rejilla de 16

    if kind == "temperature":
        painter.drawRoundedRect(QRectF(6.5 * unit, 2 * unit, 3 * unit, 8 * unit),
                                1.5 * unit, 1.5 * unit)
        painter.drawEllipse(QRectF(4.5 * unit, 8.5 * unit, 7 * unit, 7 * unit))
    elif kind in ("voltage", "current"):
        painter.drawPolygon(QPolygonF([
            QPointF(9.5 * unit, 1.5 * unit), QPointF(4 * unit, 9 * unit),
            QPointF(7.5 * unit, 9 * unit), QPointF(6.5 * unit, 14.5 * unit),
            QPointF(12 * unit, 7 * unit), QPointF(8.5 * unit, 7 * unit),
        ]))
    elif kind == "fan":
        painter.drawEllipse(QRectF(6.5 * unit, 6.5 * unit, 3 * unit, 3 * unit))
        for angle in (0, 90, 180, 270):
            painter.save()
            painter.translate(box / 2, box / 2)
            painter.rotate(angle)
            painter.drawPolygon(QPolygonF([
                QPointF(0, -1.6 * unit), QPointF(6.5 * unit, -5 * unit),
                QPointF(6.5 * unit, -0.4 * unit),
            ]))
            painter.restore()
    elif kind in ("power", "energy"):
        # El símbolo IEC de encendido: arco abierto arriba y un trazo vertical.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, 2 * unit, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(QRectF(3 * unit, 3 * unit, 10 * unit, 10 * unit), 70 * 16, 340 * 16)
        painter.drawLine(QPointF(8 * unit, 1.5 * unit), QPointF(8 * unit, 7 * unit))
    elif kind == "clock":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, 1.6 * unit))
        painter.drawEllipse(QRectF(2.5 * unit, 2.5 * unit, 11 * unit, 11 * unit))
        painter.setPen(QPen(color, 1.6 * unit, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(8 * unit, 8 * unit), QPointF(8 * unit, 4.5 * unit))
        painter.drawLine(QPointF(8 * unit, 8 * unit), QPointF(11 * unit, 9.5 * unit))
    elif kind == "usage":
        for index, height in enumerate((5, 9, 13)):
            painter.drawRoundedRect(
                QRectF((3 + index * 4) * unit, (15 - height) * unit, 2.6 * unit, height * unit),
                1.0 * unit, 1.0 * unit,
            )
    else:
        painter.drawEllipse(QRectF(5 * unit, 5 * unit, 6 * unit, 6 * unit))


def palette_for(app: QApplication, choice: str) -> Palette:
    """El tema resuelto. Es el único sitio del que se saca una paleta.

    El acento es uno, el ámbar de la marca, y va en la paleta de cada tema.
    Hubo seis a elegir en Ajustes, y bastaba un «azul» guardado para que el
    AppImage saliera de un color y las capturas de otro.
    """
    return resolve(app, choice)


def apply(app: QApplication, choice: str, density: str,
          font_scale: str = "normal") -> Palette:
    """Deja la aplicación entera con el tema pedido y devuelve la paleta.

    El estilo Fusion se fija a propósito: es el único que se comporta igual en
    todos los escritorios, y como aquí se pinta casi todo con la hoja de
    estilos, la integración nativa aporta menos que la previsibilidad.
    """
    set_density(density, font_scale)
    palette = palette_for(app, choice)
    app.setStyle("Fusion")
    app.setPalette(qt_palette(palette))
    app.setStyleSheet(stylesheet(palette))
    return palette
