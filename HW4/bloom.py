"""톤매핑 이전 HDR에서 밝은 부분을 추출하고 저해상도로 흐리게 만든다."""

import pyglet
from pyglet.gl import *
from pyglet.graphics.shader import Shader, ShaderProgram
from pyglet.image.buffer import Framebuffer

VERTEX = """#version 330 core
in vec2 POSITION;
out vec2 uv;
void main(){uv=POSITION*0.5+0.5;gl_Position=vec4(POSITION,0,1);}
"""
BRIGHT = """#version 330 core
in vec2 uv;
out vec4 final_color;
uniform sampler2D source;
uniform vec2 texel;
uniform float threshold;
void main(){
    vec3 color=vec3(0);
    for(int y=0;y<4;y++) for(int x=0;x<4;x++)
        color+=texture(source,uv+(vec2(x,y)-1.5)*texel).rgb/16.0;
    float brightness=dot(color,vec3(0.2126,0.7152,0.0722));
    float knee=threshold*0.5;
    float soft=clamp(brightness-threshold+knee,0.0,2.0*knee);
    soft=soft*soft/(4.0*knee+0.00001);
    float contribution=max(brightness-threshold,soft)/max(brightness,0.00001);
    final_color=vec4(color*contribution,1);
}
"""
BLUR = """#version 330 core
in vec2 uv;
out vec4 final_color;
uniform sampler2D source;
uniform vec2 step_uv;
void main(){
    float weights[5]=float[](0.227027,0.1945946,0.1216216,0.054054,0.016216);
    vec3 color=texture(source,uv).rgb*weights[0];
    for(int i=1;i<=4;i++)
        color+=(texture(source,uv+step_uv*float(i)).rgb
               +texture(source,uv-step_uv*float(i)).rgb)*weights[i];
    final_color=vec4(color,1);
}
"""


class Bloom:
    def __init__(self):
        # 흰 화면 주위가 넓고 하얗게 뜨지 않도록 강한 빛에만 약한 번짐을 준다.
        self.threshold = 4.0
        self.strength = 0.01
        self.radius = 1.0
        self.size = (0, 0)
        self.bright = ShaderProgram(Shader(VERTEX,"vertex"),Shader(BRIGHT,"fragment"))
        self.blur = ShaderProgram(Shader(VERTEX,"vertex"),Shader(BLUR,"fragment"))
        vertices = (-1,-1,3,-1,-1,3)
        self.quads = {p: p.vertex_list(3,GL_TRIANGLES,POSITION=("f",vertices)) for p in (self.bright,self.blur)}

    def apply(self, color, size):
        low_size = (max(1,size[0]//4),max(1,size[1]//4))
        if low_size != self.size:
            if self.size != (0,0):
                for fbo in self.fbos: fbo.delete()
                for texture in self.textures: texture.delete()
            self.size = low_size
            self.textures, self.fbos = [], []
            for _ in range(2):
                texture = pyglet.image.Texture.create(*low_size,internalformat=GL_RGBA16F,
                    min_filter=GL_LINEAR,mag_filter=GL_LINEAR,blank_data=False)
                glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE)
                glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE)
                fbo = Framebuffer()
                fbo.attach_texture(texture)
                self.textures.append(texture)
                self.fbos.append(fbo)
        glViewport(0,0,*self.size)
        glActiveTexture(GL_TEXTURE0)
        self.fbos[0].bind()
        glBindTexture(GL_TEXTURE_2D,color.id)
        self.bright.use()
        self.bright["source"] = 0
        self.bright["texel"] = (1/size[0],1/size[1])
        self.bright["threshold"] = self.threshold
        self.quads[self.bright].draw(GL_TRIANGLES)
        self.blur.use()
        self.blur["source"] = 0
        # 서로 다른 두 FBO를 번갈아 써서 읽는 텍스처에 동시에 쓰지 않는다.
        for _ in range(3):
            for src,dst,direction in ((0,1,(1,0)),(1,0,(0,1))):
                self.fbos[dst].bind()
                glBindTexture(GL_TEXTURE_2D,self.textures[src].id)
                self.blur["step_uv"] = tuple(self.radius*direction[i]/self.size[i] for i in range(2))
                self.quads[self.blur].draw(GL_TRIANGLES)
        glBindTexture(GL_TEXTURE_2D,0)
        return self.textures[0]
