import pyglet

from ctypes import byref
from pyglet.gl import *
from pyglet.math import Mat4, Vec3
from pyglet.graphics.shader import Shader, ShaderProgram
from pyglet.image.buffer import Framebuffer


MAX_SHADOW_LIGHTS = 16

DEPTH_VERTEX = """
#version 330 core
in vec3 POSITION;
uniform mat4 light_view_projection;

void main()
{
    // 현재 POSITION은 이미 월드 좌표로 배치되어 있다.
    gl_Position = light_view_projection * vec4(POSITION, 1.0);
}
"""

DEPTH_FRAGMENT = """
#version 330 core
void main() {}
"""


class AreaShadowMaps:
    def __init__(self, light_positions, size=2048):
        if not 1 <= len(light_positions) <= MAX_SHADOW_LIGHTS:
            raise ValueError("그림자 광원은 1~16개를 사용할 수 있습니다.")

        self.size = size
        self.light_count = len(light_positions)
        self.dirty = True
        self.vertex_lists = []

        self.program = ShaderProgram(
            Shader(DEPTH_VERTEX, "vertex"),
            Shader(DEPTH_FRAGMENT, "fragment"),
        )
        self.batch = pyglet.graphics.Batch()
        self.group = pyglet.graphics.ShaderGroup(self.program)

        # 한 텍스처의 각 층에 광원 하나의 깊이 맵을 저장한다.
        # 16개의 텍스처 유닛을 사용하는 대신 유닛 하나만 사용한다.
        self.texture_id = GLuint()
        glGenTextures(1, byref(self.texture_id))
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D_ARRAY, self.texture_id.value)
        glTexImage3D(
            GL_TEXTURE_2D_ARRAY, 0, GL_DEPTH_COMPONENT24,
            size, size, self.light_count, 0,
            GL_DEPTH_COMPONENT, GL_FLOAT, None,
        )

        for parameter in (GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER):
            glTexParameteri(GL_TEXTURE_2D_ARRAY, parameter, GL_NEAREST)
        for parameter in (GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T):
            glTexParameteri(
                GL_TEXTURE_2D_ARRAY, parameter, GL_CLAMP_TO_BORDER
            )
        glTexParameteri(
            GL_TEXTURE_2D_ARRAY, GL_TEXTURE_WRAP_R, GL_CLAMP_TO_EDGE
        )
        glTexParameteri(
            GL_TEXTURE_2D_ARRAY, GL_TEXTURE_COMPARE_MODE, GL_NONE
        )
        border = (GLfloat * 4)(1.0, 1.0, 1.0, 1.0)
        glTexParameterfv(
            GL_TEXTURE_2D_ARRAY, GL_TEXTURE_BORDER_COLOR, border
        )
        glBindTexture(GL_TEXTURE_2D_ARRAY, 0)

        self.fbo = Framebuffer()
        self.fbo.bind()
        glFramebufferTextureLayer(
            GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT,
            self.texture_id.value, 0, 0,
        )
        glDrawBuffer(GL_NONE)
        glReadBuffer(GL_NONE)
        if not self.fbo.is_complete:
            raise RuntimeError(self.fbo.get_status())
        self.fbo.unbind()

        projection = Mat4.perspective_projection(
            1.0, z_near=0.10, z_far=30.0, fov=150.0
        )
        self.light_vps = []
        for position in light_positions:
            position = Vec3(*position)
            view = Mat4.look_at(
                position=position,
                target=Vec3(position.x, 0.0, position.z),
                up=Vec3(0.0, 0.0, -1.0),
            )
            self.light_vps.append(projection @ view)

    def add_mesh(self, positions):
        # 모든 광원이 같은 정점 데이터를 사용하므로 등록은 한 번만 한다.
        self.vertex_lists.append(
            self.program.vertex_list(
                len(positions) // 3, GL_TRIANGLES,
                batch=self.batch,
                group=self.group,
                POSITION=("f", positions),
            )
        )
        self.dirty = True

    def render(self):
        # 카메라를 움직여도 광원 시점의 깊이 값은 변하지 않는다.
        if not self.dirty:
            return

        viewport = (GLint * 4)()
        glGetIntegerv(GL_VIEWPORT, viewport)

        self.fbo.bind()
        glViewport(0, 0, self.size, self.size)
        glDisable(GL_FRAMEBUFFER_SRGB)
        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)
        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(2.0, 4.0)

        try:
            for layer, light_vp in enumerate(self.light_vps):
                # 이번 광원에 해당하는 층을 깊이 저장소로 연결한다.
                glFramebufferTextureLayer(
                    GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT,
                    self.texture_id.value, 0, layer,
                )
                glClear(GL_DEPTH_BUFFER_BIT)
                self.program["light_view_projection"] = light_vp
                self.batch.draw()
            self.dirty = False
        finally:
            glDisable(GL_POLYGON_OFFSET_FILL)
            self.fbo.unbind()
            glViewport(*viewport)

    def bind_to(self, program):
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D_ARRAY, self.texture_id.value)
        program["shadow_map"] = 1

        # 사용하지 않는 행렬까지 채워 uniform 배열 길이를 맞춘다.
        program["light_view_projections"] = self.light_vps + [
            Mat4()
        ] * (MAX_SHADOW_LIGHTS - self.light_count)

        glActiveTexture(GL_TEXTURE0)
