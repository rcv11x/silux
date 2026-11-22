"""An SPD chip as the kernel answers on a machine that blocks its page switch.

The spd5118 driver switches pages by writing to the chip. Where the machine
blocks SPD writes, any read whose bytes go past page 0 fails with ENXIO,
whatever page it starts on, and the whole read with it: a buffered read of
128 bytes, which asks the kernel for a block, fails too. Page 0 alone reads.
"""

import builtins
import contextlib
import errno
import io
import os
import pathlib
from unittest import mock

PAGE = 128


class _BlockedRaw(io.RawIOBase):
    """The file the kernel gives: reads past page 0 fail, as one."""

    def __init__(self, content: bytes):
        self._content = content
        self._position = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def seek(self, offset, whence=os.SEEK_SET):
        base = {os.SEEK_SET: 0, os.SEEK_CUR: self._position,
                os.SEEK_END: len(self._content)}[whence]
        self._position = base + offset
        return self._position

    def tell(self):
        return self._position

    def readinto(self, buffer):
        end = min(self._position + len(buffer), len(self._content))
        if end > PAGE:
            raise OSError(errno.ENXIO, os.strerror(errno.ENXIO))
        chunk = self._content[self._position:end]
        buffer[:len(chunk)] = chunk
        self._position = end
        return len(chunk)


@contextlib.contextmanager
def blocked_past_page_zero(suffix: str, content: bytes):
    """Every open of a path ending in `suffix` gives `content` as above, with
    Python's own buffering over it when the caller asks for it."""
    real_open = io.open

    def fake_open(file, mode="r", buffering=-1, *args, **kwargs):
        if str(file).endswith(suffix) and "b" in mode:
            raw = _BlockedRaw(content)
            if buffering == 0:
                return raw
            return io.BufferedReader(raw, buffer_size=4096)
        return real_open(file, mode, buffering, *args, **kwargs)

    patches = [mock.patch.object(builtins, "open", fake_open),
               mock.patch.object(io, "open", fake_open)]
    # Python 3.10's pathlib keeps its own copy of io.open since it's imported.
    accessor = getattr(pathlib, "_NormalAccessor", None)
    if accessor is not None and hasattr(accessor, "open"):
        patches.append(mock.patch.object(accessor, "open", staticmethod(fake_open)))
    with contextlib.ExitStack() as stack:
        for patch in patches:
            stack.enter_context(patch)
        yield
