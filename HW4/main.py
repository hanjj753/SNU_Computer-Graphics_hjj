import pyglet
from pyglet.math import Vec3, Vec4
from pyglet.gl import *
from materials import apply_material_preset, PhongMaterialGroup, attach_reflections
from pie_box import create_pie_faces
from camera import TrackballCamera
from shader import create_program
from ground import create_ground
from linear_target import HdrTarget
from ceiling_light import CeilingLight
from ceiling_bounce import CeilingBounce
from transparency import TransparentRenderer
from water_surface import build_water_volume
from water_optics import WaterRenderer
from shadow_map import AreaShadowMaps
from transmission_shadow import WaterTransmissionShadow, CupTransmissionShadow
from cup_geometry import build_cup_mesh
from planar_reflection import PlanarReflections
from HUD import HUD
from tools.capture_frame import save_frame
from pathlib import Path
from io import StringIO
from copy import copy
import re
import random

# 원본 사진을 960×720으로 맞춘 뒤, 방과 상자 모서리 12점의 투영 위치로 보정한 초기 시점.
# center는 공간의 기하학적 중심이 아니라 카메라가 바라보는 점이다.
center = Vec3(1.3705, 1.7685, -1.50)
eye = Vec3(1.4376, 1.4747, 5.0614)
fov = 52.6253  # 세로 화각(도). 카메라 거리·방향과 함께 맞춘 근사값.

width = 960
height = 720

mouseRotatePressed = False
mouseMovePressed   = False
mouseDollyPressed   = False
initial_frame_saved = False

camera = TrackballCamera(eye=eye, center=center, fov=fov)
window = pyglet.window.Window( width, height, resizable=True, caption="Cornell Box" )
batch = pyglet.graphics.Batch()
hud = HUD(window)

@window.event
def on_resize(width, height):
    camera.resize(window, width, height)
    hud.resize(width, height)
    return pyglet.event.EVENT_HANDLED

@window.event
def on_draw():
    global initial_frame_saved

    # 광원과 물체가 고정되어 있으면 첫 프레임의 깊이 맵을 재사용한다.
    shadow.render()
    water_shadow.render()
    cup_shadow.render()

    camera.apply(window)

    inverse_view = ~window.view # view는 world -> camera 변환이니 inverse 하면 camera -> world 변환
    camera_world = inverse_view @ Vec4(0.0, 0.0, 0.0, 1.0)

    program["camera_position"] = (
        camera_world.x,
        camera_world.y,
        camera_world.z,
    )

    shadow.bind_to(program)
    water_shadow.bind_to(program)
    cup_shadow.bind_to(program)
    ceiling_bounce.bind_depth(program)
    shadow.bind_to(water.program)

    # 주변 반사는 물 중앙에서 본 환경맵을 재사용한다. 장면이 고정이면 최초 한 번.
    # 광원의 직접 정반사는 물 셰이더가 shadow map과 함께 별도 계산한다.
    pvc_reflections.suspended=True
    try:
        water.capture_environment(window, program, batch.draw)
    finally:
        pvc_reflections.suspended=False
    # PVC의 주변 물체 반사: 대칭 카메라로 다시 래스터화한 영상을 사용한다.
    # 직접 광원의 하이라이트는 이미 계산하므로 발광판은 이 영상에서 제외한다.
    pvc_reflections.capture(window,program,batch.draw,lambda view:transparency.draw(view))

    # 카메라 시점의 선형 HDR 장면을 그린다.
    render_target.begin(window)
    glDepthMask(GL_TRUE)
    glEnable(GL_DEPTH_TEST)
    glDisable(GL_BLEND)
    window.clear()
    draw_opaque_scene()
    render_target.resolve()  # MSAA 샘플을 합친 뒤 컵·물의 굴절 배경으로 사용한다.

    water.prepare_depth(window, render_target)
    # 뒤쪽 컵 → 배경 저장 → 물 → 앞쪽 컵 순서로 합성한다.
    transparency.draw(window.view, phase=-1, water_depth=water.front_depth, viewport_size=water.size, render_target=render_target)
    water.capture_scene(render_target)
    water.draw(window)
    transparency.draw(window.view, phase=1, water_depth=water.front_depth, viewport_size=water.size, render_target=render_target)
    
    render_target.present()
    hud.draw()

    # 첫 화면을 HUD까지 그린 뒤 한 번만 저장한다. 이후 카메라 조작으로 덮어쓰지 않는다.
    if not initial_frame_saved:
        save_frame(base_dir / "pictures" / "rendered_Cornell Box.png")
        initial_frame_saved = True


def draw_opaque_scene():
    batch.draw()
    ceiling_light.draw()
		
@window.event
def on_mouse_release( x, y, button, mods ):
	global mouseRotatePressed, mouseMovePressed, mouseDollyPressed

	mouseMovePressed   = False
	mouseRotatePressed = False
	mouseDollyPressed   = False

@window.event
def on_mouse_press( x, y, button, mods ):
	global mouseRotatePressed, mouseMovePressed, mouseDollyPressed

	if button & pyglet.window.mouse.LEFT and mods & pyglet.window.key.MOD_SHIFT:
		mouseMovePressed   = True
		mouseRotatePressed = False
		mouseDollyPressed   = False
	elif button & pyglet.window.mouse.LEFT and mods & pyglet.window.key.MOD_CTRL:
		mouseMovePressed   = False
		mouseRotatePressed = False
		mouseDollyPressed   = True
	elif button & pyglet.window.mouse.LEFT:
		camera.begin_rotate(x, y)
		mouseMovePressed   = False
		mouseRotatePressed = True
		mouseDollyPressed   = False

@window.event
def on_mouse_drag( x, y, dx, dy, button, mods ):	
	if mouseRotatePressed:
		camera.rotate(x, y)
	elif mouseMovePressed:
		camera.move(dx/window.width, dy/window.height, 0.0)
	elif mouseDollyPressed:
		camera.zoom(dy/window.height)

@window.event
def on_key_press(key, modifiers):
    if key == pyglet.window.key.R:
        camera.reset()

    elif key == pyglet.window.key.M:
        pvc_reflections.enabled=not pvc_reflections.enabled
        hud.set_reflection_state(pvc_reflections.enabled)

    elif key == pyglet.window.key.Q:
        pyglet.app.exit()	


glClearColor(0.0, 0.0, 0.0, 1.0)
glEnable(GL_DEPTH_TEST)
glClearDepth(1.0)
glDepthFunc(GL_LESS)


base_dir = Path(__file__).resolve().parent
obj_path = base_dir / "models" / "cornell_scene.obj"
obj_text = obj_path.read_text(encoding="utf-8")
obj_text = re.sub(r"(?m)^g(\s+)", r"o\1", obj_text) # pyglet이 무시하는 Blender의 group 지시문을 object 지시문으로 변환

scene = pyglet.model.load(str(obj_path), file=StringIO(obj_text))

program = create_program()
program["reflection_clip_plane"]=(0,0,0,1)
pvc_reflections = PlanarReflections()
attach_reflections(program,pvc_reflections)
render_target = HdrTarget(exposure=2.4)
transparency = TransparentRenderer(program)
water = WaterRenderer()

vertex_lists = []

MAX_LIGHTS = 16
GRID_SIZE = 4

if not 1 <= GRID_SIZE <= 4:
    raise ValueError("GRID_SIZE는 1부터 4까지 사용할 수 있습니다.")

# 실제 천장 구멍의 중앙. 모든 샘플이 발광판 범위 안에 놓인다.
light_center = Vec3(1.45, 3.001, -1.50)

light_width = 0.60
light_depth = 0.60

light_positions = []
light_rng = random.Random(2026)

for i in range(GRID_SIZE):
    for j in range(GRID_SIZE):
        # 각 칸 안에서 위치를 분산해 규칙적인 그림자 띠를 줄인다.
        # 고정 seed를 사용하므로 매 프레임 흔들리지 않는다.
        x = light_center.x + (
            (i + light_rng.random()) / GRID_SIZE - 0.5
        ) * light_width

        z = light_center.z + (
            (j + light_rng.random()) / GRID_SIZE - 0.5
        ) * light_depth

        light_positions.append(
            (x, light_center.y, z)
        )

shadow = AreaShadowMaps(light_positions)
light_count = len(light_positions)

padded_positions = light_positions + [
    (0.0, 0.0, 0.0)
] * (MAX_LIGHTS - light_count)

program["light_positions"] = padded_positions
program["light_count"] = light_count

# 실제 광원은 S24의 흰 화면이다. 화면 설정과 촬영 WB를 분리 측정하지 않았으므로
# 이 값은 해당 사진의 바닥 조명에 맞춘 선형 RGB 상대값이다.
light_color = (0.75, 0.85, 1.00)
program["light_color"] = light_color
program["light_normal"] = (0.0, -1.0, 0.0)
light_intensity = 38.0
program["light_intensity"] = light_intensity
program["ambient_strength"] = 0.38
for name in ("light_positions", "light_count", "light_color", "light_normal", "light_intensity"):
    water.program[name] = program[name]
ceiling_bounce = CeilingBounce(light_positions, light_color, light_intensity)

# 천장 구멍보다 아주 조금 위에 두어 주변 면과의 깊이 충돌을 피한다.
ceiling_light = CeilingLight(
    center=Vec3(light_center.x, 3.002, light_center.z),
    width=light_width,
    depth=light_depth,
    color=light_color,
    brightness=40.0,
)

FACE_FILES = {
    "front": "chocopie_front.jpg",
    # 앞면의 흰 글자·빨간 인쇄색에 맞춘 sRGB 사본. 원본 사진은 보존한다.
    "back": "color_matched/chocopie_back.png",
    "right": "color_matched/chocopie_bottom.png",
    "left": "color_matched/chocopie_top.png",
    "top": "color_matched/chocopie_right.png",
    "bottom": "color_matched/chocopie_left.png",
}

pie_textures = {}

for face, filename in FACE_FILES.items():
    texture = pyglet.image.load(
        str(base_dir / "textures" / filename)
    ).get_texture()

    glBindTexture(texture.target, texture.id)

    glTexParameteri(
        texture.target, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE
    )
    glTexParameteri(
        texture.target, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE
    )

    pie_textures[face] = texture

for node in scene.nodes:
    for mesh in node.meshes:
        for primitive in mesh.primitives:
            # 흰색 재질을 공유하는 바닥과 천장의 설정을 독립적으로 유지한다.
            material = copy(primitive.material)

            positions = next(
                attribute.array
                for attribute in primitive.attributes
                if attribute.name == "POSITION"
            )

            normals = next(
                attribute.array
                for attribute in primitive.attributes
                if attribute.name == "NORMAL"	
            )

            vertex_count = len(positions) // 3

            if material.name == "Cup":
                # 같은 치수의 몸체에 얇은 평평한 입구 띠를 연결한다.
                cup_mesh = build_cup_mesh(positions)
                water.set_cup(cup_mesh)
                positions, normals = cup_mesh.positions, cup_mesh.normals
                material.rim_base_y = cup_mesh.rim_base_y
                vertex_count = len(positions)//3

            if mesh.name == "Pie_Cube":
                vertex_lists.extend(
                    create_pie_faces(
                        program,
                        batch,
                        positions,
                        normals,
                        pie_textures,
                        shadow=shadow,
                        reflections=pvc_reflections,
                        bounce=ceiling_bounce,
                    )
                )
                continue

            if material.name == "Water":
                # 굴절 경로의 두께가 필요하므로 수면에 옆면과 바닥을 연결한다.
                # 여러 겹을 alpha 합성하는 대신 가장 가까운 경계에서 한 번 계산한다.
                water.set_mesh(*build_water_volume(positions,cup_mesh))
                continue

            apply_material_preset(material, mesh.name)

            if material.name in ("wall_red", "wall_green"):
                inward = Vec3(1, 0, 0) if material.name == "wall_red" else Vec3(-1, 0, 0)
                ceiling_bounce.add_room_surface(positions, normals, material, inward)

            if mesh.name.startswith("Floor"):
                ceiling_bounce.add_room_surface(positions,normals,material,Vec3(0,1,0))
            elif mesh.name.startswith("Back_Wall"):
                ceiling_bounce.add_room_surface(positions,normals,material,Vec3(0,0,1))
            elif mesh.name.startswith("Ceiling"):
                ceiling_bounce.add_room_surface(positions,normals,material,Vec3(0,-1,0))
            elif material.name=="torus_mint":
                ceiling_bounce.add_occluder(positions)

            if material.diffuse[3] >= 1.0:
                shadow.add_mesh(positions)

            material.diffuse_texture = None
            texcoords = [0.0, 0.0] * vertex_count

            if material.diffuse[3] < 1.0: # alpha가 불투명이 아니면 투명 렌더러에서 처리
                transparency.add_mesh(positions, normals, material)
                continue

            group = PhongMaterialGroup(
                material=material,
                program=program,
            )

            vertex_list = program.vertex_list(
                vertex_count,
                GL_TRIANGLES,
                batch=batch,
                group=group,
                POSITION=("f", positions),
                NORMAL=("f", normals),
                COLOR_0=("f", material.diffuse * vertex_count),
                TEXCOORD_0=("f", texcoords),
            )

            vertex_lists.append(vertex_list)

ground = create_ground(program, batch)
transparency.optics.set_cup(cup_mesh,water.top)
ceiling_bounce.bind_to(program)
water_shadow = WaterTransmissionShadow(shadow, water, light_positions)
cup_shadow = CupTransmissionShadow(shadow, cup_mesh, light_positions, water_level=water.top)
camera.resize(window, width, height)

pyglet.app.run()
