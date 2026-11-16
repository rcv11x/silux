"""Entre la cabecera de una tabla y su primera fila hay lo mismo que entre filas.

Los títulos de las columnas van en letra pequeña dentro de una celda tan
alta como las de las filas, y el texto se pegaba arriba: entre él y la
primera fila quedaba el resto de la celda más el hueco entre filas, unos
dieciocho píxeles contra siete. Se leía como una fila vacía, en todas las
tablas: discos, módulos, salidas.

La geometría de las celdas no lo delata —las cajas están a la misma
distancia—; lo que se mide es dónde acaba el texto.
"""

import unittest

from tests import qt

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "sin PySide6")
class TestElHuecoDeLaCabecera(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _tabla(self, filas):
        from silux.ui import theme
        from silux.ui.widgets import Table

        theme.set_density("normal", "normal")
        self.caja = QWidget()
        layout = QVBoxLayout(self.caja)
        tabla = Table(["Unidad", "Modelo", "Capacidad"], numeric=(False, False, True))
        layout.addWidget(tabla)
        layout.addStretch(1)
        self.caja.resize(700, 400)
        self.caja.show()
        self.addCleanup(self.caja.close)
        tabla.set_rows(filas)
        for _vez in range(5):
            self.app.processEvents()
        return tabla

    def _huecos(self, tabla):
        interior = tabla.widget()
        cabecera = [w for w in interior.findChildren(QLabel)
                    if w.objectName() == "ColumnTitle"][0]
        # Dónde acaba el texto dentro de su celda, según cómo se alinee.
        arriba = cabecera.mapTo(interior, QPoint(0, 0)).y()
        alto_texto = cabecera.fontMetrics().height()
        if cabecera.alignment() & Qt.AlignmentFlag.AlignBottom:
            fin_cabecera = arriba + cabecera.height()
        elif cabecera.alignment() & Qt.AlignmentFlag.AlignVCenter:
            fin_cabecera = arriba + (cabecera.height() + alto_texto) // 2
        else:
            fin_cabecera = arriba + alto_texto
        filas = [(fila[0].mapTo(interior, QPoint(0, 0)).y(), fila[0].height())
                 for fila in tabla._cells]
        tras_cabecera = filas[0][0] - fin_cabecera
        entre_filas = [filas[i + 1][0] - (filas[i][0] + filas[i][1])
                       for i in range(len(filas) - 1)]
        return tras_cabecera, entre_filas

    def test_la_primera_fila_no_se_aleja_de_la_cabecera(self):
        tabla = self._tabla([("nvme0n1", "WD_BLACK SN850X", "931.5 GB"),
                             ("nvme1n1", "Samsung SSD 970 EVO Plus", "1.8 TB"),
                             ("sda", "ST2000DM008", "1.8 TB")])
        tras_cabecera, entre_filas = self._huecos(tabla)
        self.assertLessEqual(tras_cabecera, max(entre_filas) + 2,
                             f"{tras_cabecera} px tras la cabecera y {entre_filas} entre filas")

    def test_y_al_cambiar_el_numero_de_filas_tampoco(self):
        tabla = self._tabla([("sda", "ST2000DM008", "1.8 TB"), ("sdb", "ST4000DM004", "3.6 TB")])
        tabla.set_rows([("a", "b", "c")] * 5)
        for _vez in range(5):
            self.app.processEvents()
        tras_cabecera, entre_filas = self._huecos(tabla)
        self.assertLessEqual(tras_cabecera, max(entre_filas) + 2)


if __name__ == "__main__":
    unittest.main()
