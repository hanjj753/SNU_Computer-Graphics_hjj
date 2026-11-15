import math

from pyglet.gl import GL_TRIANGLES
from pyglet.math import Vec3
from pyglet.model import SimpleMaterial

from materials import PhongMaterialGroup
from uv_mapping import make_pie_uvs


# 반시계 방향 90도 회전 횟수
FACE_ROTATIONS = {
    "front": 1,
    "back": 0,
    "right": 0,
    "left": 0,
    "top": 0,
    "bottom": 0,
}


def create_pie_faces(
    program, batch, positions, normals, base_material, textures
):
    angle = math.radians(30.0)
    short_axis = Vec3(math.cos(angle), 0.0, -math.sin(angle))
    long_axis = Vec3(-math.sin(angle), 0.0, -math.cos(angle))

    uvs = make_pie_uvs(positions, normals)
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
        material = SimpleMaterial(
            name=f"Pie_{face}",
            diffuse=tuple(base_material.diffuse),
            specular=tuple(base_material.specular),
            shininess=base_material.shininess,
        )
        material.diffuse_texture = textures.get(face)

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