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
from PySide6.QtWidgets import (QComboBox,QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from ... import benchmark, history, render
from ...settings import Preferences
from .. import theme
from ..theme import Palette
from ..widgets import Card, InfoGrid, Notice, ResponsiveRow, Table, clear_layout

RESULT_HEADERS = ("Carga", "Un hilo", "Todos los hilos", "Escala")
HISTORY_HEADERS = ("Cuándo", "Puntuación", "Frecuencia media", "Temp. máxima")
CONDITION_FIELDS = ("Frecuencia media", "Frecuencia máxima", "Frecuencia al final",
                    "Temperatura al empezar", "Temperatura máxima",
                    "Gobernador", "Preferencia de energía", "Carga de fondo")


# Lo que se puede pedir, y para qué sirve cada uno.
DURACIONES = (
    ("3 s · rápida", 3.0),
    ("5 s · normal", 5.0),
    ("15 s · sostenida", 15.0),
    ("30 s · con el equipo caliente", 30.0),
    ("2 min · resistencia", 120.0),
    ("5 min · estabilidad", 300.0),
    ("Otra duración…", None),
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

        self.results_card = Card("Resultados")
        self.results = Table(RESULT_HEADERS, numeric=(False, True, True, True))
        self.results_card.body.addWidget(self.results)
        self.results_card.hide()
        self._layout.addWidget(self.results_card)

        fila = ResponsiveRow(min_item_width=300)
        self.conditions_card = Card("Condiciones de la medida")
        self.conditions = InfoGrid()
        for campo in CONDITION_FIELDS:
            self.conditions.add(campo)
        self.conditions_card.body.addWidget(self.conditions)
        fila.add(self.conditions_card)
        self.explain_card = self._build_explanation()
        fila.add(self.explain_card)
        self.columns = fila
        self.columns.hide()
        self._layout.addWidget(fila)

        self.history_card = Card("Pruebas anteriores de este equipo")
        self.history = Table(HISTORY_HEADERS, numeric=(False, True, True, True))
        self.history_card.body.addWidget(self.history)
        nota = QLabel(
            "Solo de este equipo y solo en el disco: no se envía a ninguna "
            "parte. Comparar con cifras de internet casi nunca sirve, porque "
            "están medidas con otro gobernador y otra temperatura; compararse "
            "con uno mismo sí dice si algo ha cambiado.")
        nota.setObjectName("Muted")
        nota.setWordWrap(True)
        self.history_card.body.addWidget(nota)

        acciones = QHBoxLayout()
        self.open_folder = QPushButton("Abrir la carpeta")
        self.open_folder.setToolTip(str(history.history_path()))
        self.open_folder.clicked.connect(self._abrir_carpeta)
        self.clear_history = QPushButton("Borrar el historial")
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
        titulo = QLabel("Prueba de rendimiento")
        titulo.setObjectName("Headline")
        subtitulo = QLabel(
            "Mide el procesador con cinco cargas distintas, primero en un solo "
            "hilo y después en todos. Lo interesante no es solo la cifra: es "
            "que cada carga escala de una forma, y ahí se ve qué aprovecha los "
            "hilos y qué se queda esperando a la memoria. Mientras dura, el "
            "equipo irá al máximo."
        )
        subtitulo.setObjectName("Subhead")
        subtitulo.setWordWrap(True)

        self.run_button = QPushButton("Ejecutar la prueba")
        self.run_button.clicked.connect(lambda: self._start(quick=False))
        self.quick_button = QPushButton("Prueba rápida")
        self.quick_button.setToolTip(
            "Ocho segundos en vez de veinte. Suficiente para hacerse una idea, "
            "pero con menos margen para que el turbo se estabilice."
        )
        self.quick_button.clicked.connect(lambda: self._start(quick=True))

        # Alargar la prueba no cambia la cifra: cambia en qué condiciones se
        # toma. A los cinco segundos el turbo ya subió y el disipador aún está
        # frío; a los treinta se mide con el equipo asentado, que es lo que de
        # verdad pasa mientras se juega o se compila.
        self.duracion = QComboBox()
        for etiqueta, segundos in DURACIONES:
            self.duracion.addItem(etiqueta, segundos)
        self.duracion.setCurrentIndex(1)
        self.duracion.activated.connect(self._quizas_preguntar_duracion)
        self._duracion_libre: float | None = None
        self.duracion.setToolTip(
            "Cuánto dura cada una de las diez medidas: cinco cargas, en un "
            "hilo y en todos. La prueba entera tarda diez veces esto.\n\n"
            "Las largas no dan más puntuación: dan la que se sostiene cuando "
            "el equipo ya está caliente.")

        # Con diez medidas y la duración a elegir, la prueba puede irse a
        # horas. Poder pararla no es un extra: es lo que hace que probar una
        # duración larga no dé miedo.
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.clicked.connect(self._cancelar)
        self.cancel_button.hide()

        fila = QHBoxLayout()
        fila.addWidget(self.run_button)
        fila.addWidget(self.quick_button)
        fila.addWidget(self.cancel_button)
        fila.addSpacing(12)
        fila.addWidget(QLabel("Cada medida:"))
        fila.addWidget(self.duracion)
        fila.addStretch(1)

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
        card = Card("Qué se mide")
        for carga in benchmark.CARGAS:
            etiqueta = QLabel(f"<b>{carga.name}</b><br>{carga.explanation}")
            etiqueta.setObjectName("Muted")
            etiqueta.setWordWrap(True)
            card.body.addWidget(etiqueta)
        nota = QLabel(
            "<b>La escala</b><br>Cuánto multiplica el rendimiento al usar todos "
            "los hilos. Nunca llega al número de hilos: los que comparten núcleo "
            "se reparten las mismas unidades de cálculo."
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
        self.progress.setFormat("preparando…")
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
            self, "Otra duración",
            "Cuántos minutos dura cada una de las diez medidas.\n\n"
            "La prueba entera tarda diez veces esto.",
            value=(self._duracion_libre or 600.0) / 60.0,
            minValue=benchmark.MINIMO_SEGUNDOS / 60.0,
            maxValue=benchmark.MAXIMO_SEGUNDOS / 60.0, decimals=1)
        if not aceptado:
            self.duracion.setCurrentIndex(1)
            self._duracion_libre = None
            return
        self._duracion_libre = minutos * 60.0
        total = minutos * len(benchmark.CARGAS) * 2
        self.duracion.setItemText(
            indice, f"{minutos:g} min cada una · {total:g} min en total")

    def _cancelar(self) -> None:
        """Para la prueba en cuanto termine la medida que esté en curso."""
        self._parar.set()
        self.cancel_button.setEnabled(False)
        self.progress.setFormat("cancelando…")

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
            self, "Borrar el historial",
            f"Se van a borrar {cuantas} "
            f"{render.plural(cuantas, 'prueba guardada', 'pruebas guardadas')} "
            f"de este equipo.\n\nNo se puede deshacer.",
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

    def _pintar_historial(self, entradas, actual=None) -> None:
        if not entradas:
            self.history_card.hide()
            return
        filas = []
        for e in entradas:
            total = e.total()
            filas.append([
                e.when,
                f"{total:.0f}" if total else render.DASH,
                render.hz(e.frequency_avg_hz),
                render.temperature(e.temperature_peak_c, self._prefs.fahrenheit),
            ])
        self.history.set_rows(filas)
        self.history_card.show()

        if actual is not None:
            comparacion = history.comparar(actual, entradas)
            if comparacion is not None:
                otra, cambio = comparacion
                signo = "+" if cambio >= 0 else ""
                self.history_card.set_title(
                    f"Pruebas anteriores de este equipo   ·   "
                    f"{signo}{cambio:.1f} % frente a la del {otra.when}")

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
        f("Frecuencia media", render.hz(c.frequency_avg_hz))
        f("Frecuencia máxima", render.hz(c.frequency_peak_hz))
        f("Frecuencia al final", render.hz(c.frequency_end_hz),
          tooltip="La media del último tramo. Si es bastante menor que la "
                  "máxima, el procesador no aguantó su tope durante la prueba.")
        f("Temperatura al empezar", render.temperature(c.temperature_start_c,
                                                       self._prefs.fahrenheit))
        f("Temperatura máxima", render.temperature(c.temperature_peak_c,
                                                   self._prefs.fahrenheit))
        f("Gobernador", c.governor or d)
        f("Preferencia de energía", c.energy_preference or d)
        f("Carga de fondo", render.percent(c.background_load),
          tooltip="Lo que estaba ocupando la máquina justo antes de empezar. "
                  "Con carga de fondo el resultado no se puede comparar.")

        clear_layout(self._warnings_host)
        for aviso in resultado.warnings:
            self._warnings_host.addWidget(
                Notice("Antes de comparar esta cifra", aviso))

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
