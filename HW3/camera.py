import math

from pyglet.math import Mat4, Vec3, Quaternion, Vec4

class TrackballCamera:

    def __init__(self, eye:Vec3, center:Vec3, fov:float, up:Vec3=Vec3(0.0, 1.0, 0.0), near:float=0.01, far:float=100) :
        
        self.center = center
        self.initial_eye = eye
        eye_offset = eye - center
        self.initial_distance = eye_offset.length()
        self.fov = fov
        self.near = near
        self.far = far

        # view matrix의 회전 부분을 quaternion으로 변환
        self.initial_view = Mat4.look_at(position=eye, target=center, up=up)

        self.width = 1
        self.height = 1

        self.beginu = 0
        self.beginv = 0

        self.trackball_size = 0.6
        self.rotation_speed = 1.0
        self.pan_speed = 4.0
        self.dolly_speed = 15.0

        self.reset()

    def reset(self) :

        self.quaternion = [1.0, 0.0, 0.0, 0.0]
        self.tx = 0.0
        self.ty = 0.0
        self.tz = 0.0
        self.distance = self.initial_distance

    def resize(self, window, width, height) :

        self.width = int(width)
        self.height = int(height)
        aspectRatio = self.width / self.height

        window.viewport = (0, 0, width, height)
        window.projection = Mat4.perspective_projection(aspectRatio, z_near=self.near, z_far=self.far, fov=self.fov)

    def project_to_sphere(self, r, x, y) : # 2차원 화면 좌표 -> 3차원 구 좌표
        
        d = math.sqrt( x*x + y*y ) # 화면 중앙(0, 0)에서 커서 거리
        if d < r*0.70710678118654752440: #1/root(2)
            z = math.sqrt( r*r - d*d )
        else:
            t = r / 1.41421356237309504880
            z = t*t / d
        return z

    def trackball(self, p1x, p1y, p2x, p2y) : # p1, p2의 화면 좌표를 주면 회전 quaternion 반환

        if p1x == p2x and p1y == p2y : return [1.0, 0.0, 0.0, 0.0]

        p1 = [p1x, p1y, self.project_to_sphere(self.trackball_size, p1x, p1y)]
        p2 = [p2x, p2y, self.project_to_sphere(self.trackball_size, p2x, p2y)]

        axis = [p2[1]*p1[2]-p2[2]*p1[1],
                p2[2]*p1[0]-p2[0]*p1[2],
                p2[0]*p1[1]-p2[1]*p1[0]]

        difference = [p1[0] - p2[0], p1[1] - p2[1], p1[2] - p2[2]]
        t = math.sqrt(sum(difference[i]**2 for i in range(3))) / (2.0 * self.trackball_size) #현의 길이 / 2r = sin(theta/2)
        t = max(-1.0, min(1.0, t))
        angle = -self.rotation_speed * math.asin(t)

        return self.axis_to_quaternion(axis, angle)

    def axis_to_quaternion(self, axis, angle) :

        l = math.sqrt(sum(axis[i]**2 for i in range(3)))
        if l < 1e-8: return [1.0, 0.0, 0.0, 0.0]

        s = math.sin(angle/2.0)
        c = math.cos(angle/2.0)
        return [c, axis[0]*s/l, axis[1]*s/l, axis[2]*s/l]

    def multiply(self, q1, q2) :

        d = [q1[0]*q2[0] - q1[1]*q2[1] - q1[2]*q2[2] - q1[3]*q2[3],
            q1[0]*q2[1] + q1[1]*q2[0] + q1[2]*q2[3] - q1[3]*q2[2],
            q1[0]*q2[2] + q1[2]*q2[0] + q1[3]*q2[1] - q1[1]*q2[3],
            q1[0]*q2[3] + q1[3]*q2[0] + q1[1]*q2[2] - q1[2]*q2[1]]

        length = math.sqrt(sum(x**2 for x in d))

        return [component/length for component in d]

    def move(self, dx, dy, dz=0.0) :

        self.tx += self.pan_speed * dx
        self.ty += self.pan_speed * dy
        self.tz += self.pan_speed * dz

    def zoom(self, amount) :

        self.distance += self.dolly_speed * amount
        self.distance = max(0.1, self.distance)

    def begin_rotate(self, u, v) :

        self.beginu = u
        self.beginv = v

    def rotate(self, u, v) :

        # 이전 마우스 위치 정규화
        previous_u = -(self.width - 2.0*self.beginu) / self.width 
        previous_v = -(self.height - 2.0*self.beginv) / self.height

        # 현재 마우스 위치 정규화
        current_u = -(self.width - 2.0*u) / self.width
        current_v = -(self.height - 2.0*v) / self.height

        q = self.trackball(previous_u, previous_v, current_u, current_v)

        self.quaternion = self.multiply(q, self.quaternion)

        self.beginu = u
        self.beginv = v

    def apply(self, window) :
    
        q = Quaternion(*self.quaternion)
        center_offset = Vec3(-self.center.x, -self.center.y, -self.center.z) # 세계를 -center로 움직이면 center -> 0 즉 원점으로 옮겨짐.
        initial_rotation = Mat4(*self.initial_view[:12], 0.0, 0.0, 0.0, 1.0) #처음 view에서 rotation만

        window.view = (
            Mat4.from_translation(Vec3(self.tx, self.ty, self.tz-self.distance)) @ # pan
            q.to_mat4().transpose() @
            initial_rotation @
            Mat4.from_translation(center_offset)
        )

    def coord2screen(self, window, point) :
        """Point 클릭했을 때 인식하려면 화면 좌표로 바꿔야 하는데 이때 이거 사용"""
        clip = window.projection @ window.view @ Vec4(*point, 1.0) # homo coord

        nx = clip.x / clip.w
        ny = clip.y / clip.w
        nz = clip.z / clip.w

        if not (-1 <= nx <= 1 and -1 <= ny <= 1 and -1 <= nz <= 1): return None

        sx = (nx + 1) * window.width / 2 #[-1, 1]로 반환되는 값을 +1 / 2하면 [0,1]로, 그 다음 width 곱해서 화면의 x좌표
        sy = (ny + 1) * window.height / 2

        return sx, sy

    def screen2coord(self, window, x, y, plane_y) -> Vec3:
        """마우스 광선과 y=plane_y 평면의 교점을 반환."""
        self.apply(window)

        nx = 2 * x / window.width - 1 # [-1, 1]의 값으로
        ny = 2 * y / window.height - 1

        inverse = ~(window.projection @ window.view) # 역행렬 계산

        near = inverse @ Vec4(nx, ny, -1.0, 1.0)
        far = inverse @ Vec4(nx, ny, 1.0, 1.0)

        origin = Vec3(near.x, near.y, near.z) / near.w
        end = Vec3(far.x, far.y, far.z) / far.w
        direction = (end - origin).normalize()
        t = (plane_y - origin.y) / direction.y

        if t < 0:
            return None

        return origin + direction * t