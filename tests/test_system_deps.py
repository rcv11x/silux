"""What Silux uses from the system, its packages, and the note when it is missing.

The package names were asked to Debian 13, Ubuntu 24.04, Fedora 45 and Arch
(`system_deps`); docs/dependencias.md says the same. A missing piece this
machine needs is said in Diagnóstico and on its page, with the package of
this distribution. The dumps record whether each piece was there; one that
did not record it says nothing.
"""

import json
import pathlib
import re
import tempfile
import unittest
from unittest import mock

from silux import system_deps, volcado
from silux.collector import Collector
from silux.i18n import _
from silux.model import Need
from tests import pantalla, qt

ROOT = pathlib.Path(__file__).resolve().parent.parent
EQUIPOS = ROOT / "tests" / "fixtures" / "equipos"
DOCS = ROOT / "docs" / "dependencias.md"


def _photo(dump: str, presentes: dict):
    """The dump mounted with what it recorded of these pieces."""
    with volcado.montado(EQUIPOS / dump) as root:
        grabado = json.loads((root / "grabado.json").read_text())
        grabado["paquetes"] = presentes
        (root / "grabado.json").write_text(json.dumps(grabado))
        collector = Collector()
        try:
            return collector.snapshot()
        finally:
            collector.close()


def _package_notes(photo):
    return {n.path: n for n in photo.notes if n.need is Need.PACKAGE}


class TestTheTable(unittest.TestCase):

    def test_every_piece_has_a_package_in_every_family(self):
        for dep in system_deps.DEPENDENCIES:
            with self.subTest(dep=dep.key):
                self.assertEqual(set(dep.packages), set(system_deps.FAMILIES))
                # None only where that family has no package with it.
                self.assertTrue(all(p is None or p.strip() for p in dep.packages.values()))

    def test_the_docs_say_the_same(self):
        texto = DOCS.read_text(encoding="utf-8")
        filas = [l for l in texto.splitlines() if l.startswith("| ")]
        for dep in system_deps.DEPENDENCIES:
            with self.subTest(dep=dep.key):
                fila = next((l for l in filas
                             if any(f"`{n.rsplit('/', 1)[-1]}`" in l for n in dep.names)
                             or f"`{dep.key}`" in l), None)
                self.assertIsNotNone(fila, f"{dep.key} is not in docs/dependencias.md")
                celdas = [c.strip() for c in fila.strip("|").split("|")]
                for fam in system_deps.FAMILIES:
                    if dep.packages[fam] is None:
                        self.assertTrue(any(c.startswith("—") for c in celdas), f"{dep.key} in {fam}")
                        continue
                    paquete = dep.packages[fam].replace("{nvidia}", "NNN")
                    self.assertTrue(any(c.startswith(f"`{paquete}`") for c in celdas),
                                    f"{dep.key} in {fam}: {celdas}")

    def test_both_readmes_point_to_them(self):
        for readme in ("README.md", "README.en.md"):
            self.assertIn("(docs/dependencias.md)", (ROOT / readme).read_text(encoding="utf-8"))


class TestTheFamily(unittest.TestCase):

    def test_by_id_and_id_like(self):
        casos = {
            ("ubuntu", "debian"): "ubuntu", ("linuxmint", "ubuntu debian"): "ubuntu",
            ("debian", ""): "debian", ("fedora", ""): "fedora",
            ("rocky", "rhel centos fedora"): "fedora", ("cachyos", "arch"): "arch",
            ("manjaro", "arch"): "arch", ("gentoo", ""): None,
        }
        for (ident, like), familia in casos.items():
            with self.subTest(ident=ident):
                self.assertEqual(system_deps.family({"ID": ident, "ID_LIKE": like}), familia)

    def test_gentoos_single_quotes(self):
        with volcado.montado(EQUIPOS / "i7-10700f"):
            self.assertEqual(system_deps.read_os_release()["ID"], "gentoo")


class TestTheLoaderCache(unittest.TestCase):
    """ldconfig shares strings: a soname is usually the tail of its path."""

    def test_a_name_inside_its_path_counts(self):
        with tempfile.NamedTemporaryFile() as cache:
            cache.write(b"glibc-ld.so.cache1.1\x00/usr/lib/libvulkan.so.1\x00libz.so.1\x00")
            cache.flush()
            with mock.patch.object(system_deps, "LD_CACHE", cache.name):
                self.assertTrue(system_deps._in_loader_cache("libvulkan.so.1"))
                self.assertTrue(system_deps._in_loader_cache("libz.so.1"))
                self.assertFalse(system_deps._in_loader_cache("libOpenCL.so.1"))


class TestTheNotes(unittest.TestCase):

    def test_a_dump_that_did_not_record_it_says_nothing(self):
        for dump in ("i5-10400", "5800x3d", "i7-10700f"):
            with self.subTest(dump=dump):
                self.assertEqual(_package_notes(_photo(dump, {})), {})

    def test_pci_ids_on_fedora(self):
        notas = _package_notes(_photo("i5-10400", {"pci.ids": False}))
        self.assertEqual(notas["board.packages.pciids"].message, _("deps.pciids"))
        self.assertEqual(notas["board.packages.pciids"].hint,
                         _("deps.hint").format(paquete="hwdata"))

    def test_the_graphics_libraries_in_one_note(self):
        notas = _package_notes(_photo("i5-10400", {"vulkan": False, "opencl": False,
                                                   "egl": True, "opengl": True, "vaapi": True}))
        nota = notas["gpus.packages.apis"]
        self.assertEqual(nota.message, _("deps.graphics").format(cuales="Vulkan, OpenCL"))
        self.assertEqual(nota.hint, _("deps.hint.many").format(paquetes="vulkan-loader y ocl-icd"))

    def test_nvml_on_gentoo_names_every_family_and_replaces_the_drivers_note(self):
        photo = _photo("i7-10700f", {"nvml": False})
        nota = _package_notes(photo)["gpus.packages.nvml"]
        self.assertEqual(nota.message, _("deps.nvml"))
        self.assertEqual(nota.hint, _("deps.hint.any").format(paquete=(
            "libnvidia-ml1 (Debian), libnvidia-compute-NNN (Ubuntu), "
            "xorg-x11-drv-nvidia-cuda-libs (Fedora), nvidia-utils (Arch)")))
        self.assertFalse([n for n in photo.notes if n.message == _("prov.drm.nvidia")])

    def test_on_the_graphics_page(self):
        qt.app()
        photo = _photo("i5-10400", {"vulkan": False})
        with pantalla.Ventana(photo) as ventana:
            ventana.select_section("Gráficos")
            textos = pantalla.textos_de(ventana.graphics_page)
        self.assertIn(_("note.package"), textos)
        self.assertIn(_("deps.graphics").format(cuales="Vulkan"), textos)


if __name__ == "__main__":
    unittest.main()
