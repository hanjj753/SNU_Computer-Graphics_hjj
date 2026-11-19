"""거울 위치로 옮긴 카메라로 장면을 다시 그려 PVC의 흐린 반사를 만든다."""

from ctypes import byref

import pyglet
from pyglet.gl import *
from pyglet.image.buffer import Framebuffer, Renderbuffer
from pyglet.math import Mat4, Vec3, Vec4


PLANES = {
    "ceiling": (Vec3(0,-1,0),3.0),
    "left": (Vec3(1,0,0),0.0),
    "right": (Vec3(-1,0,0),2.9),
}
# 천장의 비침은 줄이고, 벽의 반사 영상은 약하게 섞는다.
REFLECTION_STRENGTH = {"ceiling":0.55,"left":0.14,"right":0.12}
REFLECTION_ROUGHNESS = {"ceiling":0.60,"left":0.58,"right":0.58}


def mirror_matrix(normal, distance):
    """n·p+d=0 평면의 대칭 변환. 광선과 물체의 교차 검사는 하지 않는다."""
    n=tuple(normal)
    values=[]
    for column in range(4):
        for row in range(4):
            if row<3 and column<3:
                values.append(float(row==column)-2*n[row]*n[column])
            elif column==3 and row<3:
                values.append(-2*distance*n[row])
            else:
                values.append(float(row==column))
    return Mat4(*values)


class ReflectionTarget:
    def __init__(self,size):
        previous=GLint();glGetIntegerv(GL_FRAMEBUFFER_BINDING,byref(previous))
        self.texture=pyglet.image.Texture.create(
            *size,internalformat=GL_RGBA16F,fmt=GL_RGBA,
            min_filter=GL_LINEAR_MIPMAP_LINEAR,mag_filter=GL_LINEAR,blank_data=False,
        )
        for name in (GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T):
            glTexParameteri(GL_TEXTURE_2D,name,GL_CLAMP_TO_EDGE)
        self.depth=Renderbuffer(*size,GL_DEPTH_COMPONENT24)
        self.fbo=Framebuffer()
        self.fbo.attach_texture(self.texture)
        self.fbo.attach_renderbuffer(self.depth,attachment=GL_DEPTH_ATTACHMENT)
        self.fbo.bind()
        if not self.fbo.is_complete:raise RuntimeError(self.fbo.get_status())
        glBindFramebuffer(GL_FRAMEBUFFER,previous.value)

    def delete(self):
        self.fbo.delete();self.texture.delete();self.depth.delete()


class PlanarReflections:
    def __init__(self):
        self.enabled=True
        self.suspended=False
        self.dirty=True
        self.size=(0,0)
        self.targets={}
        self.planes=dict(PLANES)
        self.capturing_plane=None
        self.matrices={}
        self.last_camera=None
        self.capture_count=0
        self.strength=dict(REFLECTION_STRENGTH)
        self.roughness=dict(REFLECTION_ROUGHNESS)
        self.black=pyglet.image.Texture.create(1,1,internalformat=GL_RGBA16F,fmt=GL_RGBA)
        glBindTexture(GL_TEXTURE_2D,self.black.id)
        glTexSubImage2D(GL_TEXTURE_2D,0,0,0,1,1,GL_RGBA,GL_FLOAT,(GLfloat*4)(0,0,0,1))
        glBindTexture(GL_TEXTURE_2D,0)

    def add_plane(self,name,normal,distance,*,strength,roughness):
        length=normal.length()
        self.planes[name]=(normal/length,distance/length)
        self.strength[name]=strength
        self.roughness[name]=roughness
        self.dirty=True

    def _resize(self,window):
        size=tuple(max(1,n//2) for n in window.get_framebuffer_size())
        if size==self.size and set(self.targets)==set(self.planes):return
        for target in self.targets.values():target.delete()
        self.targets={name:ReflectionTarget(size) for name in self.planes}
        self.size=size
        self.dirty=True

    def capture(self,window,program,draw_opaque,draw_transparent=None):
        if not self.enabled:return
        self._resize(window)
        camera_key=(tuple(window.projection),tuple(window.view),self.size)
        if not self.dirty and camera_key==self.last_camera:return
        projection,view=window.projection,window.view
        eye=(~view)@Vec4(0,0,0,1)
        old_camera=program["camera_position"]
        old_bounce=program["bounce_strength"]
        old_clip=program["reflection_clip_plane"]
        old_capture=program["reflection_capture"]
        old_suspended=self.suspended
        old_plane=self.capturing_plane
        viewport=(GLint*4)();previous_fbo=GLint();active=GLint();clear=(GLfloat*4)();depth_write=GLboolean()
        glGetIntegerv(GL_VIEWPORT,viewport)
        glGetIntegerv(GL_FRAMEBUFFER_BINDING,byref(previous_fbo))
        glGetIntegerv(GL_ACTIVE_TEXTURE,byref(active))
        glGetFloatv(GL_COLOR_CLEAR_VALUE,clear)
        glGetBooleanv(GL_DEPTH_WRITEMASK,byref(depth_write))
        depth_enabled=bool(glIsEnabled(GL_DEPTH_TEST));blend_enabled=bool(glIsEnabled(GL_BLEND))
        cull_enabled=bool(glIsEnabled(GL_CULL_FACE))
        try:
            self.suspended=True
            # 미리 푼 다중 간접광은 반사 영상에도 사용한다.
            # 평면 반사 텍스처의 재귀 읽기만 suspended로 막는다.
            program["reflection_capture"]=True
            glEnable(GL_DEPTH_TEST);glDepthMask(GL_TRUE)
            glDisable(GL_BLEND);glDisable(GL_CULL_FACE)
            glClearColor(0,0,0,1)
            for name,(normal,distance) in self.planes.items():
                self.capturing_plane=name
                target=self.targets[name]
                target.fbo.bind();glViewport(0,0,*self.size)
                glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
                mirror=mirror_matrix(normal,distance)
                reflected_eye=mirror@eye
                window.view=view@mirror
                self.matrices[name]=projection@window.view
                program["camera_position"]=tuple(reflected_eye[:3])
                # 반사하는 판과 그 바깥쪽은 반사 영상에서 제외한다.
                program["reflection_clip_plane"]=(*normal,distance-.001)
                draw_opaque()
                if draw_transparent is not None:draw_transparent(window.view)
                glActiveTexture(GL_TEXTURE0)
                glBindTexture(GL_TEXTURE_2D,target.texture.id)
                glGenerateMipmap(GL_TEXTURE_2D)
                glBindTexture(GL_TEXTURE_2D,0)
            self.last_camera=camera_key
            self.dirty=False
            self.capture_count+=1
        finally:
            window.projection,window.view=projection,view
            program["camera_position"]=old_camera
            program["bounce_strength"]=old_bounce
            program["reflection_clip_plane"]=old_clip
            program["reflection_capture"]=old_capture
            self.suspended=old_suspended
            self.capturing_plane=old_plane
            glClearColor(*clear)
            glBindFramebuffer(GL_FRAMEBUFFER,previous_fbo.value)
            glViewport(*viewport)
            glDepthMask(depth_write.value)
            for state,enabled in ((GL_DEPTH_TEST,depth_enabled),(GL_BLEND,blend_enabled),(GL_CULL_FACE,cull_enabled)):
                (glEnable if enabled else glDisable)(state)
            glActiveTexture(active.value)

    def bind_material(self,program,material):
        name=getattr(material,"planar_plane",None)
        program["skip_reflection_surface"]=self.capturing_plane is not None and name==self.capturing_plane
        valid=self.enabled and not self.suspended and name in self.matrices
        glActiveTexture(GL_TEXTURE11)
        # 캡처 중에는 검정 텍스처를 써 현재 쓰는 FBO를 다시 읽지 않는다.
        glBindTexture(GL_TEXTURE_2D,self.targets[name].texture.id if valid else self.black.id)
        program["planar_texture"]=11
        program["planar_strength"]=self.strength[name] if valid else 0.0
        if valid:
            program["planar_view_projection"]=self.matrices[name]
            program["planar_roughness"]=self.roughness[name]
        glActiveTexture(GL_TEXTURE0)
