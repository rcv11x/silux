"""silux: a hardware profiler for Linux.

Copyright (C) 2026 rcv11x

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option)
any later version. It is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY. The full text is in the LICENSE file.

The license is the GPL because the identification database includes the
package table inherited from CPU-X, which is GPL-3.0.

The rule the whole package rests on: providers read *values* (integers in
hertz, bytes, degrees) and the model keeps them as they are. The text the
user sees is produced in `silux.render`, never earlier.
"""

# Bumped when there is something the user notices. The minor number (0.1 to
# 0.2) is kept for when something really changes for them: a new section, a
# datum that didn't show before, or something that stops working as it did.
# The last digit, for fixes that don't require reading anything.
#
# Not cosmetic: without it, the only way to know whether a copy is behind is
# the build identifier, and a hash can't be compared at a glance. What
# changes in each version is in CHANGELOG.md, and a test won't let this
# number go up without writing it there.
__version__ = "0.4.0rc13"


def build_id() -> str:
    """Which exact copy this is: «20260829.c22e689», or empty if unknown.

    Called `build_id` rather than `build` because `report.build()` already
    exists and builds the report: imported bare, it would have shadowed it
    inside that module.

    People send screenshots of what they see, and fixes land between one and
    the next. Without this, an old screenshot of a bug already fixed gets
    investigated from scratch, and the version alone isn't enough: between
    two releases there are dozens of commits that all say the same.

    It doesn't replace `__version__`, nor the reverse: they answer two
    different people. This is for whoever maintains the program: which exact
    commit that copy came from. The version is for whoever uses it: whether
    they are behind, which a hash doesn't say.

    Three places, in this order. The file the packager writes, the case that
    matters, since the AppImage travels without a repository. Git itself, when
    running from source. And if neither (a loose tarball, a copied folder),
    nothing: a gap beats a made-up number.
    """
    global _build
    if _build is None:
        _build = _read_build() or _ask_git() or ""
    return _build


_build = None


def _read_build() -> str:
    """What the packager left written inside the package."""
    try:
        import pathlib
        text = (pathlib.Path(__file__).parent / "_build.txt").read_text(
            encoding="utf-8").strip()
    except OSError:
        return ""
    # A half-written file is worth no more than none.
    return text if text and len(text) < 64 else ""


def _ask_git() -> str:
    """The working copy's date and commit, if this is a repository.

    A trailing `+` says there are uncommitted changes: a screenshot of a copy
    edited by hand matches no commit, and knowing it saves searching the
    history for something that isn't there.
    """
    import subprocess

    from .system_env import system_environment

    root = __file__.rsplit("/", 2)[0]
    try:
        commit = subprocess.run(
            ["git", "-C", root, "log", "-1", "--format=%cd.%h", "--date=format:%Y%m%d"],
            capture_output=True, text=True, timeout=5, env=system_environment())
        if commit.returncode != 0:
            return ""
        dirty = subprocess.run(["git", "-C", root, "status", "--porcelain"],
                               capture_output=True, text=True, timeout=5,
                               env=system_environment())
    except (OSError, subprocess.SubprocessError):
        return ""
    mark = commit.stdout.strip()
    return f"{mark}+" if mark and dirty.stdout.strip() else mark
