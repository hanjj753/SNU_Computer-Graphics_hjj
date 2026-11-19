"""ID와 깊이를 다섯 방향으로 래스터화해 패치 간 빛 전달률을 구한다.

광선-삼각형 교차나 ray marching은 사용하지 않는다. 각 픽셀의 입체각과
cosine 가중치를 합산하는 Cohen/Greenberg의 hemicube 방식이다.
"""

from ctypes import byref
import math

import pyglet
from pyglet.gl import *
from pyglet.graphics.shader import Shader, ShaderProgram
from pyglet.image.buffer import Framebuffer
from pyglet.math import Mat4, Vec3

RESOLUTION = 96
NEAR, FAR = 0.004, 20.0
ORIGIN_OFFSET = 0.004

VERTEX = """#version 330 core
in vec3 POSITION;
in float PATCH_ID;
uniform mat4 capture_vp;
flat out uint patch_id;
void main(){patch_id=uint(PATCH_ID);gl_Position=capture_vp*vec4(POSITION,1);}
"""
FRAGMENT = """#version 330 core
flat in uint patch_id;
layout(location=0) out uint visible_id;
void main(){visible_id=patch_id;}
"""

# CPU의 카메라 배치와 같은 좌표계를 사용해, 최종 fragment에서도 가림을 확인한다.
VISIBILITY_SOURCE = """
uniform sampler2DArray bounce_depth_atlas;
uniform usampler2DArray bounce_surface_atlas;
uniform vec2 bounce_depth_range;
uniform vec2 bounce_atlas_size;
uniform float bounce_origin_offset;

float bounce_visibility(int index,vec3 source,vec3 normal,vec3 receiver,vec3 receiver_normal) {
    vec3 seed=abs(normal.y)<.9 ? vec3(0,1,0):vec3(1,0,0);
    vec3 tangent=normalize(cross(normal,seed));
    vec3 up=normalize(cross(tangent,normal));
    vec3 delta=receiver-source-normal*bounce_origin_offset;
    vec3 p=vec3(dot(delta,tangent),dot(delta,up),dot(delta,normal));
    if(p.z<=0.0) return 0.0;
    int face=0;vec3 q=p;
    if(abs(p.x)>p.z && abs(p.x)>=abs(p.y)) {
        if(p.x>0.0){face=1;q=vec3(-p.z,p.y,p.x);}
        else{face=2;q=vec3(p.z,p.y,-p.x);}
    } else if(abs(p.y)>p.z) {
        if(p.y>0.0){face=3;q=vec3(p.x,-p.z,p.y);}
        else{face=4;q=vec3(p.x,p.z,-p.y);}
    }
    float near=bounce_depth_range.x,far=bounce_depth_range.y;
    if(q.z<=near) return 1.0;
    float depth=far/(far-near)-far*near/((far-near)*q.z);
    vec2 face_uv=q.xy/q.z*.5+.5;
    vec2 tiles=vec2(3,2),tile=vec2(face%3,face/3);
    vec2 size=bounce_atlas_size/tiles;
    // 비스듬한 수신 면은 한 texel 안에서도 깊이가 달라진다.
    // 그 기울기만큼 bias를 넓혀 자기 자신을 그림자로 판정하는 줄무늬를 막는다.
    float cosine=max(abs(dot(normalize(receiver-source),receiver_normal)),.12);
    float slope=sqrt(max(1.0-cosine*cosine,0.0))/cosine;
    float conversion=near*far/(far-near);
    // 다른 물체에는 작은 월드 거리 허용값만 쓴다. 큰 slope bias를 쓰면
    // 얇은 상자를 통과해 빛이 새어 들어갈 수 있다.
    float strict_bias=.000001+conversion*.004/max(q.z*q.z,.00001);
    float self_bias=strict_bias+conversion*2.0*slope/(size.x*q.z);
    float result=0.0;
    // 작은 PCF로 저해상도 깊이 맵의 계단과 패치 그림자의 점무늬를 줄인다.
    for(int y=-1;y<=1;y+=2) for(int x=-1;x<=1;x+=2) {
        vec2 pixel=clamp(face_uv*size+vec2(x,y)*.75,vec2(.5),size-.5);
        vec2 uv=(tile*size+pixel)/bounce_atlas_size;
        float stored=texture(bounce_depth_atlas,vec3(uv,float(index))).r;
        uint surface=texture(bounce_surface_atlas,vec3(uv,float(index))).r;
        bool same_surface=false;
        if(surface>0u && surface<=uint(bounce_count)) {
            int owner=int(surface)-1;
            same_surface=dot(bounce_normals[owner],receiver_normal)>.985
                         && abs(dot(receiver-bounce_positions[owner],bounce_normals[owner]))<.015;
        }
        float bias=same_surface ? self_bias:strict_bias;
        result+=depth-bias<=stored ? .25:0.0;
    }
    return result;
}
"""


class Hemicube:
    def __init__(self, patches, occluders, light_positions, light_width, light_depth,
                 *, receivers=None, keep_depth=True, resolution=RESOLUTION,hidden_names=()):
        self.resolution=resolution
        self.size=(resolution*3,resolution*2)
        self.count=len(patches)
        self.receivers=patches if receivers is None else receivers
        self.receiver_is_patch=receivers is None
        self.layer_count=len(self.receivers) if keep_depth else 1
        self.program=ShaderProgram(Shader(VERTEX,'vertex'),Shader(FRAGMENT,'fragment'))
        positions=[];ids=[]
        for index,patch in enumerate(patches):
            if patch.name in hidden_names:continue
            for p in patch.vertices:positions.extend(p)
            # 곡면 패치는 실제 렌더링 메시의 여러 삼각형을 같은 ID로 묶는다.
            ids.extend([float(index+1)]*len(patch.vertices))
        for mesh in occluders:
            positions.extend(mesh);ids.extend([0.0]*(len(mesh)//3))
        center=Vec3(*(sum(p[i] for p in light_positions)/len(light_positions) for i in range(3)))
        self.light_area=light_width*light_depth
        x,y,z=center;w,d=light_width/2,light_depth/2
        positions.extend((x-w,y,z-d,x+w,y,z-d,x+w,y,z+d,
                          x-w,y,z-d,x+w,y,z+d,x-w,y,z+d))
        ids.extend([float(self.count+1)]*6)
        self.vertices=self.program.vertex_list(len(ids),GL_TRIANGLES,
            POSITION=('f',positions),PATCH_ID=('f',ids))
        self.weights=self._weights()
        self.factors,self.direct_factors=self._capture(self.receivers)

    @staticmethod
    def basis(normal):
        seed=Vec3(0,1,0) if abs(normal.y)<.9 else Vec3(1,0,0)
        tangent=normal.cross(seed).normalize()
        up=tangent.cross(normal).normalize()
        return tangent,up

    def _weights(self):
        result=[];r=self.resolution;width=self.size[0]
        for face in range(5):
            for y in range(r):
                for x in range(r):
                    u,v=2*(x+.5)/r-1,2*(y+.5)/r-1
                    z=(1.,-u,u,-v,v)[face]
                    weight=4*max(z,0.)/(r*r*math.pi*(1+u*u+v*v)**2)
                    if weight>0:
                        index=((face//3)*r+y)*width+(face%3)*r+x
                        result.append((index,weight))
        total=sum(w for _,w in result)
        return [(index,w/total) for index,w in result]

    def _capture(self,patches):
        old_fbo=GLint();old_active=GLint();viewport=(GLint*4)();write=GLboolean();cull=GLint()
        glGetIntegerv(GL_FRAMEBUFFER_BINDING,byref(old_fbo))
        glGetIntegerv(GL_ACTIVE_TEXTURE,byref(old_active));glGetIntegerv(GL_VIEWPORT,viewport)
        glGetBooleanv(GL_DEPTH_WRITEMASK,byref(write));glGetIntegerv(GL_CULL_FACE_MODE,byref(cull))
        states={state:bool(glIsEnabled(state)) for state in (GL_DEPTH_TEST,GL_BLEND,GL_CULL_FACE,GL_FRAMEBUFFER_SRGB)}
        glActiveTexture(GL_TEXTURE0)
        self.depth=GLuint();glGenTextures(1,byref(self.depth))
        glBindTexture(GL_TEXTURE_2D_ARRAY,self.depth.value)
        glTexImage3D(GL_TEXTURE_2D_ARRAY,0,GL_DEPTH_COMPONENT24,*self.size,self.layer_count,0,GL_DEPTH_COMPONENT,GL_FLOAT,None)
        for parameter,value in ((GL_TEXTURE_MIN_FILTER,GL_NEAREST),(GL_TEXTURE_MAG_FILTER,GL_NEAREST),
                                 (GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE),(GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE)):
            glTexParameteri(GL_TEXTURE_2D_ARRAY,parameter,value)
        glBindTexture(GL_TEXTURE_2D_ARRAY,0)
        # 가장 앞에 보인 면의 ID도 깊이와 같은 레이어에 남긴다.
        self.surface=GLuint();glGenTextures(1,byref(self.surface))
        glBindTexture(GL_TEXTURE_2D_ARRAY,self.surface.value)
        glTexImage3D(GL_TEXTURE_2D_ARRAY,0,GL_R32UI,*self.size,self.layer_count,0,GL_RED_INTEGER,GL_UNSIGNED_INT,None)
        for parameter,value in ((GL_TEXTURE_MIN_FILTER,GL_NEAREST),(GL_TEXTURE_MAG_FILTER,GL_NEAREST),
                                 (GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE),(GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE)):
            glTexParameteri(GL_TEXTURE_2D_ARRAY,parameter,value)
        glBindTexture(GL_TEXTURE_2D_ARRAY,0)
        fbo=Framebuffer();fbo.bind()
        buffer=(GLuint*(self.size[0]*self.size[1]))()
        factors=[];direct=[]
        projection=Mat4.perspective_projection(1,z_near=NEAR,z_far=FAR,fov=90)
        try:
            glEnable(GL_DEPTH_TEST);glDepthMask(GL_TRUE)
            glEnable(GL_CULL_FACE);glCullFace(GL_BACK)
            glDisable(GL_BLEND);glDisable(GL_FRAMEBUFFER_SRGB)
            self.program.use()
            for index,patch in enumerate(patches):
                layer=index if self.layer_count>1 else 0
                glFramebufferTextureLayer(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,self.surface.value,0,layer)
                glFramebufferTextureLayer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,self.depth.value,0,layer)
                if not fbo.is_complete:raise RuntimeError(fbo.get_status())
                glClearBufferuiv(GL_COLOR,0,(GLuint*4)(0,0,0,0));glClear(GL_DEPTH_BUFFER_BIT)
                normal=patch.normal;tangent,up=self.basis(normal)
                origin=patch.center+normal*ORIGIN_OFFSET
                directions=((normal,up),(tangent,up),(-tangent,up),(up,-normal),(-up,normal))
                for face,(direction,camera_up) in enumerate(directions):
                    size=self.resolution
                    glViewport((face%3)*size,(face//3)*size,size,size)
                    self.program['capture_vp']=projection@Mat4.look_at(origin,origin+direction,camera_up)
                    self.vertices.draw(GL_TRIANGLES)
                glReadPixels(0,0,*self.size,GL_RED_INTEGER,GL_UNSIGNED_INT,buffer)
                row=[0.0]*(self.count+2)
                for pixel,weight in self.weights:row[buffer[pixel]]+=weight
                if self.receiver_is_patch:row[index+1]=0.0
                factors.append(row[1:self.count+1]);direct.append(row[self.count+1])
        finally:
            glBindFramebuffer(GL_FRAMEBUFFER,old_fbo.value);glViewport(*viewport)
            glDepthMask(write.value);glCullFace(cull.value)
            for state,enabled in states.items():(glEnable if enabled else glDisable)(state)
            glBindTexture(GL_TEXTURE_2D,0);glActiveTexture(old_active.value)
            fbo.delete();self.vertices.delete();self.program.delete()
        return factors,direct

    def bind(self,program):
        glActiveTexture(GL_TEXTURE14);glBindTexture(GL_TEXTURE_2D_ARRAY,self.depth.value)
        program['bounce_depth_atlas']=14
        glActiveTexture(GL_TEXTURE15);glBindTexture(GL_TEXTURE_2D_ARRAY,self.surface.value)
        program['bounce_surface_atlas']=15
        program['bounce_depth_range']=(NEAR,FAR)
        program['bounce_atlas_size']=self.size
        program['bounce_origin_offset']=ORIGIN_OFFSET
        glActiveTexture(GL_TEXTURE0)

    def delete(self):
        if self.depth is not None:
            glDeleteTextures(1,byref(self.depth))
            self.depth=None
        if self.surface is not None:
            glDeleteTextures(1,byref(self.surface))
            self.surface=None
