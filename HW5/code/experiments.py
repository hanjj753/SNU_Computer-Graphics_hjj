"""Reproducible feature ablations and warmed BVH/brute-force comparisons."""

import json
import platform
import statistics
from dataclasses import replace
from pathlib import Path

import numba
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from image_io import contact_sheet, display_image, save_render
from scene import ROOT
from tracer import render


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def feature_details(output_dir, features):
    """Use the same explicit image-space crops for both sides of each pair."""
    regions = {"indirect": (.30, .24, .73, .43), "shadows": (.31, .73, .47, .86),
               "reflections": (.59, .38, .735, .73), "refraction": (.385, .645, .485, .785),
               "textures": (.46, .39, .655, .75), "aa": (.45, .34, .65, .55),
               "absorption": (.385, .675, .485, .785), "dof": (.36, .51, .67, .82)}
    panels, evidence = [], {}
    for name in features:
        bounds = regions[name]
        pair = []
        for stem in ("full", name):
            with Image.open(output_dir / f"{stem}.png") as source:
                box = tuple(round(x * (source.width if i % 2 == 0 else source.height))
                            for i, x in enumerate(bounds))
                crop = source.crop(box).resize((480, 300), Image.Resampling.NEAREST)
            pair.append((f"{name}: {'enabled / baseline' if stem == 'full' else 'comparison'}", crop))
        contact_sheet(pair, output_dir / f"detail_{name}.png", (480, 300), columns=2)
        panels.extend(pair)
        evidence[name] = {"normalized_crop_xyxy": bounds, "resize": "nearest neighbor",
                          "pair": f"detail_{name}.png", "display_adjustment": "none"}
    contact_sheet(panels, output_dir / "details.png", (480, 300), columns=2)
    return evidence


def compare(scene, config, scene_stats, options, output_dir, exposure, features, save_linear=False):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results, panels = {}, []
    feature_options = {"indirect": ("indirect", False), "shadows": ("hard_shadows", True),
                       "reflections": ("reflections", False), "refraction": ("refraction", False),
                       "textures": ("textures", False), "aa": ("antialias", False),
                       "absorption": ("absorption", False), "dof": ("aperture", 0.045)}
    labels = {"indirect": "Without indirect lighting", "shadows": "Hard shadow (light center)",
              "reflections": "Without reflections", "refraction": "Opaque cup and water",
              "textures": "Without box textures", "aa": "Pixel centers (no AA)",
              "absorption": "Without Beer-Lambert absorption", "dof": "Thin lens (radius 0.045)"}
    baseline = None
    cases = [("full", "All features", options)]
    for feature in dict.fromkeys(features):
        key, value = feature_options[feature]
        if getattr(options, key) == value:
            raise ValueError(f"The baseline already has {feature}'s comparison setting; enable it for this experiment")
        cases.append((feature, labels[feature], replace(options, **{key: value})))
    for name, label, variant in cases:
        print(f"Rendering comparison: {label}", flush=True)
        linear, stats = render(scene, config, variant)
        if baseline is None:
            baseline = linear
        stats["linear_rmse_from_full"] = float(np.sqrt(np.mean((linear - baseline) ** 2)))
        stats["scene"] = scene_stats
        path = output_dir / f"{name}.png"
        save_render(path, linear, stats, exposure, save_linear)
        panels.append((label, path))
        results[name] = stats
        print(f"  {stats['render_seconds']:.3f}s; RMSE {stats['linear_rmse_from_full']:.6g}", flush=True)
    contact_sheet(panels, output_dir / "features.png", (options.width, options.height), columns=3)
    details = feature_details(output_dir, list(dict.fromkeys(features))) if features else {}

    reference_panels = []
    for label, path in (("Photograph", ROOT / "pictures" / "Cornell Box.jpg"),
                        ("HW4 - OpenGL", ROOT / "pictures" / "HW4_render.png"),
                        ("HW5 - CPU ray tracing", output_dir / "full.png")):
        if path.exists():
            reference_panels.append((label, path))
    contact_sheet(reference_panels, output_dir / "reference.png", (640, 480), columns=3)
    # All three use the whole frame, with no hidden crop, alignment, or brightness fit.
    _write_json(output_dir / "results.json", {"comparison": "same camera, resolution, spp, seed, exposure",
                                             "reference_note": "whole-frame resize only; HW4 source contains its original HUD",
                                             "feature_details": details,
                                             "cases": results})
    print(f"Saved feature and photograph/HW4 comparisons in {output_dir.resolve()}", flush=True)


def benchmark(scene, config, scene_stats, options, output_dir, exposure, repeats=3, save_linear=False):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    variants = {"bvh": replace(options, use_bvh=True), "brute_force": replace(options, use_bvh=False)}
    runs, images = {name: [] for name in variants}, {}
    # Alternate ordering to reduce systematic thermal/scheduling bias.
    for iteration in range(repeats):
        order = ("bvh", "brute_force") if iteration % 2 == 0 else ("brute_force", "bvh")
        for name in order:
            print(f"Benchmark {iteration + 1}/{repeats}: {name}", flush=True)
            linear, stats = render(scene, config, variants[name])
            runs[name].append(stats)
            images[name] = linear
            print(f"  {stats['render_seconds']:.6f}s; {stats['triangle_tests']:,} triangle tests", flush=True)
    difference = np.abs(images["bvh"] - images["brute_force"])
    equal = bool(np.allclose(images["bvh"], images["brute_force"], rtol=1e-9, atol=1e-10))
    medians = {name: statistics.median(run["render_seconds"] for run in results) for name, results in runs.items()}
    result = {"scene": scene_stats, "runs": runs, "median_render_seconds": medians,
              "speedup": medians["brute_force"] / max(1e-12, medians["bvh"]),
              "bvh_build_seconds": scene_stats["bvh_build_seconds"],
              "bvh_build_plus_median_render_seconds": scene_stats["bvh_build_seconds"] + medians["bvh"],
              "same_image": equal, "linear_max_abs_difference": float(difference.max()),
              "linear_rmse": float(np.sqrt(np.mean(difference ** 2))),
              "timing_note": "wall-clock CPU rendering only; excludes scene loading, BVH construction, JIT/warmup, file I/O",
              "platform": platform.platform(), "python": platform.python_version(),
              "numpy": np.__version__, "numba": numba.__version__}
    _write_json(output_dir / "timings.json", result)
    for name in variants:
        save_render(output_dir / f"{name}.png", images[name], runs[name][-1], exposure, save_linear)
    # Amplified display-space error is diagnostic, never substituted for a render.
    error = np.abs(np.asarray(display_image(images["bvh"], exposure), dtype=float) -
                   np.asarray(display_image(images["brute_force"], exposure), dtype=float))
    Image.fromarray(np.uint8(np.clip(error * 16, 0, 255))).save(output_dir / "difference_x16.png")
    chart = Image.new("RGB", (760, 245), "#16191e")
    draw = ImageDraw.Draw(chart)
    font = ImageFont.load_default(size=17)
    draw.text((24, 20), f"BVH vs brute force - median of {repeats} runs", fill="white", font=font)
    largest = max(medians.values())
    for row, name in enumerate(("bvh", "brute_force")):
        y = 65 + row * 58
        draw.text((24, y + 6), name, fill="white", font=font)
        length = max(1, int(420 * medians[name] / max(1e-12, largest)))
        draw.rectangle((140, y, 140 + length, y + 30), fill="#4fd1a5" if row == 0 else "#8da6ee")
        draw.text((575, y + 6), f"{medians[name]:.5f} s", fill="white", font=font)
    draw.text((24, 204), f"Speedup {result['speedup']:.2f}x; equal images: {equal}; JIT/build/I/O excluded", fill="white", font=font)
    chart.save(output_dir / "timing.png")
    print(f"BVH speedup: {result['speedup']:.2f}x; same image: {equal}; max error: {difference.max():.3g}", flush=True)
    if not equal:
        raise RuntimeError("BVH and brute-force images differ; inspect timings.json and difference_x16.png")
