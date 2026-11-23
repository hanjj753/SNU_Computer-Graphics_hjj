"""광원에서 본 물과 컵의 투과 손실을 저장해 반투명 그림자를 만든다."""

from ctypes import byref
from pyglet.gl import *
from pyglet.graphics.shader import Shader, ShaderProgram
from pyglet.image.buffer import Framebuffer, Renderbuffer

# 컵의 한 겹을 수직으로 통과한 직접광의 유효 투과율.
# 흡수뿐 아니라 다른 방향으로 산란되어 빠지는 빛도 포함한 사진 조절값이다.
CUP_BODY_TRANSMITTANCE = 0.64
CUP_DRY_BODY_TRANSMITTANCE = 0.72
CUP_RIM_TRANSMITTANCE = 0.08
# 몸체의 극단적인 grazing 손실은 완화하고, 두꺼운 띠의 가는 윤곽은 더 진하게 남긴다.
CUP_BODY_MIN_COSINE = 0.50
CUP_RIM_MIN_COSINE = 0.18

VERTEX = """#version 330 core
in vec3 POSITION;
in vec3 NORMAL;
out vec3 p;
out vec3 n;
uniform mat4 light_vp;
void main(){p=POSITION;n=NORMAL;gl_Position=light_vp*vec4(POSITION,1.0);}
"""
FRAGMENT = """#version 330 core
in vec3 p;
in vec3 n;
out vec2 distance_fresnel;
uniform vec3 light_position;
uniform float ior;
void main(){
    vec3 to_light=light_position-p;
    float cosine=clamp(abs(dot(normalize(n),normalize(to_light))),0.0,1.0);
    float f0=pow((ior-1.0)/(ior+1.0),2.0);
    float F=f0+(1.0-f0)*pow(1.0-cosine,5.0);
    distance_fresnel=vec2(length(to_light),F);
}
"""


class WaterTransmissionShadow:
    def __init__(self, shadow, water, light_positions, size=512):
        self.shadow, self.water = shadow, water
        self.light_positions, self.size = light_positions, size
        self.dirty = True
        self.program = ShaderProgram(Shader(VERTEX,"vertex"),Shader(FRAGMENT,"fragment"))
        self.vertices = self.program.vertex_list(
            water.vertices.count, GL_TRIANGLES,
            POSITION=("f",water.positions), NORMAL=("f",water.normals),
        )
        self.textures = []
        for _ in range(2):
            texture = GLuint()
            glGenTextures(1,byref(texture))
            glBindTexture(GL_TEXTURE_2D_ARRAY,texture.value)
            glTexImage3D(GL_TEXTURE_2D_ARRAY,0,GL_RG32F,size,size,len(light_positions),0,GL_RG,GL_FLOAT,None)
            for name in (GL_TEXTURE_MIN_FILTER,GL_TEXTURE_MAG_FILTER):
                glTexParameteri(GL_TEXTURE_2D_ARRAY,name,GL_NEAREST)
            for name in (GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T):
                glTexParameteri(GL_TEXTURE_2D_ARRAY,name,GL_CLAMP_TO_EDGE)
            self.textures.append(texture)
        glBindTexture(GL_TEXTURE_2D_ARRAY,0)
        self.fbo = Framebuffer()
        self.depth = Renderbuffer(size,size,GL_DEPTH_COMPONENT24)
        self.fbo.attach_renderbuffer(self.depth,attachment=GL_DEPTH_ATTACHMENT)

    def render(self):
        if not self.dirty: return
        viewport = (GLint*4)()
        glGetIntegerv(GL_VIEWPORT,viewport)
        self.fbo.bind()
        glViewport(0,0,self.size,self.size)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)
        glEnable(GL_CULL_FACE)
        self.program.use()
        self.program["ior"] = self.water.ior
        try:
            for texture,cull in zip(self.textures,(GL_BACK,GL_FRONT)):
                glCullFace(cull)
                for i,(matrix,position) in enumerate(zip(self.shadow.light_vps,self.light_positions)):
                    glFramebufferTextureLayer(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,texture.value,0,i)
                    if not self.fbo.is_complete: raise RuntimeError(self.fbo.get_status())
                    glClear(GL_DEPTH_BUFFER_BIT)
                    glClearBufferfv(GL_COLOR,0,(GLfloat*4)(1000.0,0.0,0.0,0.0))
                    self.program["light_vp"] = matrix
                    self.program["light_position"] = position
                    self.vertices.draw(GL_TRIANGLES)
            self.dirty = False
        finally:
            glCullFace(GL_BACK)
            glDisable(GL_CULL_FACE)
            self.fbo.unbind()
            glViewport(*viewport)

    def bind_to(self, program):
        for unit,name,texture in zip((7,8),("water_shadow_front","water_shadow_back"),self.textures):
            glActiveTexture(GL_TEXTURE0+unit)
            glBindTexture(GL_TEXTURE_2D_ARRAY,texture.value)
            program[name] = unit
        program["shadow_absorption"] = self.water.absorption
        glActiveTexture(GL_TEXTURE0)


CUP_VERTEX = """#version 330 core
in vec3 POSITION;
in vec3 NORMAL;
out vec3 p;
out vec3 n;
uniform mat4 light_vp;
void main(){p=POSITION;n=NORMAL;gl_Position=light_vp*vec4(POSITION,1);}
"""
CUP_FRAGMENT = """#version 330 core
in vec3 p;
in vec3 n;
out float value;
uniform vec3 light_position;
uniform int pass_mode;
uniform float rim_base_y;
uniform float body_transmittance;
uniform float dry_body_transmittance;
uniform float rim_transmittance;
uniform float water_level;
uniform float body_min_cosine;
uniform float rim_min_cosine;
void main(){
    vec3 vector=light_position-p;
    if(pass_mode==1){value=gl_FragCoord.z;return;}
    bool rim=p.y>=rim_base_y-0.00001;
    // 물이 찬 아래쪽은 굴절로 직진 경로에서 벗어난 빛까지 유효 손실에 포함한다.
    // 비어 있는 윗부분은 더 잘 투과시켜, 낮은 몸체와 높은 입구의 투영을 구분한다.
    float filled=1.0-smoothstep(water_level-0.006,water_level+0.006,p.y);
    float T=rim ? rim_transmittance : mix(dry_body_transmittance,body_transmittance,filled);
    float min_cosine=rim ? rim_min_cosine : body_min_cosine;
    float cosine=max(abs(dot(normalize(n),normalize(vector))),min_cosine);
    // 한 겹의 양쪽 경계가 각각 반씩 기록하므로, 두 번 합치면 -log(T)가 된다.
    value=-0.5*log(clamp(T,0.001,1.0))/cosine;
}
"""


class CupTransmissionShadow:
    """컵의 모든 경계를 통과한 광학 두께를 누적해 반투명 그림자를 만든다."""
    def __init__(self, shadow, cup_mesh, light_positions, size=1024, *, water_level):
        self.shadow, self.mesh = shadow, cup_mesh
        self.light_positions, self.size = light_positions, size
        self.dirty = True
        self.body_transmittance = CUP_BODY_TRANSMITTANCE
        self.dry_body_transmittance = CUP_DRY_BODY_TRANSMITTANCE
        self.rim_transmittance = CUP_RIM_TRANSMITTANCE
        self.water_level = water_level
        self.program = ShaderProgram(Shader(CUP_VERTEX,"vertex"),Shader(CUP_FRAGMENT,"fragment"))
        self.vertices = self.program.vertex_list(
            len(cup_mesh.positions)//3,GL_TRIANGLES,
            POSITION=("f",cup_mesh.positions),NORMAL=("f",cup_mesh.normals),
        )
        self.textures = []
        for _ in range(2):
            texture=GLuint()
            glGenTextures(1,byref(texture))
            glBindTexture(GL_TEXTURE_2D_ARRAY,texture.value)
            glTexImage3D(GL_TEXTURE_2D_ARRAY,0,GL_R32F,size,size,len(light_positions),0,GL_RED,GL_FLOAT,None)
            for name in (GL_TEXTURE_MIN_FILTER,GL_TEXTURE_MAG_FILTER):
                glTexParameteri(GL_TEXTURE_2D_ARRAY,name,GL_NEAREST)
            for name in (GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T):
                glTexParameteri(GL_TEXTURE_2D_ARRAY,name,GL_CLAMP_TO_EDGE)
            self.textures.append(texture)
        glBindTexture(GL_TEXTURE_2D_ARRAY,0)
        self.fbo=Framebuffer()

    def render(self):
        if not self.dirty: return
        viewport=(GLint*4)()
        glGetIntegerv(GL_VIEWPORT,viewport)
        self.fbo.bind()
        glViewport(0,0,self.size,self.size)
        # 뒷면도 합산해야 속이 빈 컵의 두 벽과 바닥의 손실이 모두 들어간다.
        glDisable(GL_DEPTH_TEST)
        glDepthMask(GL_FALSE)
        glDisable(GL_CULL_FACE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_ONE,GL_ONE)
        self.program.use()
        self.program["rim_base_y"]=self.mesh.rim_base_y
        self.program["body_transmittance"]=self.body_transmittance
        self.program["dry_body_transmittance"]=self.dry_body_transmittance
        self.program["rim_transmittance"]=self.rim_transmittance
        self.program["water_level"]=self.water_level
        self.program["body_min_cosine"]=CUP_BODY_MIN_COSINE
        self.program["rim_min_cosine"]=CUP_RIM_MIN_COSINE
        try:
            for mode,texture in enumerate(self.textures):
                # 0: 광학 두께의 합, 1: 광원에서 가장 먼 컵 경계의 투영 깊이.
                glBlendEquation(GL_FUNC_ADD if mode==0 else GL_MAX)
                self.program["pass_mode"]=mode
                for layer,(matrix,position) in enumerate(zip(self.shadow.light_vps,self.light_positions)):
                    glFramebufferTextureLayer(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,texture.value,0,layer)
                    if not self.fbo.is_complete: raise RuntimeError(self.fbo.get_status())
                    glClearBufferfv(GL_COLOR,0,(GLfloat*4)(0,0,0,0))
                    self.program["light_vp"]=matrix
                    self.program["light_position"]=position
                    self.vertices.draw(GL_TRIANGLES)
            self.dirty=False
        finally:
            glBlendEquation(GL_FUNC_ADD)
            glBlendFuncSeparate(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA,GL_ONE,GL_ONE_MINUS_SRC_ALPHA)
            glDisable(GL_BLEND)
            glEnable(GL_DEPTH_TEST)
            glDepthMask(GL_TRUE)
            self.fbo.unbind()
            glViewport(*viewport)

    def bind_to(self,program):
        for unit,name,texture in zip((9,10),("cup_shadow_tau","cup_shadow_exit"),self.textures):
            glActiveTexture(GL_TEXTURE0+unit)
            glBindTexture(GL_TEXTURE_2D_ARRAY,texture.value)
            program[name]=unit
        glActiveTexture(GL_TEXTURE0)
