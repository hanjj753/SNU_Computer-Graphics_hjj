"""컵 하나를 깊이순으로 그린다. 물 앞/뒤 구분은 셰이더에서 픽셀마다 한다."""

from pyglet.gl import *
from pyglet.math import Vec4

from materials import PhongMaterialGroup
from cup_optics import CupOptics

CUP_RIM_OPACITY = 0.40


class TransparentRenderer:
    def __init__(self, program):
        self.program = program
        self.optics = CupOptics(program)

    def add_mesh(self, positions, normals, material):
        self.group = PhongMaterialGroup(material=material, program=self.program)
        self.centers = []
        self.sorted_view = None
        colors = []
        for i in range(0, len(positions), 9):
            triangle = positions[i:i+9]
            self.centers.append(Vec4(
                sum(triangle[0::3])/3,
                sum(triangle[1::3])/3,
                sum(triangle[2::3])/3,
                1.0,
            ))
            # 몸체와 입구 띠는 광택이 같고 alpha만 다르므로, 정점 색으로 구분한다.
            opacity = (CUP_RIM_OPACITY if min(triangle[1::3]) >= material.rim_base_y-1e-6
                       else material.diffuse[3])
            colors.extend([*material.diffuse[:3], opacity]*3)

        count = len(positions)//3
        self.vertices = self.program.vertex_list_indexed(
            count, GL_TRIANGLES, list(range(count)),
            POSITION=("f", positions), NORMAL=("f", normals),
            COLOR_0=("f", colors), TEXCOORD_0=("f", [0.0, 0.0]*count),
        )

    def draw(self, view, *, phase=0, water_depth=None, viewport_size=None, render_target=None):
        # 카메라 앞은 -Z이다. 먼 삼각형부터 그리도록 index 순서만 바꾼다.
        if view != self.sorted_view:
            ordered = sorted(range(len(self.centers)), key=lambda i: (view @ self.centers[i]).z)
            self.vertices.indices = [3*i+corner for i in ordered for corner in range(3)]
            self.sorted_view = view
        # 0은 반사맵용, -1은 물 뒤, +1은 물 앞이다. 구분은 셰이더가 픽셀마다 한다.
        self.program["transparency_phase"] = phase
        self.optics.bind(render_target)
        if phase:
            glActiveTexture(GL_TEXTURE2)
            glBindTexture(GL_TEXTURE_2D, water_depth.id)
            self.program["water_front_depth"] = 2
            self.program["viewport_size"] = viewport_size
            glActiveTexture(GL_TEXTURE0)

        glEnable(GL_BLEND)
        glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
        # 불투명 물체에 의한 깊이 검사는 유지하고, 투명 컵의 깊이 기록만 끈다.
        glDepthMask(GL_FALSE)
        try:
            self.group.set_state()
            self.vertices.draw(GL_TRIANGLES)
        finally:
            glDepthMask(GL_TRUE)
            glDisable(GL_BLEND)
            self.program["transparency_phase"] = 0
            self.optics.unbind()
            if phase:
                glActiveTexture(GL_TEXTURE2)
                glBindTexture(GL_TEXTURE_2D, 0)
                glActiveTexture(GL_TEXTURE0)
