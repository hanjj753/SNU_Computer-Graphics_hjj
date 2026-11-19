"""Geometry/animation invariants. Runs without creating an OpenGL window."""
from math import isfinite
from itertools import product
import pyglet
pyglet.options['shadow_window']=False

import geometry
from pyglet.math import Vec4
from scene import FerrisScene,MAX_LIGHTS,FAIRGROUND_LIGHTS,PALETTES,ROOM_MIN,ROOM_MAX


def verify_geometry():
    for name in ('quad','box','sphere','cylinder','torus'):
        mesh=getattr(geometry,name)()
        assert len(mesh.vertices)%8==0,name
        assert len(mesh.indices)%3==0,name
        assert all(0<=index<len(mesh.vertices)//8 for index in mesh.indices),name
        for a,b,c in zip(mesh.indices[::3],mesh.indices[1::3],mesh.indices[2::3]):
            p=[mesh.vertices[index*8:index*8+3] for index in (a,b,c)]
            u=[p[1][j]-p[0][j] for j in range(3)]
            v=[p[2][j]-p[0][j] for j in range(3)]
            cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
            if sum(x*x for x in cross)<1e-15:continue  # UV-sphere poles
            normal=[sum(mesh.vertices[index*8+3+j] for index in (a,b,c)) for j in range(3)]
            assert sum(cross[j]*normal[j] for j in range(3))>0,f'{name}: inward triangle'
        print(f'{name}: indices and outward triangle winding OK')


def verify_scene():
    scene=FerrisScene()
    bounds={}
    for name in ('quad','box','sphere','cylinder','torus'):
        vertices=getattr(geometry,name)().vertices
        bounds[name]=list(product(*[(min(vertices[j::8]),max(vertices[j::8])) for j in range(3)]))
    for palette in range(len(PALETTES)):
        scene.palette=palette
        for t in (0,6,18.75,37.5,56.25,74.9):
            scene.update(t)
            assert len(scene.lights)==FAIRGROUND_LIGHTS<=MAX_LIGHTS
            assert all(len(n.record())==28 for n in scene.nodes)
            assert all(isfinite(x) for n in scene.nodes for x in n.record())
            for light in scene.lights:
                assert light.radius>0 and light.power>=0
            panes=[n for n in scene.nodes if n.category=='glass']
            assert len(panes)==32
            # The world-space local-Y axes must remain vertical while rotating.
            assert all(abs(n.model[4])<1e-8 and abs(n.model[6])<1e-8 and n.model[5]>0 for n in panes)
            assert all(.22<n.model[13]<3.3 for n in panes)
            extra_panes=[n for n in scene.nodes if n.category=='fairglass']
            assert len(extra_panes)==6
            if palette==0:
                for node in scene.nodes:
                    if node.category in ('room','floor','ceiling'):continue
                    for corner in bounds[node.mesh]:
                        p=node.model@Vec4(*corner,1.)
                        assert all(ROOM_MIN[j]-.002<=p[j]<=ROOM_MAX[j]+.002 for j in range(3)),(
                            'Object outside Cornell box',node.mesh,node.category,tuple(p))
    scene.local_lights=False
    scene.update(0)
    assert all(light.power==0 for light in scene.lights[4:])
    assert all(light.power>0 for light in scene.lights[:4])
    scene.fairground_enabled=False
    scene.update(0)
    assert len(scene.lights)==60
    assert not any(n.category in ('fairground','fairglass') for n in scene.nodes)
    scene.fairground_enabled=True
    scene.update(0)
    assert len(scene.lights)==FAIRGROUND_LIGHTS
    print('3 palettes x 6 wheel positions: upright gondolas, finite transforms, light budget OK')
    print('Animated ride and all fairground props: conservative mesh bounds inside Cornell box')
    print('Local-light toggle: decorative lights OFF, ceiling area-light samples retained')


def verify_instance_visibility():
    """Regression: cached GPU batches must disappear when surroundings are hidden."""
    from unittest.mock import patch
    from renderer import Renderer

    class CpuMesh:
        def __init__(self,data):self.instance_count=0
        def upload(self,records):self.instance_count=len(records)//28

    renderer=Renderer.__new__(Renderer)
    renderer.scene=FerrisScene()
    renderer.data={name:None for name in ('quad','box','sphere','cylinder','torus')}
    renderer.meshes={}
    with patch('geometry.InstancedMesh',CpuMesh):
        for enabled in (True,False,True):
            renderer.scene.fairground_enabled=enabled
            renderer.scene.update(6.)
            renderer.prepare()
            total=sum(m.instance_count for m in renderer.meshes.values())+len(renderer.glass_nodes)
            assert total==len(renderer.scene.nodes)
            assert len(renderer.glass_nodes)==(38 if enabled else 32)
            if not enabled:
                assert all(m.instance_count==0 for (_,category,_),m in renderer.meshes.items()
                           if category=='fairground')
    print('Park visibility ON/OFF/ON: cached instances retired and restored correctly')


if __name__=='__main__':
    verify_geometry()
    verify_scene()
    verify_instance_visibility()
