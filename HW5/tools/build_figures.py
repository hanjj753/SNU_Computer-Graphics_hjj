"""Make report figures from measured results (optional: matplotlib)."""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
sys.path.insert(0, str(ROOT / "tests"))

from image_io import contact_sheet
from sampling import normalize
from scene import load_scene
from test_raytracer import diagnostic_scene
from tracer import shadow_transmittance


def build():
    assets = ROOT / "report/assets"
    assets.mkdir(parents=True, exist_ok=True)
    out = ROOT / "outputs"
    contact_sheet([("Photograph", ROOT / "pictures/Cornell Box.jpg"),
                   ("HW4 - OpenGL", ROOT / "pictures/HW4_render.png"),
                   ("HW5 - CPU ray tracing + denoise", out / "cornell_denoised.png")],
                  out / "reference.png", (640, 480), 3)
    contact_sheet([("Photograph", ROOT / "pictures/Cornell Box.jpg"),
                   ("HW5 render (denoised)", out / "cornell_denoised.png")],
                  out / "photo_vs_render.png", (960, 720), 2)
    contact_sheet([("Raw ray tracing - 512 spp", out / "cornell.png"),
                   ("Guided denoising (same samples)", out / "cornell_denoised.png")],
                  out / "denoising_comparison.png", (640, 480), 2)
    crops = []
    for label, name in (("Raw ray tracing - 512 spp", "cornell.png"),
                        ("Guided denoising", "cornell_denoised.png")):
        with Image.open(out / name) as source:
            box = (round(source.width * .275), round(source.height * .22),
                   round(source.width * .745), round(source.height * .87))
            crops.append((label, source.crop(box).copy()))
    contact_sheet(crops, assets / "final_detail.png", (480, 480), 2)
    timings = json.loads((out / "benchmark/timings.json").read_text(encoding="utf-8"))
    values = [timings["median_render_seconds"]["bvh"], timings["bvh_build_plus_median_render_seconds"],
              timings["median_render_seconds"]["brute_force"]]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False,
                         "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(7.5, 2.5), layout="constrained")
    ax.barh(["BVH traversal", "BVH build + render", "Brute-force render"], values,
            color=["#147D92", "#D2A046", "#4D5F83"])
    ax.invert_yaxis()
    ax.set_xlabel("Wall-clock seconds (median of 3 renders)")
    ax.set_xlim(0, max(values) * 1.26)
    for y, value in enumerate(values):
        ax.text(value + max(values) * .02, y, f"{value:.5f} s", va="center")
    fig.savefig(assets / "bvh_timing.png", dpi=180)
    plt.close(fig)

    # A separate geometry diagnostic, explicitly distinct from the Cornell Box:
    # square area light at y=2; opaque quad at y=1; receiver line at y=0.
    base, _, _ = load_scene()
    mats = np.zeros((1, 15))
    mats[0, 6], mats[0, 10] = 1., -1.
    scene = diagnostic_scene(base, [([[-.35, 1., -.4], [.35, 1., -.4],
                                      [.35, 1., .4], [-.35, 1., .4]], 0)], mats)
    flags = np.array([1, 1, 1, 1, 0, 1, 0, 0, 1], dtype=np.int64)
    xvalues = np.linspace(-1.4, 1.4, 161)
    soft, hard = [], []
    media = np.empty(68, dtype=np.int32)
    for x in xvalues:
        receiver = np.array([x, 0., 0.])
        total = 0.
        for i in range(64):
            for j in range(4):
                target = np.array([(i + .5) / 64 - .5, 2., (j + .5) / 4 - .5])
                d = target - receiver
                trans, _, _ = shadow_transmittance(tuple(receiver), normalize(tuple(d)), float(np.linalg.norm(d)),
                                                   scene, flags, media, 0)
                total += trans[0]
        soft.append(total / 256)
        d = np.array([0., 2., 0.]) - receiver
        trans, _, _ = shadow_transmittance(tuple(receiver), normalize(tuple(d)), float(np.linalg.norm(d)),
                                           scene, flags, media, 0)
        hard.append(trans[0])
    overlap = np.maximum(0., np.minimum(.5, .7 - xvalues) - np.maximum(-.5, -.7 - xvalues))
    analytic = 1. - overlap
    maximum_error = float(np.max(np.abs(np.asarray(soft) - analytic)))
    fig, ax = plt.subplots(figsize=(7.5, 2.8), layout="constrained")
    ax.axvspan(-.2, .2, color="#DCE4EC", alpha=.8, label="Umbra")
    ax.plot(xvalues, hard, ":", color="#727E8D", label="Light-center shadow ray")
    ax.plot(xvalues, analytic, color="#147D92", lw=2, label="Analytic area-light visibility")
    ax.scatter(xvalues[::4], np.asarray(soft)[::4], s=13, color="#C88825", zorder=4,
               label="Traced: 256 light samples")
    ax.set(xlabel="Receiver x (scene units)", ylabel="Visible light fraction", ylim=(-.05, 1.1))
    ax.legend(loc="upper center", ncol=2, fontsize=8)
    fig.savefig(assets / "penumbra_validation.png", dpi=180)
    plt.close(fig)
    evidence = {"scene": "independent planar-occluder diagnostic, not the Cornell render",
                "light_y": 2., "occluder_y": 1., "occluder_half_width": .35,
                "receiver_y": 0., "area_light_width": 1., "samples_per_receiver": 256,
                "maximum_visibility_error": maximum_error, "umbra_abs_x_max": .2,
                "penumbra_abs_x_range": [.2, 1.2], "passed": maximum_error <= 1 / 64}
    (out / "penumbra_validation.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Built figures; penumbra visibility maximum error: {maximum_error:.6f}")


if __name__ == "__main__":
    build()
