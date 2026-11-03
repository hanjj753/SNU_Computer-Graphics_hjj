import pyglet
from camera import TrackballCamera
from pyglet.gl import *
from pyglet.math import Vec3, Mat4
from Bspline import BSpline
from Ground import Ground
from Rail import Rails, CartTrain, trackAxes
from HUD import HUD
from pathlib import Path

center = Vec3(0, 0, 0)
eye = Vec3(8, 6, 8)
fov = 60
width = 960
height = 720
BASE_DIR = Path(__file__).resolve().parent

mouseRotatePressed = False
mouseMovePressed   = False
mouseDollyPressed   = False

camera = TrackballCamera(eye=eye, center=center, fov=fov)
window = pyglet.window.Window( width, height, resizable=True, caption="Roller Coaster")
batch = pyglet.graphics.Batch()

splines = []

for path in sorted(Path(BASE_DIR/"tracks").glob("spline_*.json")):
    spline = BSpline()
    spline.loadCurve(path)
    splines.append(spline)

if not splines:
    splines = [BSpline()]

active_spline = None
drag_mode = None
drag_plane_y = 0.0
HEIGHT_SPEED = 0.02
drag_offset = Vec3(0, 0, 0)

ground = Ground(s=20, y=-1)

hud = HUD(window)
u, t, s = 0.0, 0.0, 0.0 # inital
timer_running = False

marker_program = pyglet.graphics.get_default_shader()
marker = marker_program.vertex_list(
    1,
    GL_POINTS,
    position="f",
    colors=("Bn", (255, 220, 0, 255)),
)

train = CartTrain(BASE_DIR/"models", scale=0.1)

rails = [Rails(spline, gauge=train.gauge,radius=0.006, drop=train.wheel_drop + 0.006) for spline in splines]

def applyCamera() :
	if not hud.fp_mode : camera.apply(window); return

	spline = splines[0]
	position = spline.evaluate(u)
	_, up, forward = trackAxes(spline, u)

	eye = position + up * 0.18 + forward * 0.04
	window.view = Mat4.look_at(position=eye, target=eye + forward, up=up) #window.view를 설정하면 이게 opengl로 전달

@window.event
def on_resize(width, height):

	camera.resize( window, width, height )
	hud.resize(width, height)
	return pyglet.event.EVENT_HANDLED

@window.event
def on_draw():
	window.clear()
	applyCamera()
	batch.draw()
	ground.draw()

	for spline in splines:
		if hud.os : spline.draw()
		if hud.show_frames : spline.drawFrames(u=u)
		if not hud.watch_mode : spline.drawControlPoints()
		if hud.show_quaternion_controls: spline.quaternion_frame.drawControls(spline)

	for rail in rails: rail.draw()
	train.draw(splines[0], u)

	# 현재 u의 위치
	if hud.marker :
		position = splines[0].evaluate(u)
		marker.position[:] = position

		marker_program.use()
		glPointSize(12.0)
		marker.draw(GL_POINTS)
		glPointSize(1.0)
		marker_program.stop()

	hud.draw()
		
@window.event
def on_mouse_release( x, y, button, mods ):
	global mouseRotatePressed, mouseMovePressed, mouseDollyPressed, drag_mode

	mouseMovePressed   = False
	mouseRotatePressed = False
	mouseDollyPressed   = False
	drag_mode = None

@window.event
def on_mouse_press( x, y, button, mods ):
	global mouseRotatePressed, mouseMovePressed, mouseDollyPressed, active_spline, drag_mode, drag_plane_y, drag_offset

	mouseRotatePressed = False
	mouseMovePressed = False
	mouseDollyPressed = False
	drag_mode = None

	if hud.fp_mode: return

	if button & pyglet.window.mouse.LEFT and mods & pyglet.window.key.MOD_SHIFT:
		mouseMovePressed   = True
	elif button & pyglet.window.mouse.LEFT and mods & pyglet.window.key.MOD_CTRL:
		mouseDollyPressed   = True
	elif button & pyglet.window.mouse.LEFT:
		for spline in splines : spline.picked = -1 # 이전 선택 해제

		if not hud.watch_mode : active_spline, index = selectPoint(x, y)
		if active_spline is  None: 
			camera.begin_rotate(x, y)
			mouseRotatePressed = True
		else :
			active_spline.picked = index
			point = Vec3(*active_spline.points[index])
			if mods & pyglet.window.key.MOD_ALT: drag_mode = "y"
			else :
				hit = camera.screen2coord(window, x, y, point.y) # 선택한 점의 y좌표를 가지는 xz 평면에서 작업할 것
				if hit is not None :
					drag_mode = "xz"
					drag_plane_y = point.y
					drag_offset = point - hit

@window.event
def on_mouse_drag( x, y, dx, dy, button, mods ):	

	if hud.fp_mode: return

	if mouseRotatePressed:
		camera.rotate(x, y)
	elif mouseMovePressed:
		camera.move(dx/window.width, dy/window.height, 0.0)
	elif mouseDollyPressed:
		camera.zoom(dy/window.height)
	elif drag_mode is not None and active_spline is not None :
		i = active_spline.picked
		point = Vec3(*active_spline.points[i])

		if drag_mode == "y" : point += Vec3(0, dy*HEIGHT_SPEED, 0) #y축 방향 움직임
		else : #zx 평면 움직임
			hit = camera.screen2coord(window, x, y, drag_plane_y)
			if hit is not None : point = hit + drag_offset # 기존에 drag offset을 point-hit으로 구했기 때문에 처음에 point에서 시작한다

		active_spline.points[i] = list(point)
		active_spline.updateCurve()	

@window.event
def on_key_press(key, modifiers):
	global drag_mode, active_spline, timer_running
	
	if key == pyglet.window.key.R:
		camera.reset()
		drag_mode = None
		active_spline = None

	elif key == pyglet.window.key.Q:
		pyglet.app.exit()

	elif key == pyglet.window.key.S and modifiers & pyglet.window.key.MOD_CTRL:
		
		for i, spline in enumerate(splines): spline.saveCurve(BASE_DIR/"tracks"/f"spline_{i:03d}.json")
		print("저장되었습니다.")
	elif key == pyglet.window.key.ENTER :
		if hud.watch_mode : return
		if active_spline is None or active_spline.picked < 0: return

		i = active_spline.picked
		points = active_spline.points

		a = Vec3(*points[i])
		b = Vec3(*points[(i + 1) % len(points)]) # 마지막 꺼는 첫번째 거가 다음 거

		points.insert(i + 1, list((a + b) * 0.5)) # 선택한 점 바로 뒤에 두 점의 중점 넣기
		active_spline.updateCurve()
	elif key == pyglet.window.key.N :
		if hud.watch_mode : return
		if active_spline is None or active_spline.picked < 0: return
		active_spline.picked += 1
	elif key == pyglet.window.key.X :
		if hud.watch_mode : return
		if active_spline is None or active_spline.picked < 0: return
		if len(active_spline.points) <= 4 : return
		i = active_spline.picked
		active_spline.points.pop(i)
		active_spline.picked = i % len(active_spline.points)
		active_spline.updateCurve()
	elif key == pyglet.window.key.F:
		hud.toggleFrames()
	elif key == pyglet.window.key.W:
		hud.toggleWatchmode()
	elif key == pyglet.window.key.T:
		timer_running = not timer_running
	elif key == pyglet.window.key.C:
		hud.toggleFPmode()
	elif key == pyglet.window.key.M:
		hud.toggleMarker()
	elif key == pyglet.window.key.S:
		hud.toggleSpline()
	elif key == pyglet.window.key.G:
		
		for spline in splines: spline.use_quaternion = not spline.use_quaternion
		for rail in rails: rail.rebuild()

	elif key == pyglet.window.key.H:
		hud.toggleQuaternionControls()
	elif key in (pyglet.window.key.J, pyglet.window.key.L):
		
		timer_running = False # 타이머 멈추기
		spline = splines[0]
		spline.use_quaternion = True

		T, _, _ = spline.u2frame(u)
		degrees = -30 if key == pyglet.window.key.J else 30

		spline.quaternion_frame.rotateAt(u, T, degrees)

		for rail in rails: 
			if rail.spline is spline: rail.rebuild()

def selectPoint(x, y, radius=10):
    camera.apply(window)

    selected_spline = None
    selected_index = -1
    best_dist = radius ** 2

    for spline in splines:
        for i, point in enumerate(spline.points):
            screen = camera.coord2screen(window, point)
            if screen is None:
                continue

            sx, sy = screen
            dist = (sx - x) ** 2 + (sy - y) ** 2

            if dist < best_dist:
                best_dist = dist
                selected_spline = spline
                selected_index = i

    return selected_spline, selected_index

def update_utv(dt) :
	global u, t, s

	if timer_running : 
		t += dt
		v = splines[0].velocity(u)
		s += v*dt
		u = splines[0].dist2u(s)
		hud.setUTV(u, t, v)

glClearColor(0.0, 0.1, 0.3, 1.0)
glEnable(GL_DEPTH_TEST)
glClearDepth(1.0)
glDepthFunc(GL_LESS)

pyglet.clock.schedule_interval(update_utv, 1 / 60)
pyglet.app.run()