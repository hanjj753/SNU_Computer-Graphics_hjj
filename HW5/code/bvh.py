"""Binned-SAH BVH construction and the same triangle test for both traversals."""

from dataclasses import dataclass

import numpy as np
from numba import njit

from sampling import EPSILON


@dataclass
class BVH:
    minimum: np.ndarray
    maximum: np.ndarray
    nodes: np.ndarray  # left, right, primitive offset, primitive count
    indices: np.ndarray
    depth: int


def build_bvh(triangles, leaf_size=4, bins=12):
    lower = triangles.min(axis=1) - 1e-7
    upper = triangles.max(axis=1) + 1e-7
    centers = (lower + upper) * 0.5
    node_min, node_max, nodes, ordered = [], [], [], []
    max_depth = 0

    def area(lo, hi):
        extent = np.maximum(hi - lo, 0.0)
        return 2.0 * (extent[..., 0] * extent[..., 1] +
                      extent[..., 1] * extent[..., 2] +
                      extent[..., 2] * extent[..., 0])

    def build(ids, depth):
        nonlocal max_depth
        max_depth = max(max_depth, depth)
        index = len(nodes)
        lo, hi = lower[ids].min(axis=0), upper[ids].max(axis=0)
        node_min.append(lo)
        node_max.append(hi)
        nodes.append([-1, -1, 0, 0])
        if len(ids) <= leaf_size or depth >= 60:
            nodes[index][2:] = [len(ordered), len(ids)]
            ordered.extend(ids)
            return index

        clo, chi = centers[ids].min(axis=0), centers[ids].max(axis=0)
        best_cost, best_axis, best_bin = np.inf, -1, -1
        for axis in range(3):
            extent = chi[axis] - clo[axis]
            if extent < 1e-10:
                continue
            slots = np.minimum(((centers[ids, axis] - clo[axis]) / extent * bins).astype(int), bins - 1)
            counts = np.bincount(slots, minlength=bins)
            bmin = np.full((bins, 3), np.inf)
            bmax = np.full((bins, 3), -np.inf)
            np.minimum.at(bmin, slots, lower[ids])
            np.maximum.at(bmax, slots, upper[ids])
            lmin, lmax = np.minimum.accumulate(bmin), np.maximum.accumulate(bmax)
            rmin = np.minimum.accumulate(bmin[::-1])[::-1]
            rmax = np.maximum.accumulate(bmax[::-1])[::-1]
            lc, rc = np.cumsum(counts), np.cumsum(counts[::-1])[::-1]
            costs = area(lmin[:-1], lmax[:-1]) * lc[:-1] + area(rmin[1:], rmax[1:]) * rc[1:]
            costs[(lc[:-1] == 0) | (rc[1:] == 0)] = np.inf
            split = int(np.argmin(costs))
            if costs[split] < best_cost:
                best_cost, best_axis, best_bin = costs[split], axis, split

        if best_axis >= 0:
            slots = np.minimum(((centers[ids, best_axis] - clo[best_axis]) /
                                (chi[best_axis] - clo[best_axis]) * bins).astype(int), bins - 1)
            mask = slots <= best_bin
            left_ids, right_ids = ids[mask], ids[~mask]
        else:
            sorted_ids = ids[np.argsort(centers[ids, int(np.argmax(chi - clo))], kind="stable")]
            mid = len(ids) // 2
            left_ids, right_ids = sorted_ids[:mid], sorted_ids[mid:]
        nodes[index][0] = build(left_ids, depth + 1)
        nodes[index][1] = build(right_ids, depth + 1)
        return index

    if not len(triangles):
        raise ValueError("Cannot build a BVH for an empty scene")
    build(np.arange(len(triangles), dtype=np.int32), 0)
    return BVH(np.asarray(node_min), np.asarray(node_max),
               np.asarray(nodes, dtype=np.int32), np.asarray(ordered, dtype=np.int32), max_depth)


@njit(cache=True, inline="always")
def triangle_hit(origin, direction, v0, e1, e2, limit):
    """Two-sided Möller–Trumbore; return t, u, v (t<0 means miss)."""
    px = direction[1] * e2[2] - direction[2] * e2[1]
    py = direction[2] * e2[0] - direction[0] * e2[2]
    pz = direction[0] * e2[1] - direction[1] * e2[0]
    det = e1[0] * px + e1[1] * py + e1[2] * pz
    if abs(det) < 1e-12:
        return -1.0, 0.0, 0.0
    inv = 1.0 / det
    tx, ty, tz = origin[0] - v0[0], origin[1] - v0[1], origin[2] - v0[2]
    u = (tx * px + ty * py + tz * pz) * inv
    if u < -1e-9 or u > 1.0 + 1e-9:
        return -1.0, 0.0, 0.0
    qx, qy, qz = ty * e1[2] - tz * e1[1], tz * e1[0] - tx * e1[2], tx * e1[1] - ty * e1[0]
    v = (direction[0] * qx + direction[1] * qy + direction[2] * qz) * inv
    if v < -1e-9 or u + v > 1.0 + 1e-9:
        return -1.0, 0.0, 0.0
    t = (e2[0] * qx + e2[1] * qy + e2[2] * qz) * inv
    if t <= EPSILON or t > limit:
        return -1.0, 0.0, 0.0
    return t, u, v


@njit(cache=True, inline="always")
def aabb_hit(origin, direction, lo, hi, limit):
    near, far = 0.0, limit
    for axis in range(3):
        if abs(direction[axis]) < 1e-15:
            if origin[axis] < lo[axis] or origin[axis] > hi[axis]:
                return -1.0
        else:
            a = (lo[axis] - origin[axis]) / direction[axis]
            b = (hi[axis] - origin[axis]) / direction[axis]
            near = max(near, min(a, b))
            far = min(far, max(a, b))
            if far < near:
                return -1.0
    return near


@njit(cache=True)
def intersect(origin, direction, scene, use_bvh=True, limit=1e30):
    closest, hit, hu, hv, tests = limit, -1, 0.0, 0.0, 0
    if not use_bvh:
        for index in range(len(scene.v0)):
            t, u, v = triangle_hit(origin, direction, scene.v0[index], scene.e1[index], scene.e2[index], closest)
            tests += 1
            if t > 0.0 and (t < closest or hit < 0 or (t == closest and index < hit)):
                closest, hit, hu, hv = t, index, u, v
        return closest, hit, hu, hv, tests

    stack = np.empty(128, dtype=np.int32)
    stack[0], size = 0, 1
    while size > 0:
        size -= 1
        node = stack[size]
        if aabb_hit(origin, direction, scene.bvh_min[node], scene.bvh_max[node], closest) < 0.0:
            continue
        left, right, offset, count = scene.bvh_nodes[node]
        if count > 0:
            for slot in range(offset, offset + count):
                index = scene.bvh_indices[slot]
                t, u, v = triangle_hit(origin, direction, scene.v0[index], scene.e1[index], scene.e2[index], closest)
                tests += 1
                # Stable ID tie-breaks keep coincident seams deterministic.
                if t > 0.0 and (t < closest or hit < 0 or (t == closest and index < hit)):
                    closest, hit, hu, hv = t, index, u, v
        else:
            a = aabb_hit(origin, direction, scene.bvh_min[left], scene.bvh_max[left], closest)
            b = aabb_hit(origin, direction, scene.bvh_min[right], scene.bvh_max[right], closest)
            if a >= 0.0 and b >= 0.0:
                if a < b:
                    stack[size], stack[size + 1] = right, left
                else:
                    stack[size], stack[size + 1] = left, right
                size += 2
            elif a >= 0.0:
                stack[size], size = left, size + 1
            elif b >= 0.0:
                stack[size], size = right, size + 1
    return closest, hit, hu, hv, tests
