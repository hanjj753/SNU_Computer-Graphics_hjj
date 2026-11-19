"""여섯 면의 UV를 보존하면서 모서리가 조금 둥근 상자를 만든다."""

import math
from pyglet.math import Vec3

BEVEL_RADIUS = 0.025
BEVEL_SEGMENTS = 6
FACE_SUBDIVISIONS = 24


def box_frame(positions):
    angle = math.radians(30)
    axes = (Vec3(math.cos(angle), 0, -math.sin(angle)), Vec3(0, 1, 0),
            Vec3(-math.sin(angle), 0, -math.cos(angle)))
    points = [Vec3(*positions[i:i + 3]) for i in range(0, len(positions), 3)]
    bounds = [(min(p.dot(a) for p in points), max(p.dot(a) for p in points)) for a in axes]
    center = sum((a * ((lo + hi) / 2) for a, (lo, hi) in zip(axes, bounds)), Vec3())
    half = [(hi - lo) / 2 for lo, hi in bounds]
    return axes, center, half


def rounded_face(data, frame, bulge=0.0, *, enabled=True, ridge_height=0.0):
    """모서리·앞면의 휨과, 긴 중앙선을 따라 솟은 윗면을 만든다."""
    axes, center, half = frame
    # OBJ 반올림 때문에 UV가 정확히 0/1이 아닐 수 있으므로 삼각형의 affine map을 구한다.
    p0, p1, p2 = [Vec3(*data["positions"][i:i+3]) for i in (0,3,6)]
    uv0, uv1, uv2 = [data["uvs"][i:i+2] for i in (0,2,4)]
    u1, v1 = uv1[0]-uv0[0], uv1[1]-uv0[1]
    u2, v2 = uv2[0]-uv0[0], uv2[1]-uv0[1]
    determinant = u1*v2-u2*v1
    du = ((p1-p0)*v2-(p2-p0)*v1)/determinant
    dv = ((p2-p0)*u1-(p1-p0)*u2)/determinant
    origin = p0-du*uv0[0]-dv*uv0[1]
    normal = Vec3(*data["normals"][:3]).normalize()
    orientation = du.cross(dv).dot(normal)

    def samples(length):
        edge = BEVEL_RADIUS / length
        values = [i / FACE_SUBDIVISIONS for i in range(FACE_SUBDIVISIONS + 1)]
        values += [edge * i / BEVEL_SEGMENTS for i in range(BEVEL_SEGMENTS + 1)]
        values += [1 - edge * i / BEVEL_SEGMENTS for i in range(BEVEL_SEGMENTS + 1)]
        # OBJ 치수 반올림으로 기본 격자와 bevel 표본이 거의 겹치면 합친다.
        merged = []
        for value in sorted(set(round(x,12) for x in values)):
            if not merged or value-merged[-1]>1e-6:
                merged.append(value)
            elif value == 1.0:
                merged[-1] = 1.0
        return merged

    us, vs = samples(du.length()), samples(dv.length())
    grid = {}
    for i, u in enumerate(us):
        for j, v in enumerate(vs):
            p = origin + du * u + dv * v
            local = [(p - center).dot(axis) for axis in axes]
            local = [math.copysign(h,x) if abs(abs(x)-h)<2e-5 else x for x,h in zip(local,half)]
            inner = [max(-h + BEVEL_RADIUS, min(h - BEVEL_RADIUS, x)) for x, h in zip(local, half)]
            delta = Vec3(*(x - q for x, q in zip(local, inner))).normalize()
            rounded = [q + BEVEL_RADIUS * d for q, d in zip(inner, delta)]
            p = center + sum((axis * x for axis, x in zip(axes, rounded)), Vec3())
            n = sum((axis * x for axis, x in zip(axes, delta)), Vec3()).normalize()
            if not enabled:
                p = origin + du * u + dv * v
                n = normal

            # 평면 영역 경계에서 변위와 기울기가 0이 되어 bevel과 자연스럽게 이어진다.
            eu, ev = BEVEL_RADIUS / du.length(), BEVEL_RADIUS / dv.length()
            if bulge and eu < u < 1-eu and ev < v < 1-ev:
                a, b = (u-eu)/(1-2*eu), (v-ev)/(1-2*ev)
                height = bulge * math.sin(math.pi*a)**2 * math.sin(math.pi*b)**2
                dhdu = bulge * math.pi * math.sin(2*math.pi*a) * math.sin(math.pi*b)**2 / (1-2*eu)
                dhdv = bulge * math.pi * math.sin(2*math.pi*b) * math.sin(math.pi*a)**2 / (1-2*ev)
                p += normal * height
                n = (du + normal*dhdu).cross(dv + normal*dhdv).normalize()
                if n.dot(normal) < 0: n = -n
            if ridge_height:
                # 짧은 축을 가로질러 올라가는 아치. 긴 축 방향으로는 높이가 같다.
                # 같은 변형을 옆면 윗부분에도 적용해 끝면과 윗면 사이를 닫는다.
                short, up, _ = axes
                x = (p-center).dot(short)
                q = max(-1.0,min(1.0,x/half[0]))
                arch = math.cos(math.pi*q/2)**2
                arch_dx = -math.pi*math.sin(math.pi*q)/(2*half[0])
                shoulder = 0.10
                t = max(0.0,min(1.0,((p-center).dot(up)-half[1]+shoulder)/shoulder))
                blend = t*t*(3-2*t)
                blend_dy = 6*t*(1-t)/shoulder
                hx = ridge_height*arch_dx*blend
                hy = ridge_height*arch*blend_dy
                p += up*(ridge_height*arch*blend)
                # y'=y+h(x,y)의 역전치 Jacobian으로 법선도 함께 변환한다.
                ny = n.dot(up)
                n = (n+up*(ny/(1+hy)-ny)-short*(hx*ny/(1+hy))).normalize()
            grid[i, j] = p, n, (u, v)

    result = {"positions": [], "normals": [], "uvs": []}
    for i in range(len(us)-1):
        for j in range(len(vs)-1):
            for triangle in (((i,j),(i+1,j),(i+1,j+1)), ((i,j),(i+1,j+1),(i,j+1))):
                if orientation < 0: triangle = triangle[::-1]
                for key in triangle:
                    p, n, uv = grid[key]
                    result["positions"].extend(p)
                    result["normals"].extend(n)
                    result["uvs"].extend(uv)
    return result
