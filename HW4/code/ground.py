from pyglet.gl import GL_TRIANGLES
from pyglet.model import SimpleMaterial
from materials import PhongMaterialGroup, apply_material_preset

def create_ground(program, batch):
    half_size = 20.0
    y = -0.051

    positions = [
        -half_size, y, -half_size,
        -half_size, y,  half_size,
         half_size, y,  half_size,
         half_size, y, -half_size,
    ]

    material = SimpleMaterial(name="Ground")
    # 색과 간접광 보정값은 materials.py에서 함께 관리한다.
    apply_material_preset(material)
    material.diffuse_texture = None

    group = PhongMaterialGroup(
        material=material,
        program=program,
    )

    return program.vertex_list_indexed(
        4,
        GL_TRIANGLES,
        [0, 1, 2, 0, 2, 3],
        batch=batch,
        group=group,
        POSITION=("f", positions),
        NORMAL=("f", [0.0, 1.0, 0.0] * 4),
        COLOR_0=("f", list(material.diffuse) * 4),
        TEXCOORD_0=("f", [0.0, 0.0] * 4),
    )
