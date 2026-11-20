import math

from pyglet.gl import GL_TRIANGLES
from pyglet.math import Vec3
from pyglet.model import SimpleMaterial

from materials import PhongMaterialGroup, apply_material_preset
from uv_mapping import make_pie_uvs
from box_geometry import box_frame, rounded_face


# 반시계 방향 90도 회전 횟수
FACE_ROTATIONS = {
    "front": 1,
    "back": 0,
    "right": 0,
    "left": 0,
    "top": 0,
    "bottom": 0,
}


# 앞면 폭 2.1의 약 0.38%만 바깥으로 휘게 한다.
# 0.0이면 평면이며, 이 값은 인쇄 그림의 밝기와 무관하다.
FRONT_BULGE = 0.008
# 실물 관찰: 긴 중앙선이 약 3 mm 솟는다. 0이면 기존의 평평한 윗면이다.
TOP_RIDGE_HEIGHT = 0.030



def create_pie_faces(
    program, batch, positions, normals, textures,
    *, shadow=None, reflections=None, bounce=None,
):
    angle = math.radians(30.0)
    short_axis = Vec3(math.cos(angle), 0.0, -math.sin(angle))
    long_axis = Vec3(-math.sin(angle), 0.0, -math.cos(angle))

    uvs = make_pie_uvs(positions, normals)
    frame = box_frame(positions)
    if reflections is not None:
        axes,center,half=frame
        normal=-axes[0];point=center-axes[0]*half[0]
        reflections.add_plane("box_front",normal,-normal.dot(point),strength=.95,roughness=.23)
    faces = {}

    for i in range(len(positions) // 3):
        n = Vec3(*normals[3*i:3*i+3])

        if n.y > 0.9:
            face = "top"
        elif n.y < -0.9:
            face = "bottom"
        elif n.dot(short_axis) < -0.9:
            face = "front"
        elif n.dot(short_axis) > 0.9:
            face = "back"
        elif n.dot(long_axis) < 0.0:
            face = "right"
        else:
            face = "left"

        u, v = uvs[2*i:2*i+2]

        for _ in range(FACE_ROTATIONS[face] % 4):
            u, v = v, 1.0 - u

        data = faces.setdefault(
            face,
            {"positions": [], "normals": [], "uvs": []},
        )

        data["positions"].extend(positions[3*i:3*i+3])
        data["normals"].extend(normals[3*i:3*i+3])
        data["uvs"].extend((u, v))

    result = []

    for face, data in faces.items():
        data = rounded_face(data, frame, FRONT_BULGE if face == "front" else 0.0,
                            ridge_height=TOP_RIDGE_HEIGHT)

        # 화면과 깊이 맵에서 같은 형상을 사용한다.
        if shadow is not None:
            shadow.add_mesh(data["positions"])

        material = SimpleMaterial(name=f"Pie_{face}")
        # 각 면의 재질 계수와 포장 텍스처를 설정한다.
        apply_material_preset(material)
        if face=="front":material.planar_plane="box_front"
        material.diffuse_texture = textures[face]
        if bounce is not None:
            # 화면·그림자·간접광의 가림에 동일한 곡면 메시를 사용한다.
            bounce.add_box_face(data,material,material.diffuse_texture)

        group = PhongMaterialGroup(
            material=material,
            program=program,
        )

        count = len(data["positions"]) // 3

        vertex_list = program.vertex_list(
            count,
            GL_TRIANGLES,
            batch=batch,
            group=group,
            POSITION=("f", data["positions"]),
            NORMAL=("f", data["normals"]),
            COLOR_0=("f", list(material.diffuse) * count),
            TEXCOORD_0=("f", data["uvs"]),
        )

        result.append(vertex_list)

    return result
