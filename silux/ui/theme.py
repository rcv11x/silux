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

import pathlib
import tempfile
from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPalette, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication


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

    def q(self, name: str, alpha: float = 1.0) -> QColor:
        color = QColor(getattr(self, name))
        if alpha < 1.0:
            color.setAlphaF(alpha)
        return color


LIGHT = Palette(
    bg="#EDEFF3", surface="#FFFFFF", surface_alt="#F5F6F9",
    line="#D2D7DF", line_soft="#E3E7ED",
    ink="#161A21", ink_dim="#39414E", muted="#626C7B",
    accent="#B4501B", accent_soft="#C0601F", accent_wash="#F7EAE1",
    ok="#2A6E52", warn="#8A6408", crit="#93362E", info="#2A5F94",
    disabled="#A7AEBA",
)

DARK = Palette(
    bg="#0E1116", surface="#161A20", surface_alt="#1C2129",
    line="#2B323C", line_soft="#232932",
    ink="#E5E8ED", ink_dim="#BCC3CD", muted="#8C96A4",
    accent="#E1834A", accent_soft="#F0A272", accent_wash="#2A1D14",
    ok="#6FBF9A", warn="#D6AF4E", crit="#DE8078", info="#79A9D9",
    disabled="#525C6A",
)


# --------------------------------------------------------------------------
# color de acento
# --------------------------------------------------------------------------

# Cada acento son tres tonos y no uno: el color en sí, una variante más clara
# para lo que se superpone, y un lavado casi negro (o casi blanco) para los
# fondos de las insignias. Se eligen a mano y no por cálculo porque el mismo
# tono necesita valores distintos sobre un fondo oscuro que sobre uno claro, y
# derivarlos automáticamente da o bien colores apagados o bien texto ilegible.
ACCENTS: dict[str, dict[str, tuple[str, str, str]]] = {
    "naranja": {"dark": ("#E1834A", "#F0A272", "#2A1D14"),
                "light": ("#B4501B", "#C0601F", "#F7EAE1")},
    "azul":    {"dark": ("#5AA9E6", "#85C3F0", "#12212E"),
                "light": ("#1D6FB8", "#2782CE", "#E3EEF8")},
    "verde":   {"dark": ("#5FBF8B", "#8AD4AC", "#10241A"),
                "light": ("#1F7A4D", "#268A58", "#E2F2E9")},
    "morado":  {"dark": ("#A98BE0", "#C0A9EC", "#201A2E"),
                "light": ("#6A45B0", "#7A52C4", "#EDE7F8")},
    "rojo":    {"dark": ("#E57373", "#F09999", "#2E1618"),
                "light": ("#B23A3A", "#C44646", "#FAE7E7")},
    "cian":    {"dark": ("#4FBFC4", "#7CD5D9", "#0E2426"),
                "light": ("#10767C", "#14868C", "#E0F2F3")},
}
ACCENT_DEFAULT = "naranja"


def con_alfa(color: str, alfa: float) -> str:
    """El mismo color, translúcido, en la forma que entiende Qt.

    Los lavados de la paleta están escritos a mano para cada acento, y añadir
    uno por cada color que alguna vez necesite fondo suave sería una tabla que
    mantener. Para un tinte sobre el fondo que ya hay, esto basta y no puede
    desincronizarse de su color.
    """
    crudo = color.lstrip("#")
    if len(crudo) != 6:
        return color
    r, g, b = (int(crudo[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alfa:.2f})"


def tinted(base: Palette, accent: str, dark: bool) -> Palette:
    """La misma paleta con otro color de acento."""
    tonos = ACCENTS.get(accent)
    if tonos is None or accent == ACCENT_DEFAULT:
        return base
    fuerte, suave, lavado = tonos["dark" if dark else "light"]
    return dataclasses.replace(base, accent=fuerte, accent_soft=suave,
                               accent_wash=lavado)


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
    page_margin=12, section_gap=9, card_pad_h=13, card_pad_v=10, card_gap=7,
    grid_vspace=4, grid_hspace=16, base_pt=10, small_pt=9, mono_pt=9,
    headline_px=19, tile_value_pt=17, chart_height=30, cell_w=158, cell_h=40,
    nav_width=146, min_window_w=460, min_window_h=380,
)

COMPACT = Metrics(
    page_margin=8, section_gap=6, card_pad_h=9, card_pad_v=7, card_gap=4,
    grid_vspace=2, grid_hspace=11, base_pt=9, small_pt=8, mono_pt=8,
    headline_px=16, tile_value_pt=14, chart_height=22, cell_w=132, cell_h=34,
    nav_width=120, min_window_w=390, min_window_h=330,
)

METRICS: Metrics = NORMAL


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
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(size if size is not None else METRICS.mono_pt)
    font.setBold(bold)
    # Cifras de ancho fijo: sin esto las columnas de números bailan al refrescar.
    font.setStyleHint(QFont.StyleHint.Monospace)
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


def palette_for(app: QApplication) -> Palette:
    return resolve(app, "system")


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
    cache = pathlib.Path(tempfile.gettempdir()) / "silux-icons"
    target = cache / f"arrow-{color.lstrip('#')}-{direction}.png"
    if target.exists():
        return target.as_posix()

    size, scale = 16, 2                    # x2 para que no se vea dentado
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))

    half, mid, height = 4.0 * scale, size * scale / 2, 2.5 * scale
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


def stylesheet(p: Palette, m: Metrics | None = None) -> str:
    m = m or METRICS
    try:
        arrow_down = _arrow_icon(p.muted, "down")
        arrow_up = _arrow_icon(p.muted, "up")
        arrow_right = _arrow_icon(p.muted, "right")
        arrow_down_hot = _arrow_icon(p.accent, "down")
        arrows = f"""
    QComboBox::down-arrow {{{{
        image: url({arrow_down}); width: 9px; height: 9px; margin-right: 5px;
    }}}}
    QComboBox::down-arrow:on, QComboBox::down-arrow:hover {{{{
        image: url({arrow_down_hot});
    }}}}
    QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {{{{
        image: url({arrow_up}); width: 8px; height: 8px;
    }}}}
    QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {{{{
        image: url({arrow_down}); width: 8px; height: 8px;
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

    return f"""
    QMainWindow, QWidget#Root {{ background: {p.bg}; }}
    QWidget {{ color: {p.ink}; }}

    QFrame#Card {{
        background: {p.surface};
        border: 1px solid {p.line};
        border-radius: {max(6, m.card_pad_v // 2 + 3)}px;
    }}
    QFrame#CardFlat {{
        background: {p.surface_alt};
        border: 1px solid {p.line_soft};
        border-radius: 6px;
    }}

    QLabel#CardTitle {{
        color: {p.ink_dim};
        font-size: {m.small_pt + 4}px;
        font-weight: 700;
        letter-spacing: 1.4px;
        padding-bottom: 2px;
    }}
    /* La cabecera de una columna no es el título de una tarjeta: nombra un
       dato de la fila de abajo y tiene que quedarse por detrás de él. */
    QLabel#ColumnTitle {{
        color: {p.muted};
        font-size: {m.small_pt}px;
        font-weight: 600;
        letter-spacing: 1.1px;
    }}
    QLabel#FieldName  {{ color: {p.muted}; }}
    QLabel#FieldValue {{ color: {p.ink}; }}
    QLabel#Muted      {{ color: {p.muted}; }}
    QLabel#Accent     {{ color: {p.accent}; }}

    /* El «copiado» que aparece un momento junto al valor. Va con el color de
       acento porque confirma una acción del usuario, no un estado del
       equipo, y esos dos no deben confundirse. */
    QLabel#Toast {{
        color: {p.accent};
        background: {p.surface};
        border: 1px solid {p.accent};
        border-radius: 5px;
        padding: 3px 9px;
    }}

    QLabel#Headline {{ color: {p.ink}; font-size: {m.headline_px}px; font-weight: 600; }}
    QLabel#Subhead  {{ color: {p.ink_dim}; font-size: {m.small_pt + 3}px; }}

    QLabel#Badge {{
        background: {p.accent_wash};
        color: {p.accent};
        border: 1px solid {p.accent};
        border-radius: 5px;
        padding: 2px 9px;
        font-size: {m.small_pt + 1}px;
        font-weight: 600;
    }}
    QLabel#BadgeQuiet {{
        background: {p.surface_alt};
        color: {p.muted};
        border: 1px solid {p.line};
        border-radius: 5px;
        padding: 2px 9px;
        font-size: {m.small_pt + 1}px;
    }}

    QLabel#TileValue {{ color: {p.ink}; font-weight: 600; }}
    QLabel#TileUnit  {{ color: {p.muted}; font-size: {m.small_pt + 3}px; }}
    QLabel#TileLabel {{
        color: {p.muted}; font-size: {m.small_pt + 1}px;
        font-weight: 600; letter-spacing: 1.1px;
    }}

    QFrame#Notice {{
        background: {p.surface};
        border: 1px solid {p.line};
        border-left: 3px solid {p.warn};
        border-radius: 6px;
    }}
    /* Lo que el usuario puede arreglar va en ámbar; lo que es un hecho del
       hardware, en gris. Con el mismo color, «esta gráfica no trae sensor de
       temperatura» se lee como una avería permanente. */
    QFrame#Notice[tone="idle"] {{ border-left-color: {p.muted}; }}
    QFrame#Notice[tone="bad"]  {{ border-left-color: {p.crit}; }}
    QLabel#NoticeTitle {{ color: {p.ink}; font-weight: 600; }}
    QLabel#NoticeBody  {{ color: {p.ink_dim}; }}
    QLabel#NoticeHint  {{ color: {p.muted}; font-size: {m.small_pt + 2}px; }}

    /* El aviso de la barra de estado. Va en ámbar por lo mismo que la banda
       de un Notice: es de lo que el usuario puede arreglar. Y con el subrayado
       puesto, que en una barra llena de texto apagado nada dice que se pueda
       pulsar salvo que se note. */
    QPushButton#StatusAction {{
        background: transparent;
        border: none;
        padding: 0 6px;
        color: {p.warn};
        text-decoration: underline;
        font-size: {m.small_pt}px;
    }}
    QPushButton#StatusAction:hover {{ color: {p.ink}; }}

    QFrame#Divider {{ background: {p.line_soft}; max-height: 1px; border: none; }}

    QListWidget#Nav {{
        background: transparent; border: none; outline: none; padding: 4px 4px;
    }}
    QListWidget#Nav::item {{
        color: {p.muted};
        padding: {max(5, m.card_pad_v - 5)}px 11px;
        border-radius: 6px;
        margin-bottom: 2px;
    }}
    /* La sección abierta con el color de acento: en una lista de doce, un
       recuadro gris sobre fondo gris se busca, y este se encuentra. */
    QListWidget#Nav::item:selected {{
        background: {p.accent_wash};
        color: {p.accent};
        border: 1px solid {p.accent};
        font-weight: 600;
    }}
    QListWidget#Nav::item:hover:!selected {{ background: {p.surface_alt}; color: {p.ink_dim}; }}
    QListWidget#Nav::item:disabled {{ color: {p.disabled}; }}

    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {p.line}; border-radius: 4px; min-height: 28px; }}
    QScrollBar::handle:vertical:hover {{ background: {p.muted}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* --- controles de la página de ajustes --- */

    QComboBox, QDoubleSpinBox, QSpinBox {{
        background: {p.surface_alt};
        color: {p.ink};
        border: 1px solid {p.line};
        border-radius: 5px;
        padding: 4px 8px;
        min-height: 20px;
    }}
    QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover {{ border-color: {p.muted}; }}
    QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{ border-color: {p.accent}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
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
        background: transparent; border: none; width: 15px;
    }}

    QCheckBox {{ color: {p.ink}; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 15px; height: 15px;
        border: 1px solid {p.line};
        border-radius: 4px;
        background: {p.surface_alt};
    }}
    QCheckBox::indicator:hover {{ border-color: {p.muted}; }}
    QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}

    QPushButton {{
        background: {p.surface_alt};
        color: {p.ink_dim};
        border: 1px solid {p.line};
        border-radius: 5px;
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
    /* Para lo que acompaña a la acción principal sin competir con ella: el
       de al lado es el que la gente ha venido a pulsar. */
    QPushButton#GhostButton {{
        color: {p.muted};
        border-color: {p.line};
    }}
    QPushButton#GhostButton:hover {{
        border-color: {p.accent};
        color: {p.accent};
    }}
    QPushButton#GhostButton:pressed {{ background: {p.accent_wash}; }}
    QPushButton:hover {{ border-color: {p.accent}; color: {p.accent}; }}
    QPushButton:pressed {{ background: {p.accent_wash}; }}

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
    cache = pathlib.Path(tempfile.gettempdir()) / "silux-icons"
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


def palette_for(app: QApplication, choice: str, accent: str = ACCENT_DEFAULT) -> Palette:
    """El tema resuelto y ya teñido con el acento elegido.

    Es el único sitio del que se saca una paleta. Antes la ventana llamaba a
    `resolve` por su cuenta y se quedaba con la paleta sin teñir, así que el
    color elegido llegaba a la hoja de estilos pero no a lo que se pinta a
    mano (las gráficas, las barras, la matriz de núcleos) y salía a medias.
    """
    base = resolve(app, choice)
    return tinted(base, accent, dark=base.bg == DARK.bg)


def apply(app: QApplication, choice: str, density: str,
          font_scale: str = "normal", accent: str = ACCENT_DEFAULT) -> Palette:
    """Deja la aplicación entera con el tema pedido y devuelve la paleta.

    El estilo Fusion se fija a propósito: es el único que se comporta igual en
    todos los escritorios, y como aquí se pinta casi todo con la hoja de
    estilos, la integración nativa aporta menos que la previsibilidad.
    """
    set_density(density, font_scale)
    palette = palette_for(app, choice, accent)
    app.setStyle("Fusion")
    app.setPalette(qt_palette(palette))
    app.setStyleSheet(stylesheet(palette))
    return palette
