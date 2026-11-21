"""CPUID's own errors are technical details in English, and what reaches
the CPU page is a translated sentence with the error kept for the report.

A thread that could not be pinned to a CPU (an offline CPU, a restrictive
cgroup) put «no se pudo fijar el hilo a la CPU 3: [Errno 22] …» on the page
as it came, in Spanish whatever the interface language.
"""

import contextlib
import unittest
from unittest import mock

from silux import i18n, rawcpuid
from silux.i18n import _
from silux.model import Need
from silux.providers import cpuid_x86
from silux.providers.base import Draft


class TestTheExceptionTexts(unittest.TestCase):

    def test_a_cpu_that_cannot_be_pinned(self):
        with mock.patch.object(rawcpuid.sysroot, "active", lambda: False), \
                mock.patch.object(rawcpuid.os, "sched_getaffinity", lambda pid: {0}), \
                mock.patch.object(rawcpuid.os, "sched_setaffinity",
                                  side_effect=OSError(22, "Invalid argument")):
            with self.assertRaises(rawcpuid.CpuidError) as caught:
                with rawcpuid.pinned(3):
                    pass
        self.assertEqual(str(caught.exception),
                         "could not pin the thread to CPU 3: [Errno 22] Invalid argument")

    def test_a_machine_that_is_not_x86(self):
        with mock.patch.object(rawcpuid, "machine", lambda: "aarch64"):
            with self.assertRaises(rawcpuid.CpuidError) as caught:
                rawcpuid.CpuidReader()
        self.assertEqual(str(caught.exception), "CPUID is only implemented for x86-64, not aarch64")


class TestOnThePage(unittest.TestCase):

    def _note(self):
        @contextlib.contextmanager
        def cannot_pin(cpu):
            raise rawcpuid.CpuidError(f"could not pin the thread to CPU {cpu}: [Errno 22] Invalid argument")
            yield

        provider = cpuid_x86.CpuidIdentity.__new__(cpuid_x86.CpuidIdentity)
        provider._reader, provider._error = object(), None
        draft = Draft()
        draft.types["p"] = {"cpus": [3]}
        with mock.patch.object(cpuid_x86, "pinned", cannot_pin):
            provider.collect(draft)
        return [n for n in draft.notes if n.path == "cpu.types.p"]

    def test_a_translated_sentence_and_the_error_in_the_detail(self):
        for language in ("es", "en"):
            with self.subTest(language=language):
                i18n.set_language(language)
                try:
                    notes = self._note()
                    self.assertEqual([(n.message, n.need) for n in notes],
                                     [(_("prov.cpuid.pin").format(cpu=3), Need.PLATFORM)])
                    self.assertEqual(notes[0].detail,
                                     "could not pin the thread to CPU 3: [Errno 22] Invalid argument")
                finally:
                    i18n.set_language("es")


if __name__ == "__main__":
    unittest.main()
