"""Shared scene records. Surface colors are linear; light colors convert on upload."""
from dataclasses import dataclass
from pyglet.math import Mat4

MAX_LIGHTS=80
MAX_SHADOWS=8
FLOOR_Y=.012
ROOM_MIN=(-1.65,0,-1.85)
ROOM_MAX=(1.65,3.35,1.35)
GRYFFINDOR_CREST=22
SLYTHERIN_CREST=23
RAVENCLAW_CREST=24
HUFFLEPUFF_CREST=25
HOUSE_CRESTS=(GRYFFINDOR_CREST,SLYTHERIN_CREST,RAVENCLAW_CREST,HUFFLEPUFF_CREST)
HOUSE_LETTERING=26


@dataclass(frozen=True)
class Material:
    diffuse: tuple=(.6,.6,.6)
    specular: tuple=(.08,.08,.08)
    shininess: float=32.
    surface: float=0.
    alpha: float=1.
    emission: tuple=(0.,0.,0.)
    pattern: float=1.


@dataclass
class Node:
    mesh: str
    model: Mat4
    material: Material
    category: str='solid'
    casts_shadow: bool=True

    def record(self):
        m=self.material
        return (*self.model,*m.diffuse,m.alpha,*m.specular,m.shininess,
                *m.emission,m.surface,m.pattern,0.,0.,0.)


@dataclass
class Light:
    position: tuple
    color: tuple
    power: float
    radius: float=.035


def emissive(color,strength):
    return Material(color,specular=(0.,0.,0.),shininess=16.,
                    emission=tuple(c**2.2*strength for c in color))
