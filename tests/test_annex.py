"""The report's annex: a dump written as text and read back the same."""

import os
import pathlib
import tempfile
import unittest

from silux import annex

EQUIPOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "equipos"


def tree(folder: pathlib.Path) -> dict:
    """Every path of a folder with what it is: its bytes, its link or empty."""
    found = {}
    for path in folder.rglob("*"):
        name = path.relative_to(folder).as_posix()
        if path.is_symlink():
            found[name] = ("link", os.readlink(path))
        elif path.is_dir():
            if not any(path.iterdir()):
                found[name] = ("dir",)
        else:
            found[name] = ("file", path.read_bytes())
    return found


class TestTheDumpsGoAndComeBack(unittest.TestCase):

    def test_every_dump_in_the_suite(self):
        dumps = sorted(p for p in EQUIPOS.iterdir() if (p / "manifiesto.json").is_file())
        self.assertGreaterEqual(len(dumps), 4)
        for dump in dumps:
            with self.subTest(dump=dump.name), tempfile.TemporaryDirectory() as tmp:
                block = annex.to_text(dump)
                annex.to_folder(block, pathlib.Path(tmp) / "back")
                self.assertEqual(tree(pathlib.Path(tmp) / "back"), tree(dump))
                files = sum(1 for kind, *_ in tree(dump).values() if kind == "file")
                self.assertEqual(annex.size_of(block)[0], files)

    def test_what_the_manifest_says_comes_first(self):
        first = annex.to_text(EQUIPOS / "qemu-kvm").splitlines()[:4]
        self.assertEqual(first, ["silux-annex 1", "in /", "file grabado.json", "| {"])


class TestOddFiles(unittest.TestCase):
    """What a dump can hold and a line of text cannot say as it is."""

    CASES = {
        "one_line": b"3400000\n",
        "empty": b"",
        "just_a_break": b"\n",
        "no_break_at_the_end": b"auto",
        "blank_lines": b"a\n\n\nb\n",
        "trailing_blanks": b"AMD Ryzen 7 5800X3D 8-Core Processor   \nx\t\n",
        "tabs": b"processor\t: 0\nmodel\t\t: 33\n",
        "control": b"bell\x07 here\n",
        "binary": bytes(range(256)) + b"\x00\x01",
        "carriage_return": b"dos\r\n",
        "with = in it": b"value\n",
        "equals": b"key = value\n",
        "quote": b'"quoted"\n',
        "pipe": b"| a pipe\n|\n",
        "latin": "Núcleo · 2,5 GHz\n".encode(),
    }

    def _back(self, mangle=lambda text: text) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / "source"
            (source / "sys/x").mkdir(parents=True)
            for name, data in self.CASES.items():
                (source / "sys/x" / name).write_bytes(data)
            (source / "proc/1").mkdir(parents=True)
            (source / "proc/mounts").symlink_to("self/mounts")
            block = mangle(annex.to_text(source))
            annex.to_folder(block, pathlib.Path(tmp) / "back")
            return tree(source), tree(pathlib.Path(tmp) / "back")

    def test_each_comes_back_byte_for_byte(self):
        source, back = self._back()
        self.assertEqual(back, source)

    def test_no_control_character_reaches_the_report(self):
        # Whoever reviews a report in a terminal would have them run: an
        # escape sequence in a sysfs file is someone else's text on screen.
        with tempfile.TemporaryDirectory() as tmp:
            for name, data in self.CASES.items():
                (pathlib.Path(tmp) / name).write_bytes(data)
            text = annex.to_text(pathlib.Path(tmp))
        self.assertEqual([c for c in text if ord(c) < 0x20 and c not in "\t\n" or c == "\x7f"], [])

    def test_and_after_an_editor_trims_the_lines(self):
        source, back = self._back(lambda text: "\n".join(l.rstrip() for l in text.split("\n")))
        self.assertEqual(back, source)


class TestWhatItWillNotWrite(unittest.TestCase):
    """A report comes from someone else: reading it writes nothing outside
    the folder, nor through a link."""

    def _write(self, block: str) -> pathlib.Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = pathlib.Path(tmp.name)
        with self.assertRaises(annex.AnnexError):
            annex.to_folder(block, base / "dump" / "back")
        return base

    def test_paths_and_links_that_leave(self):
        for block in ("silux-annex 1\nin /../..\nfile x = 1\n",
                      "silux-annex 1\nin /sys\nfile .. = 1\n",
                      "silux-annex 1\nin /sys\nfile a/../../x = 1\n",
                      "silux-annex 1\nin sys\nfile x = 1\n",
                      "silux-annex 1\nfile x = 1\n",
                      "silux-annex 1\nin /sys\nlink x -> /etc/passwd\n",
                      "silux-annex 1\nin /sys\nlink x -> ../../../escape\n"):
            with self.subTest(block=block):
                base = self._write(block)
                self.assertEqual([p.name for p in base.rglob("*") if not p.is_dir()], [])

    def test_a_file_written_through_a_link_is_not(self):
        # The link goes last: when it is made, «a» already is a folder.
        block = ("silux-annex 1\nin /sys\nlink a -> ../outside\n"
                 "in /sys/a\nfile x = 1\n")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises((annex.AnnexError, FileExistsError)):
                annex.to_folder(block, pathlib.Path(tmp) / "back")
            self.assertFalse((pathlib.Path(tmp) / "outside").exists())

    def test_another_version_or_a_broken_block(self):
        for block in ("silux-annex 2\n", "nothing here\n", "silux-annex 1\nin /\nsocket x\n",
                      "silux-annex 1\nin /\nbinary x\n| 00000010  00\n",
                      "silux-annex 1\nin /\nfile x\n|\"unclosed\n"):
            with self.subTest(block=block):
                self._write(block)


class TestInTheReport(unittest.TestCase):

    def test_found_between_its_fences(self):
        block = annex.to_text(EQUIPOS / "qemu-kvm")
        report = f"# Informe\n\nAlgo.\n\n<details>\n\n```text\n{block}```\n\n</details>\n"
        self.assertEqual(annex.find(report), block)

    def test_a_report_without_one(self):
        with self.assertRaises(annex.AnnexError):
            annex.find("# Informe\n\n```\nsilux-annex 1 en una frase\n")



def _report_with(block: str) -> str:
    return ("# Informe de Silux\n\nLo de siempre.\n\n## Anexo: los datos en crudo\n\n"
            f"<details>\n<summary>…</summary>\n\n```text\n{block}```\n\n</details>\n")


class TestImportingAReport(unittest.TestCase):
    """`tools/importar_informe.py`: from someone's report to a dump of the suite."""

    def setUp(self):
        import sys
        sys.path.insert(0, str(EQUIPOS.parent.parent.parent))
        from tools import importar_informe
        self.tool = importar_informe
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = pathlib.Path(tmp.name)

    def _report(self, block: str) -> pathlib.Path:
        path = self.base / "informe.md"
        path.write_text(_report_with(block), encoding="utf-8")
        return path

    def test_the_dump_and_what_it_shows(self):
        dump = EQUIPOS / "qemu-kvm"
        target, photo = self.tool.import_report(
            self._report(annex.to_text(dump)), "otra-vm", self.base / "equipos")
        self.assertEqual(tree(target), tree(dump))
        self.assertEqual(photo.cpu.types[0].brand, "QEMU Virtual CPU version 2.5+")

    def test_a_serial_left_in_it_leaves_nothing(self):
        block = (annex.to_text(EQUIPOS / "qemu-kvm")
                 + "in /sys/devices/virtual/dmi/id\nfile board_serial = S4EWNX0M123456\n")
        with self.assertRaises(SystemExit) as caught:
            self.tool.import_report(self._report(block), "otra-vm", self.base / "equipos")
        self.assertIn("board_serial", str(caught.exception))
        self.assertNotIn("S4EWNX0M123456", str(caught.exception))
        self.assertFalse((self.base / "equipos").exists())

    def test_without_an_annex_or_a_manifest(self):
        for block in ("", "silux-annex 1\nin /proc\nfile version = Linux\n"):
            with self.subTest(block=block[:20]), self.assertRaises(SystemExit):
                path = self.base / "informe.md"
                path.write_text(_report_with(block) if block else "# Informe\n", encoding="utf-8")
                self.tool.import_report(path, "nada", self.base / "equipos")
        self.assertFalse((self.base / "equipos").exists())


class TestThisMachine(unittest.TestCase):
    """The annex of the machine running the suite, made as the report makes it."""

    def test_it_is_this_machine_read_back(self):
        from silux import volcado
        from silux.collector import Collector

        block, reason = annex.of_this_machine()
        self.assertIsNone(reason)
        with tempfile.TemporaryDirectory() as tmp:
            annex.to_folder(block, pathlib.Path(tmp) / "back")
            photo = volcado.foto_de(pathlib.Path(tmp) / "back")
        live = Collector().snapshot()
        self.assertEqual([t.brand for t in photo.cpu.types], [t.brand for t in live.cpu.types])
        self.assertEqual(len(photo.cpu.logical), len(live.cpu.logical))


if __name__ == "__main__":
    unittest.main()
