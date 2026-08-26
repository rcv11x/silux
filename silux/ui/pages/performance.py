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
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from ... import benchmark, render
from ...settings import Preferences
from .. import theme
from ..theme import Palette
from ..widgets import Card, InfoGrid, Notice, ResponsiveRow, Table, clear_layout

RESULT_HEADERS = ("Carga", "Un hilo", "Todos los hilos", "Escala")
CONDITION_FIELDS = ("Frecuencia media", "Frecuencia máxima", "Frecuencia al final",
                    "Temperatura al empezar", "Temperatura máxima",
                    "Gobernador", "Preferencia de energía", "Carga de fondo")


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

        self._warnings_host = QVBoxLayout()
        self._warnings_host.setSpacing(6)
        self._layout.addLayout(self._warnings_host)
        self._layout.addStretch(1)

        self._finished.connect(self._on_finished)
        self._progressed.connect(self._on_progress)

    # -- construcción -------------------------------------------------------

    def _build_header(self) -> Card:
        card = Card()
        titulo = QLabel("Prueba de rendimiento")
        titulo.setObjectName("Headline")
        subtitulo = QLabel(
            "Mide el procesador con dos cargas distintas, primero en un solo "
            "hilo y después en todos. Tarda unos veinte segundos y durante ese "
            "rato el equipo irá al máximo."
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

        fila = QHBoxLayout()
        fila.addWidget(self.run_button)
        fila.addWidget(self.quick_button)
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
        self.run_button.setEnabled(False)
        self.quick_button.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setFormat("preparando…")
        self.progress.show()
        clear_layout(self._warnings_host)

        def trabajo() -> None:
            resultado = benchmark.run(
                quick=quick,
                on_progress=lambda que, cuanto: self._progressed.emit(que, cuanto),
                stop=self._parar,
            )
            self._finished.emit(resultado)

        self._hilo = threading.Thread(target=trabajo, daemon=True)
        self._hilo.start()

    def _on_progress(self, que: str, cuanto: float) -> None:
        self.progress.setValue(int(cuanto * 100))
        self.progress.setFormat(f"{que}  ·  %p %")

    def _on_finished(self, resultado: benchmark.Result) -> None:
        self._resultado = resultado
        self.run_button.setEnabled(True)
        self.quick_button.setEnabled(True)
        self.progress.hide()
        self._show(resultado)

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
        """La página no depende del muestreo: solo del último resultado."""

    def stop(self) -> None:
        self._parar.set()
