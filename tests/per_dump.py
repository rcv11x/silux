"""One test per dump, so that the suite's processes share them out.

A test that loops over every dump runs whole in one process, and the suite
can't end before it does however many processes there are: one took 161 s
while the rest waited. Split by dump, each is a test of its own, and a
failure names its dump in the test's name.
"""

from tests.test_equipos import volcados


def per_dump(cls, name: str, check) -> None:
    """Add to `cls` a `test_<name>__<dump>` for each dump, which calls
    `check(self, folder)`."""
    for folder in volcados():
        def test(self, folder=folder):
            check(self, folder)
        test.__name__ = f"test_{name}__{folder.name.replace('-', '_')}"
        test.__doc__ = check.__doc__
        setattr(cls, test.__name__, test)
