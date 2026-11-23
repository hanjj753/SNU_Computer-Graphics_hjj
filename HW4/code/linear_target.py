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
uniform vec2 inverse_size;

vec3 linear_to_srgb(vec3 color)
{
    return mix(
        1.055 * pow(color, vec3(1.0 / 2.4)) - 0.055,
        12.92 * color,
        lessThanEqual(color, vec3(0.0031308))
    );
}

vec3 display_sample(vec2 coordinate)
{
    vec3 hdr = max(texture(hdr_color,coordinate).rgb,vec3(0.0));

    // Reinhard 톤매핑: 1보다 큰 밝기도 차이를 유지하며 0~1로 압축한다.
    vec3 exposed = hdr * exposure;
    vec3 mapped = exposed / (vec3(1.0) + exposed);

    // 화면에 내보낼 때 한 번만 sRGB로 변환한다.
    return linear_to_srgb(mapped);
}

void main()
{
    vec3 center=display_sample(uv);
    vec3 nw=display_sample(uv+inverse_size*vec2(-1,1));
    vec3 ne=display_sample(uv+inverse_size*vec2(1,1));
    vec3 sw=display_sample(uv+inverse_size*vec2(-1,-1));
    vec3 se=display_sample(uv+inverse_size*vec2(1,-1));
    vec3 luma=vec3(.299,.587,.114);
    float cn=dot(center,luma),lnw=dot(nw,luma),lne=dot(ne,luma),lsw=dot(sw,luma),lse=dot(se,luma);
    float low=min(cn,min(min(lnw,lne),min(lsw,lse)));
    float high=max(cn,max(max(lnw,lne),max(lsw,lse)));
    // 명암 차이가 작은 곳은 원래 색을 유지하고 윤곽에만 FXAA 방식 필터를 적용한다.
    if (high-low<max(.025,high*.125)) { final_color=vec4(center,1.0);return; }
    vec2 direction=vec2(-((lnw+lne)-(lsw+lse)),(lnw+lsw)-(lne+lse));
    float reduction=max((lnw+lne+lsw+lse)*.03125,.0078125);
    direction=clamp(direction/(min(abs(direction.x),abs(direction.y))+reduction),vec2(-6),vec2(6))*inverse_size;
    vec3 a=.5*(display_sample(uv-direction/6.)+display_sample(uv+direction/6.));
    vec3 b=.5*a+.25*(display_sample(uv-direction*.5)+display_sample(uv+direction*.5));
    float lb=dot(b,luma);
    final_color=vec4(lb<low || lb>high ? a:b,1.0);
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
                self.msaa_fbo.delete()
                self.msaa_color.delete()
                self.msaa_depth.delete()

            # 16비트 부동소수점으로 1보다 큰 조명값도 보존한다.
            # 불투명 장면의 MSAA 결과를 받은 뒤, 투명 물체를 이 저장소에 합성한다.
            self.color = pyglet.image.Texture.create(
                w, h,
                internalformat=GL_RGBA16F,
                min_filter=GL_LINEAR,
                mag_filter=GL_LINEAR,
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

            # 픽셀 안의 네 위치에서 도형이 덮는 영역과 깊이를 구한다.
            # 최종 색만 흐리는 FXAA보다 길게 비스듬한 모서리를 잘 보존한다.
            self.msaa_color = Renderbuffer(w, h, GL_RGBA16F, samples=4)
            self.msaa_depth = Renderbuffer(w, h, GL_DEPTH_COMPONENT24, samples=4)
            self.msaa_fbo = Framebuffer()
            self.msaa_fbo.attach_renderbuffer(self.msaa_color)
            self.msaa_fbo.attach_renderbuffer(
                self.msaa_depth, attachment=GL_DEPTH_ATTACHMENT
            )
            self.msaa_fbo.bind()
            if not self.msaa_fbo.is_complete:
                raise RuntimeError(self.msaa_fbo.get_status())

            self.size = (w, h)
            glBindTexture(GL_TEXTURE_2D, 0)

        self.msaa_fbo.bind()
        glEnable(GL_MULTISAMPLE)
        glViewport(0, 0, w, h)

        # 색이 이미 선형 float이므로 sRGB 변환 없이 저장·합성한다.
        glDisable(GL_FRAMEBUFFER_SRGB)

    def resolve(self):
        """불투명 장면의 샘플을 합쳐, 컵·물이 읽을 단일 색·깊이 버퍼로 옮긴다."""
        w, h = self.size
        glBindFramebuffer(GL_READ_FRAMEBUFFER, self.msaa_fbo.id)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, self.fbo.id)
        glBlitFramebuffer(0, 0, w, h, 0, 0, w, h,
                          GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT, GL_NEAREST)
        self.fbo.bind()

    def present(self):
        w, h = self.size
        glDisable(GL_FRAMEBUFFER_SRGB)

        depth_enabled = bool(glIsEnabled(GL_DEPTH_TEST))
        blend_enabled = bool(glIsEnabled(GL_BLEND))
        depth_write = GLboolean()
        glGetBooleanv(GL_DEPTH_WRITEMASK, byref(depth_write))

        glDisable(GL_DEPTH_TEST)
        glDepthMask(GL_FALSE)
        glDisable(GL_BLEND)

        try:
            glBindFramebuffer(GL_FRAMEBUFFER, 0)
            glViewport(0, 0, w, h)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.color.id)

            self.program.use()
            self.program["hdr_color"] = 0
            self.program["exposure"] = self.exposure
            self.program["inverse_size"] = (1.0/w,1.0/h)
            self.quad.draw(GL_TRIANGLES)
        finally:
            glBindTexture(GL_TEXTURE_2D, 0)
            glDepthMask(depth_write.value)
            if depth_enabled:
                glEnable(GL_DEPTH_TEST)
            if blend_enabled:
                glEnable(GL_BLEND)
