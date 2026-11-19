"""NIGHT ORBIT: a procedural miniature Ferris wheel inside a Cornell box."""
from __future__ import annotations

from dataclasses import dataclass
from math import cos, sin, pi

from pyglet.math import Mat4, Vec3, Vec4
from geometry import beam, transform

TAU = 2*pi
CENTER = Vec3(0,1.78,-.35)
RADIUS = 1.035
CABINS = 8
RIM_BULBS = 40  # per side, 80 visible bulbs in total
FLOOR_Y = .012
MAX_LIGHTS = 80
FAIRGROUND_LIGHTS = 74
SHADOW_LIGHTS = 4
ROOM_MIN = (-1.65,0,-1.85)
ROOM_MAX = (1.65,3.35,1.35)
PALETTES = (
    ("AURORA",((.025,.76,1.),(1.,.06,.32),(1.,.51,.08),(.2,1.,.62))),
    ("GOLDEN HOUR",((1.,.43,.075),(1.,.72,.28),(1.,.25,.08),(1.,.9,.57))),
    ("ELECTRIC BLUE",((.025,.35,1.),(.28,.12,1.),(.015,1.,.85),(.55,.72,1.))),
)


@dataclass(frozen=True)
class Material:
    color: tuple = (.6,.6,.6)
    metal: float = 0.
    roughness: float = .5
    surface: float = 0.  # 1 floor, 2 brushed, 3 plaster, 4 glass, 5..12 sign atlas, 13 wood
    alpha: float = 1.
    emission: tuple = (0.,0.,0.)


@dataclass
class Node:
    mesh: str
    model: Mat4
    material: Material
    category: str = "solid"
    casts_shadow: bool = True

    def record(self):
        m = self.material
        return (*self.model,*m.color,m.alpha,m.metal,m.roughness,m.surface,0.,*m.emission,0.)


@dataclass
class Light:
    position: tuple
    color: tuple
    power: float
    radius: float = .055


SILVER = Material((.64,.72,.8),.9,.33,2)
BRASS = Material((.79,.49,.17),.84,.33,2)
FRAME = Material((.055,.11,.15),.68,.32,2)
SPOKES = Material((.36,.45,.50),.75,.48,2)
BLACK = Material((.018,.028,.043),.5,.37)
CREAM = Material((.65,.68,.67),.15,.36)
GLASS = Material((.28,.65,.76),.0,.12,4,.17)


def glow(color, strength=8.):
    return Material(tuple(c*.5 for c in color),.08,.25,emission=tuple(c**2.2*strength for c in color))


class FerrisScene:
    def __init__(self):
        self.static: list[Node] = []
        self.wheel: list[Node] = []
        self.cabin: list[Node] = []
        self.palette = 0
        self.local_lights = True
        self.fairground_enabled = True
        self.ride_scale = .85
        self.ride_root = transform((.18,0,-.38),(self.ride_scale,)*3)
        self.angle = 0.
        self.time = 0.
        self._make_room()
        self._make_pedestal()
        self._make_supports()
        self._make_wheel()
        self._make_cabin()
        from fairground import Fairground
        self.fairground = Fairground()
        self.nodes, self.lights = [], []
        self.update(0.)

    @property
    def palette_name(self):
        return PALETTES[self.palette][0]

    def add(self, collection, mesh, model, material, category="solid", shadow=True):
        collection.append(Node(mesh,model,material,category,shadow))

    def _make_room(self):
        add = lambda mesh, model, material, category="room": self.add(
            self.static,mesh,model,material,category,False)
        add("quad",transform((0,FLOOR_Y,-.25),(3.3,3.2,1),-pi/2,(1,0,0)),
            Material((.32,.35,.40),.12,.24,1),"floor")
        add("box",transform((-1.70,1.675,-.25),(.10,3.35,3.2)),
            Material((.51,.026,.043),0,.83,3))
        add("box",transform((1.70,1.675,-.25),(.10,3.35,3.2)),
            Material((.026,.34,.095),0,.83,3))
        add("box",transform((0,1.675,-1.90),(3.5,3.35,.1)),
            Material((.57,.6,.65),0,.85,3))
        add("box",transform((0,3.40,-.25),(3.5,.10,3.2)),
            Material((.62,.64,.68),0,.8,3))
        add("box",transform((0,-.045,-.25),(3.5,.10,3.2)),CREAM)
        # Pale front reveals retain the unmistakable open Cornell-box silhouette.
        for x in (-1.72,1.72):
            add("box",transform((x,1.675,1.37),(.065,3.4,.065)),CREAM)
        add("box",transform((0,3.38,1.37),(3.5,.065,.065)),CREAM)
        add("box",transform((0,-.035,1.37),(3.5,.10,.065)),CREAM)
        # A conventional ceiling area emitter, sampled with four shadowed lights.
        add("box",transform((0,3.325,-.35),(.58,.012,.48)),
            glow((1.,.85,.66),2.),"ceiling")

    def _make_pedestal(self):
        self.add(self.static,"cylinder",transform((0,.11,-.35),(1.27,1.27,.19),pi/2,(1,0,0)),BLACK)
        self.add(self.static,"cylinder",transform((0,.21,-.35),(1.21,1.21,.025),pi/2,(1,0,0)),
                 Material((.14,.18,.23),.42,.32,2))
        for y in (.035,.185):
            self.add(self.static,"torus",transform((0,y,-.35),(1.26,1.26,1.26),pi/2,(1,0,0)),SILVER)

    def _make_supports(self):
        for z in (.055,-.755):
            for x in (-.67,.67):
                self.add(self.static,"cylinder",beam((x,.23,z),(0,1.78,z),.036),FRAME)
                self.add(self.static,"cylinder",beam((x,.23,z+.004),(0,1.78,z+.004),.010),SILVER)
                self.add(self.static,"box",transform((x,.245,z),(.20,.055,.20)),SILVER)
                for dx in (-.067,.067):
                    for dz in (-.067,.067):
                        self.add(self.static,"sphere",transform((x+dx,.28,z+dz),(.012,.007,.012)),BRASS)
            self.add(self.static,"cylinder",beam((-.48,.64,z),(.48,.64,z),.017),FRAME)
        self.add(self.static,"cylinder",beam((0,1.78,-.84),(0,1.78,.15),.061),SILVER)
        for z in (.13,-.83):
            self.add(self.static,"sphere",transform((0,1.78,z),(.105,.105,.035)),BRASS)

    def _make_wheel(self):
        for z in (-.205,.205):
            for radius in (RADIUS,RADIUS-.052):
                self.add(self.wheel,"torus",transform((0,0,z),(radius,radius,radius)),SILVER)
            for i in range(16):
                angle = TAU*i/16
                # Tension spokes: one radial and one offset attachment per sector.
                inner = (.12*cos(angle+.15),.12*sin(angle+.15),z*.4)
                outer = ((RADIUS-.02)*cos(angle),(RADIUS-.02)*sin(angle),z)
                self.add(self.wheel,"cylinder",beam(inner,outer,.008),SPOKES)
            self.add(self.wheel,"torus",transform((0,0,z*.4),(.14,.14,.14)),BRASS)
        for i in range(CABINS):
            a = TAU*i/CABINS
            x,y = RADIUS*cos(a),RADIUS*sin(a)
            self.add(self.wheel,"cylinder",beam((x,y,-.23),(x,y,.23),.018),BRASS)
        self.add(self.wheel,"cylinder",transform((0,0,0),(.10,.10,.43)),BRASS)

    def _make_cabin(self):
        # Local origin is the pivot. Every cabin is translated, never wheel-rotated.
        self.add(self.cabin,"cylinder",beam((0,.025,0),(0,-.073,0),.010),BRASS)
        self.add(self.cabin,"sphere",transform((0,-.094,0),(.176,.038,.145)),FRAME)
        self.add(self.cabin,"box",transform((0,-.117,0),(.31,.022,.245)),BLACK)
        self.add(self.cabin,"box",transform((0,-.331,0),(.292,.115,.23)),FRAME)
        self.add(self.cabin,"box",transform((0,-.27,0),(.24,.025,.16)),BRASS)
        self.add(self.cabin,"box",transform((0,-.323,.12),(.22,.035,.008)),CREAM)
        for x in (-.144,.144):
            for z in (-.112,.112):
                self.add(self.cabin,"cylinder",beam((x,-.12,z),(x,-.29,z),.007),BRASS)
        # Individual flat panes can be sorted back-to-front before alpha blending.
        for z in (-.116,.116):
            self.add(self.cabin,"quad",transform((0,-.205,z),(.272,.158,1)),GLASS,"glass",False)
        for x in (-.148,.148):
            self.add(self.cabin,"quad",transform((x,-.205,0),(.222,.158,1),pi/2,(0,1,0)),GLASS,"glass",False)
        self.add(self.cabin,"cylinder",beam((0,-.127,.119),(0,-.28,.119),.004),BRASS)

    def update(self, time_seconds: float):
        self.time = time_seconds
        self.angle = time_seconds*TAU/75.
        colors = PALETTES[self.palette][1]
        enabled = 1. if self.local_lights else 0.
        self.nodes = list(self.static)
        self.lights = []
        for x in (-.19,.19):
            for z in (-.50,-.20):
                self.lights.append(Light((x,3.29,z),(1.,.88,.74),.24,.16))
        world = Mat4.from_translation(CENTER) @ Mat4.from_rotation(self.angle,Vec3(0,0,1))
        for node in self.wheel:
            self.nodes.append(Node(node.mesh,world@node.model,node.material,node.category,node.casts_shadow))
        for side in (-1,1):
            for i in range(RIM_BULBS):
                a = TAU*i/RIM_BULBS
                local = Vec3(RADIUS*cos(a),RADIUS*sin(a),side*.225)
                position = Vec3(*(world@Vec4(*local,1.))[:3])
                color = colors[(i//5 + (side>0))%len(colors)]
                power = enabled*(.88+.12*sin(time_seconds*1.1+i*.32))
                self.nodes.append(Node("sphere",transform(position,(.018,.018,.018)),
                                       glow(color,10.*power),"emission",False))
                if i%2 == 0:
                    # One representative point light per adjacent pair of tiny bulbs.
                    self.lights.append(Light(tuple(position),color,.067*power,.070))
        for i in range(CABINS):
            a = TAU*i/CABINS+self.angle
            pivot = CENTER+Vec3(RADIUS*cos(a),RADIUS*sin(a),0)
            parent = Mat4.from_translation(pivot)
            for node in self.cabin:
                self.nodes.append(Node(node.mesh,parent@node.model,node.material,node.category,node.casts_shadow))
            color = colors[i%len(colors)]
            for z in (-.13,.13):
                self.nodes.append(Node("cylinder",parent@beam((-.155,-.119,z),(.155,-.119,z),.005),
                                       glow(color,5.*enabled),"emission",False))
            self.nodes.append(Node("sphere",transform(pivot+Vec3(0,-.15,0),(.023,.010,.023)),
                                   glow((1.,.68,.28),6.*enabled),"emission",False))
            self.lights.append(Light(tuple(pivot+Vec3(0,-.19,0)),(1.,.64,.27),.025*enabled,.07))
        for i in range(16):
            a = TAU*i/16
            position = (1.245*cos(a),.13,-.35+1.245*sin(a))
            color = colors[(i//4)%len(colors)]
            model = transform(position,(.11,.016,.012),-a,(0,1,0))
            self.nodes.append(Node("box",model,glow(color,4.5*enabled),"emission",False))
            if i%2 == 0:
                self.lights.append(Light(position,color,.060*enabled,.09))
        # A single uniform transform moves the whole ride, including its lights.
        # Squared scale on light power preserves illumination at scaled distances.
        self.nodes = [node if node.category in ('room','floor','ceiling') else Node(
            node.mesh,self.ride_root@node.model,node.material,node.category,node.casts_shadow)
            for node in self.nodes]
        for index,light in enumerate(self.lights[SHADOW_LIGHTS:],SHADOW_LIGHTS):
            p=self.ride_root@Vec4(*light.position,1.)
            self.lights[index]=Light(tuple(p[:3]),light.color,
                                    light.power*self.ride_scale**2,light.radius*self.ride_scale)
        if self.fairground_enabled:
            nodes,lights=self.fairground.build(colors,enabled)
            self.nodes.extend(nodes)
            self.lights.extend(lights)
        if len(self.lights)>MAX_LIGHTS:
            raise RuntimeError(f"Too many lights: {len(self.lights)} > {MAX_LIGHTS}")

    def light_uniforms(self):
        positions = [(*light.position,light.radius) for light in self.lights]
        colors = [(*(c**2.2 for c in light.color),light.power) for light in self.lights]
        positions += [(0.,0.,0.,1.)]*(MAX_LIGHTS-len(positions))
        colors += [(0.,0.,0.,0.)]*(MAX_LIGHTS-len(colors))
        return positions,colors
