import json
import math
import pyglet
from pyglet.gl import GL_TRIANGLES
from pyglet.math import Vec3, Mat4
from bisect import bisect_right
from pathlib import Path
from Bspline import BSpline

def trackAxes(spline:BSpline, u) :
    T, N, B = spline.u2frame(u)
    sign = 1 if spline.frames[0][2].y >= 0 else -1
    
    right = N * (-sign) # N = B x T이므로 B가 위쪽이면 N은 왼쪽 -> 오른쪽은 - 곱해줌
    up = B * sign

    return right, up, T

class Rails:

    def __init__(self, spline, gauge = 0.12, radius = 0.006, drop = 0.026, sides = 8):
        """
        spline에서 drop 만큼 떨어진 게 레일의 중심
        좌우로 gauge/2 만큼씩 벌어진 레일
        sides = 원통에서 원 대신 sides각형, radius의 원
        """

        self.spline:BSpline = spline
        self.gauge = gauge
        self.radius = radius
        self.drop = drop
        self.sides = sides

        self.program = pyglet.graphics.get_default_shader()
        self.vertex_list = None
        self.rebuild()

    def rebuild(self) :
        spline = self.spline

        sections = []
        for i in range(1, len(spline.frames)) :
            right, up, forward = trackAxes(spline, spline.u_table[i])
            sections.append((spline.frame_positions[i], right, up))

        vertices, indices = [], []
        for side in [-1, 1] : # 왼쪽 오른쪽
            base = len(vertices) // 3
            for position, right, up in sections:
                center = (position - up * self.drop + right * (side * self.gauge / 2)) #레일 중심 계산

                for j in range(self.sides): # 원통 그리기
                    angle = 2 * math.pi * j / self.sides
                    radial = (right * math.cos(angle)+ up * math.sin(angle))
                    vertices.extend(center + radial * self.radius)

            for i in range(len(sections) - 1): # 삼각형 그리기 위한 index 추가
                for j in range(self.sides): 
                    k = (j + 1) % self.sides

                    a = base + i * self.sides + j
                    b = base + (i + 1) * self.sides + j
                    c = base + (i + 1) * self.sides + k
                    d = base + i * self.sides + k

                    indices.extend((a, b, c, a, c, d))

        if self.vertex_list is not None:
            self.vertex_list.delete()

        count = len(vertices) // 3
        self.vertex_list = self.program.vertex_list_indexed(
            count,
            GL_TRIANGLES,
            indices,
            position=("f", vertices),
            colors=("Bn", (185, 190, 200, 255) * count),
        )
        self.frames = spline.frames # spline이 변경됐는지 트래킹

    def draw(self) :
        
        if self.frames is not self.spline.frames:
            self.rebuild()

        self.program.use()
        self.vertex_list.draw(GL_TRIANGLES)
        self.program.stop()

class CartTrain:

    def __init__(self, path:Path|str, scale=0.1) :

        path = Path(path)
        data = json.loads((path/"train.json").read_text(encoding='utf-8'))

        self.batch = pyglet.graphics.Batch()
        self.gauge = data["gauge"] * scale
        self.wheel_drop = data["wheel_drop"] * scale
        self.local = Mat4.from_scale(Vec3(scale, scale, scale))
        self.cars = []

        for i, car in enumerate(data["cars"]):
            scene = pyglet.model.load(str(path / car["file"]))
            models = scene.create_models(batch=self.batch, group=pyglet.graphics.Group(order=i))
            self.cars.append((car["offset"] * scale, models))

    def draw(self, spline, head_u) :
        # 첫 차의 u = head_u
        # 첫 차 위치 구하기
        head_u %= len(spline.points)
        j = min(bisect_right(spline.u_table, head_u), len(spline.u_table) - 1)
        i = j - 1
        alpha = (head_u - spline.u_table[i]) / (spline.u_table[j] - spline.u_table[i])
        head_s = spline.s_table[i]+ alpha * (spline.s_table[j] - spline.s_table[i])

        for offset, models in self.cars:
            # 뒤 차들은 u 차이가 아니라 거리 차이로 배치
            u = (head_u if offset == 0 else spline.dist2u(head_s - offset))
            position = spline.evaluate(u)
            right, up, forward = trackAxes(spline, u)

            # 내보낸 obj의 +X=오른쪽, +Y=위, -Z=앞
            pose = Mat4( #열 순서로 값 받기 때문에 이거의 transpose 형태의 mat4로 저장
                right.x, right.y, right.z, 0,
                up.x, up.y, up.z, 0,
                -forward.x, -forward.y, -forward.z, 0,
                position.x, position.y, position.z, 1,
            )

            for model in models:
                model.matrix = pose @ self.local

        self.batch.draw()
