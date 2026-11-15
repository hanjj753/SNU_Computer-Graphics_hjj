import pyglet

from pyglet.gl import *
from pyglet.math import Mat4, Vec3
from pyglet.graphics.shader import Shader, ShaderProgram
from pyglet.image.buffer import Framebuffer


DEPTH_VERTEX = """
#version 330 core

in vec3 POSITION;

uniform mat4 light_view_projection;

void main()
{
    gl_Position = (
        light_view_projection * vec4(POSITION, 1.0)
    );
}
"""

# 색은 출력하지 않는다.
# OpenGL이 계산한 깊이만 depth attachment에 기록한다.
DEPTH_FRAGMENT = """
#version 330 core

void main() {}
"""


class ShadowMap:
    def __init__(self, light_position, size=2048):
        self.size = size

        self.program = ShaderProgram(
            Shader(DEPTH_VERTEX, "vertex"),
            Shader(DEPTH_FRAGMENT, "fragment"),
        )

        self.batch = pyglet.graphics.Batch()
        self.group = pyglet.graphics.ShaderGroup(self.program)
        self.vertex_lists = []

        # 깊이를 저장할 텍스처.
        # 초기화 형식을 직접 지정하기 위해 먼저 객체만 만든다.
        self.texture = pyglet.image.Texture.create(
            size, size,
            internalformat=None,
            min_filter=GL_NEAREST,
            mag_filter=GL_NEAREST,
        )

        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT24,
            size, size, 0,
            GL_DEPTH_COMPONENT, GL_FLOAT, None,
        )

        # 깊이 비교는 fragment shader에서 직접 수행한다.
        glTexParameteri(
            GL_TEXTURE_2D, GL_TEXTURE_COMPARE_MODE, GL_NONE
        )

        glTexParameteri(
            GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER
        )
        glTexParameteri(
            GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER
        )

        # 맵 밖의 깊이는 가장 먼 값인 1로 취급한다.
        border = (GLfloat * 4)(1.0, 1.0, 1.0, 1.0)
        glTexParameterfv(
            GL_TEXTURE_2D, GL_TEXTURE_BORDER_COLOR, border
        )

        self.fbo = Framebuffer()
        self.fbo.attach_texture(
            self.texture,
            attachment=GL_DEPTH_ATTACHMENT,
        )

        self.fbo.bind()

        # 색 저장소가 없는 depth-only framebuffer.
        glDrawBuffer(GL_NONE)
        glReadBuffer(GL_NONE)

        if not self.fbo.is_complete:
            raise RuntimeError(self.fbo.get_status())

        self.fbo.unbind()

        # 천장 광원에서 아래쪽을 바라본다.
        # 시선이 -Y이므로 up은 평행하지 않은 -Z로 지정한다.
        light_view = Mat4.look_at(
            position=light_position,
            target=Vec3(
                light_position.x, 0.0, light_position.z
            ),
            up=Vec3(0.0, 0.0, -1.0),
        )

        light_projection = Mat4.perspective_projection(
            1.0,
            z_near=0.10,
            z_far=30.0,
            fov=150.0,
        )

        self.light_vp = light_projection @ light_view

    def add_mesh(self, positions):
        # 현재 OBJ의 위치는 이미 월드 좌표로 배치되어 있다.
        # 깊이 계산에는 위치만 필요하다.
        self.vertex_lists.append(
            self.program.vertex_list(
                len(positions) // 3,
                GL_TRIANGLES,
                batch=self.batch,
                group=self.group,
                POSITION=("f", positions),
            )
        )

    def render(self):
        self.fbo.bind()
        glViewport(0, 0, self.size, self.size)

        glDisable(GL_FRAMEBUFFER_SRGB)
        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)

        glClear(GL_DEPTH_BUFFER_BIT)

        # 깊이를 조금 더 멀게 기록해서,
        # 같은 표면을 그림자로 잘못 판단하는 현상을 줄인다.
        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(2.0, 4.0)

        try:
            self.program["light_view_projection"] = self.light_vp
            self.batch.draw()
        finally:
            # 일반 화면 렌더링에는 이 보정을 적용하지 않는다.
            glDisable(GL_POLYGON_OFFSET_FILL)
            self.fbo.unbind()

    def bind_to(self, program):
        # 유닛 0은 포장 이미지가 사용하므로 그림자는 1을 사용한다.
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self.texture.id)

        program["shadow_map"] = 1
        program["light_view_projection"] = self.light_vp

        # 이후 이미지 텍스처 설정에 영향을 주지 않도록 복구한다.
        glActiveTexture(GL_TEXTURE0)