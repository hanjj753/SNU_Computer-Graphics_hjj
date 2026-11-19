import pyglet
from copy import copy

from pyglet.gl import *
from pyglet.math import Vec4

from materials import PhongMaterialGroup
from cup_optics import CupOptics

CUP_RIM_OPACITY = 0.40


class TransparentRenderer:
    def __init__(self, program):
        self.program = program
        self.optics = CupOptics(program)

        # GPU에 정점 데이터를 저장하기 위한 batch.
        # 일반 경로는 정렬한 삼각형을 하나씩 그리고,
        # 현재 장면의 컵 하나는 아래 indexed draw 최적화를 사용한다.
        self.batch = pyglet.graphics.Batch()

        # 각 원소:
        # (삼각형 중심점, 재질 그룹, GPU 정점 목록)
        self.triangles = []
        self.fast_mesh = None
        self.fast_group = None
        self.triangle_offsets = {}

    def add_mesh(self, positions, normals, material):
        # 현재 장면의 투명 메시가 컵 하나일 때 사용할 indexed draw 경로.
        single_cup = not self.triangles and material.name == "Cup"
        colors = []
        # 같은 물체의 삼각형들은 같은 재질 그룹을 공유한다.
        group = PhongMaterialGroup(
            material=material,
            program=self.program,
        )

        # 컵 몸체는 잘 투과시키되, 두께가 있는 입구 테두리는 조금 더 보이게 한다.
        # 원본 컵의 입구는 y=0.65 부근의 좁은 고리로 구성되어 있다.
        rim_group = None
        if material.name == "Cup":
            rim_material = copy(material)
            rim_material.diffuse = (*material.diffuse[:3], CUP_RIM_OPACITY)
            rim_group = PhongMaterialGroup(material=rim_material, program=self.program)
        top = max(positions[1::3])
        rim_base = getattr(material, "rim_base_y", top - 0.002)

        # 삼각형 하나는 정점 3개로 구성된다.
        # 정점마다 XYZ가 있으므로 삼각형당 실수 9개를 읽는다.
        # 이 등록 작업은 모델을 불러올 때 한 번만 실행된다.
        for i in range(0, len(positions), 9):
            p = positions[i:i + 9]
            n = normals[i:i + 9]
            triangle_group = group
            if rim_group is not None and min(p[1::3]) >= rim_base - 1e-6:
                triangle_group = rim_group

            # 세 꼭짓점의 평균으로 삼각형 중심을 구한다.
            # w=1은 방향 벡터가 아닌 '위치'라는 뜻이다.
            #
            # 현재 OBJ는 물체 배치가 정점에 반영되어 있어서
            # 이 중심점을 바로 월드 좌표로 사용할 수 있다.
            center = Vec4(
                (p[0] + p[3] + p[6]) / 3,
                (p[1] + p[4] + p[7]) / 3,
                (p[2] + p[5] + p[8]) / 3,
                1.0,
            )

            # 삼각형 하나를 독립적으로 그릴 수 있게 등록한다.
            # COLOR_0의 네 번째 값에 재질의 alpha가 들어 있다.
            # 현재 컵과 물은 이미지 텍스처를 쓰지 않으므로 UV는 0이다.
            vertex_list = self.program.vertex_list(
                3,
                GL_TRIANGLES,
                batch=self.batch,
                group=triangle_group,
                POSITION=("f", p),
                NORMAL=("f", n),
                COLOR_0=("f", list(triangle_group.material.diffuse) * 3),
                TEXCOORD_0=("f", [0.0, 0.0] * 3),
            )

            self.triangles.append(
                (center, triangle_group, vertex_list)
            )
            self.triangle_offsets[vertex_list] = i // 3
            colors.extend(list(triangle_group.material.diffuse) * 3)

        self.fast_mesh = None
        if single_cup:
            # 몸체와 테두리는 Ks/n이 같고 alpha만 다르다. Alpha는 정점 색에 저장한다.
            # 따라서 index 순서를 정렬하면 삼각형마다 draw()할 필요가 없다.
            count = len(positions) // 3
            self.fast_group = group
            self.fast_mesh = self.program.vertex_list_indexed(
                count, GL_TRIANGLES, list(range(count)),
                POSITION=("f",positions), NORMAL=("f",normals),
                COLOR_0=("f",colors), TEXCOORD_0=("f",[0.0,0.0]*count),
            )

    def draw(self, view, *, phase=0, water_depth=None, viewport_size=None, render_target=None):
        # 카메라가 움직이면 앞뒤 관계도 달라지므로 매 프레임 정렬한다.
        #
        # view @ center: 삼각형 중심을 카메라 좌표로 변환.
        # 카메라 앞은 -Z 방향이므로 -10이 -2보다 멀다.
        # 오름차순 정렬하면 먼 삼각형부터 그리게 된다.
        #
        # 중심점 기준의 근사이므로 교차하는 삼각형의 순서를
        # 모든 상황에서 정확하게 해결하는 방법은 아니다.
        ordered = sorted(
            self.triangles,
            key=lambda item: (view @ item[0]).z,
        )

        # phase=-1에서는 물 뒤에 있는 컵 조각만, +1에서는 앞쪽만 그린다.
        # 삼각형 중심으로 컵 전체를 나누지 않고 fragment마다 깊이를 비교한다.
        self.program["transparency_phase"] = phase
        self.optics.bind(render_target)
        if phase:
            glActiveTexture(GL_TEXTURE2)
            glBindTexture(GL_TEXTURE_2D, water_depth.id)
            self.program["water_front_depth"] = 2
            self.program["viewport_size"] = viewport_size
            glActiveTexture(GL_TEXTURE0)

        glEnable(GL_BLEND)
        glBlendFuncSeparate(
            GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
            GL_ONE, GL_ONE_MINUS_SRC_ALPHA,
        )

        # 깊이 '검사'는 main에서 켠 상태로 유지한다.
        # 따라서 불투명 물체 뒤에 가려진 투명 면은 제외된다.
        #
        # 여기서는 깊이 '기록'만 끈다.
        # 투명 면이 이후의 다른 투명 면을 깊이 버퍼로
        # 차단하지 않도록 하고, 앞뒤 순서는 정렬 결과에 맡긴다.
        glDepthMask(GL_FALSE)

        active_group = None

        try:
            if self.fast_mesh is not None:
                self.fast_mesh.indices = [
                    self.triangle_offsets[vertices] + corner
                    for _, _, vertices in ordered for corner in range(3)
                ]
                self.fast_group.set_state()
                self.fast_mesh.draw(GL_TRIANGLES)
                return
            for _, group, vertex_list in ordered:
                # 재질이 달라질 때만 셰이더의 재질 값을 갱신한다.
                # 연속된 삼각형이 같은 그룹이면 중복 설정을 생략한다.
                if group is not active_group:
                    # 개별 vertex_list.draw()는 재질 상태를
                    # 자동 설정하지 않으므로 직접 호출해야 한다.
                    group.set_state()
                    active_group = group

                vertex_list.draw(GL_TRIANGLES)
        finally:
            # 오류가 발생해도 다음 렌더링에 영향을 주지 않도록 복구한다.
            # 특히 다음 프레임의 깊이 버퍼 초기화에도 기록 허용이 필요하다.
            glDepthMask(GL_TRUE)
            glDisable(GL_BLEND)
            self.program["transparency_phase"] = 0
            self.optics.unbind()
            if phase:
                glActiveTexture(GL_TEXTURE2)
                glBindTexture(GL_TEXTURE_2D, 0)
                glActiveTexture(GL_TEXTURE0)
