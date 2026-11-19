import pyglet
from weakref import WeakKeyDictionary
from pyglet.gl import GL_TEXTURE0, glActiveTexture, glBindTexture

MATERIAL_PRESETS = {
    "wall_white": ((0.0, 0.0, 0.0), 16.0),
    # 사진의 PVC 광택에 맞춘 넓은 정반사 하이라이트.
    "wall_red": ((0.09, 0.09, 0.09), 18.0),
    "wall_green": ((0.09, 0.09, 0.09), 18.0),

    "torus_mint": ((0.03, 0.03, 0.03), 9.0),
    "Cup": ((0.04, 0.04, 0.04), 96.0),
    # 물의 최종 광학 계산은 water_optics.py의 별도 셰이더가 담당한다.
    "Water": ((0.0, 0.0, 0.0), 160.0),

    "Default": ((0.008, 0.008, 0.008), 40.0),
    # 윗면은 윤곽이 흐릿하게 비치는 코팅. 반사 계수는 유지하고 lobe를 넓힌다.
    "Pie_top": ((0.04, 0.04, 0.04), 24.0),
    # 앞면의 코팅은 넓고 완만한 정반사 분포로 근사한다.
    "Pie_front": ((0.045, 0.045, 0.045), 20.0),
    "Pie_bottom": ((0.0, 0.0, 0.0), 16.0),
    "Ground": ((0.0, 0.0, 0.0), 16.0),
}

OPACITY_PRESETS = {
    "Cup": 0.12,
    "Water": 0.0,
}

# 현재 조명, HDR 노출 2.4, 카메라에서 실물 사진에 맞춘 선형 RGB 보정값.
# 사진의 조명과 색 번짐도 포함한 유효 색이며, 측정한 반사율은 아니다.
# 직접광과 간접광 모두 이 색과 같은 Ks로 난반사 반사율을 계산한다.
DIFFUSE_PRESETS = {
    "wall_white": (0.305, 0.282, 0.327),
    # 다중 간접광을 함께 계산하므로 과하게 순색이던 기본색을 사진 쪽으로 되돌린다.
    "wall_red": (0.36, 0.014, 0.019),
    "wall_green": (0.006, 0.060, 0.019),
    "torus_mint": (0.20, 0.73, 0.43),
    "Cup": (0.72, 0.74, 0.77),
    # 맑은 물에 흰 난반사를 넣으면 우유처럼 보이므로 정반사만 남긴다.
    "Water": (0.0, 0.0, 0.0),
    "Ground": (0.30, 0.19, 0.10),
    "Default": (0.80, 0.80, 0.84),
}

# 원본 OBJ에서는 바닥, 뒷벽, 천장이 같은 wall_white 재질을 쓴다.
# 면마다 다른 조명 상태를 사진에 맞추기 위해 색을 따로 보정한다.
MESH_DIFFUSE_PRESETS = {
    "Floor_Cube.001": (0.65, 0.81, 1.00),
    # PVC의 재질은 중립적인 흰색. 붉고 초록인 빛은 간접광에서 계산한다.
    "Ceiling1_Cube.005": (0.68, 0.68, 0.68),
    "Ceiling2_Cube.006": (0.68, 0.68, 0.68),
    "Ceiling3_Cube.007": (0.68, 0.68, 0.68),
    "Ceiling4_Cube.008": (0.68, 0.68, 0.68),
}

# 천장 PVC의 광택 계수도 실측 반사율이 아닌 사진 조절값이다.
MESH_SPECULAR_PRESETS = {
    name: ((0.16, 0.16, 0.16), 24.0)
    for name in MESH_DIFFUSE_PRESETS if name.startswith("Ceiling")
}

# 간접광을 실제로 추적하는 대신 ambient 항의 크기를 보정한다.
# BRDF 계수와는 별개이며, 지정하지 않은 재질은 1.0을 사용한다.
AMBIENT_SCALE_PRESETS = {
    "wall_red": 0.30,
    "wall_green": 0.30,
    # 도넛의 어두운 앞면은 ambient를 줄이고, 밝은 윗면은 높은 반사색으로 살린다.
    "torus_mint": 0.22,
    "Cup": 1.00,
    "Pie_right": 0.015,
    # 바닥에 닿아 직접광이 없는 밑면에 ambient로 무늬를 띄우지 않는다.
    "Pie_bottom": 0.0,
    "Ground": 0.03,
}

MESH_AMBIENT_SCALE_PRESETS = {
    "Floor_Cube.001": 0.12,
    # 뒷벽은 계산한 직접광·간접광으로 밝히고, 균일한 ambient는 더하지 않는다.
    "Back_Wall_Cube.002": 0.1,
    "Ceiling1_Cube.005": 0.0,
    "Ceiling2_Cube.006": 0.0,
    "Ceiling3_Cube.007": 0.0,
    "Ceiling4_Cube.008": 0.0,
}


def apply_material_preset(material, mesh_name=None):
    # 상자는 기본 재질을 공유하되 Pie_top의 코팅 광택을 따로 설정할 수 있다.
    name = "Default" if material.name.startswith("Pie_") else material.name

    specular, shininess = MATERIAL_PRESETS.get(
        material.name, MATERIAL_PRESETS.get(name, ((0.10, 0.10, 0.10), 32.0))
    )
    specular, shininess = MESH_SPECULAR_PRESETS.get(mesh_name, (specular, shininess))

    material.specular = (*specular, 1.0)
    material.shininess = shininess
    material.surface_grain = 0.065 if material.name=="torus_mint" else 0.0
    diffuse = DIFFUSE_PRESETS.get(name, material.diffuse[:3])
    diffuse = MESH_DIFFUSE_PRESETS.get(mesh_name, diffuse)
    opacity = OPACITY_PRESETS.get(name, 1.0)
    material.diffuse = (*diffuse, opacity)

    # 상자와 벽의 색 번짐을 Cornell box의 천장·벽·바닥에서 받는다.
    material.receive_ceiling_bounce = material.name in ("wall_white","wall_red","wall_green") or (
        material.name.startswith("Pie_") and material.name!="Pie_bottom"
    )
    # Use the computed GI without an extra brightness multiplier.
    material.indirect_diffuse_gain = 1.0
    material.baked_ceiling_surface = bool(mesh_name and mesh_name.startswith("Ceiling"))
    material.planar_plane = (
        "ceiling" if mesh_name and mesh_name.startswith("Ceiling") else
        {"wall_red":"left","wall_green":"right"}.get(material.name)
    )

    ambient_scale = AMBIENT_SCALE_PRESETS.get(
        material.name, AMBIENT_SCALE_PRESETS.get(name, 1.0)
    )
    material.ambient_scale = MESH_AMBIENT_SCALE_PRESETS.get(
        mesh_name, ambient_scale
    )

_reflection_renderers = WeakKeyDictionary()


def attach_reflections(program, renderer):
    _reflection_renderers[program] = renderer


class PhongMaterialGroup(pyglet.model.MaterialGroup) :

    def set_state(self) :
        super().set_state()

        self.program["specular_color"] = self.material.specular[:3]
        self.program["shininess"] = self.material.shininess
        self.program["surface_grain"] = getattr(self.material,"surface_grain",0.0)
        self.program["indirect_diffuse_gain"] = getattr(self.material,"indirect_diffuse_gain",1.0)
        self.program["baked_ceiling_surface"] = getattr(self.material,"baked_ceiling_surface",False)
        self.program["cup_surface"] = self.material.name=="Cup"
        self.program["contact_occlusion_height"] = (
            0.04 if self.material.name.startswith("Pie_") else 0.0
        )
        self.program["ambient_scale"] = getattr(
            self.material, "ambient_scale", 1.0
        )
        self.program["receive_ceiling_bounce"] = getattr(
            self.material, "receive_ceiling_bounce", False
        )

        texture = getattr(self.material, "diffuse_texture", None)
        self.program["use_texture"] = texture is not None

        if texture is not None:
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(texture.target, texture.id)

            self.program["diffuse_texture"] = 0 # 텍스쳐 유닛 번호

        reflections = _reflection_renderers.get(self.program)
        if reflections is not None:
            reflections.bind_material(self.program,self.material)
        else:
            self.program["planar_strength"] = 0.0
