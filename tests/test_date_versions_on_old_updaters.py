"""The copies already out there reach a release named by its date.

Silux becomes a rolling release numbered by the day it comes out,
«2026.11.28». Whoever runs a prueba (0.4.0rc1 to rc14) must get it with
«Buscar ahora» or the check at startup, without downloading anything by
hand. Each published updater is in `tests/fixtures/updaters`, copied from
the tag of the first prueba that carried it, and is asked here, as the
version that ran it, what a GitHub listing that release offers. Their own
code, not this one's: the rules they follow can't change any more.
"""

import io
import json
import pathlib
import sys
import types
import unittest

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "updaters"

# Each copy of the updater and the pruebas that shipped it.
VARIANTS = {
    "updates_0_4_0rc1.py": ("0.4.0rc1",),
    "updates_0_4_0rc2.py": ("0.4.0rc2", "0.4.0rc3", "0.4.0rc4"),
    "updates_0_4_0rc5.py": ("0.4.0rc5", "0.4.0rc6", "0.4.0rc7"),
    "updates_0_4_0rc8.py": ("0.4.0rc8", "0.4.0rc9", "0.4.0rc10", "0.4.0rc11"),
    "updates_0_4_0rc12.py": ("0.4.0rc12", "0.4.0rc13", "0.4.0rc14"),
}

DATE = "2026.11.28"
NORMAL, COMPAT, SUMS = "silux-x86_64.AppImage", "silux-x86_64-compat.AppImage", "SHA256SUMS"
DIGESTS = {NORMAL: "a" * 64, COMPAT: "b" * 64}


def load(file: str, running: str) -> types.ModuleType:
    """That updater as the version `running` ran it."""
    source = (FIXTURES / file).read_text(encoding="utf-8")
    source = source.replace("from . import __version__, build_id\n", "", 1)
    name = f"old_updates_{running.replace('.', '_')}"
    module = types.ModuleType(name)
    module.__version__ = running
    module.build_id = lambda: "20261127.0000000"
    sys.modules[name] = module
    try:
        exec(compile(source, str(FIXTURES / file), "exec"), module.__dict__)
    finally:
        del sys.modules[name]
    return module


def listing(date_prerelease: bool) -> list:
    """What GitHub's API lists, newest first: the date release, the last
    two pruebas (prereleases, as they were published) and the 0.3."""
    def entry(tag: str, prerelease: bool) -> dict:
        base = f"https://github.com/rcv11x/silux/releases/download/{tag}/"
        return {"tag_name": tag, "draft": False, "prerelease": prerelease,
                "html_url": f"https://github.com/rcv11x/silux/releases/tag/{tag}",
                "assets": [{"name": n, "browser_download_url": base + n}
                           for n in (NORMAL, COMPAT, SUMS)]}
    return [entry(DATE, date_prerelease), entry("0.4.0rc14", True),
            entry("0.4.0rc13", True), entry("v0.3.0", False)]


def opener_for(date_prerelease: bool):
    sums = "".join(f"{digest}  {name}\n" for name, digest in DIGESTS.items()).encode()
    listed = json.dumps(listing(date_prerelease)).encode()

    def opener(url, timeout=None):
        return io.BytesIO(sums if url.endswith(SUMS) else listed)
    return opener


def offered(module, running: str, preference: str, date_prerelease: bool):
    """The release that copy offers to update to, or None."""
    opener = opener_for(date_prerelease)
    if hasattr(module, "channel_for"):
        found = module.check(opener, module.channel_for(preference, running))
    else:
        found = module.check(opener)
    return found if module.is_newer(found, running) else None


class TestTheOldUpdaters(unittest.TestCase):
    def test_a_normal_release_on_every_channel(self):
        # Without a choice, a test version looks in «Pruebas»; «Estable» and
        # «Pruebas» are what Settings offered. The prueba1 had no channels.
        for file, versions in VARIANTS.items():
            for running in versions:
                module = load(file, running)
                for preference in ("", "stable", "testing"):
                    with self.subTest(running=running, channel=preference or "default"):
                        release = offered(module, running, preference, False)
                        self.assertIsNotNone(release)
                        self.assertEqual(release.tag, DATE)
                        self.assertEqual(release.version_text, DATE)

    def test_a_prerelease_only_where_tests_are_looked_for(self):
        for file, versions in VARIANTS.items():
            for running in versions:
                module = load(file, running)
                for preference in ("", "stable", "testing"):
                    seen = offered(module, running, preference, True)
                    with self.subTest(running=running, channel=preference or "default"):
                        if not hasattr(module, "channel_for") or preference == "stable":
                            self.assertIsNone(seen)
                        else:
                            self.assertEqual(seen.tag, DATE)

    def test_both_appimages_and_their_sums_are_found(self):
        for file, versions in VARIANTS.items():
            module = load(file, versions[-1])
            release = offered(module, versions[-1], "", False)
            with self.subTest(updater=file):
                self.assertEqual(set(release.assets), {NORMAL, COMPAT, SUMS})
                for name, digest in DIGESTS.items():
                    self.assertEqual(module.expected_hash(release, name, opener_for(False)),
                                     digest)

    def test_the_date_is_ahead_of_every_prueba(self):
        for file, versions in VARIANTS.items():
            module = load(file, versions[-1])
            release = offered(module, versions[-1], "", False)
            for running in [v for vs in VARIANTS.values() for v in vs]:
                with self.subTest(updater=file, running=running):
                    self.assertTrue(module.is_newer(release, running))

    def test_a_date_written_otherwise_reaches_nobody(self):
        # «2026-11-28» isn't x.y.z: every old updater skips it. The format
        # of the tag is what keeps the old copies on board.
        global DATE
        saved, DATE = DATE, "2026-11-28"
        try:
            for file, versions in VARIANTS.items():
                module = load(file, versions[-1])
                seen = offered(module, versions[-1], "", False)
                with self.subTest(updater=file):
                    # At most a later prueba, never the date.
                    self.assertTrue(seen is None or seen.tag != DATE, seen)
        finally:
            DATE = saved


if __name__ == "__main__":
    unittest.main()
