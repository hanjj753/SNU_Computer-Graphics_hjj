import math

from pyglet.gl import GL_TRIANGLES
from pyglet.math import Vec3
from pyglet.model import SimpleMaterial

from materials import PhongMaterialGroup, apply_material_preset
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


# 앞면 폭 2.1의 약 0.38%만 바깥으로 휘게 한다.
# 0.0이면 평면이며, 이 값은 인쇄 그림의 밝기와 무관하다.
FRONT_BULGE = 0.008
FRONT_SUBDIVISIONS = 24


def _curve_front_face(data, subdivisions, bulge):
    """앞면을 분할하고, 경계가 고정된 완만한 곡면으로 만든다."""
    if subdivisions < 1:
        raise ValueError("앞면 분할 수는 1 이상이어야 합니다.")

    result = {"positions": [], "normals": [], "uvs": []}

    for start in range(0, len(data["positions"]), 9):
        points = [
            Vec3(*data["positions"][start + 3*i:start + 3*i + 3])
            for i in range(3)
        ]
        uv_start = (start // 3) * 2
        texcoords = [
            data["uvs"][uv_start + 2*i:uv_start + 2*i + 2]
            for i in range(3)
        ]
        exported_normal = Vec3(*data["normals"][start:start + 3]).normalize()

        # 원래 평면에서 UV가 1만큼 변할 때의 월드 좌표 변화량.
        # 앞면 텍스처가 90도 회전되어 있어도 올바른 접선이 나온다.
        edge1 = points[1] - points[0]
        edge2 = points[2] - points[0]
        # OBJ 법선의 반올림 오차를 피하고 실제 삼각형의 법선을 사용한다.
        normal = edge1.cross(edge2).normalize()
        if normal.dot(exported_normal) < 0.0:
            normal = -normal
        du1 = texcoords[1][0] - texcoords[0][0]
        dv1 = texcoords[1][1] - texcoords[0][1]
        du2 = texcoords[2][0] - texcoords[0][0]
        dv2 = texcoords[2][1] - texcoords[0][1]
        determinant = du1 * dv2 - du2 * dv1
        if abs(determinant) < 1e-10:
            raise ValueError("상자 앞면의 UV 삼각형이 퇴화했습니다.")

        dpdu = (edge1 * dv2 - edge2 * dv1) / determinant
        dpdv = (edge2 * du1 - edge1 * du2) / determinant
        orientation = 1.0 if dpdu.cross(dpdv).dot(normal) > 0.0 else -1.0

        # 원본 삼각형 안에서 위치와 UV를 같은 비율로 보간한다.
        grid = {}
        for i in range(subdivisions + 1):
            for j in range(subdivisions + 1 - i):
                b = i / subdivisions
                c = j / subdivisions
                a = 1.0 - b - c
                position = points[0] * a + points[1] * b + points[2] * c
                u = texcoords[0][0] * a + texcoords[1][0] * b + texcoords[2][0] * c
                v = texcoords[0][1] * a + texcoords[1][1] * b + texcoords[2][1] * c

                # UV를 곡면의 좌표로만 쓴다. 인쇄된 파이 그림은 높이로 쓰지 않는다.
                # h = A sin²(pi*u) sin²(pi*v)
                # 경계에서는 변위와 기울기가 0이라 옆면과 틈이 생기지 않는다.
                sin_u = math.sin(math.pi * u)
                sin_v = math.sin(math.pi * v)
                height = bulge * sin_u**2 * sin_v**2
                dhdu = bulge * math.pi * math.sin(2 * math.pi * u) * sin_v**2
                dhdv = bulge * math.pi * sin_u**2 * math.sin(2 * math.pi * v)
                position += normal * height

                # 변형된 곡면의 접선 두 개를 외적해 새 법선을 계산한다.
                tangent_u = dpdu + normal * dhdu
                tangent_v = dpdv + normal * dhdv
                curved_normal = tangent_u.cross(tangent_v).normalize() * orientation
                grid[i, j] = position, curved_normal, (u, v)

        for i in range(subdivisions):
            for j in range(subdivisions - i):
                triangles = [((i, j), (i + 1, j), (i, j + 1))]
                if i + j < subdivisions - 1:
                    triangles.append(((i + 1, j), (i + 1, j + 1), (i, j + 1)))
                for triangle in triangles:
                    for key in triangle:
                        position, curved_normal, uv = grid[key]
                        result["positions"].extend(position)
                        result["normals"].extend(curved_normal)
                        result["uvs"].extend(uv)

    return result


def create_pie_faces(
    program, batch, positions, normals, base_material, textures,
    *, shadow=None,
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
        if face == "front":
            data = _curve_front_face(data, FRONT_SUBDIVISIONS, FRONT_BULGE)

        # 화면과 깊이 맵에서 같은 형상을 사용한다.
        if shadow is not None:
            shadow.add_mesh(data["positions"])

        material = SimpleMaterial(
            name=f"Pie_{face}",
            diffuse=tuple(base_material.diffuse),
            specular=tuple(base_material.specular),
            shininess=base_material.shininess,
        )
        # 광택은 공통값을 쓰고, 사진에서 어두운 측면의 간접광은 따로 보정한다.
        apply_material_preset(material)
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
