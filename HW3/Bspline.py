from pathlib import Path
from pyglet.gl import GL_LINE_STRIP, GL_POINTS, GL_LINES, glPointSize
from pyglet.math import Vec3
import pyglet
import json
import math
from bisect import bisect_right

class BSpline() :

    def __init__(self, resolution:int=20, points:list=[], samples_per_line:int=200, energy:float=2.75125):
        
        self.resolution = resolution
        self.points = points        # control points
        self.curve = []             # 그릴 때 연결할 점들
        self.vertex_list = None     # shader program의 vertex list
        self.point_vertex_list = None # point용 shader program vertex list
        self.picked = -1     # 선택된 점, 없으면 =1
        self.frames = []        # frame 계산용 list
        self.frame_vertex_list = None
        self.energy = energy
        self.samples_per_line = samples_per_line
        if len(points) == 0 : self.initCurve()
        else : self.updateCurve()

    def initCurve(self) :
        """XZ 평면에 4개의 control point 가진 Bspline 생성"""
        if self.resolution < 2: raise ValueError("resolution > 2여야 함.")

        self.points = [
            [-3.0, 0.0, -3.0],
            [ 3.0, 0.0, -3.0],
            [ 3.0, 0.0,  3.0],
            [-3.0, 0.0,  3.0],
        ]
        self.updateCurve()

    def loadCurve(self, path:Path|str) :
        """저장해둔 Bspline의 points load"""
        if isinstance(path, str) : path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))

        points = data["points"]
        resolution = data.get("resolution", self.resolution)

        if any(len(point) != 3 for point in points): raise ValueError("각 제어점에는 x, y, z 좌표가 필요.")
        if not isinstance(resolution, int) or resolution < 2: raise ValueError("resolution은 2 이상의 정수.")

        points = [[float(coord) for coord in point] for point in points] # points 는 [[x1, y1, z1], [x2, y2, z2]]

        self.points = points
        self.resolution = resolution
        self.updateCurve()

    def saveCurve(self, path:Path|str=Path("tracks/spline_control_points.json")) :
        """Bspline의 points를 path에 저장"""
        if isinstance(path, str) : path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "resolution": self.resolution,
            "points": [list(point) for point in self.points]
        }

        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def updateCurve(self) :
        """ self.points에 변화가 생긴 뒤 이 함수를 호출하면 curve를 points에 따라 업데이트함. """

        def discretize(p0, p1, p2, p3) :
            curve = []
            for j in range(self.resolution) :
                t = 1.0/(self.resolution-1)*j
                b0 = (1.0-t)**3.0/6.0
                b1 = (3.0*t*t*t - 6.0*t*t + 4.0)/6.0
                b2 = (-3.0*t*t*t + 3*t*t + 3*t + 1)/6.0
                b3 = t**3/6.0

                x = b0*p0[0] + b1*p1[0] + b2*p2[0] + b3*p3[0]
                y = b0*p0[1] + b1*p1[1] + b2*p2[1] + b3*p3[1]
                z = b0*p0[2] + b1*p1[2] + b2*p2[2] + b3*p3[2]
                curve.append((x,y,z))

            self.curve.extend(curve)

        self.curve = []
        
        num = len(self.points)
        if num < 4 : raise ValueError("Control Point의 개수가 4개 미만.")

        for i in range(num-3): discretize(self.points[i], self.points[i+1], self.points[i+2], self.points[i+3])

        discretize(self.points[num-3], self.points[num-2], self.points[num-1], self.points[0])
        discretize(self.points[num-2], self.points[num-1], self.points[0], self.points[1])
        discretize(self.points[num-1], self.points[0], self.points[1], self.points[2])

        self.buildArcLengthTable()
        self.buildFrames()

    def draw(self) :

        count = len(self.curve)
        if count < 2 : return

        program = pyglet.graphics.get_default_shader()

        if self.vertex_list is None or self.vertex_list.count != count :

            if self.vertex_list is not None : self.vertex_list.delete() # vertex 개수 자체가 다르면 초기화

            self.vertex_list = program.vertex_list(
                count,
                GL_LINE_STRIP,
                position="f",
                colors=("Bn", (255, 255, 255, 255) * count),
            )

        self.vertex_list.position[:] = [
            coord for point in self.curve for coord in point
        ]

        program.use()
        self.vertex_list.draw(GL_LINE_STRIP)
        program.stop()

    def drawControlPoints(self) :
        
        count = len(self.points)

        program = pyglet.graphics.get_default_shader()
        if self.point_vertex_list is None or self.point_vertex_list.count != count :

            if self.point_vertex_list is not None : self.point_vertex_list.delete()
            
            self.point_vertex_list = program.vertex_list(
                count,
                GL_POINTS,
                position="f",
                colors="Bn",
            )

        self.point_vertex_list.position[:] = [coord for point in self.points for coord in point]

        colors = []
        for i in range(count) : colors.extend((255, 220, 0, 255) if i == self.picked else (255, 80, 80, 255))

        self.point_vertex_list.colors[:] = colors

        program.use()
        glPointSize(10.0)
        self.point_vertex_list.draw(GL_POINTS)
        glPointSize(1.0)
        program.stop()

    def evaluate(self, u:float) -> Vec3:
        """u에 따른 위치 P(u) 계산
        control points를 points에 모두 저장했기 때문에, |u| = i이라고 하면 i, i+1, i+2, i+3 이 만드는 curve를 parametrize 시킨다
        """

        n = len(self.points)
        u = u % n

        i = int(u)
        t = u - i # 소수 부분
        u_points = [Vec3(*self.points[(i + k) % n]) for k in range(4)]

        b0 = (1.0-t)**3.0/6.0
        b1 = (3.0*t*t*t - 6.0*t*t + 4.0)/6.0
        b2 = (-3.0*t*t*t + 3*t*t + 3*t + 1)/6.0
        b3 = t**3/6.0
        weights = [b0, b1, b2, b3]

        position = Vec3(0, 0, 0)

        for p, w in zip(u_points, weights) : position += p*w

        return position

    def getDerivatives(self, u:float)->tuple[Vec3, Vec3] :
        """P'(u)랑 P''(u) 계산"""
        n = len(self.points)
        u = u % n

        i = int(u)
        t = u - i # 소수 부분
        u_points = [Vec3(*self.points[(i + k) % n]) for k in range(4)]

        d0 = -0.5*(1.0 - t)**2.0
        d1 = 1.5*t*t - 2*t
        d2 = -1.5*t*t + t + 0.5
        d3 = 0.5*t*t
        derivatives = [d0, d1, d2, d3]

        sd0 = 1.0 - t
        sd1 = 3*t - 2
        sd2 = 1 - 3*t
        sd3 = t
        sderivatives = [sd0, sd1, sd2, sd3]

        derivative = Vec3(0, 0, 0)
        sderivative = Vec3(0, 0, 0)

        for p, d, sd in zip(u_points, derivatives, sderivatives) : 
            derivative += p*d
            sderivative += p*sd

        return derivative, sderivative

    def buildFrames(self) :
        """resolution에 따라 미리 frame 계산해둠
        buildArcLengthTable()에서 만들어둔 self.u_table 활용
        """
        # steps = len(self.points) * samples_per_line
        # self.u_table = [j/samples_per_line for j in range(steps+1)]
        self.frame_positions = [self.evaluate(u) for u in self.u_table]
        derivatives = [d.normalize() for d, _ in [self.getDerivatives(u) for u in self.u_table]]

        der, sder = self.getDerivatives(0)
        T = der.normalize()

        # up = Vec3(1, 0, 0)
        # N = up
        # B = T.cross(N).normalize()

        cross = der.cross(sder)
        B = cross.normalize()
        N = B.cross(T)

        frames = [(T, N, B)]
        for i, T in enumerate(derivatives[1:], start=1) :
            pT, pN, pB = frames[-1]
            N = pB.cross(T).normalize()
            B = T.cross(N).normalize()
            frames.append((T, N, B))

        # 추가 : 마지막에 회전이 한번에 꺾이는 것 방지로 남는 양만큼 분산 (AI한테 물어봄)
        T0, N0, B0 = frames[0]
        end_N = frames[-1][1]

        twist = math.atan2(T0.dot(end_N.cross(N0)), end_N.dot(N0))

        for i, (T, N, B) in enumerate(frames):
            angle = twist * self.s_table[i] / self.total_length

            N = N * math.cos(angle) + B * math.sin(angle)
            B = T.cross(N).normalize()
            N = B.cross(T).normalize()

            frames[i] = (T, N, B)

        frames[-1] = frames[0]

        self.frames = frames

    def drawFrames(self, u=None, stride=40, scale=0.35) :

        if not self.frames : return

        vertices, colors = [], []
        axis_colors = (
            (255, 70, 70, 255),   # T: 접선
            (70, 255, 70, 255),   # N: 법선
            (70, 130, 255, 255),  # B: 종법선
        )

        if u is None:
            items = [(self.frame_positions[i], self.frames[i]) for i in range(0, len(self.frames) - 1, stride)]
        else:
            position = self.evaluate(u)
            items = [(position, self.u2frame(u))]

        for position, frame in items:
            for direction, color in zip(frame, axis_colors):
                end = position + direction * scale
                vertices.extend((*position, *end))
                colors.extend(color * 2)

        count = len(vertices) // 3
        program = pyglet.graphics.get_default_shader()

        if (self.frame_vertex_list is None or self.frame_vertex_list.count != count):
            if self.frame_vertex_list is not None:
                self.frame_vertex_list.delete()

            self.frame_vertex_list = program.vertex_list(
                count, GL_LINES, 
                position="f", 
                colors="Bn"
            )

        self.frame_vertex_list.position[:] = vertices
        self.frame_vertex_list.colors[:] = colors

        program.use()
        self.frame_vertex_list.draw(GL_LINES)
        program.stop()

    def buildArcLengthTable(self) :
        """ 현재 그려진 Arc에 따라서 미리 u에 따른 s 계산해둬서 u= u(s) 꺼낼 수 있도록
        curve가 업데이트 될때마다 해야함"""

        steps = len(self.points) * self.samples_per_line
        self.u_table = [j/self.samples_per_line for j in range(steps+1)] #0~len(points)까지 한 point당 samples 개로 잘라서 미리 계산해둔다
        self.s_table = [0.0] #처음은 0, 마지막은 전체 닫힌 곡선 길이

        previous = self.evaluate(self.u_table[0]) #시작 position
        for u in self.u_table[1:] :
            position = self.evaluate(u)
            self.s_table.append(self.s_table[-1]+(position-previous).length())
            previous = position

        self.total_length = self.s_table[-1]

    def dist2u(self, s:float) -> float:
        """u=u(s)를 u_table, s_table을 이용해 구현"""

        s %= self.total_length
        j = min(bisect_right(self.s_table, s), len(self.s_table) - 1) # s가 total_length보다 크면 그냥 마지막 점이라고 하면 됨.(오차 보정)
        i = j - 1 #j는 s보다 큰 값의 첫 index이므로 s는 i와 j번째 사이에 위치

        length = self.s_table[j] - self.s_table[i] # i와 j 안에서 linear interpolation
        if length <= 1e-12: alpha = 0
        else : alpha = (s - self.s_table[i]) / length

        return self.u_table[i] + alpha * (self.u_table[j] - self.u_table[i])

    def u2frame(self, u:float) :
        u %= len(self.points)

        T, _ = self.getDerivatives(u)
        T = T.normalize()

        j = min(bisect_right(self.u_table, u), len(self.u_table) - 1)
        i = j-1
        alpha = (u - self.u_table[i]) / (self.u_table[j] - self.u_table[i])
        B0 = self.frames[i][2]
        B1 = self.frames[j][2]
        reference = B0 * (1 - alpha) + B1 * alpha
        N = reference.cross(T).normalize()
        B = T.cross(N).normalize()

        return (T, N, B)

    def velocity(self, u):
        """u일 때 velocity 계산"""
        position = self.evaluate(u)
        v2 = 2*(self.energy - 0.98*position.y)
        if v2 <=0 : raise ValueError("velocity <= 0")
        return v2**0.5
