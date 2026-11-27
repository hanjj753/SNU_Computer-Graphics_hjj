"""Small, independently testable sampling and dielectric optics functions."""

import math

import numpy as np
from numba import njit

PI = math.pi
EPSILON = 2e-6


@njit(cache=True, inline="always")
def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


@njit(cache=True, inline="always")
def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


@njit(cache=True, inline="always")
def normalize(v):
    length = math.sqrt(max(1e-30, dot(v, v)))
    return (v[0] / length, v[1] / length, v[2] / length)


@njit(cache=True, inline="always")
def reflect(direction, normal):
    c = 2.0 * dot(direction, normal)
    return (direction[0] - c * normal[0], direction[1] - c * normal[1],
            direction[2] - c * normal[2])


@njit(cache=True)
def dielectric(direction, normal, eta_i, eta_t):
    """Exact unpolarized Fresnel and Snell; normal points into incident medium.

    Return (reflectance, transmitted direction, total internal reflection).
    Radiance transport's eta^2 factor is applied by the path integrator.
    """
    ci = min(1.0, max(0.0, -dot(direction, normal)))
    eta = eta_i / eta_t
    st2 = eta * eta * max(0.0, 1.0 - ci * ci)
    if st2 >= 1.0:
        return 1.0, (0.0, 0.0, 0.0), True
    ct = math.sqrt(1.0 - st2)
    rs = (eta_i * ci - eta_t * ct) / max(1e-20, eta_i * ci + eta_t * ct)
    rp = (eta_t * ci - eta_i * ct) / max(1e-20, eta_t * ci + eta_i * ct)
    f = 0.5 * (rs * rs + rp * rp)
    k = eta * ci - ct
    transmitted = normalize((eta * direction[0] + k * normal[0],
                             eta * direction[1] + k * normal[1],
                             eta * direction[2] + k * normal[2]))
    return f, transmitted, False


@njit(cache=True, inline="always")
def random_float(state):
    state = np.uint32(state ^ (state << np.uint32(13)))
    state = np.uint32(state ^ (state >> np.uint32(17)))
    state = np.uint32(state ^ (state << np.uint32(5)))
    return state, (float(state) + 0.5) / 4294967296.0


@njit(cache=True)
def sample_seed(pixel, sample, seed):
    state = np.uint32((pixel + 1) * 747796405 + (sample + 1) * 2891336453 + seed)
    state = np.uint32((state ^ (state >> np.uint32(16))) * np.uint32(2246822519))
    state = np.uint32((state ^ (state >> np.uint32(13))) * np.uint32(3266489917))
    state = np.uint32(state ^ (state >> np.uint32(16)))
    if state == 0:
        state = np.uint32(1)
    return state


@njit(cache=True, inline="always")
def local_to_world(axis, x, y, z):
    if abs(axis[2]) < 0.999:
        tangent = normalize((-axis[1], axis[0], 0.0))
    else:
        tangent = normalize((0.0, -axis[2], axis[1]))
    bitangent = cross(axis, tangent)
    return normalize((tangent[0] * x + bitangent[0] * y + axis[0] * z,
                      tangent[1] * x + bitangent[1] * y + axis[1] * z,
                      tangent[2] * x + bitangent[2] * y + axis[2] * z))


@njit(cache=True, inline="always")
def cosine_direction(normal, u, v):
    radius = math.sqrt(u)
    angle = 2.0 * PI * v
    return local_to_world(normal, radius * math.cos(angle), radius * math.sin(angle),
                          math.sqrt(max(0.0, 1.0 - u)))


@njit(cache=True, inline="always")
def phong_direction(axis, exponent, u, v):
    z = u ** (1.0 / (exponent + 1.0))
    radius = math.sqrt(max(0.0, 1.0 - z * z))
    angle = 2.0 * PI * v
    return local_to_world(axis, radius * math.cos(angle), radius * math.sin(angle), z)


@njit(cache=True, inline="always")
def power_heuristic(a, b):
    return a * a / max(1e-30, a * a + b * b)


@njit(cache=True)
def radical_inverse(value):
    result, factor = 0.0, 0.5
    while value:
        result += (value & 1) * factor
        value >>= 1
        factor *= 0.5
    return result
