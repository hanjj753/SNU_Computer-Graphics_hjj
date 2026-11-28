"""Optics, topology, sampling and acceleration invariants (stdlib unittest)."""

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import numpy as np
from numba import set_num_threads

from bvh import aabb_hit, build_bvh, intersect, triangle_hit
from denoise import atrous_pass
from image_io import display_image
from sampling import dielectric, normalize, sample_seed
from scene import load_scene
from tracer import (RenderOptions, camera_buffer, camera_ray, medium_transition,
                    render, shadow_transmittance, texture_color, trace_path, update_media)
from volume import free_flight, isotropic_direction, shell_connection_distance


def diagnostic_scene(base, quads, materials, light=None):
    """Tiny independent configurations that isolate complete light paths."""
    positions, mids = [], []
    for points, mid in quads:
        points = np.asarray(points, dtype=float)
        positions.extend([points[[0, 1, 2]], points[[0, 2, 3]]])
        mids.extend([mid, mid])
    p = np.asarray(positions)
    e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    gn = np.cross(e1, e2)
    gn /= np.linalg.norm(gn, axis=1, keepdims=True)
    bvh = build_bvh(p, leaf_size=1)
    return base._replace(v0=np.ascontiguousarray(p[:, 0]), e1=e1, e2=e2,
                         normals=np.repeat(gn[:, None], 3, axis=1), geometric_normals=gn,
                         uvs=np.zeros((len(p), 3, 2)), material_ids=np.array(mids, dtype=np.int32),
                         bvh_min=bvh.minimum, bvh_max=bvh.maximum, bvh_nodes=bvh.nodes,
                         bvh_indices=bvh.indices, materials=np.asarray(materials),
                         light=np.array([0., 2., 0., 4., 4., 0., 0., 0.]) if light is None else light)


def horizontal_quad(y, radius, upward):
    points = np.array([[-radius, y, -radius], [radius, y, -radius],
                       [radius, y, radius], [-radius, y, radius]])
    return points[::-1] if upward else points


class OpticsTests(unittest.TestCase):
    def test_normal_incidence_fresnel_and_direction(self):
        f, t, tir = dielectric((0., -1., 0.), (0., 1., 0.), 1., 1.5)
        self.assertAlmostEqual(f, 0.04, places=12)
        np.testing.assert_allclose(t, [0, -1, 0], atol=1e-12)
        self.assertFalse(tir)

    def test_snell_and_total_internal_reflection(self):
        direction = normalize((1., -1., 0.))
        f, transmitted, tir = dielectric(direction, (0., 1., 0.), 1., 1.333)
        self.assertAlmostEqual(transmitted[0], direction[0] / 1.333, places=12)
        self.assertFalse(tir)
        self.assertTrue(0 < f < 1)
        f, _, tir = dielectric(normalize((np.sqrt(3.), -1., 0.)), (0., 1., 0.), 1.5, 1.)
        self.assertTrue(tir)
        self.assertEqual(f, 1)

    def test_nested_medium_stack(self):
        materials = np.zeros((2, 14))
        materials[:, 6] = [1.5, 1.333]
        stack = np.empty(8, dtype=np.int32)
        a, b, remove = medium_transition(stack, 0, 0, True, materials)
        self.assertEqual((a, b), (1., 1.5))
        size = update_media(stack, 0, 0, True, remove)
        a, b, remove = medium_transition(stack, size, 1, True, materials)
        self.assertEqual((a, b), (1.5, 1.333))
        size = update_media(stack, size, 1, True, remove)
        a, b, remove = medium_transition(stack, size, 1, False, materials)
        self.assertEqual((a, b), (1.333, 1.5))
        size = update_media(stack, size, 1, False, remove)
        a, b, _ = medium_transition(stack, size, 0, False, materials)
        self.assertEqual((a, b), (1.5, 1.))

    def test_two_sided_triangle_and_parallel_box(self):
        p, e1, e2 = np.array([0., 0., 0.]), np.array([1., 0., 0.]), np.array([0., 1., 0.])
        for z, dz in ((1., -1.), (-1., 1.)):
            t, u, v = triangle_hit((.2, .3, z), (0., 0., dz), p, e1, e2, 10.)
            np.testing.assert_allclose([t, u, v], [1, .2, .3], atol=1e-12)
        t, _, _ = triangle_hit((1., 1., 1.), (0., 0., -1.), p, e1, e2, 10.)
        self.assertLess(t, 0)
        lo, hi = np.array([-1., -1., -1.]), np.array([1., 1., 1.])
        self.assertEqual(aabb_hit((0., 0., 0.), (0., 1., 0.), lo, hi, 100.), 0.)
        self.assertLess(aabb_hit((2., 0., 0.), (0., 1., 0.), lo, hi, 100.), 0.)

    def test_display_transfer(self):
        pixels = np.asarray(display_image(np.array([[[0., 1., 1e20]]]), exposure=1.))
        np.testing.assert_array_equal(pixels, [[[0, 188, 255]]])

    def test_free_flight_obeys_beer_extinction(self):
        distances = np.array([free_flight(120., (i + .5) / 8192) for i in range(8192)])
        self.assertAlmostEqual(float(np.mean(distances > .01)), np.exp(-1.2), delta=.0002)
        self.assertEqual(free_flight(0., .5), 1e30)

    def test_isotropic_phase_is_normalized_and_unbiased_in_direction(self):
        directions = np.array([isotropic_direction((i + .5) / 4096, (i * .61803398875) % 1)
                               for i in range(4096)])
        np.testing.assert_allclose(np.linalg.norm(directions, axis=1), 1., atol=1e-12)
        np.testing.assert_allclose(directions.mean(axis=0), 0., atol=.003)
        np.testing.assert_allclose((directions ** 2).mean(axis=0), 1 / 3, atol=.003)

    def test_thin_shell_light_connection_has_finite_refracted_optical_length(self):
        material = np.zeros(17)
        material[6], material[16] = 1.5, .005
        self.assertAlmostEqual(shell_connection_distance(material, .005, 1.), .005)
        length = shell_connection_distance(material, .1, .05)
        self.assertTrue(.005 < length < .007)

    def test_denoising_reduces_noise_without_crossing_material_edge(self):
        target = np.full((8, 12, 3), .2)
        target[:, 6:] = .8
        noise = np.random.default_rng(84).normal(0, .05, target.shape)
        color, variance = target + noise, np.full_like(target, .05 ** 2)
        normals = np.zeros_like(target)
        normals[:, :, 2] = 1.
        ids = np.zeros((8, 12), dtype=np.int32)
        ids[:, 6:] = 1
        filtered, _ = atrous_pass(color, variance, normals, np.ones((8, 12)), ids, 1)
        self.assertLess(np.mean((filtered - target) ** 2), np.mean(noise ** 2) * .5)
        self.assertLess(filtered[:, :6].max(), .4)
        self.assertGreater(filtered[:, 6:].min(), .6)


class SceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        set_num_threads(2)
        cls.scene, cls.config, cls.stats = load_scene()

    def test_closed_outward_dielectric_meshes(self):
        s = self.scene
        points = np.stack([s.v0, s.v0 + s.e1, s.v0 + s.e2], axis=1)
        for name in ("plastic", "water"):
            mid = self.stats["materials"].index(name)
            mesh = points[s.material_ids == mid]
            # Signed volume tests winding; welded edge multiplicity tests closure.
            volume = np.einsum("ij,ij->i", mesh[:, 0], np.cross(mesh[:, 1], mesh[:, 2])).sum() / 6
            self.assertGreater(volume, 0, name)
            edges = {}
            for tri in np.round(mesh, 7):
                for a, b in ((0, 1), (1, 2), (2, 0)):
                    edge = tuple(sorted((tuple(tri[a]), tuple(tri[b]))))
                    edges[edge] = edges.get(edge, 0) + 1
            self.assertTrue(all(count == 2 for count in edges.values()), name)

    def test_bvh_matches_brute_force_for_arbitrary_rays(self):
        rng = np.random.default_rng(51)
        for _ in range(160):
            origin = rng.uniform([-1, -.5, -4], [4, 4, 6])
            direction = normalize(tuple(rng.normal(size=3)))
            brute = intersect(tuple(origin), direction, self.scene, False)
            fast = intersect(tuple(origin), direction, self.scene, True)
            self.assertEqual(brute[1] >= 0, fast[1] >= 0)
            if brute[1] >= 0:
                self.assertAlmostEqual(brute[0], fast[0], places=10)
                self.assertEqual(self.scene.material_ids[brute[1]], self.scene.material_ids[fast[1]])

    def test_coincident_triangles_use_stable_primitive_id(self):
        # Visit the higher-ID duplicate first in the BVH. Both traversals must
        # still select ID 0, including at a shared material/contact boundary.
        v0 = np.zeros((2, 3))
        e1, e2 = np.tile([1., 0., 0.], (2, 1)), np.tile([0., 1., 0.], (2, 1))
        lo, hi = np.tile([-1e-7, -1e-7, -1e-7], (3, 1)), np.tile([1.0000001, 1.0000001, 1e-7], (3, 1))
        nodes = np.array([[1, 2, 0, 0], [-1, -1, 0, 1], [-1, -1, 1, 1]], dtype=np.int32)
        scene = self.scene._replace(v0=v0, e1=e1, e2=e2, bvh_min=lo, bvh_max=hi,
                                    bvh_nodes=nodes, bvh_indices=np.array([0, 1], dtype=np.int32))
        for accelerated in (False, True):
            hit = intersect((.2, .3, 1.), (0., 0., -1.), scene, accelerated)
            self.assertEqual(hit[1], 0)

    def test_bilinear_texture_preserves_uv_corners(self):
        s = self.scene
        offset, width, height = s.texture_info[0]
        np.testing.assert_allclose(texture_color(s, 0, 0., 1.), s.texture_pixels[offset])
        np.testing.assert_allclose(texture_color(s, 0, 1., 0.), s.texture_pixels[offset + width * height - 1])

    def test_integrator_follows_reflection_to_visible_emitter(self):
        materials = np.zeros((2, 15))
        materials[:, 6], materials[:, 10] = 1., -1.
        materials[0, 3:5] = [1., 10000.]
        materials[1, 5], materials[1, 11:14] = 2., [2., 3., 4.]
        scene = diagnostic_scene(self.scene, [(horizontal_quad(0, 10, True), 0),
                                             (horizontal_quad(2, 10, False), 1)], materials)
        flags = np.array([1, 1, 1, 1, 0, 1, 0, 0, 1], dtype=np.int64)
        args = ((0., 1., 0.), (0., -1., 0.), scene, flags)
        one, _, _ = trace_path(*args, 1, 0, 1, np.uint32(12345))
        recursive, _, _ = trace_path(*args, 2, 0, 1, np.uint32(12345))
        np.testing.assert_array_equal(one, 0.)
        self.assertGreater(recursive.min(), 1.)
        flags[2] = 0
        disabled, _, _ = trace_path(*args, 2, 0, 1, np.uint32(12345))
        np.testing.assert_array_equal(disabled, 0.)

    def test_integrator_transmits_through_both_dielectric_boundaries(self):
        materials = np.zeros((2, 15))
        materials[:, 6], materials[:, 10] = 1., -1.
        materials[0, 5:7], materials[0, 7:10] = [1., 1.5], [0.3, 0.6, 0.9]
        materials[1, 5], materials[1, 11:14] = 2., [3., 3., 3.]
        scene = diagnostic_scene(self.scene, [(horizontal_quad(0, 10, True), 0),
                                             (horizontal_quad(-.2, 10, False), 0),
                                             (horizontal_quad(-1, 10, True), 1)], materials)
        flags = np.array([1, 1, 1, 1, 0, 1, 0, 0, 1], dtype=np.int64)
        sums = np.zeros((3, 3))
        for seed in range(64):
            for j, depth in enumerate((2, 3, 8)):
                color, _, _ = trace_path((0., 1., 0.), (0., -1., 0.), scene, flags,
                                         depth, 0, 1, sample_seed(0, seed, 2026))
                sums[j] += color
        np.testing.assert_array_equal(sums[0], 0.)
        self.assertTrue((sums[1] > 0).all())
        self.assertGreater(sums[2, 0], sums[2, 1])
        self.assertGreater(sums[2, 1], sums[2, 2])
        flags[3] = 0
        disabled, _, _ = trace_path((0., 1., 0.), (0., -1., 0.), scene, flags,
                                    8, 0, 1, np.uint32(13579))
        np.testing.assert_array_equal(disabled, 0.)

    def test_scattering_medium_extinguishes_unscattered_shadow_connections(self):
        materials = np.zeros((1, 16))
        materials[0, 5:7], materials[0, 10], materials[0, 15] = [1., 1.], -1., 4.
        materials[0, 7:10] = [.2, .3, .4]
        scene = diagnostic_scene(self.scene, [(horizontal_quad(0, 10, True), 0),
                                             (horizontal_quad(-.2, 10, False), 0)], materials)
        flags = np.array([1, 1, 1, 1, 1, 1, 0, 0, 1], dtype=np.int64)
        trans, _, _ = shadow_transmittance((0., 1., 0.), (0., -1., 0.), 3., scene, flags,
                                           np.empty(68, dtype=np.int32), 0)
        np.testing.assert_allclose(trans, np.exp(-.2 * np.array([4.2, 4.3, 4.4])), atol=.00003)

    def test_volume_scattering_receives_light_without_an_emissive_material(self):
        materials = np.zeros((2, 16))
        materials[:, 6], materials[:, 10] = 1., -1.
        materials[0, 5:7], materials[0, 15] = [1., 1.], 20.
        materials[1, 5], materials[1, 11:14] = 2., [2., 2., 2.]
        scene = diagnostic_scene(self.scene, [(horizontal_quad(0, 10, True), 0),
                                             (horizontal_quad(-.2, 10, False), 0),
                                             (horizontal_quad(2, 2, False), 1)], materials,
                                 np.array([0., 2., 0., 4., 4., 2., 2., 2.]))
        flags = np.array([1, 1, 1, 1, 0, 1, 0, 0, 1], dtype=np.int64)
        total = 0.
        for sample in range(64):
            color, _, _ = trace_path((0., 1., 0.), (0., -1., 0.), scene, flags,
                                     8, 0, 4, sample_seed(0, sample, 2026))
            total += color[0]
        self.assertGreater(total / 64, .01)
        materials[0, 15] = 0.
        clear, _, _ = trace_path((0., 1., 0.), (0., -1., 0.), scene, flags,
                                 8, 0, 4, sample_seed(0, 0, 2026))
        np.testing.assert_array_equal(clear, 0.)

    def test_volume_light_connection_cancels_camera_ior_radiance_factor(self):
        materials = np.zeros((1, 16))
        materials[0, 5:7], materials[0, 10], materials[0, 15] = [1., 1.5], -1., 1e-12
        scene = diagnostic_scene(self.scene, [(horizontal_quad(0, 10, True), 0),
                                             (horizontal_quad(-.2, 10, False), 0)], materials)
        flags = np.array([1, 1, 1, 1, 0, 1, 0, 0, 1], dtype=np.int64)
        stack = np.array([0] + [0] * 67, dtype=np.int32)
        value, _, _ = shadow_transmittance((0., -.1, 0.), (0., 1., 0.), 2., scene, flags,
                                           stack, 1, True)
        # Camera entry is 1/eta^2; light connection exit is eta^2*(1-F).
        np.testing.assert_allclose(value / 1.5 ** 2, .96, atol=1e-10)

    def test_area_light_visibility_has_umbra_penumbra_and_lit_region(self):
        materials = np.zeros((1, 15))
        materials[0, 6], materials[0, 10] = 1., -1.
        quad = [[-.35, 1, -.4], [.35, 1, -.4], [.35, 1, .4], [-.35, 1, .4]]
        scene = diagnostic_scene(self.scene, [(quad, 0)], materials)
        flags = np.array([1, 1, 1, 1, 0, 1, 0, 0, 1], dtype=np.int64)
        visible = []
        for x in (0., .6, 1.3):
            total = 0.
            for i in range(16):
                for j in range(16):
                    target = np.array([(i + .5) / 16 - .5, 2., (j + .5) / 16 - .5])
                    origin = np.array([x, 0., 0.])
                    direction = normalize(tuple(target - origin))
                    trans, _, _ = shadow_transmittance(tuple(origin), direction, float(np.linalg.norm(target - origin)),
                                                       scene, flags, np.empty(68, dtype=np.int32), 0)
                    total += trans[0]
            visible.append(total / 256)
        self.assertEqual(visible[0], 0.)
        self.assertTrue(.1 < visible[1] < .9, visible)
        self.assertEqual(visible[2], 1.)

    def test_glossy_only_continuation_preserves_direct_diffuse_energy(self):
        materials = np.zeros((2, 15))
        materials[:, 6], materials[:, 10] = 1., -1.
        materials[0, :3], materials[0, 3:5] = [.8, .8, .8], [.5, 0.]
        materials[1, 5], materials[1, 11:14] = 2., [2., 2., 2.]
        scene = diagnostic_scene(self.scene, [(horizontal_quad(0, 10, True), 0),
                                             (horizontal_quad(2, 2, False), 1)], materials,
                                 np.array([0., 2., 0., 4., 4., 2., 2., 2.]))
        flags = np.array([1, 1, 1, 1, 0, 1, 0, 0, 1], dtype=np.int64)
        totals = np.zeros(2)
        for sample in range(8192):
            for index, depth in enumerate((1, 2)):
                color, _, _ = trace_path((0., 1., 0.), (0., -1., 0.), scene, flags,
                                         depth, 0, 1, sample_seed(0, sample, 2026))
                totals[index] += color[0]
        self.assertLess(abs(totals[0] - totals[1]) / totals[0], .04)

    def test_thin_lens_rays_converge_on_focus_plane(self):
        options = RenderOptions(aperture=.1, focus_distance=6.)
        camera = camera_buffer(self.config, options)
        hits = []
        for lu, lv in ((.2, .1), (.9, .7)):
            origin, direction = camera_ray(camera, 100, 75, 41, 30, .3, .4, lu, lv)
            origin, direction = np.array(origin), np.array(direction)
            distance = (6. - np.dot(origin - camera[0], camera[1])) / np.dot(direction, camera[1])
            hits.append(origin + direction * distance)
        np.testing.assert_allclose(hits[0], hits[1], atol=1e-12)

    def test_bvh_render_equivalence_and_seed_reproducibility(self):
        options = RenderOptions(width=16, height=12, spp=2, max_depth=8, light_samples=1, diffuse_bounces=2)
        aovs = {}
        fast, sf = render(self.scene, self.config, options, aovs=aovs)
        self.assertTrue(np.isfinite(aovs["variance"]).all())
        self.assertTrue((aovs["variance"] >= 0).all())
        self.assertTrue((aovs["variance"] > 0).any())
        brute, sb = render(self.scene, self.config, replace(options, use_bvh=False))
        np.testing.assert_allclose(fast, brute, atol=1e-10, rtol=1e-9)
        repeat, _ = render(self.scene, self.config, options, pass_spp=1)
        np.testing.assert_array_equal(fast, repeat)
        self.assertTrue(np.isfinite(fast).all())
        self.assertGreater(fast.max(), 0)
        self.assertLess(sf["triangle_tests"], sb["triangle_tests"])


if __name__ == "__main__":
    unittest.main()
