"""A GPU's state row says plainly whether it is held back: «sin límites»
read oddly, and «recortando por en reposo» did not read at all."""

import unittest

from silux import render
from tests.test_equipos import EQUIPOS, shared_snapshot

class TestTheStateRow(unittest.TestCase):
    def test_says_whether_it_is_held_back(self):
        import dataclasses
        gpu = shared_snapshot(EQUIPOS / "5800x3d").gpus[0]
        free = dataclasses.replace(gpu, throttled=False, throttle_reasons=())
        self.assertEqual(render.throttle_state(free), "no está limitada")
        held = dataclasses.replace(gpu, throttled=True, throttle_reasons=("gpu.throttle.nv.idle",))
        self.assertEqual(render.throttle_state(held), "limitada: en reposo")


if __name__ == "__main__":
    unittest.main()
