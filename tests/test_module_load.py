"""«Load now»: a kernel module that would give missing data, on the pages
that miss it.

The helper loads it until the next boot and writes nothing; the line that
makes it load at every boot is left to copy. The Super I/O keeps only its
command: each board has a different chip, and the wrong driver reads garbage.
"""

import dataclasses
import unittest
from unittest import mock

from silux.i18n import _
from silux.model import DriverHint
from tests import pantalla, qt
from tests.test_equipos import EQUIPOS, shared_snapshot

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


def _with_spd_hint(snapshot):
    """As `privileged_memory._spd_hint` writes it when the SPD chips are
    registered and spd5118 isn't loaded."""
    hint = DriverHint(module="spd5118", provides=_("prov.hint.spd").format(n=2),
                      command="sudo modprobe spd5118", caution=_("prov.hint.spd.caution"))
    return dataclasses.replace(snapshot, driver_hints=snapshot.driver_hints + (hint,))


def _with_msr_hint(snapshot):
    """As the voltage provider writes it when the helper finds no msr module.
    The helper is running then, so the voltage's permission note isn't there."""
    from silux.providers.base import Draft
    from silux.providers.msr_voltage import missing_msr_module

    draft = Draft()
    missing_msr_module(draft, voltage=True)
    return dataclasses.replace(
        snapshot, driver_hints=snapshot.driver_hints + tuple(draft.driver_hints),
        notes=tuple(n for n in snapshot.notes if n.path != "cpu.voltage_v"))


@unittest.skipIf(QApplication is None, "no PySide6")
class TestTheNotice(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()

    def _settle(self):
        for _turn in range(4):
            self.app.processEvents()

    def _notices(self, window, section):
        from silux.ui.widgets import ModuleNotice

        window.select_section(section)
        self._settle()
        return {n.module: n for n in window.stack.currentWidget().findChildren(ModuleNotice)
                if n.isVisibleTo(window)}

    def test_each_page_shows_its_own(self):
        photo = _with_spd_hint(shared_snapshot(EQUIPOS / "athlon-3000g"))
        with pantalla.Ventana(photo) as window:
            self.assertEqual(set(self._notices(window, "Almacenamiento")), {"drivetemp"})
            self.assertEqual(set(self._notices(window, "Memoria")), {"spd5118"})
            self.assertEqual(set(self._notices(window, "Sensores")),
                             {"drivetemp", "spd5118", "(Super I/O)"})

    def test_load_now_and_the_line_to_copy(self):
        photo = shared_snapshot(EQUIPOS / "5800x3d")
        with pantalla.Ventana(photo) as window:
            notice = self._notices(window, "Almacenamiento")["drivetemp"]
            self.assertEqual(notice.action_button.text(), _("module.load.now"))
            texts = pantalla.textos_de(notice)
            self.assertIn(_("module.load.always"), texts)
            self.assertEqual(notice.command.full_text(),
                             "echo drivetemp | sudo tee /etc/modules-load.d/drivetemp.conf")

    def test_the_super_io_only_has_its_command(self):
        photo = shared_snapshot(EQUIPOS / "athlon-3000g")
        with pantalla.Ventana(photo) as window:
            notice = self._notices(window, "Sensores")["(Super I/O)"]
            self.assertIsNone(notice.action_button)
            self.assertEqual(notice.command.full_text(), "sudo sensors-detect")
            self.assertNotIn(_("module.load.always"), pantalla.textos_de(notice))

    def test_the_click_goes_to_the_sampler_and_every_page_says_so(self):
        photo = shared_snapshot(EQUIPOS / "5800x3d")
        with pantalla.Ventana(photo) as window:
            storage = self._notices(window, "Almacenamiento")["drivetemp"]
            with mock.patch.object(window.sampler, "request_module_load") as asked:
                storage.action_button.click()
            asked.assert_called_once_with("drivetemp")
            sensors = self._notices(window, "Sensores")["drivetemp"]
            for notice in (storage, sensors):
                self.assertFalse(notice.action_button.isEnabled())
                self.assertEqual(notice.action_button.text(), _("module.load.loading"))

    def test_what_comes_back(self):
        photo = shared_snapshot(EQUIPOS / "5800x3d")
        with pantalla.Ventana(photo) as window:
            notice = self._notices(window, "Almacenamiento")["drivetemp"]
            window._on_module_load("drivetemp")

            window._on_module_loaded("drivetemp", "modprobe: FATAL: Module drivetemp not found.")
            self.assertTrue(notice.action_button.isEnabled())
            self.assertFalse(notice.error.isHidden())
            self.assertIn("not found", notice.error.text())

            window._on_module_load("drivetemp")
            window._on_module_loaded("drivetemp", None)          # password cancelled
            self.assertTrue(notice.action_button.isEnabled())
            self.assertTrue(notice.error.isHidden())

            window._on_module_load("drivetemp")
            window._on_module_loaded("drivetemp", "")
            self.assertEqual(notice.action_button.text(), _("module.load.done"))

    def test_msr_goes_with_the_processor_not_the_sensors(self):
        photo = _with_msr_hint(shared_snapshot(EQUIPOS / "i5-10400"))
        with pantalla.Ventana(photo) as window:
            notice = self._notices(window, "CPU")["msr"]
            self.assertNotIn("msr", self._notices(window, "Sensores"))
            self.assertEqual(notice.action_button.text(), _("module.load.now"))
            self.assertIn(_("prov.hint.msr.voltage"), " ".join(pantalla.textos_de(notice)))
            self.assertEqual(notice.command.full_text(),
                             "echo msr | sudo tee /etc/modules-load.d/msr.conf")
            with mock.patch.object(window.sampler, "request_module_load") as asked:
                notice.action_button.click()
            asked.assert_called_once_with("msr")
            self.assertEqual(notice.action_button.text(), _("module.load.loading"))

    def test_once_loaded_the_notice_goes(self):
        photo = shared_snapshot(EQUIPOS / "5800x3d")
        with pantalla.Ventana(photo) as window:
            self.assertTrue(self._notices(window, "Almacenamiento"))
            window._on_sample(dataclasses.replace(photo, driver_hints=()))
            self.assertEqual(self._notices(window, "Almacenamiento"), {})


if __name__ == "__main__":
    unittest.main()
