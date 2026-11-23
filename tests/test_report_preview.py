"""«View and save the report» in Settings: the full report, seen first.

The button saved the short report, not the full one people are asked to
send, and without showing it. Now it opens a preview of the full report,
asks for the missing permissions right there and refreshes the text when
they arrive (rule 9), and saves exactly what it shows.
"""

import dataclasses
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from silux.i18n import _
from tests import qt
from tests.test_equipos import EQUIPOS, foto

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None

ROOT = pathlib.Path(__file__).resolve().parent.parent


@unittest.skipIf(QApplication is None, "no PySide6")
class TestReportPreview(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = qt.app()
        cls.snapshot = foto(EQUIPOS / "5800x3d")[0]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        patch.start()
        self.addCleanup(patch.stop)
        from silux.settings import Preferences
        from silux.ui.app import MainWindow
        self.window = MainWindow(Preferences().normalized())
        self.addCleanup(self.window.deleteLater)
        self.window.show()
        self.window._on_sample(self.snapshot)

    def open_preview(self):
        self.window.settings_page.report_requested.emit()
        self.app.processEvents()
        dialog = self.window._report_preview
        self.addCleanup(dialog.close)
        # Before the window goes: a QThread destroyed while it runs aborts.
        self.addCleanup(dialog.cancel_annex)
        return dialog

    def wait_for_the_annex(self, dialog):
        import time
        deadline = time.monotonic() + 90
        while dialog.annex_pending() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
        self.assertFalse(dialog.annex_pending())

    def test_it_is_the_full_report(self):
        dialog = self.open_preview()
        self.assertTrue(dialog.isVisible())
        text = dialog.report()
        for heading in ("## CPU", "### Núcleos lógicos", "## Dispositivos"):
            with self.subTest(heading=heading):
                self.assertIn(heading, text)
        # Anonymous, like the one the terminal writes.
        from silux import privacidad
        self.assertIn(privacidad.HOST_NAME, text)

    def test_it_shows_it_formatted_and_saves_the_markdown(self):
        dialog = self.open_preview()
        shown = dialog.text.toPlainText()
        for syntax in ("|---", "**", "## "):
            with self.subTest(syntax=syntax):
                self.assertIn(syntax, dialog.report())
                self.assertNotIn(syntax, shown)

    def test_each_line_stays_on_its_own(self):
        """A card's lines are not joined into a paragraph."""
        dialog = self.open_preview()
        shown = dialog.text.toPlainText()
        raw = dialog.report().splitlines()
        plain = [(a, b) for a, b in zip(raw, raw[1:])
                 if a.strip() and b.strip() and not a.startswith(("|", "#", "-"))
                 and not b.startswith(("|", "#", "-"))]
        self.assertTrue(plain)
        for a, b in plain:
            with self.subTest(line=a):
                self.assertNotIn(f"{a.strip()} {b.strip()}", shown)

    def test_it_opens_with_the_version_as_the_app_says_it_and_no_table(self):
        from silux import __version__, render
        lines = [line for line in self.open_preview().report().splitlines() if line.strip()]
        self.assertTrue(lines[0].startswith(
            f"# Informe de Silux {render.version(__version__)}"))
        self.assertFalse(lines[1].startswith("|"), lines[1])

    def test_new_permissions_keep_the_reader_where_they_were(self):
        dialog = self.open_preview()
        dialog.resize(700, 400)
        self.app.processEvents()
        bar = dialog.text.verticalScrollBar()
        bar.setValue(bar.maximum() // 2)
        granted = dataclasses.replace(
            self.snapshot, notes=tuple(n for n in self.snapshot.notes
                                       if n not in self.snapshot.permission_notes))
        before = bar.value()
        self.window._on_sample(granted)
        self.app.processEvents()
        self.assertGreater(before, 0)
        self.assertEqual(bar.value(), before)

    def test_it_does_not_restyle_the_app_or_show_another_window(self):
        before = self.app.styleSheet()
        visible = {w for w in self.app.topLevelWidgets() if w.isVisible()}
        dialog = self.open_preview()
        self.assertEqual(self.app.styleSheet(), before)
        now = {w for w in self.app.topLevelWidgets() if w.isVisible()}
        self.assertEqual(now - visible, {dialog})

    def test_missing_permissions_are_asked_for_and_the_text_follows(self):
        dialog = self.open_preview()
        self.assertTrue(self.snapshot.permission_notes)
        self.assertTrue(dialog.grant_button.isVisible())
        with mock.patch.object(self.window.sampler, "request_elevation") as ask, \
             mock.patch("silux.privileged.client.PrivilegedClient.installed", return_value=True), \
             mock.patch("silux.privileged.client.PrivilegedClient.up_to_date", return_value=True):
            dialog.grant_button.click()
        ask.assert_called_once()
        granted = dataclasses.replace(
            self.snapshot, notes=tuple(n for n in self.snapshot.notes
                                       if n not in self.snapshot.permission_notes))
        self.window._on_sample(granted)
        self.app.processEvents()
        self.assertFalse(dialog.grant_button.isVisible())

    def test_what_needs_a_second_reading_arrives_too(self):
        # Two testers' reports, made right after «Dar permisos», had «Consumo:
        # —»: the first sample through the helper only takes RAPL's reference,
        # and the preview was rebuilt only when the permissions changed.
        dialog = self.open_preview()
        granted = dataclasses.replace(
            self.snapshot, notes=tuple(n for n in self.snapshot.notes
                                       if n not in self.snapshot.permission_notes))
        self.assertIsNone(granted.cpu.power.package_w)
        self.window._on_sample(granted)
        self.app.processEvents()
        con_consumo = dataclasses.replace(
            granted, notes=tuple(n for n in granted.notes if n.path != "cpu.power"),
            cpu=dataclasses.replace(granted.cpu, power=dataclasses.replace(
                granted.cpu.power, package_w=42.0)))
        self.window._on_sample(con_consumo)
        self.app.processEvents()
        self.assertIn("- Consumo: 42 W", dialog.report())

    def test_it_saves_what_it_shows(self):
        dialog = self.open_preview()
        self.wait_for_the_annex(dialog)
        target = self.tmp / "informe.md"
        with mock.patch("PySide6.QtWidgets.QFileDialog.getSaveFileName",
                        return_value=(str(target), "")), \
             mock.patch("PySide6.QtWidgets.QMessageBox.information"):
            dialog.save_button.click()
        self.assertEqual(target.read_text(encoding="utf-8"), dialog.report())


    # -- the annex: this machine's raw data at the end of the file ----------------

    def test_while_it_is_made_the_preview_says_so_and_saving_waits(self):
        dialog = self.open_preview()
        self.assertTrue(dialog.annex_pending())
        self.assertFalse(dialog.save_button.isEnabled())
        self.assertIn(_("report.annex.preparing"), dialog.text.toPlainText())
        # Also beside the button, wherever the reader is scrolled to.
        self.assertEqual(dialog.annex_status.text(), _("report.annex.preparing"))
        self.assertTrue(dialog.annex_status.isVisible())
        self.assertNotIn("silux-annex", dialog.report())

    def test_once_made_the_preview_says_what_goes_and_the_file_carries_it(self):
        from silux import annex, render
        dialog = self.open_preview()
        self.wait_for_the_annex(dialog)
        self.assertTrue(dialog.save_button.isEnabled())
        block = annex.find(dialog.report())
        files, size = annex.size_of(block)
        shown = dialog.text.toPlainText()
        self.assertIn(_("report.annex.summary").format(files=files, size=render.size(size)), shown)
        self.assertIn(_("report.annex.onsave"), shown)
        # The preview names it; the block itself only goes in the file.
        self.assertNotIn("silux-annex", shown)
        self.assertEqual(dialog.annex_status.text(),
                         _("report.annex.status").format(summary=annex.summary_of(block)))

    def test_with_a_dump_mounted_the_annex_is_that_dumps(self):
        # The report is the mounted dump's, and so is its annex: the dumper
        # reads through sysroot.
        import json

        from silux import annex
        from tests.test_volcar_equipo import _herramienta
        with _herramienta().mounted(EQUIPOS / "qemu-kvm"):
            dialog = self.open_preview()
            self.wait_for_the_annex(dialog)
        block = annex.find(dialog.report())
        for kind, rest, content, current in annex._entries(block):
            if current == "/" and rest == "manifiesto.json":
                manifest = json.loads(annex._file(kind, rest, content)[1])
        self.assertEqual(manifest["cpu"], "QEMU Virtual CPU version 2.5+")

    def test_closing_the_window_stops_it(self):
        dialog = self.open_preview()
        job = dialog._annex_job
        deadline = __import__("time").monotonic() + 10
        while job._proceso is None and __import__("time").monotonic() < deadline:
            self.app.processEvents()
        child = job._proceso
        self.assertIsNotNone(child)
        self.window.close()
        self.assertIsNone(dialog._annex_job)
        self.assertIsNotNone(child.poll())
        self.assertTrue(job.isFinished())


class TestIssueTemplate(unittest.TestCase):

    def test_my_cpu_and_board(self):
        text = (ROOT / ".github" / "ISSUE_TEMPLATE" / "mi-cpu-y-placa.yml").read_text()
        self.assertIn("name: Mi CPU y placa", text)
        self.assertIn("--report informe.md", text)
        self.assertIn(_("settings.report.button"), text)


if __name__ == "__main__":
    unittest.main()
