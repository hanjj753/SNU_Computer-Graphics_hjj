import argparse
import json
import math
import sys
from pathlib import Path

from numba import get_num_threads, set_num_threads

from image_io import save_render
from scene import ROOT, load_scene
from tracer import RenderOptions, render

PRESETS = {
    "preview": dict(width=320, height=240, spp=16, max_depth=12, diffuse_bounces=3, light_samples=4),
    "draft": dict(width=640, height=480, spp=64, max_depth=16, diffuse_bounces=4, light_samples=4),
    "final": dict(width=960, height=720, spp=512, max_depth=24, diffuse_bounces=6, light_samples=4),
}


def _common(parser):
    parser.add_argument("--preset", choices=PRESETS, default="preview")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--spp", type=int, help="camera samples per pixel")
    parser.add_argument("--max-depth", type=int)
    parser.add_argument("--diffuse-bounces", type=int)
    parser.add_argument("--light-samples", type=int)
    parser.add_argument("--threads", type=int, help="Numba CPU workers (default: all available)")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--config", type=Path, help="scene JSON (default: HW5/scene.json)")
    parser.add_argument("--exposure", type=float, help="override display exposure")
    parser.add_argument("--aperture", type=float, help="thin-lens radius, 0 = pinhole")
    parser.add_argument("--focus-distance", type=float)
    parser.add_argument("--no-bvh", action="store_true")
    parser.add_argument("--no-shadows", action="store_true")
    parser.add_argument("--no-reflections", action="store_true")
    parser.add_argument("--no-refraction", action="store_true")
    parser.add_argument("--no-indirect", action="store_true")
    parser.add_argument("--no-textures", action="store_true")
    parser.add_argument("--no-aa", action="store_true", help="reuse pixel centers, retaining lighting samples")
    parser.add_argument("--no-absorption", action="store_true")
    parser.add_argument("--hard-shadows", action="store_true", help="sample only the area light's center")
    parser.add_argument("--save-linear", action="store_true", help="also save linear RGB as .npy")
    parser.add_argument("--quiet", action="store_true")


def make_parser():
    parser = argparse.ArgumentParser(description="HW5: standalone CPU ray tracer (no OpenGL/PyGlet)")
    commands = parser.add_subparsers(dest="command", required=True)
    single = commands.add_parser("render", help="render the Cornell Box")
    _common(single)
    single.add_argument("--output", type=Path, help="default: outputs/cornell_<preset>.png")
    single.add_argument("--pass-spp", type=int, default=8, help="samples per progress/checkpoint pass")
    single.add_argument("--checkpoint", action="store_true", help="save a progressive preview after each pass")
    single.add_argument("--denoise", action="store_true", help="save a guided-filter copy as *_denoised.png; retains raw render")
    single.add_argument("--denoise-strength", type=float, default=0.8,
                        help="filtered fraction in [0,1]; used with --denoise (default: 0.8)")
    single.add_argument("--denoise-iterations", type=int, choices=range(1, 6), default=2,
                        help="a trous passes; used with --denoise (default: 2)")
    compare = commands.add_parser("compare", help="render feature ablations and photograph/HW4 comparison")
    _common(compare)
    compare.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "comparison")
    compare.add_argument("--features", nargs="+", choices=("indirect", "shadows", "reflections", "refraction", "textures", "aa", "absorption", "dof"),
                         default=["indirect", "shadows", "reflections", "refraction", "textures", "aa"])
    benchmark = commands.add_parser("benchmark", help="time identical rays with BVH and brute-force traversal")
    _common(benchmark)
    benchmark.set_defaults(width=128, height=96, spp=4, max_depth=12, light_samples=1, diffuse_bounces=3)
    benchmark.add_argument("--repeats", type=int, default=3)
    benchmark.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "benchmark")
    saved = commands.add_parser("denoise-file", help="gently denoise an existing PNG using its render metadata; no path tracing")
    saved.add_argument("input", type=Path)
    saved.add_argument("--output", type=Path)
    saved.add_argument("--strength", type=float, default=.55)
    saved.add_argument("--detail-strength", type=float, default=.35)
    saved.add_argument("--iterations", type=int, choices=range(1, 4), default=1)
    return parser


def options_from_args(args):
    values = dict(PRESETS[args.preset])
    for key in ("width", "height", "spp", "max_depth", "diffuse_bounces", "light_samples"):
        if getattr(args, key) is not None:
            values[key] = getattr(args, key)
    options = RenderOptions(**values, seed=args.seed, aperture=args.aperture, focus_distance=args.focus_distance)
    for option, flag in (("use_bvh", "no_bvh"), ("shadows", "no_shadows"), ("reflections", "no_reflections"),
                         ("refraction", "no_refraction"), ("indirect", "no_indirect"), ("textures", "no_textures"),
                         ("antialias", "no_aa"), ("absorption", "no_absorption")):
        setattr(options, option, not getattr(args, flag))
    options.hard_shadows = args.hard_shadows
    options.validate()
    return options


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
        argv.insert(0, "render")
    parser = make_parser()
    args = parser.parse_args(argv)
    if args.command == "render" and args.output is None:
        args.output = ROOT / "outputs" / f"cornell_{args.preset}.png"
    try:
        if args.command == "denoise-file":
            from postprocess import denoise_saved_png
            output, stats = denoise_saved_png(args.input, args.output, strength=args.strength,
                                              detail_strength=args.detail_strength,
                                              iterations=args.iterations)
            print(f"Saved {output}\nPNG postprocess {stats['seconds_including_scene_and_jit']:.3f}s; no additional path samples", flush=True)
            return 0
        options = options_from_args(args)
        if args.threads is not None:
            if not 1 <= args.threads <= get_num_threads():
                raise ValueError(f"threads must be between 1 and {get_num_threads()}")
            set_num_threads(args.threads)
        if args.exposure is not None and (args.exposure <= 0 or not math.isfinite(args.exposure)):
            raise ValueError("exposure must be positive and finite")
        if args.command == "render" and args.pass_spp < 1:
            raise ValueError("pass-spp must be positive")
        if args.command == "render" and (not math.isfinite(args.denoise_strength) or not 0 <= args.denoise_strength <= 1):
            raise ValueError("denoise-strength must be finite and in [0, 1]")
        if args.command == "benchmark" and args.repeats < 1:
            raise ValueError("repeats must be positive")
        if not args.quiet:
            print("Loading standalone HW5 scene and building SAH BVH...", flush=True)
        scene, config, scene_stats = load_scene(args.config)
        exposure = args.exposure if args.exposure is not None else config["exposure"]
        if not args.quiet:
            print(f"{scene_stats['triangles']:,} triangles, {scene_stats['bvh_nodes']:,} BVH nodes, "
                  f"{get_num_threads()} CPU threads; first run includes JIT compilation.", flush=True)
        if args.command != "render":
            from experiments import benchmark, compare
            if args.command == "benchmark":
                benchmark(scene, config, scene_stats, options, args.output_dir, exposure, args.repeats, args.save_linear)
            else:
                compare(scene, config, scene_stats, options, args.output_dir, exposure, args.features, args.save_linear)
            return 0

        def progress(done, total, linear, elapsed):
            if not args.quiet:
                print(f"  {done:4d}/{total} spp  {elapsed:7.1f}s", flush=True)
            if args.checkpoint:
                from image_io import display_image
                args.output.parent.mkdir(parents=True, exist_ok=True)
                display_image(linear, exposure).save(args.output.with_stem(args.output.stem + "_progress"))

        aovs = {} if args.denoise else None
        linear, stats = render(scene, config, options, progress=progress, pass_spp=args.pass_spp, aovs=aovs)
        stats["scene"] = scene_stats
        save_render(args.output, linear, stats, exposure, args.save_linear)
        if args.denoise:
            from denoise import denoise
            filtered, filter_stats = denoise(linear, aovs["variance"], scene, config, options,
                                             iterations=args.denoise_iterations,
                                             strength=args.denoise_strength)
            filtered_path = args.output.with_stem(args.output.stem + "_denoised")
            save_render(filtered_path, filtered, {**stats, "denoising": filter_stats}, exposure, args.save_linear)
            print(f"Saved filtered copy: {filtered_path.resolve()}", flush=True)
        print(f"Saved {args.output.resolve()}\n"
              f"Render {stats['render_seconds']:.3f}s; {stats['rays']:,} rays; "
              f"{stats['triangle_tests']:,} triangle tests; warmup {stats['warmup_seconds']:.3f}s", flush=True)
        return 0
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
