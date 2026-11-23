"""Instanced Phong lighting, shadow maps, reflections, contact shading and HDR."""
from __future__ import annotations

from collections import defaultdict
from ctypes import byref
from pyglet.gl import *
from pyglet.math import Mat4,Vec3,Vec4
from pyglet.graphics.shader import Shader,ShaderProgram

import geometry
import shaders
from scene_data import FLOOR_Y,MAX_SHADOWS,ROOM_MIN,ROOM_MAX
from textures import load_wood_set,load_house_crests,load_banner_lettering


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
            glGenTextures(1,byref(self.depth))
            glBindTexture(GL_TEXTURE_2D,self.depth)
            glTexImage2D(GL_TEXTURE_2D,0,GL_DEPTH_COMPONENT24,*self.size,0,GL_DEPTH_COMPONENT,GL_UNSIGNED_INT,None)
            for key in (GL_TEXTURE_MIN_FILTER,GL_TEXTURE_MAG_FILTER):glTexParameteri(GL_TEXTURE_2D,key,GL_NEAREST)
            for key in (GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T):glTexParameteri(GL_TEXTURE_2D,key,GL_CLAMP_TO_EDGE)
            glFramebufferTexture2D(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_TEXTURE_2D,self.depth,0)
        check_framebuffer('HDR target')
        glBindFramebuffer(GL_FRAMEBUFFER,0)

    def bind(self):
        glBindFramebuffer(GL_FRAMEBUFFER,self.fbo)
        glViewport(0,0,*self.size)

    def delete(self):
        glDeleteFramebuffers(1,byref(self.fbo))
        glDeleteTextures(1,byref(self.texture))
        if self.depth.value:glDeleteTextures(1,byref(self.depth))


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
        glBlitFramebuffer(0,0,w,h,0,0,w,h,GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT,GL_NEAREST)

    def delete(self):
        glDeleteFramebuffers(1,byref(self.fbo))
        glDeleteRenderbuffers(1,byref(self.color))
        glDeleteRenderbuffers(1,byref(self.depth))


class Renderer:
    def __init__(self,scene,shadow_size=1024):
        self.scene=scene
        self.surface=program(shaders.SURFACE_VERTEX,shaders.SURFACE_FRAGMENT)
        self.depth_program=program(shaders.DEPTH_VERTEX,shaders.DEPTH_FRAGMENT)
        self.post=program(shaders.FULLSCREEN_VERTEX,shaders.POST_FRAGMENT)
        self.ao_program=program(shaders.FULLSCREEN_VERTEX,shaders.AO_FRAGMENT)
        self.empty_vao=GLuint()
        glGenVertexArrays(1,byref(self.empty_vao))
        self.data=geometry.mesh_library()
        self.meshes={}
        self.glass_meshes={}
        self.targets=[]
        self.size=(0,0)
        self.shadows=True
        self.reflections=True
        self.glass=True
        self.bump=True
        self.ao=True
        self.exposure=getattr(scene,'exposure',1.3)
        self.reflection_vp=Mat4()
        self.probe_position=getattr(scene,'probe_position',Vec3(0,1.54,-.35))
        self.probe_time=None
        self.probe_ready=False
        self.shadow_time=None
        self.last_shadow_toggle=True
        self.shadow_size=shadow_size
        self.shadow_count=getattr(scene,'shadow_count',4)
        if not 1<=self.shadow_count<=MAX_SHADOWS:raise ValueError('Invalid shadow sample count')
        self.shadow_fbo=GLuint()
        self.shadow_texture=GLuint()
        glGenFramebuffers(1,byref(self.shadow_fbo))
        glGenTextures(1,byref(self.shadow_texture))
        glBindTexture(GL_TEXTURE_2D_ARRAY,self.shadow_texture)
        glTexImage3D(GL_TEXTURE_2D_ARRAY,0,GL_DEPTH_COMPONENT24,shadow_size,shadow_size,self.shadow_count,
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
        self.shadow_projection=Mat4.perspective_projection(1,z_near=.035,z_far=8.,fov=128.)
        self.shadow_vps=[]
        self._update_shadow_matrices()
        self._create_probe()
        self.wood_maps=load_wood_set()
        self.crest_maps,self.crest_uvs=load_house_crests()
        self.banner_lettering=load_banner_lettering(self.scene.lettering_file)
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
        self.probe_size=256
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
        self.ao_target=Target(max(1,w//2),max(1,h//2),False)
        self.targets=[self.hdr,self.msaa,self.reflection,self.ao_target]
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
        # Retire cached instances when an optional object group is hidden.
        for key,mesh in self.meshes.items():
            if key not in buckets:mesh.upload([])

    def _draw_opaque(self,probe=False,reflection=False,depth=False):
        for (_,category,casts_shadow),mesh in self.meshes.items():
            if depth and not casts_shadow:continue
            if probe and category not in self.scene.probe_categories:continue
            if reflection and category=='floor':continue
            mesh.draw()

    def _draw_glass(self,view):
        if not self.glass:return
        # Sort transparent vessels before drawing back and front surfaces.
        def depth(node):
            return (view@Vec4(node.model[12],node.model[13],node.model[14],1.)).z
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE)
        glEnable(GL_CULL_FACE)
        for node in sorted(self.glass_nodes,key=depth):
            if node.mesh not in self.glass_meshes:
                self.glass_meshes[node.mesh]=geometry.InstancedMesh(self.data[node.mesh])
            mesh=self.glass_meshes[node.mesh]
            mesh.upload(list(node.record()))
            # Hollow vessels need their rear-facing surfaces before the fronts.
            glCullFace(GL_FRONT)
            mesh.draw()
            glCullFace(GL_BACK)
            mesh.draw()
        glDisable(GL_CULL_FACE)
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
        p['shadow_vp']=self.shadow_vps+[Mat4()]*(MAX_SHADOWS-self.shadow_count)
        p['shadow_count']=self.shadow_count
        p['reflection_vp']=self.reflection_vp
        p['shadows_enabled']=self.shadows
        p['reflections_enabled']=self.reflections and self.probe_ready and pass_number!=2
        p['bump_enabled']=self.bump
        p['capture_pass']=pass_number
        p['floor_y']=FLOOR_Y
        p['probe_position']=tuple(self.probe_position)
        p['room_min']=ROOM_MIN
        p['room_max']=ROOM_MAX
        p['gryffindor_uv']=self.crest_uvs[0]
        p['slytherin_uv']=self.crest_uvs[1]
        p['ravenclaw_uv']=self.crest_uvs[2]
        p['hufflepuff_uv']=self.crest_uvs[3]
        for unit,target,texture,name in (
            (0,GL_TEXTURE_2D_ARRAY,self.shadow_texture,'shadow_map'),
            (1,GL_TEXTURE_CUBE_MAP,self.black_cube if pass_number==2 else self.probe_texture,'environment_map'),
            (2,GL_TEXTURE_2D,self.reflection.texture if pass_number==0 else self.black,'floor_reflection'),
            (3,GL_TEXTURE_2D,self.crest_maps[0].id,'gryffindor_crest'),
            (4,GL_TEXTURE_2D,self.wood_maps[0].id,'wood_diffuse'),
            (5,GL_TEXTURE_2D,self.wood_maps[1].id,'wood_normal'),
            (6,GL_TEXTURE_2D,self.wood_maps[2].id,'wood_gloss_source'),
            (7,GL_TEXTURE_2D,self.crest_maps[1].id,'slytherin_crest'),
            (8,GL_TEXTURE_2D,self.crest_maps[2].id,'ravenclaw_crest'),
            (9,GL_TEXTURE_2D,self.crest_maps[3].id,'hufflepuff_crest'),
            (10,GL_TEXTURE_2D,self.banner_lettering.id,'banner_lettering'),
        ):
            glActiveTexture(GL_TEXTURE0+unit)
            glBindTexture(target,texture)
            p[name]=unit
        glActiveTexture(GL_TEXTURE0)

    def _update_shadow_matrices(self):
        self.shadow_vps=[]
        for light in self.scene.lights[:self.shadow_count]:
            p=Vec3(*light.position)
            self.shadow_vps.append(self.shadow_projection@Mat4.look_at(p,Vec3(p.x,0,p.z),Vec3(0,0,-1)))

    def _shadows(self):
        if not self.shadows:return
        # Frozen views reuse depth maps. Animation updates all selected samples.
        if self.shadow_time==self.scene.time and self.last_shadow_toggle:return
        self._update_shadow_matrices()
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
        self._postprocess(projection)

    def _fullscreen(self):
        glBindVertexArray(self.empty_vao)
        glDrawArrays(GL_TRIANGLES,0,3)
        glBindVertexArray(0)

    def _postprocess(self,projection):
        glDisable(GL_DEPTH_TEST)
        glDepthMask(GL_FALSE)
        glDisable(GL_BLEND)
        glActiveTexture(GL_TEXTURE0)
        if self.ao:
            self.ao_target.bind()
            self.ao_program.use()
            self.ao_program['depth_texture']=0
            self.ao_program['projection']=projection
            self.ao_program['inverse_projection']=~projection
            glBindTexture(GL_TEXTURE_2D,self.hdr.depth)
            self._fullscreen()
        glBindFramebuffer(GL_FRAMEBUFFER,0)
        glViewport(0,0,*self.size)
        self.post.use()
        self.post['source']=0
        self.post['exposure']=self.exposure
        self.post['resolution']=self.size
        self.post['ao_texture']=1
        self.post['depth_texture']=2
        self.post['inverse_projection']=~projection
        self.post['ao_enabled']=self.ao
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D,self.hdr.texture)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D,self.ao_target.texture)
        glActiveTexture(GL_TEXTURE2)
        glBindTexture(GL_TEXTURE_2D,self.hdr.depth)
        self._fullscreen()
        glActiveTexture(GL_TEXTURE0)
        glDepthMask(GL_TRUE)

    def delete(self):
        for mesh in self.meshes.values():mesh.delete()
        for mesh in self.glass_meshes.values():mesh.delete()
        for target in self.targets:target.delete()
        for texture in self.wood_maps:texture.delete()
        for texture in self.crest_maps:texture.delete()
        self.banner_lettering.delete()
        for texture in (self.shadow_texture,self.probe_texture,self.black_cube,self.black):
            glDeleteTextures(1,byref(texture))
        for fbo in (self.shadow_fbo,self.probe_fbo):glDeleteFramebuffers(1,byref(fbo))
        glDeleteRenderbuffers(1,byref(self.probe_depth))
        glDeleteVertexArrays(1,byref(self.empty_vao))
        for p in (self.surface,self.depth_program,self.post,self.ao_program):p.delete()
