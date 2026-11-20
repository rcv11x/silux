"""tools/gen_cpu_db.py: the cpuid tarball, from whichever mirror has it.

On 20 November 2026 the monthly task failed: etallen.com answered GitHub's
runner with an HTML page (b'<!') and tarfile choked on it. Debian keeps the
same tarball byte for byte, and the pinned hash is what makes either one
acceptable.
"""

import hashlib
import io
import pathlib
import tarfile
import tempfile
import unittest
from unittest import mock

import tools.gen_cpu_db as gen

HTML = b"<!DOCTYPE html><html><body>Checking your browser</body></html>"


def tarball(text: str) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        data = text.encode()
        member = tarfile.TarInfo(f"cpuid-{gen.CPUID_VERSION}/cpuid.c")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class TestCpuidDownload(unittest.TestCase):

    def fetch(self, answers: dict, expected: bytes):
        def urlopen(request, timeout=None):
            return Response(answers[request.full_url])
        with tempfile.TemporaryDirectory() as cache, \
                mock.patch("urllib.request.urlopen", urlopen), \
                mock.patch.object(gen, "CPUID_SHA256", hashlib.sha256(expected).hexdigest()):
            text = gen.fetch_cpuid_source(pathlib.Path(cache), offline=False)
            cached = (pathlib.Path(cache) / "cpuid" / gen.CPUID_VERSION / "cpuid.c").read_text()
        return text, cached

    def test_an_html_page_falls_through_to_the_mirror(self):
        good = tarball("decode_uarch_intel() {}\n")
        first, mirror = gen.CPUID_TARBALLS
        text, cached = self.fetch({first: HTML, mirror: good}, good)
        self.assertEqual(text, "decode_uarch_intel() {}\n")
        self.assertEqual(cached, text)

    def test_a_tarball_with_another_hash_is_refused(self):
        good = tarball("the pinned one\n")
        first, mirror = gen.CPUID_TARBALLS
        text, _cached = self.fetch({first: tarball("someone else's\n"), mirror: good}, good)
        self.assertEqual(text, "the pinned one\n")

    def test_when_none_has_it_the_error_says_what_each_one_gave(self):
        with self.assertRaises(SystemExit) as raised:
            self.fetch({url: HTML for url in gen.CPUID_TARBALLS}, tarball("x"))
        message = str(raised.exception)
        for url in gen.CPUID_TARBALLS:
            self.assertIn(url, message)
        self.assertIn("b'<!DOCTYPE", message)


if __name__ == "__main__":
    unittest.main()
