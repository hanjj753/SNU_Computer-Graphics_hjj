"""메니스커스 수면과, 굴절용으로 경계가 닫힌 물 메시를 만든다."""

import math


# 장면 단위의 근사값. 실제 유체나 접촉각을 계산하는 시뮬레이션은 아니다.
MENISCUS_HEIGHT = 0.004
MENISCUS_WIDTH = 0.012
RADIUS_MARGIN = 0.001
ANGULAR_SEGMENTS = 96
MENISCUS_RINGS = 12


def meniscus_height(t):
    """중앙에서 평평하고 접촉선에서는 가파르게 올라가는 타원호 단면."""
    t = max(0.0, min(1.0, t))
    return MENISCUS_HEIGHT * (1.0-math.sqrt(max(0.0, 1.0-t*t)))


def build_water_surface(positions):
    """원본 물의 위치·높이를 읽고, 위쪽 수면의 positions/normals를 반환한다."""
    points = list(zip(positions[0::3], positions[1::3], positions[2::3]))
    level = max(p[1] for p in points)
    center_x = (min(p[0] for p in points) + max(p[0] for p in points)) / 2
    center_z = (min(p[2] for p in points) + max(p[2] for p in points)) / 2

    # 기존 수면과 컵 안쪽 벽 사이의 작은 틈을 줄인다.
    # 현재 OBJ 치수에 맞춘 여유값이며, 컵보다 커지게 설정하면 안 된다.
    radius = max(
        math.hypot(x - center_x, z - center_z)
        for x, y, z in points if abs(y - level) < 1e-5
    ) + RADIUS_MARGIN
    flat_radius = radius - MENISCUS_WIDTH

    def vertex(r, angle):
        # 중앙에서는 t=0. 벽 근처의 좁은 구간에서만 수면이 올라간다.
        t = max(0.0, min(1.0, (r - flat_radius) / MENISCUS_WIDTH))
        y = level + meniscus_height(t)
        slope = MENISCUS_HEIGHT*t/(MENISCUS_WIDTH*math.sqrt(max(1e-12,1.0-t*t)))
        c, s = math.cos(angle), math.sin(angle)

        # y=h(r)의 기울기에서 구한 위쪽 법선: (-dh/dx, 1, -dh/dz).
        # 법선도 곡면에 맞게 바뀌어야 가장자리 광택이 둥글게 이어진다.
        length = math.sqrt(1.0 + slope * slope)
        normal = (-slope * c / length, 1.0 / length, -slope * s / length)
        return (center_x + r * c, y, center_z + r * s), normal

    radii = [flat_radius] + [
        flat_radius + MENISCUS_WIDTH * i / MENISCUS_RINGS
        for i in range(1, MENISCUS_RINGS + 1)
    ]
    rings = [
        [vertex(r, 2.0 * math.pi * i / ANGULAR_SEGMENTS)
         for i in range(ANGULAR_SEGMENTS)]
        for r in radii
    ]
    center = ((center_x, level, center_z), (0.0, 1.0, 0.0))
    surface_positions, surface_normals = [], []

    def add_triangle(a, b, c):
        for position, normal in (a, b, c):
            surface_positions.extend(position)
            surface_normals.extend(normal)

    for i in range(ANGULAR_SEGMENTS):
        j = (i + 1) % ANGULAR_SEGMENTS
        # 위에서 보아 반시계 방향으로 연결한다.
        add_triangle(center, rings[0][j], rings[0][i])
        for inner, outer in zip(rings, rings[1:]):
            add_triangle(inner[i], inner[j], outer[j])
            add_triangle(inner[i], outer[j], outer[i])

    return surface_positions, surface_normals


def build_water_volume(positions, cup_mesh):
    """수면에 옆면·바닥을 연결해 매질 진입/이탈을 추적할 닫힌 경계를 만든다."""
    surface_positions, surface_normals = build_water_surface(positions)
    points = list(zip(positions[0::3], positions[1::3], positions[2::3]))
    cx = (min(p[0] for p in points) + max(p[0] for p in points)) / 2
    cz = (min(p[2] for p in points) + max(p[2] for p in points)) / 2
    raw_bottom = min(p[1] for p in points)
    # 물의 바닥이 플라스틱 바닥 안으로 들어가지 않도록 컵 안쪽 높이에 맞춘다.
    bottom = max(raw_bottom,cup_mesh.inner_profile[0][0]+0.0001)
    top = max(surface_positions[1::3])
    lower_radius = max(
        math.hypot(x - cx, z - cz) for x, y, z in points
        if abs(y - raw_bottom) < 1e-5
    )
    upper_radius = max(
        math.hypot(x - cx, z - cz)
        for x, y, z in zip(surface_positions[0::3], surface_positions[1::3], surface_positions[2::3])
    )
    lower_radius += (upper_radius-lower_radius)*(bottom-raw_bottom)/(top-raw_bottom)
    slope = (upper_radius - lower_radius) / (top - bottom)
    length = math.sqrt(1 + slope * slope)

    def ring_vertex(i, y, radius):
        angle = 2 * math.pi * i / ANGULAR_SEGMENTS
        c, s = math.cos(angle), math.sin(angle)
        return (cx + radius * c, y, cz + radius * s), (c / length, -slope / length, s / length)

    def add_triangle(a, b, c):
        for position, normal in (a, b, c):
            surface_positions.extend(position)
            surface_normals.extend(normal)

    for i in range(ANGULAR_SEGMENTS):
        j = (i + 1) % ANGULAR_SEGMENTS
        a, b = ring_vertex(i, bottom, lower_radius), ring_vertex(j, bottom, lower_radius)
        c, d = ring_vertex(i, top, upper_radius), ring_vertex(j, top, upper_radius)
        add_triangle(a, c, d)
        add_triangle(a, d, b)
        add_triangle(((cx, bottom, cz), (0, -1, 0)),
                     (a[0], (0, -1, 0)), (b[0], (0, -1, 0)))

    # 바깥쪽 winding을 유지한다. tracer.py가 각 경계에서 굴절하고,
    # 경계 사이의 실제 이동 거리로 Beer–Lambert 흡수를 계산한다.
    return surface_positions, surface_normals
