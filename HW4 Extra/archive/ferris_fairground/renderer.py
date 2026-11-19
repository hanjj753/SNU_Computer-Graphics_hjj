"""Instanced forward rendering, four shadow maps, two reflection techniques, HDR."""
from __future__ import annotations

from collections import defaultdict
from ctypes import byref
from pyglet.gl import *
from pyglet.math import Mat4,Vec3,Vec4
from pyglet.graphics.shader import Shader,ShaderProgram

import geometry
import shaders
from scene import FLOOR_Y,SHADOW_LIGHTS,ROOM_MIN,ROOM_MAX
from textures import create_nameplate


def program(vertex,fragment):
    return ShaderProgram(Shader(vertex,'vertex'),Shader(fragment,'fragment'))


def texture_2d(width,height):
    texture=GLuint()
    glGenTextures(1,byref(texture))
    glBindTexture(GL_TEXTURE_2D,texture)
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA16F,width,height,0,GL_RGBA,GL_FLOAT,None)
    for key in (GL_TEXTURE_MIN_FILTER,GL_TEXTURE_MAG_FILTER):glTexParameteri(GL_TEXTURE_2D,key,GL_LINEAR)
    for key in (GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T):glTexParameteri(GL_TEXTURE_2D,key,GL_CLAMP_TO_EDGE)
    return texture


def check_framebuffer(label):
    status=glCheckFramebufferStatus(GL_FRAMEBUFFER)
    if status!=GL_FRAMEBUFFER_COMPLETE:
        raise RuntimeError(f'{label}: framebuffer incomplete (0x{status:x})')


class Target:
    def __init__(self,width,height,depth=True):
        self.size=(max(1,width),max(1,height))
        self.texture=texture_2d(*self.size)
        self.fbo=GLuint()
        self.depth=GLuint()
        glGenFramebuffers(1,byref(self.fbo))
        glBindFramebuffer(GL_FRAMEBUFFER,self.fbo)
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,self.texture,0)
        if depth:
            glGenRenderbuffers(1,byref(self.depth))
            glBindRenderbuffer(GL_RENDERBUFFER,self.depth)
            glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT24,*self.size)
            glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,self.depth)
        check_framebuffer('HDR target')
        glBindFramebuffer(GL_FRAMEBUFFER,0)

    def bind(self):
        glBindFramebuffer(GL_FRAMEBUFFER,self.fbo)
        glViewport(0,0,*self.size)

    def delete(self):
        glDeleteFramebuffers(1,byref(self.fbo))
        glDeleteTextures(1,byref(self.texture))
        if self.depth.value:glDeleteRenderbuffers(1,byref(self.depth))


class MultisampleTarget:
    """Four raster samples for thin spokes; resolved to the HDR texture."""
    def __init__(self,width,height):
        self.size=(width,height)
        self.fbo,self.color,self.depth=GLuint(),GLuint(),GLuint()
        glGenFramebuffers(1,byref(self.fbo))
        glBindFramebuffer(GL_FRAMEBUFFER,self.fbo)
        for renderbuffer,format_,attachment in (
            (self.color,GL_RGBA16F,GL_COLOR_ATTACHMENT0),
            (self.depth,GL_DEPTH_COMPONENT24,GL_DEPTH_ATTACHMENT),
        ):
            glGenRenderbuffers(1,byref(renderbuffer))
            glBindRenderbuffer(GL_RENDERBUFFER,renderbuffer)
            glRenderbufferStorageMultisample(GL_RENDERBUFFER,4,format_,width,height)
            glFramebufferRenderbuffer(GL_FRAMEBUFFER,attachment,GL_RENDERBUFFER,renderbuffer)
        check_framebuffer('4x MSAA target')
        glBindFramebuffer(GL_FRAMEBUFFER,0)

    def bind(self):
        glBindFramebuffer(GL_FRAMEBUFFER,self.fbo)
        glViewport(0,0,*self.size)

    def resolve(self,destination):
        glBindFramebuffer(GL_READ_FRAMEBUFFER,self.fbo)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER,destination.fbo)
        w,h=self.size
        glBlitFramebuffer(0,0,w,h,0,0,w,h,GL_COLOR_BUFFER_BIT,GL_NEAREST)

    def delete(self):
        glDeleteFramebuffers(1,byref(self.fbo))
        glDeleteRenderbuffers(1,byref(self.color))
        glDeleteRenderbuffers(1,byref(self.depth))


class Renderer:
    def __init__(self,scene,shadow_size=1024):
        self.scene=scene
        self.surface=program(shaders.SURFACE_VERTEX,shaders.SURFACE_FRAGMENT)
        self.depth_program=program(shaders.DEPTH_VERTEX,shaders.DEPTH_FRAGMENT)
        self.bright=program(shaders.FULLSCREEN_VERTEX,shaders.BRIGHT_FRAGMENT)
        self.blur=program(shaders.FULLSCREEN_VERTEX,shaders.BLUR_FRAGMENT)
        self.post=program(shaders.FULLSCREEN_VERTEX,shaders.POST_FRAGMENT)
        self.empty_vao=GLuint()
        glGenVertexArrays(1,byref(self.empty_vao))
        self.data={name:getattr(geometry,name)() for name in ('quad','box','sphere','cylinder','torus')}
        self.meshes={}
        self.glass_mesh=geometry.InstancedMesh(self.data['quad'])
        self.targets=[]
        self.size=(0,0)
        self.shadows=True
        self.reflections=True
        self.bloom=True
        self.glass=True
        self.bump=True
        self.exposure=1.18
        self.reflection_vp=Mat4()
        self.probe_position=Vec3(0,1.54,-.35)
        self.probe_time=None
        self.probe_ready=False
        self.shadow_time=None
        self.last_shadow_toggle=True
        self.shadow_size=shadow_size
        self.shadow_fbo=GLuint()
        self.shadow_texture=GLuint()
        glGenFramebuffers(1,byref(self.shadow_fbo))
        glGenTextures(1,byref(self.shadow_texture))
        glBindTexture(GL_TEXTURE_2D_ARRAY,self.shadow_texture)
        glTexImage3D(GL_TEXTURE_2D_ARRAY,0,GL_DEPTH_COMPONENT24,shadow_size,shadow_size,SHADOW_LIGHTS,
                     0,GL_DEPTH_COMPONENT,GL_FLOAT,None)
        for key in (GL_TEXTURE_MIN_FILTER,GL_TEXTURE_MAG_FILTER):glTexParameteri(GL_TEXTURE_2D_ARRAY,key,GL_NEAREST)
        for key in (GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T):glTexParameteri(GL_TEXTURE_2D_ARRAY,key,GL_CLAMP_TO_BORDER)
        border=(GLfloat*4)(1,1,1,1)
        glTexParameterfv(GL_TEXTURE_2D_ARRAY,GL_TEXTURE_BORDER_COLOR,border)
        glBindFramebuffer(GL_FRAMEBUFFER,self.shadow_fbo)
        glFramebufferTextureLayer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,self.shadow_texture,0,0)
        glDrawBuffer(GL_NONE)
        glReadBuffer(GL_NONE)
        check_framebuffer('Shadow map')
        glBindFramebuffer(GL_FRAMEBUFFER,0)
        projection=Mat4.perspective_projection(1,z_near=.07,z_far=8.,fov=128.)
        self.shadow_vps=[]
        for light in scene.lights[:SHADOW_LIGHTS]:
            p=Vec3(*light.position)
            self.shadow_vps.append(projection@Mat4.look_at(p,Vec3(p.x,0,p.z),Vec3(0,0,-1)))
        self._create_probe()
        self.sign=create_nameplate()
        self.black=texture_2d(1,1)
        glBindTexture(GL_TEXTURE_2D,self.black)
        black=(GLfloat*4)(0,0,0,1)
        glTexSubImage2D(GL_TEXTURE_2D,0,0,0,1,1,GL_RGBA,GL_FLOAT,black)
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        glDisable(GL_CULL_FACE)
        glEnable(GL_TEXTURE_CUBE_MAP_SEAMLESS)
        glEnable(GL_MULTISAMPLE)
        glDisable(GL_FRAMEBUFFER_SRGB)

    def _create_probe(self):
        self.probe_size=128
        self.probe_texture,self.black_cube=GLuint(),GLuint()
        self.probe_fbo,self.probe_depth=GLuint(),GLuint()
        glGenTextures(1,byref(self.probe_texture))
        glGenTextures(1,byref(self.black_cube))
        black=(GLfloat*4)(0,0,0,1)
        for texture,size in ((self.probe_texture,self.probe_size),(self.black_cube,1)):
            glBindTexture(GL_TEXTURE_CUBE_MAP,texture)
            for face in range(6):
                glTexImage2D(GL_TEXTURE_CUBE_MAP_POSITIVE_X+face,0,GL_RGBA16F,size,size,0,
                             GL_RGBA,GL_FLOAT,black if size==1 else None)
            glTexParameteri(GL_TEXTURE_CUBE_MAP,GL_TEXTURE_MIN_FILTER,GL_LINEAR_MIPMAP_LINEAR)
            glTexParameteri(GL_TEXTURE_CUBE_MAP,GL_TEXTURE_MAG_FILTER,GL_LINEAR)
            for key in (GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T,GL_TEXTURE_WRAP_R):
                glTexParameteri(GL_TEXTURE_CUBE_MAP,key,GL_CLAMP_TO_EDGE)
            glGenerateMipmap(GL_TEXTURE_CUBE_MAP)
        glGenFramebuffers(1,byref(self.probe_fbo))
        glGenRenderbuffers(1,byref(self.probe_depth))
        glBindRenderbuffer(GL_RENDERBUFFER,self.probe_depth)
        glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT24,self.probe_size,self.probe_size)
        glBindFramebuffer(GL_FRAMEBUFFER,self.probe_fbo)
        glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,self.probe_depth)
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_CUBE_MAP_POSITIVE_X,self.probe_texture,0)
        check_framebuffer('Environment probe')
        glBindFramebuffer(GL_FRAMEBUFFER,0)

    def resize(self,width,height):
        size=(max(1,width),max(1,height))
        if size==self.size:return
        for target in self.targets:target.delete()
        w,h=size
        self.hdr=Target(w,h)
        self.msaa=MultisampleTarget(w,h)
        self.reflection=Target(max(1,w//2),max(1,h//2))
        self.blur_targets=[Target(max(1,w//4),max(1,h//4),False) for _ in range(2)]
        self.targets=[self.hdr,self.msaa,self.reflection,*self.blur_targets]
        self.size=size

    def prepare(self):
        buckets=defaultdict(list)
        self.glass_nodes=[]
        for node in self.scene.nodes:
            if node.category in ('glass','fairglass'):
                self.glass_nodes.append(node)
            else:
                buckets[(node.mesh,node.category,node.casts_shadow)].extend(node.record())
        for key,records in buckets.items():
            if key not in self.meshes:self.meshes[key]=geometry.InstancedMesh(self.data[key[0]])
            self.meshes[key].upload(records)
        # Keys disappear when the park is hidden. Retire their old GPU instances.
        for key,mesh in self.meshes.items():
            if key not in buckets:mesh.upload([])

    def _draw_opaque(self,probe=False,reflection=False,depth=False):
        for (_,category,casts_shadow),mesh in self.meshes.items():
            if depth and not casts_shadow:continue
            if probe and category not in ('room','ceiling','emission','fairground'):continue
            if reflection and category=='floor':continue
            mesh.draw()

    def _draw_glass(self,view):
        if not self.glass:return
        # All panes share one mesh; sorted instance order preserves blend order.
        def depth(node):
            return (view@Vec4(node.model[12],node.model[13],node.model[14],1.)).z
        records=[]
        for node in sorted(self.glass_nodes,key=depth):records.extend(node.record())
        self.glass_mesh.upload(records)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE)
        self.glass_mesh.draw()
        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)

    def _bind_surface(self,vp,camera,pass_number):
        p=self.surface
        p.use()
        p['view_projection']=vp
        p['camera_position']=tuple(camera)
        positions,colors=self.scene.light_uniforms()
        p['light_positions']=positions
        p['light_colors']=colors
        p['light_count']=len(self.scene.lights)
        p['shadow_vp']=self.shadow_vps
        p['reflection_vp']=self.reflection_vp
        p['shadows_enabled']=self.shadows
        p['reflections_enabled']=self.reflections and self.probe_ready and pass_number!=2
        p['bump_enabled']=self.bump
        p['capture_pass']=pass_number
        p['floor_y']=FLOOR_Y
        p['probe_position']=tuple(self.probe_position)
        p['room_min']=ROOM_MIN
        p['room_max']=ROOM_MAX
        for unit,target,texture,name in (
            (0,GL_TEXTURE_2D_ARRAY,self.shadow_texture,'shadow_map'),
            (1,GL_TEXTURE_CUBE_MAP,self.black_cube if pass_number==2 else self.probe_texture,'environment_map'),
            (2,GL_TEXTURE_2D,self.reflection.texture if pass_number==0 else self.black,'floor_reflection'),
            (3,GL_TEXTURE_2D,self.sign.id,'sign_texture'),
        ):
            glActiveTexture(GL_TEXTURE0+unit)
            glBindTexture(target,texture)
            p[name]=unit
        glActiveTexture(GL_TEXTURE0)

    def _shadows(self):
        if not self.shadows:return
        # Frozen views reuse depth maps. Animation updates all four samples.
        if self.shadow_time==self.scene.time and self.last_shadow_toggle:return
        glBindFramebuffer(GL_FRAMEBUFFER,self.shadow_fbo)
        glViewport(0,0,self.shadow_size,self.shadow_size)
        glDisable(GL_BLEND)
        glDepthMask(GL_TRUE)
        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(1.5,2.)
        self.depth_program.use()
        for layer,matrix in enumerate(self.shadow_vps):
            glFramebufferTextureLayer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,self.shadow_texture,0,layer)
            glClear(GL_DEPTH_BUFFER_BIT)
            self.depth_program['light_vp']=matrix
            self._draw_opaque(depth=True)
        glDisable(GL_POLYGON_OFFSET_FILL)
        self.shadow_time=self.scene.time
        self.last_shadow_toggle=True

    def _probe(self):
        if not self.reflections:return
        if self.probe_time is not None and abs(self.scene.time-self.probe_time)<.4:return
        glBindFramebuffer(GL_FRAMEBUFFER,self.probe_fbo)
        glViewport(0,0,self.probe_size,self.probe_size)
        projection=Mat4.perspective_projection(1,z_near=.06,z_far=15.,fov=90.)
        axes=(((1,0,0),(0,-1,0)),((-1,0,0),(0,-1,0)),
              ((0,1,0),(0,0,1)),((0,-1,0),(0,0,-1)),
              ((0,0,1),(0,-1,0)),((0,0,-1),(0,-1,0)))
        for face,(direction,up) in enumerate(axes):
            glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_CUBE_MAP_POSITIVE_X+face,self.probe_texture,0)
            glClearColor(.004,.006,.012,1)
            glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
            view=Mat4.look_at(self.probe_position,self.probe_position+Vec3(*direction),Vec3(*up))
            self._bind_surface(projection@view,self.probe_position,2)
            self._draw_opaque(probe=True)
        glBindFramebuffer(GL_FRAMEBUFFER,0)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_CUBE_MAP,self.probe_texture)
        glGenerateMipmap(GL_TEXTURE_CUBE_MAP)
        self.probe_ready=True
        self.probe_time=self.scene.time

    def invalidate(self):
        self.probe_time=None
        self.shadow_time=None

    def draw(self,eye,target,projection,width,height):
        self.resize(width,height)
        self.prepare()
        glDisable(GL_FRAMEBUFFER_SRGB)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)
        glDisable(GL_CULL_FACE)
        self._shadows()
        self._probe()
        view=Mat4.look_at(eye,target,Vec3(0,1,0))
        if self.reflections:
            reflected_eye=Vec3(eye.x,2*FLOOR_Y-eye.y,eye.z)
            reflected_target=Vec3(target.x,2*FLOOR_Y-target.y,target.z)
            reflected_view=Mat4.look_at(reflected_eye,reflected_target,Vec3(0,-1,0))
            self.reflection_vp=projection@reflected_view
            self.reflection.bind()
            glClearColor(.003,.005,.009,1)
            glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
            self._bind_surface(self.reflection_vp,reflected_eye,1)
            self._draw_opaque(reflection=True)
            self._draw_glass(reflected_view)
        self.msaa.bind()
        glClearColor(.008,.012,.020,1)
        glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
        self._bind_surface(projection@view,eye,0)
        self._draw_opaque()
        self._draw_glass(view)
        self.msaa.resolve(self.hdr)
        self._postprocess()

    def _fullscreen(self):
        glBindVertexArray(self.empty_vao)
        glDrawArrays(GL_TRIANGLES,0,3)
        glBindVertexArray(0)

    def _postprocess(self):
        glDisable(GL_DEPTH_TEST)
        glDepthMask(GL_FALSE)
        glDisable(GL_BLEND)
        glActiveTexture(GL_TEXTURE0)
        bloom_texture=self.black
        if self.bloom:
            self.blur_targets[0].bind()
            self.bright.use()
            self.bright['source']=0
            self.bright['texel']=(1/self.size[0],1/self.size[1])
            glBindTexture(GL_TEXTURE_2D,self.hdr.texture)
            self._fullscreen()
            self.blur.use()
            self.blur['source']=0
            for iteration in range(4):
                for source,dest,axis in ((0,1,(1,0)),(1,0,(0,1))):
                    self.blur_targets[dest].bind()
                    glBindTexture(GL_TEXTURE_2D,self.blur_targets[source].texture)
                    w,h=self.blur_targets[source].size
                    radius=1.8+iteration*.6
                    self.blur['step_uv']=(radius*axis[0]/w,radius*axis[1]/h)
                    self._fullscreen()
            bloom_texture=self.blur_targets[0].texture
        glBindFramebuffer(GL_FRAMEBUFFER,0)
        glViewport(0,0,*self.size)
        self.post.use()
        self.post['source']=0
        self.post['bloom_texture']=1
        self.post['exposure']=self.exposure
        self.post['bloom_strength']=.19 if self.bloom else 0.
        self.post['resolution']=self.size
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D,self.hdr.texture)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D,bloom_texture)
        self._fullscreen()
        glActiveTexture(GL_TEXTURE0)
        glDepthMask(GL_TRUE)

    def delete(self):
        for mesh in self.meshes.values():mesh.delete()
        self.glass_mesh.delete()
        for target in self.targets:target.delete()
        self.sign.delete()
        for texture in (self.shadow_texture,self.probe_texture,self.black_cube,self.black):
            glDeleteTextures(1,byref(texture))
        for fbo in (self.shadow_fbo,self.probe_fbo):glDeleteFramebuffers(1,byref(fbo))
        glDeleteRenderbuffers(1,byref(self.probe_depth))
        glDeleteVertexArrays(1,byref(self.empty_vao))
        for p in (self.surface,self.depth_program,self.bright,self.blur,self.post):p.delete()
