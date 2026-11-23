import math
from pyglet.math import Vec3

def make_pie_uvs(positions, normals) :

    origin = Vec3(2.10, 0.0, -0.50) # 상자 왼쪽 아래 꼭짓점
    angle = math.radians(30.0)

    short_axis = Vec3(math.cos(angle), 0.0, -math.sin(angle))
    long_axis = Vec3(-math.sin(angle), 0.0, -math.cos(angle))

    texcoords = []
    for i in range(0, len(positions), 3) :

        p = Vec3(*positions[i:i+3]) - origin 
        n = Vec3(*normals[i:i+3])

        # 축 방향으로 얼마나 움직였는지 -> (0, 1) 범위로
        s = p.dot(short_axis) / 0.60 
        t = p.dot(long_axis) / 2.10
        h = p.y / 2.50

        # s, t, h로 면 상의 (u, v) 좌표 구하기
        if abs(n.y) > 0.9: #위 아래 면
            u = s
            v = t if n.y > 0.0 else 1.0 - t
        elif abs(n.dot(short_axis)) > 0.9: # 넒은 옆면
            u = t if n.dot(short_axis) > 0.0 else 1.0 - t
            v = h
        else : # 좁은 옆면
            u = 1.0 - s if n.dot(long_axis) > 0.0 else s
            v = h   

        texcoords.extend((
            max(0.0, min(1.0, u)),
            max(0.0, min(1.0, v)),
        ))

    return texcoords