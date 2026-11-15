import pyglet
from pyglet.gl import GL_TEXTURE0, glActiveTexture, glBindTexture

MATERIAL_PRESETS = {
    "wall_white": ((0.0, 0.0, 0.0), 16.0),
    "wall_red": ((0.0, 0.0, 0.0), 16.0),
    "wall_green": ((0.0, 0.0, 0.0), 16.0),

    "torus_mint": ((0.20, 0.20, 0.20), 48.0),
    "Cup": ((0.35, 0.35, 0.35), 96.0),
    "Water": ((0.50, 0.50, 0.50), 128.0),

    "Default": ((0.08, 0.08, 0.08), 32.0),
}

OPACITY_PRESETS = {
    "Cup": 0.20,
    "Water": 0.10,
}

def apply_material_preset(material) :

    specular, shininess = MATERIAL_PRESETS.get(
        material.name, ((0.10, 0.10, 0.10), 32.0),
    )

    material.specular = (*specular, 1.0)
    material.shininess = shininess
    opacity = OPACITY_PRESETS.get(material.name, 1.0)
    material.diffuse = (*material.diffuse[:3], opacity) 

class PhongMaterialGroup(pyglet.model.MaterialGroup) :

    def set_state(self) :
        super().set_state()

        self.program["specular_color"] = self.material.specular[:3]
        self.program["shininess"] = self.material.shininess

        texture = getattr(self.material, "diffuse_texture", None)
        self.program["use_texture"] = texture is not None

        if texture is not None:
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(texture.target, texture.id)

            self.program["diffuse_texture"] = 0 # 텍스쳐 유닛 번호
