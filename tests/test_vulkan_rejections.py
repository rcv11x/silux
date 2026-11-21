"""A Vulkan driver that is installed and rejects the card says why.

On a laptop with an Intel UHD and an NVIDIA, Mesa's Intel driver was there
and Vulkan listed only the NVIDIA and llvmpipe: the page said «neither
Vulkan nor OpenGL use it», and the driver had said why on stderr.
"""

import unittest

from silux import gpuapi

MESA_REJECTION = ("Vulkan requires context isolation for Intel(R) Graphics (ADL GT2) "
        "(VK_ERROR_INCOMPATIBLE_DRIVER)")


class TestWhatTheDriverSaid(unittest.TestCase):

    def test_a_rejection_with_its_reason_and_card(self):
        texto = "MESA-INTEL: warning: something else\n" + MESA_REJECTION + "\n"
        self.assertEqual(gpuapi.vulkan_rejections(texto),
                         [{"device": "Intel(R) Graphics (ADL GT2)",
                           "reason": "Vulkan requires context isolation",
                           "code": "VK_ERROR_INCOMPATIBLE_DRIVER"}])

    def test_a_mesa_prefix_is_not_part_of_the_reason(self):
        texto = "MESA: error: " + MESA_REJECTION
        self.assertEqual(gpuapi.vulkan_rejections(texto)[0]["reason"],
                         "Vulkan requires context isolation")

    def test_other_noise_is_no_rejection(self):
        self.assertEqual(gpuapi.vulkan_rejections(
            "WARNING: radv is not a conformant Vulkan implementation\n"), [])


if __name__ == "__main__":
    unittest.main()
