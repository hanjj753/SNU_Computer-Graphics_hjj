import pyglet
from pyglet.math import Vec3, Vec4
from pyglet.gl import *
from materials import apply_material_preset, PhongMaterialGroup
from pie_box import create_pie_faces
from camera import TrackballCamera
from shader import create_program
from ground import create_ground
from linear_target import SrgbTarget
from transparency import TransparentRenderer
from shadow_map import AreaShadowMaps
from HUD import HUD
from pathlib import Path
from io import StringIO
from copy import copy
import re

# 왼쪽 아래를 (0, 0, 0)으로 놓았을 때 Cornell box의 정 중앙의 좌표가 (1.45, 1.5, -1.5) 
center = Vec3(1.45, 1.50, -1.50)
eye = Vec3(1.45, 1.50, 5.00) # camera가 (1.45, 1.5, 5)
fov = 53.0  # 실물 사진에서 상자가 차지하는 비율에 맞춘 화각.

width = 960
height = 720

mouseRotatePressed = False
mouseMovePressed   = False
mouseDollyPressed   = False

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
    # 1차: 광원 시점에서 깊이 저장
    shadow.render()

    # 2차: 카메라 시점에서 색과 투명도 계산
    # begin()이 shadow map용 viewport도 창 크기로 되돌린다.
    render_target.begin(window)

    glDepthMask(GL_TRUE)
    glEnable(GL_DEPTH_TEST)
    glDisable(GL_BLEND)
    window.clear()

    camera.apply(window)

    inverse_view = ~window.view # view는 world -> camera 변환이니 inverse 하면 camera -> world 변환
    camera_world = inverse_view @ Vec4(0.0, 0.0, 0.0, 1.0)

    program["camera_position"] = (
        camera_world.x,
        camera_world.y,
        camera_world.z,
    )

    shadow.bind_to(program)

    batch.draw()
    transparency.draw(window.view)
    
    render_target.present()
    hud.draw()
		
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
render_target = SrgbTarget()
transparency = TransparentRenderer(program)

vertex_lists = []

MAX_LIGHTS = 64
GRID_SIZE = 2

if not 1 <= GRID_SIZE <= 8:
    raise ValueError("GRID_SIZE는 1부터 8까지 사용할 수 있습니다.")

light_center = Vec3(1.35, 2.95, -1.38)

light_width = 0.60
light_depth = 0.60

light_positions = []

for i in range(GRID_SIZE):
    for j in range(GRID_SIZE):
        x = light_center.x + (
            (i + 0.5) / GRID_SIZE - 0.5
        ) * light_width

        z = light_center.z + (
            (j + 0.5) / GRID_SIZE - 0.5
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

# 사진의 차가운 바닥 조명에 맞춘 선형 RGB 상대 세기.
program["light_color"] = (0.75, 0.85, 1.15)
program["light_intensity"] = 22.0
program["ambient_strength"] = 0.38

for node in scene.nodes:

    FACE_FILES = {
        "front": "chocopie_front.jpg",
        "back": "chocopie_back.png",
        "right": "chocopie_bottom.png",
        "left": "chocopie_top.png",
        "top": "chocopie_right.png",
        "bottom": "chocopie_left.jpg",
    }

    pie_textures = {}

    for face, filename in FACE_FILES.items():
        if filename is None:
            continue

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

    for mesh in node.meshes:
        for primitive in mesh.primitives:
            # 흰색 재질을 공유하는 바닥과 천장의 설정을 독립적으로 유지한다.
            material = copy(primitive.material)
            apply_material_preset(material, mesh.name)

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

            if material.diffuse[3] >= 1.0:
                shadow.add_mesh(positions) 

            vertex_count = len(positions) // 3

            if mesh.name == "Pie_Cube":
                vertex_lists.extend(
                    create_pie_faces(
                        program,
                        batch,
                        positions,
                        normals,
                        material,
                        pie_textures,
                    )
                )
                continue

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
camera.resize(window, width, height)

pyglet.app.run()
