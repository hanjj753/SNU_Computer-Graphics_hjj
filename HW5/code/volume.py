"""Homogeneous, achromatic scattering for the thin cloudy plastic volume.

Distances and sigma_s use scene units (one unit is about 10 cm). Absorption
remains RGB Beer-Lambert in tracer.py. No image-space filtering is involved.
"""

import math

from numba import njit

ISOTROPIC_PDF = 1.0 / (4.0 * math.pi)


@njit(cache=True, inline="always")
def scattering_coefficient(material):
    # Older diagnostic buffers contain just the original 15 columns.
    return material[15] if len(material) > 15 else 0.0


@njit(cache=True, inline="always")
def free_flight(sigma_s, uniform):
    if sigma_s <= 0.0:
        return 1e30
    return -math.log(max(1e-15, 1.0 - uniform)) / sigma_s


@njit(cache=True, inline="always")
def isotropic_direction(u, v):
    z = 1.0 - 2.0 * u
    radius = math.sqrt(max(0.0, 1.0 - z * z))
    phi = 2.0 * math.pi * v
    return (radius * math.cos(phi), radius * math.sin(phi), z)


@njit(cache=True, inline="always")
def shell_connection_distance(material, distance, outside_cosine):
    """Approximate refracted optical length for a straight thin-shell connection.

    The shell thickness is derived from the cup geometry. This correction is
    only used for direct light sampled from a scattering event, not camera rays.
    """
    thickness = material[16] if len(material) > 16 else 0.0
    if thickness <= 0.0:
        return distance
    cosine = min(1.0, max(0.0, abs(outside_cosine)))
    inside_cosine = math.sqrt(max(1e-12, 1.0 - (1.0 - cosine * cosine) / (material[6] ** 2)))
    return min(distance * cosine, thickness) / inside_cosine
