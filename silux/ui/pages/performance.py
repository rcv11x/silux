"""Página de rendimiento: una prueba que dice en qué condiciones se hizo.

Lo que se enseña no es un número sino un número con su contexto. La cifra de un
benchmark depende del gobernador de energía, de lo caliente que esté el equipo
y de lo que estuviera haciendo por detrás, y sin eso comparar con el resultado
de otra máquina no significa nada.

La prueba corre en su propio hilo. Si corriera en el de la interfaz, la ventana
se quedaría congelada los veinte segundos, y además la propia interfaz robaría
tiempo de procesador a lo que se está midiendo.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QProgressBar,
                               QPushButton, QWidget,
                               QScrollArea, QVBoxLayout, QWidget)

from ... import benchmark, history, render, score
from ...i18n import _
from ...settings import Preferences
from .. import theme
from ..theme import Palette, ui_font
from ..scorebar import ScoreBar
from ..widgets import (Card, InfoGrid, Notice, ResponsiveRow, Table,
                       clear_layout, mono_font)

RESULT_HEADERS = ("bench.col.load", "bench.col.one", "bench.col.all", "bench.col.scale")
HISTORY_HEADERS = ("bench.col.test", "bench.col.measure", "bench.col.score", "bench.col.avgfreq",
                   "bench.col.maxtemp")
CONDITION_FIELDS = ("bench.col.avgfreq", "bench.cond.maxfreq", "bench.cond.endfreq",
                    "bench.cond.starttemp", "bench.cond.maxtemp",
                    "bench.cond.governor", "bench.cond.epp", "bench.cond.load")


# Lo que se puede pedir, y para qué sirve cada uno.
DURACIONES = (
    ("bench.dur.quick", 3.0),
    ("bench.dur.normal", 5.0),
    ("bench.dur.sustained", 15.0),
    ("bench.dur.warm", 30.0),
    ("bench.dur.endurance", 120.0),
    ("bench.dur.stability", 300.0),
    ("bench.dur.other", None),
)


class PerformancePage(QScrollArea):
    _finished = Signal(object)
    _progressed = Signal(str, float)

    def __init__(self, palette: Palette, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._p = palette
        self._prefs = prefs
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._resultado: benchmark.Result | None = None
        m = theme.METRICS

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root = QWidget()
        root.setObjectName("Root")
        self.setWidget(root)

        self._layout = QVBoxLayout(root)
        self._layout.setContentsMargins(m.page_margin, m.page_margin,
                                        m.page_margin, m.page_margin)
        self._layout.setSpacing(m.section_gap)

        self._layout.addWidget(self._build_header())

        # Antes que la tabla de medidas: es la cifra que se mira primero, y
        # la única que significa algo fuera de este equipo.
        self.score_card = Card(_("bench.card.score"))
        self.score_value = QLabel("")
        self.score_value.setObjectName("Headline")
        self.score_value.setFont(ui_font(theme.METRICS.headline_px))
        self.score_card.body.addWidget(self.score_value)
        self.score_detail = QLabel("")
        self.score_detail.setObjectName("Muted")
        self.score_detail.setWordWrap(True)
        self.score_card.body.addWidget(self.score_detail)
        self.score_bar = ScoreBar(palette)
        self.score_card.body.addWidget(self.score_bar)
        self.score_range = QLabel("")
        self.score_range.setObjectName("Muted")
        self.score_range.setFont(ui_font(theme.METRICS.small_pt))
        self.score_card.body.addWidget(self.score_range)
        self.score_card.hide()
        self._layout.addWidget(self.score_card)

        self.results_card = Card(_("bench.card.results"))
        self.results = Table([_(h) for h in RESULT_HEADERS], numeric=(False, True, True, True))
        self.results_card.body.addWidget(self.results)
        self.results_card.hide()
        self._layout.addWidget(self.results_card)

        fila = ResponsiveRow(min_item_width=300)
        self.conditions_card = Card(_("bench.card.conditions"))
        self.conditions = InfoGrid()
        for campo in CONDITION_FIELDS:
            self.conditions.add(_(campo))
        self.conditions_card.body.addWidget(self.conditions)
        fila.add(self.conditions_card)
        self.explain_card = self._build_explanation()
        fila.add(self.explain_card)
        self.columns = fila
        self.columns.hide()
        self._layout.addWidget(fila)

        self.history_card = Card(_("bench.card.history"))
        self.history_note = QLabel("")
        self.history_note.setObjectName("Muted")
        self.history_note.setWordWrap(True)
        # Rejilla propia y no una Table: cada fila lleva dos botones, y Table
        # solo sabe de texto. Se reconstruye al guardar o borrar, no en cada
        # muestreo, así que aquí no aplica la regla de reutilizar widgets.
        self.history_host = QVBoxLayout()
        self.history_host.setSpacing(0)
        self.history_card.body.addLayout(self.history_host)
        self.history_card.body.addWidget(self.history_note)

        # Va dentro de la tarjeta del historial y no en un aviso aparte: solo
        # significa algo al lado de las pruebas de las que sale.
        self.deriva_hint = QLabel()
        self.deriva_hint.setObjectName("NoticeHint")
        self.deriva_hint.setWordWrap(True)
        self.deriva_hint.hide()
        self.history_card.body.addWidget(self.deriva_hint)

        nota = QLabel(
            _("bench.history.note"))
        nota.setObjectName("Muted")
        nota.setWordWrap(True)
        self.history_card.body.addWidget(nota)

        acciones = QHBoxLayout()
        self.open_folder = QPushButton(_("bench.button.folder"))
        self.open_folder.setToolTip(str(history.history_path()))
        self.open_folder.clicked.connect(self._abrir_carpeta)
        self.clear_history = QPushButton(_("bench.button.clear"))
        self.clear_history.clicked.connect(self._borrar_historial)
        acciones.addWidget(self.open_folder)
        acciones.addWidget(self.clear_history)
        acciones.addStretch(1)
        self.history_card.body.addLayout(acciones)
        self.history_card.hide()
        self._layout.addWidget(self.history_card)

        self._warnings_host = QVBoxLayout()
        self._warnings_host.setSpacing(6)
        self._layout.addLayout(self._warnings_host)
        self._layout.addStretch(1)

        self._cpu_actual = "?"
        self._pintar_historial(history.load())

        self._finished.connect(self._on_finished)
        self._progressed.connect(self._on_progress)

    # -- construcción -------------------------------------------------------

    def _build_header(self) -> Card:
        card = Card()
        titulo = QLabel(_("bench.card.title"))
        titulo.setObjectName("Headline")
        subtitulo = QLabel(
            _("bench.intro")
        )
        subtitulo.setObjectName("Subhead")
        subtitulo.setWordWrap(True)

        self.run_button = QPushButton(_("bench.button.run"))
        self.run_button.clicked.connect(lambda: self._start(quick=False))
        self.quick_button = QPushButton(_("bench.button.quick"))
        self.quick_button.setToolTip(
            _("bench.quick.tip")
        )
        self.quick_button.clicked.connect(lambda: self._start(quick=True))

        # Alargar la prueba no cambia la cifra: cambia en qué condiciones se
        # toma. A los cinco segundos el turbo ya subió y el disipador aún está
        # frío; a los treinta se mide con el equipo asentado, que es lo que de
        # verdad pasa mientras se juega o se compila.
        self.duracion = QComboBox()
        for etiqueta, segundos in DURACIONES:
            # La que se puede comparar con otros equipos va marcada: sin esto,
            # elegirla era cuestión de suerte y la barra de comparación no
            # aparecía nunca sin que nada dijera por qué.
            nombre = _(etiqueta)
            if segundos == score.SEGUNDOS_CANONICOS:
                nombre += _("bench.dur.comparable")
            self.duracion.addItem(nombre, segundos)
        self.duracion.setCurrentIndex(
            next((i for i, (_e, s) in enumerate(DURACIONES)
                  if s == score.SEGUNDOS_CANONICOS), 1))
        self.duracion.activated.connect(self._quizas_preguntar_duracion)
        self._duracion_libre: float | None = None
        self.duracion.setToolTip(
            _("bench.duration.tip"))

        # Con diez medidas y la duración a elegir, la prueba puede irse a
        # horas. Poder pararla no es un extra: es lo que hace que probar una
        # duración larga no dé miedo.
        self.cancel_button = QPushButton(_("bench.button.cancel"))
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.clicked.connect(self._cancelar)
        self.cancel_button.hide()

        fila = QHBoxLayout()
        fila.addWidget(self.run_button)
        fila.addWidget(self.quick_button)
        fila.addWidget(self.cancel_button)
        fila.addSpacing(12)
        fila.addWidget(QLabel(_("bench.label.each")))
        fila.addWidget(self.duracion)
        # Cuánto tarda la prueba entera. Son diez medidas, así que «30 s» son
        # cinco minutos: la cuenta la hace nadie de cabeza mientras elige.
        self.duracion_total = QLabel("")
        self.duracion_total.setObjectName("Muted")
        fila.addWidget(self.duracion_total)
        fila.addStretch(1)
        self.duracion.currentIndexChanged.connect(self._pintar_total)
        self._pintar_total()

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(True)
        self.progress.hide()

        card.body.addWidget(titulo)
        card.body.addWidget(subtitulo)
        card.body.addLayout(fila)
        card.body.addWidget(self.progress)
        return card

    def _build_explanation(self) -> Card:
        card = Card(_("bench.card.what"))
        for carga in benchmark.CARGAS:
            etiqueta = QLabel(f"<b>{carga.name}</b><br>{carga.explanation}")
            etiqueta.setObjectName("Muted")
            etiqueta.setWordWrap(True)
            card.body.addWidget(etiqueta)
        nota = QLabel(
            _("bench.explain.scaling")
        )
        nota.setObjectName("Muted")
        nota.setWordWrap(True)
        card.body.addWidget(nota)
        return card

    # -- ejecución ----------------------------------------------------------

    def _start(self, quick: bool) -> None:
        if self._hilo is not None and self._hilo.is_alive():
            return
        self._parar.clear()
        self.cancel_button.setEnabled(True)
        self.run_button.setEnabled(False)
        self.quick_button.setEnabled(False)
        self.cancel_button.show()
        self.progress.setValue(0)
        self.progress.setFormat(_("bench.state.preparing"))
        self.progress.show()
        clear_layout(self._warnings_host)

        segundos = None if quick else self._segundos_elegidos()

        def trabajo() -> None:
            resultado = benchmark.run(
                quick=quick,
                seconds=segundos,
                on_progress=lambda que, cuanto: self._progressed.emit(que, cuanto),
                stop=self._parar,
            )
            self._finished.emit(resultado)

        self._hilo = threading.Thread(target=trabajo, daemon=True)
        self._hilo.start()

    def _on_progress(self, que: str, cuanto: float) -> None:
        self.progress.setValue(int(cuanto * 100))
        self.progress.setFormat(f"{que}  ·  %p %")

    def _pintar_total(self) -> None:
        segundos = self._segundos_elegidos() if hasattr(self, "_duracion_libre") else \
            self.duracion.currentData()
        if not segundos:
            self.duracion_total.setText("")
            return
        total = segundos * len(benchmark.CARGAS) * 2
        if total < 90:
            texto = _("bench.total.s").format(n=f"{total:.0f}")
        elif total < 3600:
            texto = _("bench.total.min").format(n=f"{total / 60:.0f}")
        else:
            texto = _("bench.total.h").format(n=f"{total / 3600:.1f}")
        self.duracion_total.setText(texto)

    def _segundos_elegidos(self) -> float | None:
        elegido = self.duracion.currentData()
        return self._duracion_libre if elegido is None else elegido

    def _quizas_preguntar_duracion(self, indice: int) -> None:
        """Si han elegido «Otra duración», pregunta cuántos minutos.

        En minutos y no en segundos porque quien llega hasta aquí ya no está
        midiendo un pico: quiere dejar el equipo trabajando un rato largo para
        ver si aguanta, y eso se piensa en minutos.
        """
        from PySide6.QtWidgets import QInputDialog

        if self.duracion.itemData(indice) is not None:
            self._duracion_libre = None
            return
        minutos, aceptado = QInputDialog.getDouble(
            self, _("bench.dialog.duration"),
            _("bench.dialog.duration.body"),
            value=(self._duracion_libre or 600.0) / 60.0,
            minValue=benchmark.MINIMO_SEGUNDOS / 60.0,
            maxValue=benchmark.MAXIMO_SEGUNDOS / 60.0, decimals=1)
        if not aceptado:
            self.duracion.setCurrentIndex(1)
            self._duracion_libre = None
            return
        self._duracion_libre = minutos * 60.0
        self.duracion.setItemText(
            indice, _("bench.dur.each").format(n=f"{minutos:g}"))
        self._pintar_total()

    def _pintar_filas(self, entradas) -> None:
        """Una fila por prueba, con su nombre, sus cifras y sus dos botones."""
        from PySide6.QtWidgets import QGridLayout

        clear_layout(self.history_host)
        rejilla = QGridLayout()
        rejilla.setContentsMargins(0, 0, 0, 0)
        rejilla.setHorizontalSpacing(theme.METRICS.grid_hspace)
        rejilla.setVerticalSpacing(theme.METRICS.grid_vspace + 3)

        for columna, titulo in enumerate(HISTORY_HEADERS):
            etiqueta = QLabel(_(titulo).upper())
            etiqueta.setObjectName("ColumnTitle")
            etiqueta.setAlignment(Qt.AlignmentFlag.AlignRight if columna in (2, 3, 4)
                                  else Qt.AlignmentFlag.AlignLeft)
            rejilla.addWidget(etiqueta, 0, columna)

        for fila, entrada in enumerate(entradas, start=1):
            # La misma cifra que arriba. Antes esta columna traía la suma en
            # crudo de operaciones por segundo, así que la misma prueba salía
            # con dos números distintos en la misma pantalla.
            # Una prueba medida con otra escala no se pone al lado de estas:
            # su cifra diría una diferencia que no existe.
            de_esta_escala = entrada.score_version == score.VERSION
            puntos = (score.puntuar(entrada.scores, entrada.threads)
                      if de_esta_escala else None)
            celdas = (
                entrada.label or entrada.when,
                self._duracion_de(entrada),
                f"{puntos[1]:n}" if puntos else render.DASH,
                render.hz(entrada.frequency_avg_hz),
                render.temperature(entrada.temperature_peak_c, self._prefs.fahrenheit),
            )
            for columna, texto in enumerate(celdas):
                etiqueta = QLabel(texto)
                etiqueta.setObjectName("FieldValue" if columna == 0 else "FieldName")
                if columna:
                    etiqueta.setFont(mono_font())
                etiqueta.setAlignment(Qt.AlignmentFlag.AlignRight if columna in (2, 3, 4)
                                      else Qt.AlignmentFlag.AlignLeft)
                if columna == 0 and entrada.label:
                    etiqueta.setToolTip(entrada.when)
                rejilla.addWidget(etiqueta, fila, columna)

            acciones = QHBoxLayout()
            acciones.setSpacing(4)
            renombrar = QPushButton(_("bench.button.rename"))
            renombrar.setToolTip(_("bench.dialog.name.tip"))
            renombrar.clicked.connect(
                lambda _=False, e=entrada: self._renombrar(e))
            borrar = QPushButton(_("bench.button.delete"))
            borrar.setObjectName("Danger")
            borrar.clicked.connect(lambda _=False, e=entrada: self._borrar_una(e))
            acciones.addWidget(renombrar)
            acciones.addWidget(borrar)
            contenedor = QWidget()
            contenedor.setLayout(acciones)
            rejilla.addWidget(contenedor, fila, len(HISTORY_HEADERS))

        # El sobrante va detrás de los botones y no a la columna del nombre.
        # Estirando la primera, en pantalla completa quedaba un palmo entre la
        # fecha de la prueba y sus cifras, que son justo lo que se compara.
        rejilla.setColumnStretch(len(HISTORY_HEADERS) + 1, 1)
        envoltorio = QWidget()
        envoltorio.setLayout(rejilla)
        self.history_host.addWidget(envoltorio)

    def _duracion_de(self, entrada) -> str:
        """Cómo se midió: es la mitad de lo que hace comparable una cifra.

        Se redondea porque lo guardado es lo que tardó de verdad —2,00182 s—
        y esa precisión no es un dato: nadie eligió medir durante dos segundos
        y mil ochocientas microsegundos. Lo que importa es contra qué se puede
        comparar, y para eso basta el número que se pidió.
        """
        segundos = entrada.seconds
        if segundos < 90:
            return f"{segundos:.0f} s" if segundos >= 10 else f"{segundos:.1f} s"
        return f"{segundos / 60:.0f} min"

    def _renombrar(self, entrada) -> None:
        from PySide6.QtWidgets import QInputDialog

        nombre, aceptado = QInputDialog.getText(
            self, _("bench.dialog.name"),
            _("bench.dialog.name.body"),
            text=entrada.label or "")
        if aceptado:
            self._pintar_historial(history.rename(entrada.timestamp, nombre))

    def _borrar_una(self, entrada) -> None:
        from PySide6.QtWidgets import QMessageBox

        cual = entrada.label or entrada.when
        if QMessageBox.question(
                self, _("bench.dialog.delete"),
                _("bench.dialog.delete.body").format(nombre=cual),
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        quedan = history.remove(entrada.timestamp)
        self._pintar_historial(quedan)
        if not quedan:
            self.history_card.hide()

    def _cancelar(self) -> None:
        """Para la prueba en cuanto termine la medida que esté en curso."""
        self._parar.set()
        self.cancel_button.setEnabled(False)
        self.progress.setFormat(_("bench.state.cancelling"))

    def _abrir_carpeta(self) -> None:
        """Abre el gestor de archivos donde se guardan las pruebas.

        Con el gestor del escritorio, no con una ruta escrita en un aviso:
        quien quiere ver el archivo lo quiere abrir, no leer dónde está.
        """
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        history.data_dir().mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(history.data_dir())))

    def _borrar_historial(self) -> None:
        """Borra las pruebas guardadas, preguntando antes."""
        from PySide6.QtWidgets import QMessageBox

        cuantas = len(history.load())
        if not cuantas:
            return
        respuesta = QMessageBox.question(
            self, _("bench.button.clear"),
            _("bench.dialog.clear.body").format(
                n=cuantas,
                plural=_("bench.saved.one" if cuantas == 1
                         else "bench.saved.many")),
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel)
        if respuesta == QMessageBox.StandardButton.Yes:
            history.clear()
            self.history.set_rows([])
            self.history_card.hide()

    def _on_finished(self, resultado: benchmark.Result) -> None:
        self._resultado = resultado
        self.run_button.setEnabled(True)
        self.quick_button.setEnabled(True)
        self.cancel_button.hide()
        self.progress.hide()
        if not resultado.measures:
            # Cancelada antes de la primera medida: no hay nada que enseñar ni
            # que guardar, y apuntar media prueba en el historial la
            # ensuciaría con cifras que no se pueden comparar con nada.
            return
        self._show(resultado)
        self._guardar(resultado)

    def _guardar(self, resultado: benchmark.Result) -> None:
        """Apunta la prueba en el historial y enseña con qué se compara."""
        if not resultado.measures:
            return
        segundos = max(m.seconds for m in resultado.measures)
        entrada = history.from_result(resultado, self._cpu_actual, segundos)
        anteriores = history.append(entrada)
        self._pintar_historial(anteriores, entrada)
        self._pintar_puntuacion(entrada)

    def _pintar_puntuacion(self, entrada) -> None:
        """La cifra comparable, y dónde cae entre las de su misma pieza.

        Las dos cosas pueden faltar por separado. Sin la duración canónica no
        hay cifra —una prueba de tres segundos y otra de treinta no se ponen
        juntas—, y aun teniéndola puede no haber con qué compararla, que es lo
        normal mientras la tabla esté vacía. Cada hueco se explica en vez de
        dejar la tarjeta a medias.
        """
        puntos = score.puntuar(entrada.scores, entrada.threads)
        if puntos is None:
            self.score_card.hide()
            return
        un_hilo, multi = puntos
        self.score_value.setText(_("bench.score.value").format(n=f"{multi:n}"))
        self.score_detail.setText(_("bench.score.single").format(
            n=f"{un_hilo:n}", cpu=entrada.cpu, hilos=entrada.threads))

        # Compararse con otros equipos pide la duración canónica; compararse
        # consigo mismo, no. Son dos preguntas y se contestan por separado.
        if not score.comparable(entrada.seconds):
            self.score_bar.set_comparacion(None)
            self.score_range.setText(_("bench.score.onlyown").format(
                s=f"{score.SEGUNDOS_CANONICOS:.0f}"))
            self.score_card.show()
            return

        comparacion = score.comparar(entrada.cpu, multi)
        self.score_bar.set_comparacion(comparacion)
        if comparacion is None:
            self.score_range.setText(_("bench.score.alone"))
        else:
            clave = ("bench.score.normal" if comparacion.normal
                     else "bench.score.above" if comparacion.desvio > 0
                     else "bench.score.below")
            self.score_range.setText(
                _(clave).format(pct=f"{abs(comparacion.desvio) * 100:.0f}",
                                min=f"{comparacion.minimo:n}",
                                max=f"{comparacion.maximo:n}",
                                n=comparacion.muestras))
        self.score_card.show()

    def _pintar_historial(self, entradas, actual=None) -> None:
        if not entradas:
            self.history_card.hide()
            return
        self._pintar_filas(entradas)
        # Trece filas repitiendo «otra escala» son ruido; el motivo es el
        # mismo para todas y se dice una vez.
        viejas = sum(1 for e in entradas if e.score_version != score.VERSION)
        self.history_note.setText(
            _("bench.history.oldscale").format(n=viejas) if viejas else "")
        self.history_note.setVisible(bool(viejas))
        self.history_card.show()

        if actual is not None:
            comparacion = history.comparar(actual, entradas)
            if comparacion is not None:
                otra, cambio = comparacion
                signo = "+" if cambio >= 0 else ""
                self.history_card.set_title(
                    _("bench.compare.title").format(
                        signo=signo, pct=f"{cambio:.1f}", fecha=otra.when))
            self._avisar_de_la_deriva(actual, entradas)

    def _avisar_de_la_deriva(self, actual, entradas) -> None:
        """Lo que delata pasta seca o polvo: el mismo trabajo, más caliente.

        La puntuación aguanta mientras el ventilador compensa, así que subir
        de grados haciendo lo mismo se nota antes que bajar de cifra.
        """
        deriva = history.deriva_termica(actual, entradas)
        if deriva is None:
            self.deriva_hint.hide()
            return
        grados, cuantas = deriva
        pruebas = _("bench.runs.one" if cuantas == 1 else "bench.runs.many")
        clave = "bench.drift.hotter" if grados > 0 else "bench.drift.cooler"
        texto = _(clave).format(grados=f"{abs(grados):.0f}", n=cuantas,
                                pruebas=pruebas)
        self.deriva_hint.setText(texto)
        self.deriva_hint.show()

    def _show(self, resultado: benchmark.Result) -> None:
        d = render.DASH
        hilos = max((m.threads for m in resultado.measures), default=1)

        filas = []
        for carga in benchmark.CARGAS:
            uno = resultado.find(carga.key, 1)
            todos = resultado.find(carga.key, hilos)
            escala = resultado.scaling(carga.key, hilos)
            filas.append((
                carga.name,
                f"{uno.per_second:.0f} op/s" if uno else d,
                f"{todos.per_second:.0f} op/s" if todos else d,
                f"×{escala}" if escala else d,
            ))
        self.results.set_rows(filas)
        self.results_card.show()
        self.columns.show()

        c = resultado.conditions
        f = self.conditions.set
        f(_("bench.col.avgfreq"), render.hz(c.frequency_avg_hz))
        f(_("bench.cond.maxfreq"), render.hz(c.frequency_peak_hz))
        f(_("bench.cond.endfreq"), render.hz(c.frequency_end_hz),
          tooltip=_("bench.cond.endfreq.tip"))
        f(_("bench.cond.starttemp"), render.temperature(c.temperature_start_c,
                                                       self._prefs.fahrenheit))
        f(_("bench.cond.maxtemp"), render.temperature(c.temperature_peak_c,
                                                   self._prefs.fahrenheit))
        f(_("bench.cond.governor"), c.governor or d)
        f(_("bench.cond.epp"), c.energy_preference or d)
        # Las dos, y por separado. La de arriba se toma antes de empezar y la
        # otra vigila durante los dos minutos y medio que dura la prueba, así
        # que decían cosas distintas del mismo equipo: la ficha ponía «2.9 %»
        # al lado de un aviso que hablaba de un 60 %, y eso se lee como una
        # contradicción aunque las dos cifras sean ciertas. Van con la misma
        # forma que la temperatura, que ya tenía este problema resuelto.
        f(_("bench.cond.load"), render.percent(c.background_load),
          tooltip=_("bench.cond.load.tip"))
        f(_("bench.cond.maxload"), render.percent(c.background_peak),
          tooltip=_("bench.cond.maxload.tip"))

        clear_layout(self._warnings_host)
        for aviso in resultado.warnings:
            self._warnings_host.addWidget(
                Notice(_("bench.notice.compare"), aviso))

    def apply(self, snapshot) -> None:
        """La página no depende del muestreo, salvo para saber qué CPU es.

        El historial guarda contra qué procesador se midió: comparar la
        puntuación de este equipo con la de otro no significa nada, y en un
        portátil que cambia de dueño o en un banco de pruebas ese dato evita
        poner dos equipos en la misma tabla.
        """
        if snapshot.cpu.types:
            self._cpu_actual = render.cpu_short_name(snapshot.cpu.types[0].brand)

    def stop(self) -> None:
        self._parar.set()
