import pyglet
from pyglet.gl import GL_TEXTURE0, glActiveTexture, glBindTexture

MATERIAL_PRESETS = {
    "wall_white": ((0.0, 0.0, 0.0), 16.0),
    "wall_red": ((0.0, 0.0, 0.0), 16.0),
    "wall_green": ((0.0, 0.0, 0.0), 16.0),

    "torus_mint": ((0.02, 0.02, 0.02), 10.0),
    "Cup": ((0.04, 0.04, 0.04), 96.0),
    "Water": ((0.025, 0.025, 0.025), 160.0),

    "Default": ((0.008, 0.008, 0.008), 40.0),
    "Ground": ((0.0, 0.0, 0.0), 16.0),
}

OPACITY_PRESETS = {
    "Cup": 0.22,
    "Water": 0.08,
}

# 현재 조명, HDR 노출 2.4, 카메라에서 실물 사진에 맞춘 선형 RGB 보정값.
# 사진의 조명과 색 번짐도 포함한 유효 색이며, 측정한 반사율은 아니다.
DIFFUSE_PRESETS = {
    "wall_white": (0.305, 0.282, 0.327),
    "wall_red": (0.38, 0.035, 0.037),
    "wall_green": (0.016, 0.029, 0.020),
    "torus_mint": (0.10, 0.37, 0.22),
    "Cup": (0.69, 0.52, 0.54),
    "Water": (0.90, 0.95, 1.00),
    "Ground": (0.30, 0.19, 0.10),
    "Default": (0.80, 0.80, 0.84),
}

# 원본 OBJ에서는 바닥, 뒷벽, 천장이 같은 wall_white 재질을 쓴다.
# 면마다 다른 조명 상태를 사진에 맞추기 위해 색을 따로 보정한다.
MESH_DIFFUSE_PRESETS = {
    "Floor_Cube.001": (0.65, 0.81, 1.00),
    "Ceiling1_Cube.005": (0.66, 0.30, 0.37),
    "Ceiling2_Cube.006": (0.66, 0.30, 0.37),
    "Ceiling3_Cube.007": (0.66, 0.30, 0.37),
    "Ceiling4_Cube.008": (0.66, 0.30, 0.37),
}

# 간접광을 실제로 추적하는 대신 ambient 항의 크기를 보정한다.
# BRDF 계수와는 별개이며, 지정하지 않은 재질은 1.0을 사용한다.
AMBIENT_SCALE_PRESETS = {
    "Cup": 1.00,
    "Pie_right": 0.015,
    "Ground": 0.03,
}

MESH_AMBIENT_SCALE_PRESETS = {
    "Floor_Cube.001": 0.12,
}


def apply_material_preset(material, mesh_name=None):
    # 상자의 여섯 면은 기본 광택을 공유하고, 간접광 보정은 개별 적용한다.
    name = "Default" if material.name.startswith("Pie_") else material.name

    specular, shininess = MATERIAL_PRESETS.get(
        name, ((0.10, 0.10, 0.10), 32.0),
    )

    material.specular = (*specular, 1.0)
    material.shininess = shininess
    diffuse = DIFFUSE_PRESETS.get(name, material.diffuse[:3])
    diffuse = MESH_DIFFUSE_PRESETS.get(mesh_name, diffuse)
    opacity = OPACITY_PRESETS.get(name, 1.0)
    material.diffuse = (*diffuse, opacity)

    ambient_scale = AMBIENT_SCALE_PRESETS.get(
        material.name, AMBIENT_SCALE_PRESETS.get(name, 1.0)
    )
    material.ambient_scale = MESH_AMBIENT_SCALE_PRESETS.get(
        mesh_name, ambient_scale
    )

class PhongMaterialGroup(pyglet.model.MaterialGroup) :

    def set_state(self) :
        super().set_state()

        self.program["specular_color"] = self.material.specular[:3]
        self.program["shininess"] = self.material.shininess
        self.program["ambient_scale"] = getattr(
            self.material, "ambient_scale", 1.0
        )

        texture = getattr(self.material, "diffuse_texture", None)
        self.program["use_texture"] = texture is not None

        if texture is not None:
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(texture.target, texture.id)

            self.program["diffuse_texture"] = 0 # 텍스쳐 유닛 번호
