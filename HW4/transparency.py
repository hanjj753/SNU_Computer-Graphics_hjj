import pyglet

from pyglet.gl import *
from pyglet.math import Vec4

from materials import PhongMaterialGroup


class TransparentRenderer:
    def __init__(self, program):
        self.program = program

        # GPU에 정점 데이터를 저장하기 위한 batch.
        # 실제로 그릴 때는 batch.draw()를 호출하지 않고,
        # 아래에서 정렬한 삼각형을 하나씩 그린다.
        self.batch = pyglet.graphics.Batch()

        # 각 원소:
        # (삼각형 중심점, 재질 그룹, GPU 정점 목록)
        self.triangles = []

    def add_mesh(self, positions, normals, material):
        # 같은 물체의 삼각형들은 같은 재질 그룹을 공유한다.
        group = PhongMaterialGroup(
            material=material,
            program=self.program,
        )

        # 삼각형 하나는 정점 3개로 구성된다.
        # 정점마다 XYZ가 있으므로 삼각형당 실수 9개를 읽는다.
        # 이 등록 작업은 모델을 불러올 때 한 번만 실행된다.
        for i in range(0, len(positions), 9):
            p = positions[i:i + 9]
            n = normals[i:i + 9]

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
                group=group,
                POSITION=("f", p),
                NORMAL=("f", n),
                COLOR_0=("f", list(material.diffuse) * 3),
                TEXCOORD_0=("f", [0.0, 0.0] * 3),
            )

            self.triangles.append(
                (center, group, vertex_list)
            )

    def draw(self, view):
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

        glEnable(GL_BLEND)

        # 앞: 지금 그리는 투명 fragment
        # 뒤: 버퍼에 이미 그려져 있는 색
        #
        # RGB = 앞 색 × 앞 alpha + 뒤 색 × (1 - 앞 alpha)
        # A   = 앞 alpha + 뒤 alpha × (1 - 앞 alpha)
        #
        # 앞의 두 인자는 RGB용, 뒤의 두 인자는 alpha용 계수다.
        glBlendFuncSeparate(
            GL_SRC_ALPHA,
            GL_ONE_MINUS_SRC_ALPHA,
            GL_ONE,
            GL_ONE_MINUS_SRC_ALPHA,
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