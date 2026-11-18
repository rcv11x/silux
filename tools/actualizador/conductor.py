"""Conduce el actualizador de verdad, dentro del Python del AppImage, sin clics.

Se ejecuta con el entorno de su AppRun, `APPIMAGE` apuntando a la copia que se
va a sustituir, y la red por el GitHub falso (mitmproxy).
"""
import os
import sys
import time

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QMessageBox

from silux import desktop, updates
from silux.ui import app as appmod

dialogos = []


def responder(tipo, valor):
    def falso(parent, titulo, texto, *args, **kwargs):
        dialogos.append((tipo, titulo, texto))
        print(f"DIÁLOGO {tipo}: {titulo} | {texto}", flush=True)
        return valor
    return staticmethod(falso)


QMessageBox.question = responder("pregunta", QMessageBox.StandardButton.Yes)
QMessageBox.warning = responder("aviso", QMessageBox.StandardButton.Ok)
QMessageBox.information = responder("información", QMessageBox.StandardButton.Ok)

app, ventana, _args = appmod.build_app([])
ventana.show()
desktop.install()
print("estado de la entrada antes:", desktop.status().state, desktop.status().target, flush=True)


def esperar(segundos=60):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        app.processEvents()
        tarea = getattr(ventana, "_tarea_de_red", None)
        if tarea is None or tarea.isFinished():
            for _vez in range(5):
                app.processEvents()
            return
        time.sleep(0.05)
    print("SE ACABÓ EL TIEMPO", flush=True)


ventana.settings_page.update_now.click()
esperar()
print("Ajustes dice:", ventana.settings_page.update_status.text(), flush=True)
print("botón:", "visible" if not ventana.update_button.isHidden() else "escondido",
      ventana.update_button.text(), flush=True)
print("sustituible:", updates.replaceable_path(), flush=True)
ventana.update_button.click()
esperar(120)
print("estado de la entrada después:", desktop.status().state, desktop.status().target, flush=True)
print("FIN SIN REINICIAR", flush=True)
os._exit(0)
