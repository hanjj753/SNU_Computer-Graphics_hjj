"""Geometry, containment, animation and buffer-cache checks; creates no GL window."""
from itertools import product
from math import isfinite
from pathlib import Path
from unittest.mock import patch
import pyglet
pyglet.options['shadow_window']=False

from pyglet.math import Vec4
import geometry
from great_hall import GreatHallScene,PALETTES,BANNER_FONTS
from scene_data import (MAX_LIGHTS,MAX_SHADOWS,ROOM_MIN,ROOM_MAX,FLOOR_Y,
                        GRYFFINDOR_CREST,SLYTHERIN_CREST,RAVENCLAW_CREST,HUFFLEPUFF_CREST,
                        HOUSE_CRESTS,HOUSE_LETTERING)


def verify_geometry(meshes):
    for name,mesh in meshes.items():
        assert len(mesh.vertices)%8==0 and len(mesh.indices)%3==0,name
        assert all(0<=i<len(mesh.vertices)//8 for i in mesh.indices),name
        volume=0.
        for a,b,c in zip(mesh.indices[::3],mesh.indices[1::3],mesh.indices[2::3]):
            p=[mesh.vertices[i*8:i*8+3] for i in (a,b,c)]
            u=[p[1][j]-p[0][j] for j in range(3)]
            v=[p[2][j]-p[0][j] for j in range(3)]
            cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
            if sum(x*x for x in cross)<1e-15:continue
            normal=[sum(mesh.vertices[i*8+3+j] for i in (a,b,c)) for j in range(3)]
            assert sum(cross[j]*normal[j] for j in range(3))>=-1e-11,(name,'inward normal')
            volume+=sum(p[0][j]*cross[j] for j in range(3))/6.
        if name not in ('quad','arch'):assert volume>0,(name,'inward closed surface',volume)
        print(f'{name}: indices, surface orientation and volume OK')


def verify_scene(meshes):
    bounds={name:list(product(*[(min(m.vertices[j::8]),max(m.vertices[j::8])) for j in range(3)]))
            for name,m in meshes.items()}
    scene=GreatHallScene()
    assert len(scene.floating)==32 and len(scene.candles)==14
    assert len(scene.books)==6
    names=[n for n in scene.static if n.material.surface==HOUSE_LETTERING]
    assert len(names)==4 and {n.material.pattern for n in names}=={0,1,2,3}
    assert all(n.material.emission==(0.,0.,0.) for n in names)
    for surface in HOUSE_CRESTS:
        assert sum(n.material.surface==surface for n in scene.static)==1
    assert next(n for n in scene.static if n.material.surface==GRYFFINDOR_CREST).model[12]<0
    assert next(n for n in scene.static if n.material.surface==SLYTHERIN_CREST).model[12]>0
    assert next(n for n in scene.static if n.material.surface==HUFFLEPUFF_CREST).model[12]<0
    assert next(n for n in scene.static if n.material.surface==RAVENCLAW_CREST).model[12]>0
    for node in scene.static:
        if node.material.surface in (*HOUSE_CRESTS,HOUSE_LETTERING):
            # The local +Z normal must be parallel to the side wall's X normal.
            normal=node.model@Vec4(0,0,1,0)
            assert abs(abs(normal.x)-1.)<1e-6 and abs(normal.z)<1e-6
    assert scene.shadow_count==8<=MAX_SHADOWS
    for palette in range(len(PALETTES)):
        scene.palette=palette
        for t in (0.,6.,17.,39.):
            scene.update(t)
            assert len(scene.lights)==52<=MAX_LIGHTS
            assert sum(n.mesh=='flame' for n in scene.nodes)==46
            assert sum(n.category=='glass' for n in scene.nodes)==2
            assert all(len(n.record())==28 for n in scene.nodes)
            assert all(isfinite(v) for n in scene.nodes for v in n.record())
            if palette==0:
                for node in scene.nodes:
                    if node.category in ('room','ceiling','floor'):continue
                    for corner in bounds[node.mesh]:
                        p=node.model@Vec4(*corner,1.)
                        assert all(ROOM_MIN[j]-.002<=p[j]<=ROOM_MAX[j]+.002 for j in range(3)),(
                            'Outside Cornell box',node.mesh,tuple(p))
                        assert p.y>=FLOOR_Y-.001,(node.mesh,'below floor',p.y)
    scene.update(0.)
    old_position=scene.lights[4].position
    old_power=scene.lights[4].power
    old_books=[n.model for n in scene.receivers]
    scene.update(6.)
    assert scene.lights[4].position!=old_position and scene.lights[4].power!=old_power
    assert all(a!=b.model for a,b in zip(old_books,scene.receivers))
    scene.local_lights=False
    scene.update(6.)
    assert not any(n.mesh=='flame' for n in scene.nodes)
    assert all(l.power==0 for l in scene.lights[4:50])
    assert all(l.power>0 for l in [*scene.lights[:4],*scene.lights[-2:]])
    for name in ('diffuse','nor_gl','rough'):
        assert (Path(__file__).parent/'assets'/'wood'/f'{name}.jpg').is_file()
    for house in ('gryffindor','slytherin','ravenclaw','hufflepuff'):
        path=Path(__file__).parent/'assets'/'crests'/f'{house}_crest.png'
        im=pyglet.image.load(str(path)).get_image_data()
        alpha=im.get_bytes('RGBA',im.width*4)[3::4]
        assert min(alpha)==0 and max(alpha)==255,(house,'PNG must have real transparency')
    for _,filename in BANNER_FONTS.values():
        lettering=pyglet.image.load(str(Path(__file__).parent/'assets'/'lettering'/filename)).get_image_data()
        alpha=lettering.get_bytes('RGBA',lettering.width*4)[3::4]
        assert min(alpha)==0 and max(alpha)==255,filename
        assert lettering.width==2048 and lettering.height==2048
    print('3 lighting profiles x 4 times: 46 candles, 52 lights, contained geometry, bundled maps OK')
    print('Candles animate, toggle OFF removes flames and retains ceiling/window fill')


def verify_instance_visibility(meshes):
    from renderer import Renderer

    class CpuMesh:
        def __init__(self,data):self.instance_count=0
        def upload(self,records):self.instance_count=len(records)//28

    renderer=Renderer.__new__(Renderer)
    renderer.scene=GreatHallScene()
    renderer.data=meshes
    renderer.meshes={}
    with patch('geometry.InstancedMesh',CpuMesh):
        for enabled in (True,False,True):
            renderer.scene.dressing_enabled=enabled
            renderer.scene.update(6.)
            renderer.prepare()
            count=sum(m.instance_count for m in renderer.meshes.values())+len(renderer.glass_nodes)
            assert count==len(renderer.scene.nodes)
            assert len(renderer.glass_nodes)==(2 if enabled else 0)
        renderer.scene.local_lights=False
        renderer.scene.update(6.)
        renderer.prepare()
        assert all(m.instance_count==0 for (mesh,_,_),m in renderer.meshes.items() if mesh=='flame')
        for enabled in (False,True):
            renderer.scene.receivers_enabled=enabled
            renderer.scene.update(6.)
            renderer.prepare()
            total=sum(m.instance_count for m in renderer.meshes.values())+len(renderer.glass_nodes)
            assert total==len(renderer.scene.nodes)
            if not enabled:
                assert all(m.instance_count==0 for (_,category,_),m in renderer.meshes.items()
                           if category=='receivers')
    print('Tableware ON/OFF/ON and candle OFF: cached instance counts match the scene')
    print('Four house crests parallel to side walls; floating books animate and toggle without stale instances')


if __name__=='__main__':
    meshes=geometry.mesh_library()
    verify_geometry(meshes)
    verify_scene(meshes)
    verify_instance_visibility(meshes)
