"""컵의 유한한 벽 두께에 의한 굴절과 반투명 플라스틱의 흐림을 근사한다."""

import pyglet
from pyglet.gl import *
from pyglet.image.buffer import Framebuffer


CUP_OPTICS_SOURCE = """
uniform WindowBlock { mat4 projection; mat4 view; } window;
uniform bool cup_surface;
uniform bool cup_optics_enabled;
uniform sampler2D cup_background;
uniform sampler2D cup_background_depth;
uniform vec2 cup_center_xz;
uniform vec4 cup_profile; // 아래 y, 위 y, 아래 두께, 위 두께
uniform float cup_base_thickness;
uniform float cup_slope;
uniform float cup_ior;
uniform float cup_water_top;
uniform float cup_refraction_strength;
uniform float cup_frost_radius;

vec2 cup_project(vec3 position_view) {
    vec4 clip=window.projection*vec4(position_view,1.0);
    return clip.xy/clip.w*.5+.5;
}

vec3 cup_view_position(vec2 uv,float depth) {
    vec4 p=inverse(window.projection)*vec4(uv*2.0-1.0,depth*2.0-1.0,1.0);
    return p.xyz/p.w;
}

bool cup_valid_sample(vec2 uv) {
    return all(greaterThanEqual(uv,vec2(0.0))) && all(lessThanEqual(uv,vec2(1.0)))
           && texture(cup_background_depth,uv).r>=gl_FragCoord.z-0.00001;
}

vec3 cup_background_sample(vec2 uv,vec2 fallback) {
    // 굴절된 좌표에 컵보다 앞에 있는 물체가 있으면 원래 픽셀로 돌아간다.
    return texture(cup_background,cup_valid_sample(uv) ? uv:fallback).rgb;
}

vec4 cup_transmitted_color(vec3 N,vec3 V,vec3 surface_color,float opacity) {
    vec2 uv=gl_FragCoord.xy/viewport_size;
    vec3 I=-V;
    vec3 in_plastic=refract(I,N,1.0/cup_ior);
    float h=clamp((world_position.y-cup_profile.x)/max(cup_profile.y-cup_profile.x,1e-5),0.0,1.0);
    float thickness=mix(cup_profile.z,cup_profile.w,h);
    bool side=abs(N.y)<.9;
    if (!side) thickness=cup_base_thickness;
    float path=thickness/max(abs(dot(in_plastic,N)),.15);
    vec3 exit_position=world_position+in_plastic*path;

    // 곡면의 반대쪽 경계에서는 법선도 조금 달라진다.
    // 같은 법선을 두 번 쓰면 평행한 얇은 판처럼 횡이동만 생긴다.
    vec3 exit_normal=N;
    if (side) {
        vec2 radial=normalize(exit_position.xz-cup_center_xz);
        exit_normal=normalize(vec3(radial.x,-cup_slope,radial.y));
        if (dot(exit_normal,N)<0.0) exit_normal=-exit_normal;
        // 가장자리에서 단순한 두께 이동이 반대편 곡면을 넘어가면
        // 출구 법선이 입사 방향을 향할 수 있다. 그때는 평행한 벽 근사로 돌아간다.
        if (dot(exit_normal,in_plastic)>=0.0) exit_normal=N;
    }
    vec3 outgoing=refract(in_plastic,exit_normal,cup_ior);
    vec2 offset=vec2(0.0);
    if (dot(outgoing,outgoing)>.01) {
        vec3 p=(window.view*vec4(exit_position,1.0)).xyz;
        vec3 direction=(window.view*vec4(outgoing,0.0)).xyz;
        float backdrop_z=cup_view_position(uv,texture(cup_background_depth,uv).r).z;
        float distance=abs(direction.z)>1e-4 ? clamp((backdrop_z-p.z)/direction.z,0.0,4.0):0.0;
        offset=cup_project(p+direction*distance)-uv;
    }
    // 수면 위의 빈 컵은 앞·뒤 두 벽을 통과한 결과를 한 번에 근사한다.
    // 수면 아래는 물 렌더링 전후에 각각 한 벽씩 처리한다.
    bool wet=world_position.y<cup_water_top && transparency_phase!=0
             && texture(water_front_depth,uv).r<.999999;
    float walls=wet ? 1.0:2.0;
    offset*=walls*cup_refraction_strength;
    offset*=min(1.0,.035/max(length(offset),1e-6));
    // 수면 아래 앞쪽 벽은 water_optics의 공기→플라스틱→물 경로에
    // 이미 포함되어 있다. 이 부분은 여기서 산란만 더해 이중 굴절을 피한다.
    if (wet && transparency_phase>0) offset=vec2(0.0);
    // 굴절률이 공기와 같으면 광학 경계가 없다. 스침각의 상쇄 오차도 피한다.
    if (abs(cup_ior-1.0)<1e-6) offset=vec2(0.0);
    vec2 candidate=uv+offset;
    if (!cup_valid_sample(candidate)) candidate=uv;

    // 반투명 플라스틱의 산란을 배경의 작은 저역 통과 필터로 표현한다.
    // 이 흐림은 표면을 스스로 발광시키거나 흰 띠를 추가하는 처리가 아니다.
    vec2 pixel=cup_frost_radius*(wet ? .6:1.0)/viewport_size;
    vec3 transmitted=.28*cup_background_sample(candidate,uv);
    transmitted+=.12*(cup_background_sample(candidate+vec2(pixel.x,0),uv)
                      +cup_background_sample(candidate-vec2(pixel.x,0),uv)
                      +cup_background_sample(candidate+vec2(0,pixel.y),uv)
                      +cup_background_sample(candidate-vec2(0,pixel.y),uv));
    transmitted+=.06*(cup_background_sample(candidate+pixel,uv)
                      +cup_background_sample(candidate-pixel,uv)
                      +cup_background_sample(candidate+vec2(pixel.x,-pixel.y),uv)
                      +cup_background_sample(candidate+vec2(-pixel.x,pixel.y),uv));
    float scattering=1.0-pow(1.0-opacity,2.0*walls);
    // 배경까지 포함해 합성한 색이므로 바깥 alpha blend에서 다시 섞지 않는다.
    return vec4(mix(transmitted,surface_color,scattering),1.0);
}
"""


class CupOptics:
    def __init__(self, program):
        self.program=program
        self.ior=1.49
        self.refraction_strength=1.1
        self.frost_radius=1.8
        self.size=(0,0)
        self.fbo=None

    def set_cup(self, mesh, water_top):
        self.center=mesh.center
        (lo,rlo),(hi,rhi)=mesh.outer_profile
        self.profile=(lo,hi,mesh.wall_thickness(lo),mesh.wall_thickness(hi))
        self.slope=(rhi-rlo)/(hi-lo)
        self.base_thickness=mesh.base_thickness
        self.water_top=water_top

    def _resize(self,size):
        if self.size==size:return
        if self.fbo is not None:
            self.fbo.delete();self.color.delete();self.depth.delete()
        self.size=size
        def texture(depth=False):
            tex=pyglet.image.Texture.create(
                *size,internalformat=GL_DEPTH_COMPONENT24 if depth else GL_RGBA16F,
                fmt=GL_DEPTH_COMPONENT if depth else GL_RGBA,
                min_filter=GL_NEAREST if depth else GL_LINEAR,
                mag_filter=GL_NEAREST if depth else GL_LINEAR,blank_data=False,
            )
            for axis in (GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T):
                glTexParameteri(GL_TEXTURE_2D,axis,GL_CLAMP_TO_EDGE)
            return tex
        self.color,self.depth=texture(),texture(True)
        self.fbo=Framebuffer()
        self.fbo.attach_texture(self.color)
        self.fbo.attach_texture(self.depth,attachment=GL_DEPTH_ATTACHMENT)
        self.fbo.bind()
        if not self.fbo.is_complete:raise RuntimeError(self.fbo.get_status())

    def bind(self,render_target):
        active=render_target is not None
        self.program['cup_optics_enabled']=active
        if not active:return
        self._resize(render_target.size)
        # 현재 그리고 있는 색 텍스처를 바로 읽으면 결과가 정의되지 않는다.
        # 물 뒤/앞의 컵을 그리기 직전에 각각 배경 색과 깊이를 별도로 복사한다.
        glBindFramebuffer(GL_READ_FRAMEBUFFER,render_target.fbo.id)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER,self.fbo.id)
        glBlitFramebuffer(0,0,*self.size,0,0,*self.size,
                          GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT,GL_NEAREST)
        render_target.fbo.bind()
        for unit,name,texture in ((12,'cup_background',self.color),(13,'cup_background_depth',self.depth)):
            glActiveTexture(GL_TEXTURE0+unit)
            glBindTexture(GL_TEXTURE_2D,texture.id)
            self.program[name]=unit
        self.program['viewport_size']=self.size
        self.program['cup_center_xz']=self.center
        self.program['cup_profile']=self.profile
        self.program['cup_base_thickness']=self.base_thickness
        self.program['cup_slope']=self.slope
        self.program['cup_ior']=self.ior
        self.program['cup_water_top']=self.water_top
        self.program['cup_refraction_strength']=self.refraction_strength
        self.program['cup_frost_radius']=self.frost_radius
        glActiveTexture(GL_TEXTURE0)

    def unbind(self):
        self.program['cup_optics_enabled']=False
        for unit in (12,13):
            glActiveTexture(GL_TEXTURE0+unit)
            glBindTexture(GL_TEXTURE_2D,0)
        glActiveTexture(GL_TEXTURE0)
