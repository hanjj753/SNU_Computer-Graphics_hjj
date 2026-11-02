from pathlib import Path
from pyglet.gl import GL_LINE_STRIP, GL_POINTS, GL_LINES, glPointSize
from pyglet.math import Vec3
import pyglet
import json

class BSpline() :

    def __init__(self, resolution:int=20, points:list=[]):
        
        self.resolution = resolution
        self.points = points        # control points
        self.curve = []             # 그릴 때 연결할 점들
        self.vertex_list = None     # shader program의 vertex list
        self.point_vertex_list = None # point용 shader program vertex list
        self.picked = -1     # 선택된 점, 없으면 =1
        self.frames = []        # frame 계산용 list
        self.frame_vertex_list = None
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

    def evaluate(self, u) :
        """u에 따른 위치 P(u)와 기울기 P'(u) 계산
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
        
        d0 = -0.5*(1.0 - t)**2.0
        d1 = 1.5*t*t - 2*t
        d2 = -1.5*t*t + t + 0.5
        d3 = 0.5*t*t
        derivatives = [d0, d1, d2, d3]

        position = Vec3(0, 0, 0)
        derivative = Vec3(0, 0, 0)

        for p, w, d in zip(u_points, weights, derivatives) :
            position += p*w
            derivative += p*d

        return position, derivative

    def buildFrames(self) :
        pass

    def drawFrames(self) :
        pass

