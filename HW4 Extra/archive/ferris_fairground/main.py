"""Run NIGHT ORBIT: python main.py. Requires pyglet 2.1.16 and OpenGL 3.3."""
from __future__ import annotations

import argparse
from ctypes import cast,c_char_p
from datetime import datetime
import json
from math import sin,cos
from pathlib import Path
import time

import pyglet

# Create exactly one explicit OpenGL window, including for automated captures.
pyglet.options['shadow_window']=False
pyglet.options['debug_gl']=False

from pyglet.gl import *
from pyglet.math import Mat4,Vec3
from pyglet.window import key,mouse

from scene import FerrisScene,PALETTES
from renderer import Renderer

ROOT=Path(__file__).resolve().parent


def arguments():
    parser=argparse.ArgumentParser(description='NIGHT ORBIT / Cornell-box Ferris wheel')
    parser.add_argument('--width',type=int,default=1280)
    parser.add_argument('--height',type=int,default=900)
    parser.add_argument('--capture',type=Path,help='Save a PNG + render metadata, then exit')
    parser.add_argument('--frames',type=int,default=5,help='Warm-up frames before a capture')
    parser.add_argument('--time',type=float,default=6.,help='Initial simulation time in seconds')
    parser.add_argument('--hidden',action='store_true',help='Create an invisible rendering window')
    parser.add_argument('--paused',action='store_true')
    parser.add_argument('--no-hud',action='store_true')
    parser.add_argument('--palette',type=int,choices=range(len(PALETTES)),default=0)
    parser.add_argument('--view',choices=('front','angle'),default='front')
    parser.add_argument('--disable',default='',help='Comma-separated: lights,bloom,reflections,shadows,glass,bump,fairground')
    parser.add_argument('--shadow-size',type=int,choices=(512,1024,2048),default=1024)
    result=parser.parse_args()
    if result.width<320 or result.height<240:parser.error('Minimum size is 320 x 240')
    if result.frames<1:parser.error('--frames must be at least 1')
    if result.hidden and not result.capture:parser.error('--hidden requires --capture')
    allowed={'lights','bloom','reflections','shadows','glass','bump','fairground'}
    result.disabled=set(filter(None,result.disable.split(',')))
    if result.disabled-allowed:parser.error(f'Unknown effects: {result.disabled-allowed}')
    return result


class FerrisWindow(pyglet.window.Window):
    def __init__(self,args):
        self.ready=False
        self.args=args
        config=Config(major_version=3,minor_version=3,depth_size=24,double_buffer=True)
        super().__init__(width=args.width,height=args.height,resizable=True,
                         caption='NIGHT ORBIT | HW4 Extra',config=config,
                         visible=not args.hidden,vsync=not bool(args.capture))
        self.set_minimum_size(640,480)
        self.scene=FerrisScene()
        self.scene.palette=args.palette
        self.scene.local_lights='lights' not in args.disabled
        self.scene.fairground_enabled='fairground' not in args.disabled
        self.sim_time=args.time
        self.scene.update(self.sim_time)
        self.renderer=Renderer(self.scene,args.shadow_size)
        for effect in args.disabled-{'lights','fairground'}:setattr(self.renderer,effect,False)
        self.paused=args.paused or bool(args.capture)
        self.speed=1.
        self.show_hud=not args.no_hud
        self.target=Vec3(0,1.60,-.35)
        self.reset_camera()
        if args.view=='angle':self.yaw,self.pitch=.40,.23
        self.frames=0
        self.render_seconds=[]
        self.fps=60.
        self.status=''
        self.status_until=0.
        self.pending_capture=None
        self.cleaned=False
        self._create_hud()
        self.ready=True
        pyglet.clock.schedule_interval(self.update,1/60.)
        info={name:cast(glGetString(enum),c_char_p).value.decode('utf-8','replace')
              for name,enum in (('renderer',GL_RENDERER),('version',GL_VERSION))}
        print(json.dumps({'application':'NIGHT ORBIT','lights':len(self.scene.lights),**info}),flush=True)
        self.gl_info=info

    def reset_camera(self):
        self.yaw=.10
        self.pitch=.115
        self.distance=7.40
        self.pan=Vec3(0,0,0)

    def _create_hud(self):
        self.hud_batch=pyglet.graphics.Batch()
        def label(text,size,color,bold=False):
            return pyglet.text.Label(text,font_name='Segoe UI',font_size=size,
                                     weight='bold' if bold else 'normal',
                                     color=(*color,255),batch=self.hud_batch)
        self.eyebrow=label('C O R N E L L   S T U D I E S     /     0 4',8,(142,169,175))
        self.title=label('NIGHT ORBIT',24,(239,231,213),True)
        self.subtitle=label('A little fairground.  After the lights go down.',10,(149,164,176))
        self.theme_label=label('',10,(113,218,215),True)
        self.motion_label=label('',9,(150,167,181))
        self.control1=label('SPACE  Pause     DRAG  Orbit     SCROLL  Zoom     R  Reset     C  Palette',9,(188,199,207))
        self.control2=label('',8,(119,144,158))
        self.toast=label('',10,(247,206,139))
        self._position_hud()

    def _position_hud(self):
        if not hasattr(self,'title'):return
        w,h=self.get_size()
        self.eyebrow.position=(30,h-30,0)
        self.title.position=(28,h-66,0)
        self.subtitle.position=(30,h-87,0)
        self.theme_label.anchor_x='right'
        self.motion_label.anchor_x='right'
        self.theme_label.position=(w-30,h-37,0)
        self.motion_label.position=(w-30,h-56,0)
        self.control1.position=(30,40,0)
        self.control2.position=(30,21,0)
        if w<1000:
            self.control1.text='SPACE Pause    Drag Orbit    Scroll Zoom    R Reset    C Palette'
            self.control2.text='1 Lights  2 Bloom  3 Reflections  4 Shadows  5 Glass  6 Bump  7 Park  H Hide  S Save'
        else:
            self.control1.text='SPACE  Pause     DRAG  Orbit     SCROLL  Zoom     R  Reset     C  Palette'
            self.control2.text='1  Lights    2  Bloom    3  Reflections    4  Shadows    5  Glass    6  Bump    7  Park    H  Hide    S  Save'
        self.toast.position=(30,67,0)

    def update(self,dt):
        if not self.paused:self.sim_time+=min(dt,.10)*self.speed
        self.scene.update(self.sim_time)
        self.fps=.94*self.fps+.06/max(dt,.001)

    def on_draw(self):
        if not self.ready:return
        start=time.perf_counter()
        w,h=self.get_framebuffer_size()
        target=self.target+self.pan
        offset=Vec3(sin(self.yaw)*cos(self.pitch),sin(self.pitch),cos(self.yaw)*cos(self.pitch))*self.distance
        eye=target+offset
        projection=Mat4.perspective_projection(max(1,w)/max(1,h),z_near=.06,z_far=35.,fov=40.)
        self.renderer.draw(eye,target,projection,w,h)
        if self.show_hud:
            self.theme_label.text=f'{self.scene.palette_name}   /   {len(self.scene.lights):02d} LIGHTS'
            self.motion_label.text=f'{"PAUSED" if self.paused else "IN MOTION"}     {self.speed:.2g}x     {self.fps:.0f} FPS'
            self.toast.text=self.status if time.monotonic()<self.status_until else ''
            glDisable(GL_DEPTH_TEST)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
            self.hud_batch.draw()
            glDisable(GL_BLEND)
        self.render_seconds.append(time.perf_counter()-start)
        self.frames+=1
        capture=self.pending_capture
        if self.args.capture and self.frames>=self.args.frames:capture=self.args.capture
        if capture:
            self.save_capture(capture,eye,target)
            self.pending_capture=None
            if self.args.capture:
                self.args.capture=None
                pyglet.clock.schedule_once(self._finish_capture,0)

    def _finish_capture(self,dt):
        self.close()
        pyglet.app.exit()

    def save_capture(self,path,eye,target):
        path=Path(path).resolve()
        path.parent.mkdir(parents=True,exist_ok=True)
        glFinish()
        pyglet.image.get_buffer_manager().get_color_buffer().save(str(path))
        samples=self.render_seconds[-max(1,min(60,len(self.render_seconds))):]
        metadata={
            'scene':'NIGHT ORBIT','palette':self.scene.palette_name,
            'simulation_time':self.sim_time,'size':self.get_framebuffer_size(),
            'visible_rim_bulbs':80,'gondolas':8,'actual_point_lights':len(self.scene.lights),
            'glass_panes':len(self.renderer.glass_nodes),
            'fairground_props':self.scene.fairground_enabled,
            'area_light_shadow_samples':4,'shadow_map_size':self.renderer.shadow_size,
            'instances':len(self.scene.nodes),'triangles':sum(
                len(self.renderer.data[n.mesh].indices)//3 for n in self.scene.nodes),
            'camera_eye':list(eye),'camera_target':list(target),
            'effects':{'lights':self.scene.local_lights,'fairground':self.scene.fairground_enabled,
                       **{name:getattr(self.renderer,name)
                          for name in ('bloom','reflections','shadows','glass','bump')}},
            'exposure':self.renderer.exposure,
            'cpu_submission_ms':1000*sum(samples)/len(samples),
            'opengl':self.gl_info,'gl_error':int(glGetError()),
        }
        if metadata['gl_error']:
            raise RuntimeError(f"OpenGL error after render: 0x{metadata['gl_error']:x}")
        path.with_suffix('.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        print(f'SAVED {path}',flush=True)
        self.notify(f'Saved: {path.name}')

    def notify(self,text):
        self.status=text
        self.status_until=time.monotonic()+3.

    def on_resize(self,width,height):
        super().on_resize(width,height)
        self._position_hud()

    def on_mouse_drag(self,x,y,dx,dy,buttons,modifiers):
        if buttons&mouse.RIGHT or buttons&mouse.MIDDLE or modifiers&key.MOD_SHIFT:
            self.pan+=Vec3(dx*.003,dy*.003,0)
        elif buttons&mouse.LEFT:
            self.yaw=max(-.68,min(.68,self.yaw-dx*.005))
            self.pitch=max(-.06,min(.48,self.pitch+dy*.004))

    def on_mouse_scroll(self,x,y,scroll_x,scroll_y):
        self.distance=max(4.8,min(12.,self.distance*(.92**scroll_y)))

    def on_key_press(self,symbol,modifiers):
        toggles={key._2:'bloom',key._3:'reflections',key._4:'shadows',key._5:'glass',key._6:'bump'}
        if symbol in (key.ESCAPE,key.Q):self.close()
        elif symbol==key.SPACE:self.paused=not self.paused
        elif symbol==key.R:self.reset_camera()
        elif symbol==key.F:self.yaw,self.pitch=0.,.10
        elif symbol==key.V:self.yaw,self.pitch=.40,.23
        elif symbol==key.H:self.show_hud=not self.show_hud
        elif symbol==key.C:
            self.scene.palette=(self.scene.palette+1)%len(PALETTES)
            self.scene.update(self.sim_time)
            self.renderer.invalidate()
            self.notify(self.scene.palette_name)
        elif symbol==key._1:
            self.scene.local_lights=not self.scene.local_lights
            self.scene.update(self.sim_time)
            self.renderer.invalidate()
            self.notify('Local lights '+('ON' if self.scene.local_lights else 'OFF'))
        elif symbol==key._7:
            self.scene.fairground_enabled=not self.scene.fairground_enabled
            self.scene.update(self.sim_time)
            self.renderer.invalidate()
            self.notify('Park surroundings '+('ON' if self.scene.fairground_enabled else 'OFF'))
        elif symbol in toggles:
            effect=toggles[symbol]
            setattr(self.renderer,effect,not getattr(self.renderer,effect))
            self.renderer.invalidate()
            self.notify(effect.capitalize()+' '+('ON' if getattr(self.renderer,effect) else 'OFF'))
        elif symbol in (key.PLUS,key.EQUAL,key.NUM_ADD):self.renderer.exposure=min(4.,self.renderer.exposure*1.12)
        elif symbol in (key.MINUS,key.NUM_SUBTRACT):self.renderer.exposure=max(.15,self.renderer.exposure/1.12)
        elif symbol==key.BRACKETLEFT:self.speed=max(.125,self.speed*.5)
        elif symbol==key.BRACKETRIGHT:self.speed=min(8.,self.speed*2.)
        elif symbol==key.S:
            self.pending_capture=ROOT/'captures'/f'orbit_{datetime.now():%Y%m%d_%H%M%S}.png'

    def close(self):
        pyglet.clock.unschedule(self.update)
        if getattr(self,'ready',False) and not self.cleaned:
            self.renderer.delete()
            self.cleaned=True
        super().close()


def main():
    args=arguments()
    window=FerrisWindow(args)
    pyglet.app.run(interval=1/60.)


if __name__=='__main__':main()
