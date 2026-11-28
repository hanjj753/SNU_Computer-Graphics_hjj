"""Saved-PNG color fidelity and robust noise estimation; no path rendering."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from image_io import display_image
from postprocess import png_noise, png_radiance


class SavedPngTests(unittest.TestCase):
    def test_inverse_display_preserves_every_8bit_value(self):
        rgb = np.repeat(np.arange(256, dtype=np.uint8).reshape(16, 16, 1), 3, axis=2)
        for exposure in (.7, 2.4, 5.):
            linear, jacobian = png_radiance(rgb, exposure)
            np.testing.assert_array_equal(np.asarray(display_image(linear, exposure)), rgb)
            self.assertTrue(np.isfinite(linear).all())
            self.assertTrue((jacobian > 0).all())

    def test_noise_estimate_ignores_linear_shading_and_horizontal_waterline(self):
        height, width = 128, 192
        y, x = np.indices((height, width))
        target = 80. + .2 * x + .15 * y + 25. * (y >= height // 2)
        rgb = np.uint8(np.clip(np.rint(target[:, :, None]
                                      + np.random.default_rng(7).normal(0, 3., (height, width, 3))), 0, 255))
        normals = np.zeros((height, width, 3))
        normals[:, :, 2] = 1.
        sigma, _ = png_noise(rgb, np.ones_like(normals), normals,
                             np.ones((height, width)), np.zeros((height, width), dtype=np.int32))
        np.testing.assert_allclose(sigma[0, 0] * 255., 3., atol=.3)


if __name__ == "__main__":
    unittest.main()
