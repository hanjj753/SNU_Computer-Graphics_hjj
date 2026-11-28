"""Optional normal/depth/material-guided à trous filtering in linear RGB.

This is an explicitly biased image filter. Raw path-traced PNG/NPY files are
always retained. It is not part of the timed acceleration benchmark.
"""

import math
import time

import numpy as np
from numba import njit, prange

from bvh import intersect
from sampling import dot, normalize
from tracer import camera_buffer, camera_ray, texture_color


@njit(cache=True, parallel=True)
def guides(scene, camera, width, height, use_textures):
    albedo = np.ones((height, width, 3))
    normals = np.zeros((height, width, 3))
    depth = np.zeros((height, width))
    ids = np.full((height, width), -1, dtype=np.int32)
    for pixel in prange(width * height):
        x, y = pixel % width, pixel // width
        origin, direction = camera_ray(camera, width, height, x, y, .5, .5, .5, .5)
        t, hit, u, v, _ = intersect(origin, direction, scene, True)
        if hit < 0:
            continue
        mid, w = scene.material_ids[hit], 1 - u - v
        mat, ns = scene.materials[mid], scene.normals[hit]
        n = normalize((ns[0, 0] * w + ns[1, 0] * u + ns[2, 0] * v,
                       ns[0, 1] * w + ns[1, 1] * u + ns[2, 1] * v,
                       ns[0, 2] * w + ns[1, 2] * u + ns[2, 2] * v))
        ids[y, x], depth[y, x] = mid, t
        normals[y, x, 0], normals[y, x, 1], normals[y, x, 2] = n
        if int(mat[5]) == 0:
            for c in range(3):
                albedo[y, x, c] = max(0.1, mat[c])
            if use_textures and int(mat[10]) >= 0:
                uv = scene.uvs[hit]
                tu, tv = uv[0, 0] * w + uv[1, 0] * u + uv[2, 0] * v, uv[0, 1] * w + uv[1, 1] * u + uv[2, 1] * v
                tex = texture_color(scene, int(mat[10]), tu, tv)
                for c in range(3):
                    albedo[y, x, c] = max(0.1, mat[c] * tex[c])
    return albedo, normals, depth, ids


@njit(cache=True, parallel=True)
def atrous_pass(color, variance, normals, depth, ids, step):
    height, width = depth.shape
    result, result_var = np.empty_like(color), np.empty_like(variance)
    kernel = (1.0, 4.0, 6.0, 4.0, 1.0)
    for pixel in prange(width * height):
        x, y = pixel % width, pixel // width
        if ids[y, x] < 0:
            result[y, x] = color[y, x]
            result_var[y, x] = variance[y, x]
            continue
        total = np.zeros(3)
        total_var = np.zeros(3)
        weight_sum = 0.0
        for j in range(-2, 3):
            yy = y + j * step
            if yy < 0 or yy >= height:
                continue
            for i in range(-2, 3):
                xx = x + i * step
                if xx < 0 or xx >= width or ids[yy, xx] != ids[y, x]:
                    continue
                normal_weight = max(0.0, dot(normals[y, x], normals[yy, xx])) ** 64
                dz = abs(depth[y, x] - depth[yy, xx]) / (0.02 * step * max(1., depth[y, x]))
                color_error = 0.0
                for c in range(3):
                    delta = color[y, x, c] - color[yy, xx, c]
                    color_error += delta * delta / (16 * (variance[y, x, c] + variance[yy, xx, c]) + 0.0001)
                weight = kernel[i + 2] * kernel[j + 2] * normal_weight * math.exp(-dz - color_error / 3)
                weight_sum += weight
                for c in range(3):
                    total[c] += color[yy, xx, c] * weight
                    total_var[c] += variance[yy, xx, c] * weight * weight
        for c in range(3):
            result[y, x, c] = total[c] / max(1e-30, weight_sum)
            result_var[y, x, c] = total_var[c] / max(1e-30, weight_sum * weight_sum)
    return result, result_var


def denoise(linear, variance, scene, config, options, iterations=2, strength=0.8):
    """Filter a copy, then retain some unfiltered radiance to preserve detail.

    strength=1 uses the full filter; strength=0 returns the input unchanged.
    Fewer iterations avoid the largest spatial kernels around thin highlights.
    """
    if not isinstance(iterations, int) or not 1 <= iterations <= 5:
        raise ValueError("denoise iterations must be an integer from 1 to 5")
    if not math.isfinite(strength) or not 0.0 <= strength <= 1.0:
        raise ValueError("denoise strength must be finite and in [0, 1]")
    started = time.perf_counter()
    camera = camera_buffer(config, options)
    # Center-lens guides preserve a consistent focus plane; the raw DOF image
    # remains available when filtering is too conservative near blur edges.
    camera[4, 1] = 0.0
    albedo, normals, depth, ids = guides(scene, camera, options.width, options.height, options.textures)
    color, var = linear / albedo, variance / (albedo * albedo)
    for level in range(iterations):
        color, var = atrous_pass(color, var, normals, depth, ids, 2 ** level)
    filtered = np.maximum(0., color * albedo)
    result = linear + strength * (filtered - linear)
    return result, {"method": "albedo-demodulated, normal/depth/material-guided a trous",
                    "iterations": iterations, "strength": strength,
                    "seconds_including_jit": time.perf_counter() - started,
                    "biased_filter": True, "raw_render_retained": True}
