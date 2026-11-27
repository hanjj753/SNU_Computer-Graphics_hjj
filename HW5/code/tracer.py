"""CPU Monte Carlo ray tracer: NEE + MIS, coated Phong and dielectric paths.

The loop evaluates the recursive rendering equation without a Python call stack.
No rasterizer, graphics context, GPU renderer, or precomputed lighting is used.
"""

import math
import time
from dataclasses import asdict, dataclass

import numpy as np
from numba import get_num_threads, njit, prange

from bvh import intersect
from sampling import (EPSILON, PI, cosine_direction, dielectric, dot,
                      normalize, phong_direction, power_heuristic,
                      radical_inverse, random_float, reflect, sample_seed)


@dataclass
class RenderOptions:
    width: int = 640
    height: int = 480
    spp: int = 64
    max_depth: int = 16
    diffuse_bounces: int = 4
    light_samples: int = 4
    seed: int = 2026
    use_bvh: bool = True
    shadows: bool = True
    reflections: bool = True
    refraction: bool = True
    indirect: bool = True
    textures: bool = True
    antialias: bool = True
    hard_shadows: bool = False
    absorption: bool = True
    aperture: float | None = None  # lens radius in scene units
    focus_distance: float | None = None

    def validate(self):
        for name in ("width", "height", "spp", "max_depth", "light_samples"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")
        if self.max_depth > 64:
            raise ValueError("max_depth must be at most 64")
        if self.diffuse_bounces < 0:
            raise ValueError("diffuse_bounces cannot be negative")
        if self.aperture is not None and (not math.isfinite(self.aperture) or self.aperture < 0):
            raise ValueError("aperture must be a finite nonnegative lens radius")
        if self.focus_distance is not None and (not math.isfinite(self.focus_distance) or self.focus_distance <= 0):
            raise ValueError("focus_distance must be positive and finite")


@njit(cache=True)
def texture_color(scene, texture, u, v):
    offset, width, height = scene.texture_info[texture]
    x = min(1., max(0., u)) * (width - 1)
    y = (1. - min(1., max(0., v))) * (height - 1)
    x0, y0 = int(x), int(y)
    x1, y1 = min(x0 + 1, width - 1), min(y0 + 1, height - 1)
    tx, ty = x - x0, y - y0
    result = np.empty(3, dtype=np.float64)
    for c in range(3):
        a = scene.texture_pixels[offset + y0 * width + x0, c] * (1 - tx) + scene.texture_pixels[offset + y0 * width + x1, c] * tx
        b = scene.texture_pixels[offset + y1 * width + x0, c] * (1 - tx) + scene.texture_pixels[offset + y1 * width + x1, c] * tx
        result[c] = a * (1 - ty) + b * ty
    return result


@njit(cache=True, inline="always")
def offset_origin(point, geometric_normal, direction):
    sign = 1.0 if dot(geometric_normal, direction) >= 0.0 else -1.0
    return (point[0] + geometric_normal[0] * EPSILON * 4 * sign,
            point[1] + geometric_normal[1] * EPSILON * 4 * sign,
            point[2] + geometric_normal[2] * EPSILON * 4 * sign)


@njit(cache=True)
def medium_transition(media, size, material_id, entering, materials):
    """Resolve IORs and the stack slot to remove on a transmitted exit."""
    eta_i = materials[media[size - 1], 6] if size else 1.0
    if entering:
        return eta_i, materials[material_id, 6], -1
    remove = -1
    for j in range(size - 1, -1, -1):
        if media[j] == material_id:
            remove = j
            break
    if remove >= 0:
        # Removing a medium under an overlapping top does not change the top IOR.
        top = size - 1 if remove != size - 1 else size - 2
        eta_t = materials[media[top], 6] if top >= 0 else 1.0
    else:
        eta_i, eta_t = materials[material_id, 6], eta_i
    return eta_i, eta_t, remove


@njit(cache=True, inline="always")
def update_media(media, size, material_id, entering, remove):
    if entering:
        media[size] = material_id
        size += 1
    elif remove >= 0:
        for j in range(remove, size - 1):
            media[j] = media[j + 1]
        size -= 1
    return size


@njit(cache=True)
def shadow_transmittance(origin, direction, distance, scene, flags, initial_media, initial_size):
    """Colored visibility along a straight light connection.

    Fresnel and Beer–Lambert account for thin plastic and water. Refractive
    bending of shadow paths (focused caustics) is intentionally not approximated
    by changing direction: that would no longer connect to the light sample.
    """
    trans = np.ones(3, dtype=np.float64)
    media = initial_media.copy()
    size, remaining, tests, rays = initial_size, distance, 0, 0
    for _ in range(64):
        t, hit, _, _, count = intersect(origin, direction, scene, flags[0] != 0, remaining)
        tests += count
        rays += 1
        segment = min(t, remaining)
        if size > 0 and flags[8]:
            for c in range(3):
                trans[c] *= math.exp(-scene.materials[media[size - 1], 7 + c] * segment)
        if hit < 0:
            return trans, tests, rays
        mid = scene.material_ids[hit]
        if int(scene.materials[mid, 5]) != 1 or not flags[3]:
            return np.zeros(3), tests, rays
        gn = scene.geometric_normals[hit]
        entering = dot(direction, gn) < 0
        n = (gn[0], gn[1], gn[2]) if entering else (-gn[0], -gn[1], -gn[2])
        eta_i, eta_t, remove = medium_transition(media, size, mid, entering, scene.materials)
        fresnel, _, tir = dielectric(direction, n, eta_i, eta_t)
        if tir:
            return np.zeros(3), tests, rays
        if not flags[2]:
            fresnel = 0.0
        trans *= (1.0 - fresnel) * (1.0 - scene.materials[mid, 14])
        size = update_media(media, size, mid, entering, remove)
        # Advance along the same light connection, preserving its exact endpoint.
        advance = t + EPSILON * 4
        origin = (origin[0] + direction[0] * advance,
                  origin[1] + direction[1] * advance,
                  origin[2] + direction[2] * advance)
        remaining -= advance
        if remaining <= EPSILON:
            return trans, tests, rays
    return np.zeros(3), tests, rays


@njit(cache=True, inline="always")
def bsdf_pdf(normal, reflected, wi, ks, exponent, specular_probability):
    diffuse_pdf = max(0.0, dot(normal, wi)) / PI
    glossy_pdf = (exponent + 1.0) / (2.0 * PI) * max(0.0, dot(reflected, wi)) ** exponent
    return (1.0 - specular_probability) * diffuse_pdf + specular_probability * glossy_pdf


@njit(cache=True, inline="always")
def brdf_channel(albedo, ks, exponent, reflected_cosine):
    # Energy-conserving Lambert + normalized modified Phong.
    return albedo * (1.0 - ks) / PI + ks * (exponent + 2.0) / (2.0 * PI) * reflected_cosine ** exponent


@njit(cache=True, inline="always")
def direct_brdf(albedo, ks, exponent, reflected_cosine, mis_weight, diffuse_continuation):
    diffuse = albedo * (1.0 - ks) / PI
    glossy = ks * (exponent + 2.0) / (2.0 * PI) * reflected_cosine ** exponent
    # A glossy-only continuation cannot provide the diffuse part of the MIS
    # estimator. Its direct-light sample must retain the full Lambert term.
    return ((diffuse + glossy) * mis_weight if diffuse_continuation else
            diffuse + glossy * mis_weight)


@njit(cache=True)
def trace_path(origin, direction, scene, flags, max_depth, diffuse_limit, light_samples, state):
    radiance = np.zeros(3, dtype=np.float64)
    throughput = np.ones(3, dtype=np.float64)
    media = np.empty(max_depth + 68, dtype=np.int32)
    media_size = 0
    previous_delta, previous_pdf, previous_samples = True, 0.0, 1
    diffuse_depth, ray_count, triangle_tests = 0, 0, 0
    eta_scale = 1.0
    for depth in range(max_depth):
        t, hit, u, v, tests = intersect(origin, direction, scene, flags[0] != 0)
        ray_count += 1
        triangle_tests += tests
        if hit < 0:
            break  # black environment, matching the photographed enclosure
        if media_size > 0 and flags[8]:
            for c in range(3):
                throughput[c] *= math.exp(-scene.materials[media[media_size - 1], 7 + c] * t)
        mid = scene.material_ids[hit]
        mat = scene.materials[mid]
        point = (origin[0] + direction[0] * t, origin[1] + direction[1] * t,
                 origin[2] + direction[2] * t)
        gn = scene.geometric_normals[hit]
        entering = dot(direction, gn) < 0.0
        geometric_normal = (gn[0], gn[1], gn[2]) if entering else (-gn[0], -gn[1], -gn[2])
        w = 1.0 - u - v
        ns = scene.normals[hit]
        normal = normalize((ns[0, 0] * w + ns[1, 0] * u + ns[2, 0] * v,
                            ns[0, 1] * w + ns[1, 1] * u + ns[2, 1] * v,
                            ns[0, 2] * w + ns[1, 2] * u + ns[2, 2] * v))
        if not entering:
            normal = (-normal[0], -normal[1], -normal[2])
        if dot(normal, direction) >= -1e-5:
            normal = geometric_normal
        kind = int(mat[5])
        if kind == 2:
            if entering:
                weight = 1.0
                if not previous_delta:
                    light_pdf = t * t / max(1e-20, abs(direction[1]) * scene.light[3] * scene.light[4])
                    weight = power_heuristic(previous_pdf, previous_samples * light_pdf)
                    if flags[7]:
                        weight = 0.0  # center-light ablation already estimates this term
                for c in range(3):
                    radiance[c] += throughput[c] * mat[11 + c] * weight
            break

        diffuse_interface = False
        if kind == 1 and flags[3]:
            # A small Lambert reflection mixture models the observed cloudy cup.
            # It is an explicit surface model, not bulk multiple scattering.
            state, mixture_coin = random_float(state)
            diffuse_interface = mixture_coin < mat[14]
        if kind == 1 and flags[3] and not diffuse_interface:
            eta_i, eta_t, remove = medium_transition(media, media_size, mid, entering, scene.materials)
            fresnel, transmitted, tir = dielectric(direction, normal, eta_i, eta_t)
            if not tir and dot(transmitted, geometric_normal) >= 0.0:
                normal = geometric_normal
                fresnel, transmitted, tir = dielectric(direction, normal, eta_i, eta_t)
            if not flags[2] and not tir:
                fresnel = 0.0
            state, coin = random_float(state)
            if coin < fresnel or tir:
                direction = reflect(direction, normal)
                # A smooth normal can reflect under the actual polygon at a seam.
                if dot(direction, geometric_normal) <= 0:
                    direction = reflect(direction, geometric_normal)
            else:
                direction = transmitted
                media_size = update_media(media, media_size, mid, entering, remove)
                ratio = (eta_i / eta_t) ** 2
                throughput *= ratio
                eta_scale /= ratio
            origin = offset_origin(point, gn, direction)
            previous_delta, previous_pdf = True, 0.0
            continue

        albedo = mat[:3].copy()
        if kind == 1 and not diffuse_interface:  # opaque-material ablation
            albedo[0], albedo[1], albedo[2] = 0.65, 0.68, 0.72
        if flags[5] and int(mat[10]) >= 0:
            uv = scene.uvs[hit]
            tu, tv = uv[0, 0] * w + uv[1, 0] * u + uv[2, 0] * v, uv[0, 1] * w + uv[1, 1] * u + uv[2, 1] * v
            albedo *= texture_color(scene, int(mat[10]), tu, tv)
        ks = mat[3] if flags[2] else 0.0
        exponent = mat[4]
        reflected = normalize(reflect(direction, normal))
        can_diffuse = flags[4] != 0 and diffuse_depth < diffuse_limit
        # Use the same continuation distribution for direct-light MIS weights.
        p_spec = min(0.8, max(0.1, ks)) if ks > 0.0 else 0.0
        if not can_diffuse:
            p_spec = 1.0 if ks > 0.0 else 0.0
        can_continue = depth + 1 < max_depth and (can_diffuse or ks > 0)
        direct_samples = light_samples if depth == 0 else 1
        side = int(math.sqrt(direct_samples))
        for sample in range(direct_samples):
            state, a = random_float(state)
            state, b = random_float(state)
            if flags[7]:
                a, b = 0.5, 0.5
            elif side * side == direct_samples:
                a, b = (sample % side + a) / side, (sample // side + b) / side
            lx = scene.light[0] + (a - 0.5) * scene.light[3]
            ly = scene.light[1]
            lz = scene.light[2] + (b - 0.5) * scene.light[4]
            wi = (lx - point[0], ly - point[1], lz - point[2])
            distance2 = dot(wi, wi)
            distance = math.sqrt(distance2)
            wi = (wi[0] / distance, wi[1] / distance, wi[2] / distance)
            cosine, light_cosine = max(0.0, dot(normal, wi)), max(0.0, wi[1])
            if cosine <= 0 or light_cosine <= 0 or dot(geometric_normal, wi) <= 0:
                continue
            visibility = np.ones(3)
            if flags[1]:
                # Advance on the connection itself so shadow and MIS endpoints agree.
                shadow_origin = (point[0] + wi[0] * EPSILON * 4,
                                 point[1] + wi[1] * EPSILON * 4,
                                 point[2] + wi[2] * EPSILON * 4)
                visibility, count, rays = shadow_transmittance(shadow_origin, wi, distance - EPSILON * 8,
                                                               scene, flags, media, media_size)
                triangle_tests += count
                ray_count += rays
            light_pdf = distance2 / (light_cosine * scene.light[3] * scene.light[4])
            pdf = bsdf_pdf(normal, reflected, wi, ks, exponent, p_spec)
            # If diffuse paths are disabled, only glossy continuation is sampled.
            if not can_diffuse:
                pdf = (exponent + 1.0) / (2.0 * PI) * max(0., dot(reflected, wi)) ** exponent if ks > 0 else 0.
            weight = power_heuristic(direct_samples * light_pdf, pdf) if can_continue and not flags[7] else 1.0
            spec_cos = max(0.0, dot(reflected, wi))
            for c in range(3):
                brdf = direct_brdf(albedo[c], ks, exponent, spec_cos, weight, can_diffuse)
                radiance[c] += throughput[c] * brdf * scene.light[5 + c] * visibility[c] * cosine / (light_pdf * direct_samples)
        if not can_continue:
            break
        state, coin = random_float(state)
        state, a = random_float(state)
        state, b = random_float(state)
        if coin < p_spec:
            new_direction = phong_direction(reflected, exponent, a, b)
        else:
            new_direction = cosine_direction(normal, a, b)
            diffuse_depth += 1
        cosine = max(0.0, dot(normal, new_direction))
        if cosine <= 0 or dot(geometric_normal, new_direction) <= 0:
            break
        pdf = bsdf_pdf(normal, reflected, new_direction, ks, exponent, p_spec)
        glossy = max(0.0, dot(reflected, new_direction))
        for c in range(3):
            brdf = brdf_channel(albedo[c], ks, exponent, glossy)
            if not can_diffuse:
                brdf = ks * (exponent + 2.0) / (2.0 * PI) * glossy ** exponent
            throughput[c] *= brdf * cosine / max(1e-30, pdf)
        previous_delta, previous_pdf, previous_samples = False, pdf, direct_samples
        direction = new_direction
        origin = offset_origin(point, gn, direction)
        if depth >= 4:
            survival = min(0.95, max(0.05, max(throughput[0], throughput[1], throughput[2]) * eta_scale))
            state, coin = random_float(state)
            if coin > survival:
                break
            throughput /= survival
    return radiance, ray_count, triangle_tests


def camera_buffer(config, options):
    cam = config["camera"]
    eye, target, up = np.array(cam["eye"]), np.array(cam["target"]), np.array(cam["up"])
    forward = target - eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    aperture = options.aperture if options.aperture is not None else cam.get("aperture", 0.0)
    focus = options.focus_distance if options.focus_distance is not None else cam.get("focus_distance", np.linalg.norm(target - eye))
    return np.asarray([eye, forward, right, up,
                       [math.tan(math.radians(cam["fov"]) / 2), aperture, focus]])


@njit(cache=True, inline="always")
def camera_ray(camera, width, height, x, y, jx, jy, lens_u, lens_v):
    scale = camera[4, 0]
    sx = (2.0 * (x + jx) / width - 1.0) * width / height * scale
    sy = (1.0 - 2.0 * (y + jy) / height) * scale
    d = normalize((camera[1, 0] + sx * camera[2, 0] + sy * camera[3, 0],
                   camera[1, 1] + sx * camera[2, 1] + sy * camera[3, 1],
                   camera[1, 2] + sx * camera[2, 2] + sy * camera[3, 2]))
    origin = (camera[0, 0], camera[0, 1], camera[0, 2])
    if camera[4, 1] > 0.0:
        r, angle = camera[4, 1] * math.sqrt(lens_u), 2.0 * PI * lens_v
        dx, dy = r * math.cos(angle), r * math.sin(angle)
        distance = camera[4, 2] / dot(d, camera[1])
        focus = (origin[0] + d[0] * distance, origin[1] + d[1] * distance, origin[2] + d[2] * distance)
        origin = (origin[0] + dx * camera[2, 0] + dy * camera[3, 0],
                  origin[1] + dx * camera[2, 1] + dy * camera[3, 1],
                  origin[2] + dx * camera[2, 2] + dy * camera[3, 2])
        d = normalize((focus[0] - origin[0], focus[1] - origin[1], focus[2] - origin[2]))
    return origin, d


@njit(cache=True, parallel=True)
def render_pass(scene, camera, flags, width, height, total_spp, start, stop,
                max_depth, diffuse_limit, light_samples, seed, image, moments, counters):
    side = int(math.sqrt(total_spp))
    for pixel in prange(width * height):
        x, y = pixel % width, pixel // width
        for sample in range(start, stop):
            state = sample_seed(pixel, sample, seed)
            state, a = random_float(state)
            state, b = random_float(state)
            if flags[6]:
                if side * side == total_spp:
                    jx, jy = (sample % side + a) / side, (sample // side + b) / side
                else:
                    jx, jy = a, (radical_inverse(sample) + b) % 1.0
            else:
                jx, jy = 0.5, 0.5
            state, lu = random_float(state)
            state, lv = random_float(state)
            origin, direction = camera_ray(camera, width, height, x, y, jx, jy, lu, lv)
            color, rays, tests = trace_path(origin, direction, scene, flags, max_depth, diffuse_limit, light_samples, state)
            for c in range(3):
                image[y, x, c] += color[c]
                moments[y, x, c] += color[c] * color[c]
            counters[pixel, 0] += rays
            counters[pixel, 1] += tests


def render(scene, config, options, progress=None, pass_spp=8, aovs=None):
    options.validate()
    if pass_spp < 1:
        raise ValueError("pass_spp must be positive")
    camera = camera_buffer(config, options)
    flags = np.asarray([options.use_bvh, options.shadows, options.reflections, options.refraction,
                        options.indirect, options.textures, options.antialias, options.hard_shadows,
                        options.absorption], dtype=np.int64)
    # Compile/warm this exact signature outside measured render time.
    warm_started = time.perf_counter()
    render_pass(scene, camera, flags, 1, 1, 1, 0, 1, min(options.max_depth, 2),
                options.diffuse_bounces, options.light_samples, options.seed,
                np.zeros((1, 1, 3)), np.zeros((1, 1, 3)), np.zeros((1, 2), dtype=np.int64))
    warm_seconds = time.perf_counter() - warm_started
    image = np.zeros((options.height, options.width, 3), dtype=np.float64)
    moments = np.zeros_like(image)
    counters = np.zeros((options.width * options.height, 2), dtype=np.int64)
    started = time.perf_counter()
    render_seconds = 0.0
    for first in range(0, options.spp, pass_spp):
        stop = min(first + pass_spp, options.spp)
        pass_started = time.perf_counter()
        render_pass(scene, camera, flags, options.width, options.height, options.spp, first, stop,
                    options.max_depth, options.diffuse_bounces, options.light_samples,
                    options.seed, image, moments, counters)
        render_seconds += time.perf_counter() - pass_started
        if progress:
            progress(stop, options.spp, image / stop, time.perf_counter() - started)
    linear = image / options.spp
    if aovs is not None:
        aovs["variance"] = np.maximum(0., moments / options.spp - linear * linear) / max(1, options.spp - 1)
    if not np.isfinite(linear).all():
        raise RuntimeError("Non-finite radiance encountered")
    stats = {"options": asdict(options), "threads": get_num_threads(),
             "warmup_seconds": warm_seconds, "render_seconds": render_seconds,
             "elapsed_seconds": time.perf_counter() - started,
             "rays": int(counters[:, 0].sum()), "triangle_tests": int(counters[:, 1].sum()),
             "linear_mean": linear.mean(axis=(0, 1)).tolist(), "linear_max": float(linear.max())}
    stats["rays_per_second"] = stats["rays"] / max(render_seconds, 1e-12)
    return linear, stats
