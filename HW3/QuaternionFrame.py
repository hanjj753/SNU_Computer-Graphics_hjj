import math
from pyglet.math import Vec3, Quaternion
from pyglet.gl import GL_LINES
import pyglet

def frame2Quaternion(T, N, B) :
    # 회전 행렬로 본다
    m00, m10, m20 = T
    m01, m11, m21 = N
    m02, m12, m22 = B
    trace = m00 + m11 + m22

    if trace > 0:
        s = 2 * math.sqrt(trace + 1)
        q = Quaternion(s / 4, (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s)
    elif m00 >= m11 and m00 >= m22:
        s = 2 * math.sqrt(1 + m00 - m11 - m22)
        q = Quaternion((m21 - m12) / s, s / 4, (m01 + m10) / s, (m02 + m20) / s)
    elif m11 >= m22:
        s = 2 * math.sqrt(1 + m11 - m00 - m22)
        q = Quaternion((m02 - m20) / s, (m01 + m10) / s, s / 4, (m12 + m21) / s)
    else:
        s = 2 * math.sqrt(1 + m22 - m00 - m11)
        q = Quaternion((m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, s / 4)

    return q.normalize()

def quaternion2Frame(q): # 강의자료 공식 참고
    q = q.normalize()
    w, x, y, z = q

    T = Vec3(
        1 - 2 * (y*y + z*z),
        2 * (x*y + w*z),
        2 * (x*z - w*y),
    )

    N = Vec3(
        2 * (x*y - w*z),
        1 - 2 * (x*x + z*z),
        2 * (y*z + w*x),
    )

    B = Vec3(
        2 * (x*z + w*y),
        2 * (y*z - w*x),
        1 - 2 * (x*x + y*y),
    )

    return T, N, B

class QuaternionFrame:

    def __init__(self, spline, subdivisions=4):
        """step = quaternion 배치한 간격 """

        self.period = len(spline.points)
        self.step = 1 / subdivisions
        self.us = [i * self.step for i in range(self.period*subdivisions)] # point 간격당 4개의 quaternion
        self.controls:list[Quaternion] = [] # 제어 quaternion 저장
        self.vertex_list = None

        for u in self.us:
            q = frame2Quaternion(*spline.movingFrame(u))

            if self.controls and self.controls[-1].dot(q) < 0 : 
                q = q * -1 #q와 -q는 같은 회전 -> 이전 q와 유사한 방향 선택

            self.controls.append(q)

        self.wrap_sign = 1 if self.controls[-1].dot(self.controls[0]) >= 0 else -1 #마지막에 역전되는지

    def control(self, index) : # 한 바퀴 돈 후 부호 반대인 거 보정, 두 바퀴 돌면 원래대로
        turns, j = divmod(index, len(self.controls))
        sign = self.wrap_sign if turns % 2 else 1
        return self.controls[j] * sign

    def evaluate(self, u) :
        x = (u % self.period) / self.step
        i = math.floor(x) #i 번쨰 제어 quaternion
        t = x - i         # i번째부터 t% 움직임 t = (0, 1)

        b0 = (1 - t)**3 / 6
        b1 = (3*t**3 - 6*t*t + 4) / 6
        b2 = (-3*t**3 + 3*t*t + 3*t + 1) / 6
        b3 = t**3 / 6
        b = [b0, b1, b2, b3]

        q = Quaternion(0, 0, 0, 0)
        for k, w in enumerate(b) :
            q = q + self.control(i+k-1) * w

        return q.normalize()

    def drawControls(self, spline, scale=0.12) :
        if self.vertex_list is None:
            vertices, colors = [], []
            axis_colors = ( #Frenet Frame이랑 동일
                (255, 70, 70, 255),
                (70, 255, 70, 255),
                (70, 130, 255, 255),
            )

            for u, q in zip(self.us, self.controls):
                p = spline.evaluate(u) # position of u
                axes = quaternion2Frame(q) # Frame 꺼내기

                for axis, color in zip(axes, axis_colors):
                    vertices.extend((*p, *(p + axis * scale)))
                    colors.extend(color * 2)

            self.program = pyglet.graphics.get_default_shader()
            self.vertex_list = self.program.vertex_list(
                len(vertices) // 3,
                GL_LINES,
                position=("f", vertices),
                colors=("Bn", colors),
            )

        self.program.use()
        self.vertex_list.draw(GL_LINES)
        self.program.stop()

    def delete(self):
        if self.vertex_list is not None:
            self.vertex_list.delete()
            self.vertex_list = None

    def rotateAt(self, u, axis, degrees) :
        axis = axis.normalize()
        theta = math.radians(degrees) / 2 # quaternion으로 rotation 시킬때 theta/2만큼

        rotation_q = Quaternion(math.cos(theta), axis.x * math.sin(theta), axis.y * math.sin(theta), axis.z * math.sin(theta))

        i = math.floor((u % self.period) / self.step) # 몇번째 제어 quaternion인지
        for j in range(4) :
            idx = (i + j - 1) % len(self.controls) #closed라 마지막에 % 연산
            self.controls[idx] = (rotation_q @ self.controls[idx]).normalize()
        
        self.delete() # 다시 그리기

    def toDict(self):
        return {
            "subdivisions": round(1 / self.step),
            "wrap_sign": self.wrap_sign,
            "controls": [list(q) for q in self.controls],
        }

    @classmethod
    def fromDict(cls, spline, data):
        result = cls(spline, subdivisions=int(data["subdivisions"]))

        rows = data["controls"]
        if len(rows) != len(result.us): raise ValueError("Quaternion control 개수가 안 맞음")

        controls = []
        for row in rows:
            q = Quaternion(*row)
            controls.append(q.normalize())

        result.controls = controls
        result.wrap_sign = int(data["wrap_sign"])

        if result.wrap_sign not in (-1, 1): raise ValueError("Wrap sign 오류")

        return result