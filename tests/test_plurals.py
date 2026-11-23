"""One of something is singular: «1 módulo», «1 núcleo · 1 hilo».

The share image read «1 módulos» and «2 núcleos · 4 hilos · — · Athlon
(Picasso)»; a dozen other texts said the plural with a count of one.
"""

import pathlib
import re
import unittest

from silux import render
from silux.i18n import _
from tests.test_equipos import EQUIPOS, shared_snapshot

ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestCounted(unittest.TestCase):

    def test_one_and_many(self):
        self.assertEqual(render.counted("share.modules", 1), _("share.modules.one").format(n=1))
        self.assertEqual(render.counted("share.modules", 2), _("share.modules").format(n=2))
        self.assertEqual(render.counted("cache.ways", 16), _("cache.ways").format(n=16))

    def test_every_counted_text_has_its_singular_in_both_languages(self):
        import json

        keys = set()
        for path in (ROOT / "silux").rglob("*.py"):
            keys |= set(re.findall(r'counted\(\s*"([\w.]+)"', path.read_text(encoding="utf-8")))
        self.assertGreater(len(keys), 10)
        for lang in ("es", "en"):
            texts = json.loads((ROOT / "silux/db/lang" / f"{lang}.json").read_text(encoding="utf-8"))
            missing = sorted(k for k in keys if f"{k}.one" not in texts)
            with self.subTest(lang=lang):
                self.assertEqual(missing, [])


class TestTheShareImage(unittest.TestCase):

    def _rows(self, dump):
        from silux.ui.tarjeta import _fila
        return {label: (main, detail) for label, main, detail in _fila(shared_snapshot(EQUIPOS / dump))}

    def test_a_missing_datum_goes_and_leaves_no_dash(self):
        detail = self._rows("athlon-3000g")[_("nav.cpu")][1]
        self.assertNotIn(render.DASH, detail)
        self.assertEqual(detail, f"{_('share.cores').format(n=2)} · "
                                 f"{_('share.threads').format(n=4)} · Athlon (Picasso)")

    def test_one_of_each(self):
        rows = self._rows("celeron-560")
        self.assertTrue(rows[_("nav.cpu")][1].startswith(
            f"{_('share.cores.one').format(n=1)} · {_('share.threads.one').format(n=1)}"))
        self.assertIn(_("share.modules.one").format(n=1), self._rows("athlon-3000g")[_("nav.memory")][1])


if __name__ == "__main__":
    unittest.main()
