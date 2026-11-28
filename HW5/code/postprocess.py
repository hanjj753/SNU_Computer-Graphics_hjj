"""Conservative guided denoising of a saved PNG, without retracing paths.

PNG inversion recovers quantized radiance, not the original HDR samples.
Noise is estimated from same-material 2x2 Haar residuals, not sample moments.
"""

import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
from PIL import Image

from denoise import atrous_pass, guides
from image_io import display_image, save_render
from scene import load_scene
from tracer import RenderOptions, camera_buffer


def png_radiance(rgb, exposure):
    """Invert this renderer's sRGB/Reinhard transform, with its Jacobian."""
    if not math.isfinite(exposure) or exposure <= 0:
        raise ValueError("exposure must be positive and finite")
    encoded = np.asarray(rgb, dtype=np.float64) / 255.
    mapped = np.where(encoded <= .04045, encoded / 12.92,
                      ((encoded + .055) / 1.055) ** 2.4)
    slope = np.where(encoded <= .04045, 1. / 12.92,
                     2.4 / 1.055 * ((encoded + .055) / 1.055) ** 1.4)
    remaining = np.maximum(1e-6, 1. - mapped)
    return mapped / remaining / exposure, slope / (remaining ** 2 * exposure)


def png_noise(rgb, albedo, normals, depth, ids):
    """Robust display-space sigma; linear ramps cancel in the Haar residual."""
    encoded = np.asarray(rgb, dtype=np.float64) / 255.
    haar = (encoded[:-1, :-1] - encoded[:-1, 1:]
            - encoded[1:, :-1] + encoded[1:, 1:]) * .5
    anchor = ids[:-1, :-1]
    valid = ((anchor >= 0) & (anchor == ids[:-1, 1:])
             & (anchor == ids[1:, :-1]) & (anchor == ids[1:, 1:]))
    for yy, xx in ((0, 1), (1, 0), (1, 1)):
        a = albedo[yy:yy + anchor.shape[0], xx:xx + anchor.shape[1]]
        valid &= np.max(np.abs(a - albedo[:-1, :-1]), axis=2) < .03
        n = normals[yy:yy + anchor.shape[0], xx:xx + anchor.shape[1]]
        valid &= np.sum(n * normals[:-1, :-1], axis=2) > .95
        d = depth[yy:yy + anchor.shape[0], xx:xx + anchor.shape[1]]
        valid &= np.abs(d - depth[:-1, :-1]) < .02 * np.maximum(1., depth[:-1, :-1])
    floor = .5 / 255.
    fallback = (np.median(np.abs(haar[valid]), axis=0) / .6744897501960817
                if np.count_nonzero(valid) >= 32 else np.full(3, floor))
    fallback = np.maximum(floor, fallback)
    sigma = np.broadcast_to(fallback, encoded.shape).copy()
    estimates = {}
    for mid in np.unique(ids[ids >= 0]):
        selection = valid & (anchor == mid)
        value = (np.median(np.abs(haar[selection]), axis=0) / .6744897501960817
                 if np.count_nonzero(selection) >= 32 else fallback)
        value = np.maximum(floor, value)
        sigma[ids == mid] = value
        estimates[str(int(mid))] = (value * 255.).tolist()
    return sigma, estimates


def denoise_saved_png(input_path, output_path=None, *, strength=.55,
                      detail_strength=.35, iterations=1):
    for name, value in (("strength", strength), ("detail strength", detail_strength)):
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"{name} must be finite and in [0, 1]")
    if not isinstance(iterations, int) or not 1 <= iterations <= 3:
        raise ValueError("PNG denoise iterations must be an integer from 1 to 3")
    source = Path(input_path).resolve()
    output = (Path(output_path).resolve() if output_path else
              source.with_stem(source.stem + "_denoised"))
    if source.suffix.lower() != ".png" or output.suffix.lower() != ".png":
        raise ValueError("Saved-image denoising requires PNG input and output")
    if source == output or source.with_suffix(".json") == output.with_suffix(".json"):
        raise ValueError("Denoised output must differ from the original")
    started = time.perf_counter()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    metadata = json.loads(source.with_suffix(".json").read_text(encoding="utf-8"))
    if metadata.get("tone_mapping") != "Reinhard, then exact sRGB transfer":
        raise ValueError("Unsupported saved-image display transform")
    scene, config, _ = load_scene(config=metadata["scene"]["config"])
    options = RenderOptions(**metadata["options"])
    rgb = np.asarray(Image.open(source).convert("RGB"))
    if rgb.shape != (options.height, options.width, 3):
        raise ValueError("PNG dimensions differ from render metadata")
    exposure = metadata["exposure"]
    linear, jacobian = png_radiance(rgb, exposure)
    if not np.array_equal(np.asarray(display_image(linear, exposure)), rgb):
        raise ValueError("Saved PNG does not round-trip through the renderer's display transform")
    camera = camera_buffer(config, options)
    camera[4, 1] = 0.
    albedo, normals, depth, ids = guides(scene, camera, options.width, options.height, options.textures)
    # Clipping destroys HDR information. Keep such pixels and exclude them
    # from neighbors' kernels rather than guessing a bright radiance halo.
    clipped = np.any(rgb == 255, axis=2)
    ids[clipped] = -1
    sigma, estimates = png_noise(rgb, albedo, normals, depth, ids)
    variance = (sigma * jacobian) ** 2
    color = linear / albedo
    # The existing kernel uses 4-sigma color support. A quarter of the estimated
    # variance narrows that support to 2 sigma, retaining more contrast.
    var = .25 * variance / (albedo * albedo)
    for level in range(iterations):
        color, var = atrous_pass(color, var, normals, depth, ids, 2 ** level)
    filtered = np.maximum(0., color * albedo)
    blend = np.full(ids.shape, strength)
    for mid, material in enumerate(scene.materials):
        if int(material[5]) == 1:
            blend[ids == mid] = min(strength, detail_strength)
        elif int(material[5]) == 2:
            blend[ids == mid] = 0.
    blend[ids < 0] = 0.
    # Retain high-contrast details rather than flattening bright reflections or
    # dark waterline edges. This deliberately also retains some residual noise.
    contrast = np.max(np.abs(linear - filtered) / np.maximum(1e-12, np.sqrt(variance)), axis=2)
    blend *= 1. - .75 * np.clip((contrast - 1.) / 2., 0., 1.)
    result = linear + blend[:, :, None] * (filtered - linear)
    if not np.isfinite(result).all():
        raise ValueError("Non-finite PNG denoising result")
    stats = {"method": "PNG-derived, material/normal/depth-guided a trous",
             "iterations": iterations, "strength": strength,
             "transparent_material_strength_cap": min(strength, detail_strength),
             "color_support_sigma": 2., "contrast_detail_protection": True,
             "clipped_pixels_retained": int(np.count_nonzero(clipped)),
             "radiance_source": "Approximate inverse of quantized 8-bit sRGB/Reinhard PNG",
             "variance_source": "Estimated from same-material 2x2 Haar residuals; not Monte Carlo sample moments",
             "estimated_sigma_srgb_255_by_material": estimates,
             "seconds_including_scene_and_jit": time.perf_counter() - started,
             "additional_path_samples": 0, "biased_filter": True, "raw_render_retained": True}
    save_render(output, result, {**metadata, "denoising": stats,
                                "source": str(source), "source_sha256": source_hash,
                                "source_render_seconds": metadata["render_seconds"]}, exposure)
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError("Original PNG was modified")
    return output, stats
