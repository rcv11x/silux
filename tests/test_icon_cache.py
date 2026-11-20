"""The drawn icons are kept where only the user can write.

They were kept in /tmp/silux-icons, a fixed name: another user of the machine
could create that folder first and leave the files Qt would load.
"""

import os
import pathlib
import stat
import tempfile
import unittest
from unittest import mock

from tests import qt

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                    # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "no PySide6")
class TestTheIconCache(unittest.TestCase):

    def test_in_the_users_own_folder(self):
        from silux.ui import theme

        qt.app()
        with tempfile.TemporaryDirectory() as runtime:
            os.chmod(runtime, 0o700)
            with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime}):
                path = pathlib.Path(theme._arrow_icon("#ffffff", "down"))
        self.assertNotEqual(path.parent, pathlib.Path(tempfile.gettempdir()) / "silux-icons")
        self.assertEqual(path.parent.parent, pathlib.Path(runtime))

    def test_never_a_runtime_folder_that_is_someone_elses(self):
        from silux.ui import theme

        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": "/"}):
            cache = theme.icon_cache()
        self.assertNotEqual(cache.parent, pathlib.Path("/"))
        info = os.stat(next(p for p in [cache, *cache.parents] if p.exists()))
        self.assertEqual(info.st_uid, os.getuid())
        self.assertFalse(info.st_mode & stat.S_IWOTH)


if __name__ == "__main__":
    unittest.main()
