import pyglet

from ctypes import byref
from pyglet.gl import *
from pyglet.graphics.shader import Shader, ShaderProgram
from pyglet.image.buffer import Framebuffer, Renderbuffer


POST_VERTEX = """
#version 330 core
in vec2 POSITION;
out vec2 uv;

void main()
{
    uv = POSITION * 0.5 + 0.5;
    gl_Position = vec4(POSITION, 0.0, 1.0);
}
"""

POST_FRAGMENT = """
#version 330 core
in vec2 uv;
out vec4 final_color;

uniform sampler2D hdr_color;
uniform float exposure;

vec3 linear_to_srgb(vec3 color)
{
    return mix(
        1.055 * pow(color, vec3(1.0 / 2.4)) - 0.055,
        12.92 * color,
        lessThanEqual(color, vec3(0.0031308))
    );
}

void main()
{
    vec3 hdr = max(texture(hdr_color, uv).rgb, vec3(0.0));

    // Reinhard 톤매핑: 1보다 큰 밝기도 차이를 유지하며 0~1로 압축한다.
    vec3 exposed = hdr * exposure;
    vec3 mapped = exposed / (vec3(1.0) + exposed);

    // 화면에 내보낼 때 한 번만 sRGB로 변환한다.
    final_color = vec4(linear_to_srgb(mapped), 1.0);
}
"""


class HdrTarget:
    def __init__(self, exposure=1.6):
        self.exposure = exposure
        self.size = (0, 0)
        self.fbo = None

        self.program = ShaderProgram(
            Shader(POST_VERTEX, "vertex"),
            Shader(POST_FRAGMENT, "fragment"),
        )

        # 화면 전체를 덮는 삼각형. 카메라 행렬의 영향을 받지 않는다.
        self.quad = self.program.vertex_list(
            3, GL_TRIANGLES,
            POSITION=("f", (-1.0, -1.0, 3.0, -1.0, -1.0, 3.0)),
        )

    def begin(self, window):
        w, h = window.get_framebuffer_size()
        w, h = max(1, w), max(1, h)

        if self.size != (w, h):
            if self.fbo is not None:
                self.fbo.delete()
                self.color.delete()
                self.depth.delete()

            # 16비트 부동소수점으로 1보다 큰 조명값도 보존한다.
            # 불투명 물체와 투명 물체 모두 이 선형 RGB 저장소에 그린다.
            self.color = pyglet.image.Texture.create(
                w, h,
                internalformat=GL_RGBA16F,
                min_filter=GL_NEAREST,
                mag_filter=GL_NEAREST,
                blank_data=False,
            )
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

            self.depth = Renderbuffer(w, h, GL_DEPTH_COMPONENT24)
            self.fbo = Framebuffer()
            self.fbo.attach_texture(self.color)
            self.fbo.attach_renderbuffer(
                self.depth, attachment=GL_DEPTH_ATTACHMENT
            )
            self.fbo.bind()

            if not self.fbo.is_complete:
                raise RuntimeError(self.fbo.get_status())

            self.size = (w, h)
            glBindTexture(GL_TEXTURE_2D, 0)

        self.fbo.bind()
        glViewport(0, 0, w, h)

        # 색이 이미 선형 float이므로 sRGB 변환 없이 저장·합성한다.
        glDisable(GL_FRAMEBUFFER_SRGB)

    def present(self):
        w, h = self.size
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glViewport(0, 0, w, h)
        glDisable(GL_FRAMEBUFFER_SRGB)

        depth_enabled = bool(glIsEnabled(GL_DEPTH_TEST))
        blend_enabled = bool(glIsEnabled(GL_BLEND))
        depth_write = GLboolean()
        glGetBooleanv(GL_DEPTH_WRITEMASK, byref(depth_write))

        glDisable(GL_DEPTH_TEST)
        glDepthMask(GL_FALSE)
        glDisable(GL_BLEND)

        try:
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.color.id)

            self.program.use()
            self.program["hdr_color"] = 0
            self.program["exposure"] = self.exposure
            self.quad.draw(GL_TRIANGLES)
        finally:
            glBindTexture(GL_TEXTURE_2D, 0)
            glDepthMask(depth_write.value)
            if depth_enabled:
                glEnable(GL_DEPTH_TEST)
            if blend_enabled:
                glEnable(GL_BLEND)
