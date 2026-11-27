"""Standalone HW5 assets, OBJ loading, physical materials and scene assembly.

No OpenGL/pyglet imports or sibling HW directories are needed at runtime.
All color/absorption values in scene.json are fitted scene parameters, not
measured reflectance or material data. One scene unit is approximately 10 cm.
"""

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import numpy as np
from PIL import Image

from bvh import build_bvh
from cup_geometry import build_cup_mesh
from water_surface import build_water_volume

ROOT = Path(__file__).resolve().parent.parent

# materials: albedo RGB, coating Ks, Phong exponent, type, IOR,
#            absorption RGB, texture ID, emitted radiance RGB, diffuse interface mix.
OPAQUE, DIELECTRIC, EMITTER = 0, 1, 2


class SceneBuffers(NamedTuple):
    v0: np.ndarray
    e1: np.ndarray
    e2: np.ndarray
    normals: np.ndarray
    uvs: np.ndarray
    geometric_normals: np.ndarray
    material_ids: np.ndarray
    bvh_min: np.ndarray
    bvh_max: np.ndarray
    bvh_nodes: np.ndarray
    bvh_indices: np.ndarray
    materials: np.ndarray
    texture_pixels: np.ndarray
    texture_info: np.ndarray
    light: np.ndarray  # center xyz, width, depth, radiance rgb


@dataclass
class Mesh:
    name: str
    material: str
    positions: np.ndarray
    normals: np.ndarray


def load_obj(path):
    """Read OBJ positions/normals and triangulate polygons, including negative indices.

    Box UVs are rebuilt separately to preserve HW4's per-face texture layout.
    """
    vertices, normals, groups = [], [], {}
    name, material = "default", ""

    def index(value, values):
        i = int(value)
        return values[i - 1 if i > 0 else i]

    for line in Path(path).read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        kind = fields[0]
        if kind == "v":
            vertices.append(tuple(map(float, fields[1:4])))
        elif kind == "vn":
            normals.append(tuple(map(float, fields[1:4])))
        elif kind in ("g", "o"):
            name = fields[1]
        elif kind == "usemtl":
            material = fields[1]
        elif kind == "f":
            tokens = [token.split("/") for token in fields[1:]]
            positions, ns = groups.setdefault((name, material), ([], []))
            for j in range(1, len(tokens) - 1):
                triangle = [tokens[0], tokens[j], tokens[j + 1]]
                points = np.asarray([index(t[0], vertices) for t in triangle])
                face_n = np.cross(points[1] - points[0], points[2] - points[0])
                face_n /= max(1e-20, np.linalg.norm(face_n))
                positions.extend(points)
                ns.extend([index(t[2], normals) if len(t) > 2 and t[2] else face_n for t in triangle])
    return [Mesh(name, mat, np.asarray(p).reshape(-1, 3, 3), np.asarray(n).reshape(-1, 3, 3))
            for (name, mat), (p, n) in groups.items()]


def _box_faces(mesh):
    """Rebuild the six beveled faces, preserving HW4's affine texture mapping."""
    a = math.radians(30)
    short = np.array([math.cos(a), 0.0, -math.sin(a)])
    up = np.array([0.0, 1.0, 0.0])
    long = np.array([-math.sin(a), 0.0, -math.cos(a)])
    axes = np.stack([short, up, long])
    flat = mesh.positions.reshape(-1, 3)
    local = flat @ axes.T
    lo, hi = local.min(axis=0), local.max(axis=0)
    half = (hi - lo) * 0.5
    center = (hi + lo) * 0.5 @ axes
    origin = np.array([2.10, 0.0, -0.50])
    faces = {}
    for points, normals in zip(mesh.positions, mesh.normals):
        normal = normals[0]
        s, t, h = ((points - origin) @ short / 0.60,
                   (points - origin) @ long / 2.10, points[:, 1] / 2.50)
        if normal[1] > 0.9:
            face, uv = "top", np.stack([s, t], axis=1)
        elif normal[1] < -0.9:
            face, uv = "bottom", np.stack([s, 1.0 - t], axis=1)
        elif np.dot(normal, short) < -0.9:
            face, uv = "front", np.stack([h, t], axis=1)  # HW4: rotate (1-t,h) once
        elif np.dot(normal, short) > 0.9:
            face, uv = "back", np.stack([t, h], axis=1)
        elif np.dot(normal, long) < 0:
            face, uv = "right", np.stack([s, h], axis=1)
        else:
            face, uv = "left", np.stack([1.0 - s, h], axis=1)
        if face in faces:
            continue
        # Recover origin and tangents from the first triangle's UVs.
        uv = np.clip(uv, 0, 1)
        uv_edges = np.stack([uv[1] - uv[0], uv[2] - uv[0]])
        du, dv = np.linalg.solve(uv_edges, np.stack([points[1] - points[0], points[2] - points[0]]))
        corner = points[0] - du * uv[0, 0] - dv * uv[0, 1]
        radius = 0.025

        def samples(length):
            edge = radius / length
            values = list(np.linspace(0, 1, 17))
            values += [edge * i / 4 for i in range(5)]
            values += [1 - edge * i / 4 for i in range(5)]
            return np.unique(np.round(values, 10))

        us, vs = samples(np.linalg.norm(du)), samples(np.linalg.norm(dv))
        vertices, vertex_normals, texcoords = [], [], []
        for u in us:
            for v in vs:
                p = corner + du * u + dv * v
                q = (p - center) @ axes.T
                q = np.where(np.abs(np.abs(q) - half) < 2e-5, np.sign(q) * half, q)
                inner = np.clip(q, -half + radius, half - radius)
                delta = q - inner
                delta /= max(1e-20, np.linalg.norm(delta))
                p = center + (inner + radius * delta) @ axes
                n = delta @ axes
                if face == "front":
                    eu, ev = radius / np.linalg.norm(du), radius / np.linalg.norm(dv)
                    if eu < u < 1 - eu and ev < v < 1 - ev:
                        x, y = (u - eu) / (1 - 2 * eu), (v - ev) / (1 - 2 * ev)
                        height = 0.008 * math.sin(math.pi * x) ** 2 * math.sin(math.pi * y) ** 2
                        dhdu = 0.008 * math.pi * math.sin(2 * math.pi * x) * math.sin(math.pi * y) ** 2 / (1 - 2 * eu)
                        dhdv = 0.008 * math.pi * math.sin(2 * math.pi * y) * math.sin(math.pi * x) ** 2 / (1 - 2 * ev)
                        p += normal * height
                        n = np.cross(du + normal * dhdu, dv + normal * dhdv)
                        if n @ normal < 0:
                            n = -n
                        n /= np.linalg.norm(n)
                # Shared deformation on all faces keeps the top ridge watertight.
                x = np.clip((p - center) @ short / half[0], -1, 1)
                arch = math.cos(math.pi * x / 2) ** 2
                arch_dx = -math.pi * math.sin(math.pi * x) / (2 * half[0])
                blend_t = np.clip(((p - center) @ up - half[1] + 0.1) / 0.1, 0, 1)
                blend = blend_t * blend_t * (3 - 2 * blend_t)
                hx = 0.03 * arch_dx * blend
                hy = 0.03 * arch * 6 * blend_t * (1 - blend_t) / 0.1
                p += up * (0.03 * arch * blend)
                ny = n @ up
                n = n + up * (ny / (1 + hy) - ny) - short * (hx * ny / (1 + hy))
                n /= np.linalg.norm(n)
                vertices.append(p)
                vertex_normals.append(n)
                texcoords.append((u, v))
        indices = []
        for i in range(len(us) - 1):
            for j in range(len(vs) - 1):
                k, stride = i * len(vs) + j, len(vs)
                indices.extend([(k, k + stride, k + stride + 1), (k, k + stride + 1, k + 1)])
        indices = np.asarray(indices)
        if np.cross(du, dv) @ normal < 0:
            indices = indices[:, ::-1]
        faces[face] = (np.asarray(vertices)[indices], np.asarray(vertex_normals)[indices],
                       np.asarray(texcoords)[indices])
    return faces


def srgb_to_linear(color):
    return np.where(color <= 0.04045, color / 12.92, ((color + 0.055) / 1.055) ** 2.4)


def validate_config(config):
    def vector(value, name, nonnegative=False):
        array = np.asarray(value, dtype=float)
        if array.shape != (3,) or not np.isfinite(array).all() or (nonnegative and (array < 0).any()):
            raise ValueError(f"{name} must be three finite {'nonnegative ' if nonnegative else ''}numbers")
        return array

    camera, light = config["camera"], config["light"]
    eye = vector(camera["eye"], "camera.eye")
    target = vector(camera["target"], "camera.target")
    up = vector(camera["up"], "camera.up")
    if np.linalg.norm(np.cross(target - eye, up)) < 1e-10:
        raise ValueError("Camera eye/target must differ and up must not be parallel to the view")
    if not 0 < camera["fov"] < 179:
        raise ValueError("camera.fov must be between 0 and 179 degrees")
    if not math.isfinite(camera.get("aperture", 0)) or camera.get("aperture", 0) < 0:
        raise ValueError("camera.aperture must be a finite nonnegative lens radius")
    if not math.isfinite(camera.get("focus_distance", 1)) or camera.get("focus_distance", 1) <= 0:
        raise ValueError("camera.focus_distance must be positive and finite")
    vector(light["center"], "light.center")
    vector(light["radiance"], "light.radiance", nonnegative=True)
    for name, value in (("exposure", config["exposure"]), ("light.width", light["width"]), ("light.depth", light["depth"])):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be positive and finite")
    for name, material in config["materials"].items():
        color = vector(material.get("color", [1, 1, 1]), name + ".color", nonnegative=True)
        if (color > 1).any():
            raise ValueError(f"{name}.color cannot exceed 1 (linear reflectance)")
        vector(material.get("absorption", [0, 0, 0]), name + ".absorption", nonnegative=True)
        for key in ("specular", "diffuse_interface"):
            if not 0 <= material.get(key, 0) <= 1:
                raise ValueError(f"{name}.{key} must be in [0, 1]")
        if not math.isfinite(material.get("ior", 1)) or material.get("ior", 1) <= 0:
            raise ValueError(f"{name}.ior must be positive and finite")
        if not math.isfinite(material.get("exponent", 24)) or material.get("exponent", 24) < 0:
            raise ValueError(f"{name}.exponent must be finite and nonnegative")


def load_scene(config_path=None):
    started = time.perf_counter()
    config_path = Path(config_path) if config_path else ROOT / "scene.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validate_config(config)
    source = load_obj(ROOT / "assets" / "models" / "cornell_scene.obj")
    config_mats = config["materials"]
    materials, material_names, texture_pixels, texture_info = [], [], [], []
    positions, normals, uvs, material_ids = [], [], [], []
    object_counts = {}
    texture_offset = 0

    def material(name, kind=OPAQUE, texture=None):
        nonlocal texture_offset
        settings = config_mats[name if not name.startswith("box_") else "box"]
        data = np.zeros(15, dtype=np.float64)
        data[:3] = settings.get("color", [1, 1, 1])
        data[3:7] = settings.get("specular", 0), settings.get("exponent", 24), kind, settings.get("ior", 1.0)
        data[7:10] = settings.get("absorption", [0, 0, 0])
        data[14] = settings.get("diffuse_interface", 0.0)
        data[10] = -1
        if texture is not None:
            path = ROOT / "assets" / "textures" / texture
            with Image.open(path) as image:
                image = image.convert("RGB")
                image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                pixels = srgb_to_linear(np.asarray(image, dtype=np.float32) / 255.0)
            height, width = pixels.shape[:2]
            data[10] = len(texture_info)
            texture_info.append([texture_offset, width, height])
            texture_offset += width * height
            texture_pixels.append(pixels.reshape(-1, 3))
        materials.append(data)
        material_names.append(name)
        return len(materials) - 1

    ids = {name: material(name) for name in ("back", "floor", "ceiling", "red", "green", "mint", "ground")}
    ids["plastic"] = material("plastic", DIELECTRIC)
    ids["water"] = material("water", DIELECTRIC)
    for face in ("front", "back", "right", "left", "top", "bottom"):
        ids["box_" + face] = material("box_" + face, texture=face + (".jpg" if face == "front" else ".png"))
        if face == "top":
            materials[-1][3:5] = [0.04, 24.0]
        elif face == "bottom":
            materials[-1][3] = 0.0

    def add(name, p, n, mat_id, uv=None):
        p, n = np.asarray(p).reshape(-1, 3, 3), np.asarray(n).reshape(-1, 3, 3)
        uv = np.zeros((len(p), 3, 2)) if uv is None else np.asarray(uv)
        good = np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1) > 1e-12
        p, n, uv = p[good], n[good], uv[good]
        positions.append(p)
        normals.append(n / np.maximum(1e-20, np.linalg.norm(n, axis=2, keepdims=True)))
        uvs.append(uv)
        material_ids.extend([mat_id] * len(p))
        object_counts[name] = len(p)

    cup_source = next(m for m in source if m.material == "Cup")
    cup = build_cup_mesh(cup_source.positions.reshape(-1).tolist())
    for mesh in source:
        if mesh.name == "Pie_Cube":
            for face, (p, n, uv) in _box_faces(mesh).items():
                add("box_" + face, p, n, ids["box_" + face], uv)
        elif mesh.material == "Cup":
            p = np.asarray(cup.positions).reshape(-1, 3)
            p[:, 1] += 0.0001  # Avoid coincident plastic/floor boundaries.
            add("plastic_cup", p, cup.normals, ids["plastic"])
        elif mesh.material == "Water":
            p, n = build_water_volume(mesh.positions.reshape(-1).tolist(), cup)
            p = np.asarray(p).reshape(-1, 3)
            p[:, 1] += 0.0001
            add("water", p, n, ids["water"])
        else:
            key = ("floor" if mesh.name.startswith("Floor") else
                   "back" if mesh.name.startswith("Back") else
                   "ceiling" if mesh.name.startswith("Ceiling") else
                   "red" if mesh.material == "wall_red" else
                   "green" if mesh.material == "wall_green" else "mint")
            add(mesh.name, mesh.positions, mesh.normals, ids[key])

    p = np.array([[-20, -0.051, -20], [-20, -0.051, 20], [20, -0.051, 20], [20, -0.051, -20]])
    add("ground", p[[[0, 1, 2], [0, 2, 3]]], np.tile([0., 1., 0.], (2, 3, 1)), ids["ground"])
    light = config["light"]
    center = np.asarray(light["center"])
    w, d = light["width"] / 2, light["depth"] / 2
    p = center + np.array([[-w, 0, -d], [w, 0, -d], [w, 0, d], [-w, 0, d]])
    data = np.zeros(15)
    data[5], data[6], data[10], data[11:14] = EMITTER, 1.0, -1, light["radiance"]
    light_id = len(materials)
    materials.append(data)
    material_names.append("area_light")
    add("area_light", p[[[0, 1, 2], [0, 2, 3]]], np.tile([0., -1., 0.], (2, 3, 1)), light_id)

    p, n, uv = np.concatenate(positions), np.concatenate(normals), np.concatenate(uvs)
    e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    gn = np.cross(e1, e2)
    gn /= np.linalg.norm(gn, axis=1, keepdims=True)
    # Dielectric topology uses winding; smooth normals must stay in its hemisphere.
    n *= np.where(np.sum(n * gn[:, None, :], axis=2, keepdims=True) < 0, -1., 1.)
    bvh_started = time.perf_counter()
    bvh = build_bvh(p)
    bvh_seconds = time.perf_counter() - bvh_started
    arrays = SceneBuffers(np.ascontiguousarray(p[:, 0]), np.ascontiguousarray(e1), np.ascontiguousarray(e2),
                          np.ascontiguousarray(n), np.ascontiguousarray(uv), np.ascontiguousarray(gn),
                          np.asarray(material_ids, dtype=np.int32), bvh.minimum, bvh.maximum, bvh.nodes, bvh.indices,
                          np.asarray(materials), np.concatenate(texture_pixels).astype(np.float32),
                          np.asarray(texture_info, dtype=np.int64),
                          np.asarray([*center, light["width"], light["depth"], *light["radiance"]]))
    stats = {"triangles": len(p), "bvh_nodes": len(bvh.nodes), "bvh_depth": bvh.depth,
             "bvh_build_seconds": bvh_seconds, "scene_load_seconds": time.perf_counter() - started,
             "objects": object_counts, "materials": material_names, "config": config}
    return arrays, config, stats
