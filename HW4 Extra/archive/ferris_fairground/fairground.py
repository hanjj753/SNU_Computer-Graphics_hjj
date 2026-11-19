"""Small fairground props, all modeled in code and kept inside the Cornell box.

The wheel has its own moving hierarchy. This module supplies its surroundings:
ticket kiosk, popcorn cart, benches, railings, visitors, lamps and festoons.
"""
from dataclasses import dataclass
from math import cos, sin, pi

from pyglet.math import Mat4,Vec3
from geometry import beam,transform


@dataclass
class Emitter:
    mesh: str
    model: Mat4
    color: tuple = (1.,.69,.32)
    strength: float = 5.
    palette_index: int | None = None


@dataclass
class PropLight:
    position: tuple
    power: float
    color: tuple = (1.,.69,.32)
    radius: float = .10
    palette_index: int | None = None


class Fairground:
    def __init__(self):
        # Local import avoids coupling scene-data declarations to prop assembly.
        from scene import Material,FRAME,BRASS,CREAM,BLACK,GLASS
        self.Material=Material
        self.frame,self.brass,self.cream,self.black=FRAME,BRASS,CREAM,BLACK
        self.glass=GLASS
        self.wood=Material((.29,.12,.045),.05,.61,13)
        self.ivory=Material((.74,.66,.46),.10,.44)
        self.red=Material((.38,.025,.042),.16,.40)
        self.teal=Material((.025,.20,.22),.24,.39)
        self.nodes=[]
        self.emitters=[]
        self.lights=[]
        self._marquee()
        self._festoons()
        self._ticket_kiosk()
        self._popcorn_cart()
        self._walkway_and_gate()
        self._benches_and_plants()
        self._lamps()
        self._visitors()

    def node(self,mesh,model,material,category='fairground',shadow=True):
        from scene import Node
        self.nodes.append(Node(mesh,model,material,category,shadow))

    def box(self,p,size,material,root=Mat4(),angle=0.,axis=(0,0,1)):
        self.node('box',root@transform(p,size,angle,axis),material)

    def rod(self,a,b,r,material,root=Mat4()):
        self.node('cylinder',root@beam(a,b,r),material)

    def ball(self,p,size,material,root=Mat4()):
        self.node('sphere',root@transform(p,size),material)

    def sign(self,p,size,index,root=Mat4()):
        self.node('quad',root@transform(p,(*size,1)),
                  self.Material((1.,1.,1.),.08,.43,5+index),shadow=False)

    def glow(self,mesh,model,color=(1.,.69,.32),strength=5.,palette=None):
        self.emitters.append(Emitter(mesh,model,color,strength,palette))

    def rope(self,points,r=.006,material=None):
        for a,b in zip(points,points[1:]):self.rod(a,b,r,material or self.black)

    @staticmethod
    def sagging_wire(a,b,sag,segments=20):
        return [(a[0]+(b[0]-a[0])*i/segments,
                 a[1]+(b[1]-a[1])*i/segments-4*sag*(i/segments)*(1-i/segments),
                 a[2]+(b[2]-a[2])*i/segments) for i in range(segments+1)]

    def _marquee(self):
        self.box((0,2.67,-1.785),(2.38,.48,.065),self.frame)
        self.box((0,2.67,-1.745),(2.30,.415,.025),self.brass)
        self.sign((0,2.67,-1.727),(2.24,.36),0)
        for y in (2.465,2.875):
            for i in range(11):
                x=-1.09+i*.218
                self.ball((x,y,-1.702),(.025,.025,.012),self.brass)
                self.glow('sphere',transform((x,y,-1.687),(.016,.016,.012)),
                          strength=6.,palette=i//3)
        for x in (-1.14,1.14):
            for y in (2.57,2.77):
                self.glow('sphere',transform((x,y,-1.687),(.016,.016,.012)),strength=6.,palette=2)
        for x,y,index in ((-.72,2.85,0),(.72,2.85,1),(-.72,2.49,2),(.72,2.49,3)):
            self.lights.append(PropLight((x,y,-1.60),.055,palette_index=index))

    def _festoons(self):
        for row,(z,height,sag) in enumerate(((.30,3.10,.25),(-.90,3.17,.19))):
            a,b=(-1.59,height,z),(1.59,height,z-.12)
            points=self.sagging_wire(a,b,sag,48)
            self.rope(points,.004)
            for i in range(14):
                t=(i+.5)/14
                x=a[0]+(b[0]-a[0])*t
                y=height-4*sag*t*(1-t)
                bz=a[2]+(b[2]-a[2])*t
                self.rod((x,y,bz),(x,y-.045,bz),.007,self.brass)
                self.glow('sphere',transform((x,y-.065,bz),(.022,.029,.022)),
                          strength=7.,palette=(i//2+row))
            for t,index in ((.27,row),(.73,row+2)):
                position=(a[0]+(b[0]-a[0])*t,height-4*sag*t*(1-t)-.08,a[2]+(b[2]-a[2])*t)
                self.lights.append(PropLight(position,.075,palette_index=index))

    def _ticket_kiosk(self):
        root=transform((-1.14,.015,.27))
        self.box((0,.045,0),(.63,.075,.57),self.wood,root)
        self.box((0,.275,0),(.54,.39,.48),self.red,root)
        for x in (-.22,-.11,0,.11,.22):
            self.box((x,.275,.246),(.018,.33,.014),self.ivory,root)
        self.box((0,.49,.16),(.62,.045,.30),self.ivory,root)
        self.box((0,.68,-.226),(.54,.43,.045),self.teal,root)
        self.box((0,.515,0),(.47,.035,.39),self.wood,root)
        for x in (-.25,.25):
            for z in (-.22,.22):
                self.rod((x,.48,z),(x,.92,z),.014,self.brass,root)
        for z in (-.23,.23):
            self.box((0,.905,z),(.56,.045,.026),self.brass,root)
        # One back pane and a side pane leave the service window open.
        self.node('quad',root@transform((-.255,.70,0),(.42,.32,1),pi/2,(0,1,0)),
                  self.glass,'fairglass',False)
        self.node('quad',root@transform((.255,.70,0),(.42,.32,1),pi/2,(0,1,0)),
                  self.glass,'fairglass',False)
        for i in range(8):
            x=-.30625+i*.0875
            material=self.ivory if i%2==0 else self.red
            self.box((x,.945,.02),(.0875,.032,.67),material,root,-.09,(1,0,0))
            self.box((x,.884,.35),(.0875,.075,.016),material,root)
        self.box((0,1.045,.10),(.64,.18,.035),self.brass,root)
        self.sign((0,1.045,.122),(.60,.15),1,root)
        # Interior ticket rolls and a cash register.
        self.box((.10,.565,.015),(.13,.085,.115),self.frame,root)
        self.box((.10,.613,.033),(.10,.012,.07),self.ivory,root)
        for x in (-.17,-.095):
            self.node('cylinder',root@transform((x,.56,.07),(.027,.027,.067),pi/2,(0,1,0)),self.ivory)
        for i in range(6):
            self.glow('sphere',root@transform((-.25+i*.1,.865,.365),(.013,.013,.013)),strength=5.)
        self.glow('box',root@transform((0,.84,-.11),(.28,.015,.18)),strength=1.8)
        self.lights.append(PropLight((-1.14,.76,.46),.105))

    def _popcorn_cart(self):
        root=transform((1.09,.015,.65),rotation=-.10,axis=(0,1,0))
        self.box((0,.32,0),(.49,.32,.36),self.red,root)
        self.box((0,.49,0),(.57,.032,.43),self.ivory,root)
        self.box((0,.175,0),(.48,.035,.35),self.brass,root)
        for x in (-.23,.23):
            self.rod((x,.14,0),(x,.90,0),.012,self.brass,root)
        for x in (-.27,.27):
            self.node('cylinder',root@transform((x,.13,0),(.092,.092,.032),pi/2,(0,1,0)),self.cream)
            self.node('cylinder',root@transform((x*1.07,.13,0),(.025,.025,.038),pi/2,(0,1,0)),self.brass)
        self.rod((.23,.42,-.10),(.42,.42,-.10),.012,self.brass,root)
        self.rod((.23,.42,.10),(.42,.42,.10),.012,self.brass,root)
        self.rod((.42,.42,-.10),(.42,.42,.10),.012,self.wood,root)
        self.box((0,.535,0),(.39,.04,.29),self.brass,root)
        for x in (-.19,.19):
            for z in (-.14,.14):self.rod((x,.55,z),(x,.80,z),.007,self.brass,root)
        self.box((0,.805,0),(.41,.025,.31),self.brass,root)
        for z in (-.145,.145):
            self.node('quad',root@transform((0,.674,z),(.37,.23,1)),self.glass,'fairglass',False)
        for x in (-.195,.195):
            self.node('quad',root@transform((x,.674,0),(.27,.23,1),pi/2,(0,1,0)),self.glass,'fairglass',False)
        # Popcorn kernels form a little mound behind the transparent front.
        for i in range(32):
            x=((i*17)%29/28-.5)*.31
            z=((i*11)%23/22-.5)*.20
            y=.575+.060*(1-min(1,abs(x)/.16))+(i%3)*.011
            kernel=self.Material((.76,.48+.05*(i%3),.13),0.,.64)
            self.ball((x,y,z),(.019,.016,.017),kernel,root)
        for i in range(8):
            x=-.284375+i*.08125
            material=self.ivory if i%2==0 else self.red
            self.box((x,.94,0),(.08125,.035,.53),material,root,-.07,(1,0,0))
            self.box((x,.89,.272),(.08125,.075,.018),material,root)
        self.box((0,.818,.303),(.52,.115,.018),self.frame,root)
        self.sign((0,.818,.318),(.49,.095),2,root)
        for i in range(6):
            self.glow('sphere',root@transform((-.25+i*.1,.913,.313),(.012,.012,.012)),strength=5.)
        self.glow('box',root@transform((0,.79,0),(.32,.012,.22)),strength=2.2)
        self.lights.append(PropLight((1.09,.745,.72),.075))

    def _walkway_and_gate(self):
        # Three steps lead from the open entrance to the ride's loading platform.
        for i,(z,y,w) in enumerate(((.62,.043,.54),(.51,.095,.51),(.40,.147,.48))):
            self.box((.18,y,z),(w,.055,.23),self.cream)
            self.box((.18,y+.028,z+.09),(w*.88,.003,.015),self.brass)
        # Inlaid path markers guide the eye inward without fencing off the center.
        for z in (.85,1.05,1.25):
            for x in (-.16,.16,.48):
                self.box((x,.0155,z),(.26,.004,.16),self.Material((.37,.37,.32),.2,.31))
        for x in (-.43,.68):
            self.node('cylinder',transform((x,.04,1.16),(.070,.070,.05),pi/2,(1,0,0)),self.frame)
            self.rod((x,.06,1.16),(x,.40,1.16),.016,self.brass)
            self.glow('sphere',transform((x,.425,1.16),(.028,.035,.028)),strength=5.)
            self.lights.append(PropLight((x,.43,1.16),.028,radius=.075))
        self.box((.80,.40,1.165),(.36,.135,.025),self.frame)
        self.sign((.80,.40,1.181),(.33,.11),3)
        for a,b in (((-.43,.32,1.16),(-.91,.36,.84)),((.68,.32,1.16),(.97,.36,.91))):
            self.rope(self.sagging_wire(a,b,.085,16),.009,self.teal)
        # Low side rails separate the ride from the rest area.
        for x,zs in ((-1.00,(-1.55,-1.04,-.53)),(1.35,(-1.48,-.95,-.42))):
            for z in zs:
                self.rod((x,.02,z),(x,.33,z),.012,self.cream)
                self.ball((x,.345,z),(.022,.022,.022),self.brass)
            for za,zb in zip(zs,zs[1:]):
                for y in (.15,.29):self.rod((x,y,za),(x,y,zb),.008,self.cream)
        # A tiny timetable next to the loading steps.
        self.rod((-.28,.02,.56),(-.28,.48,.56),.010,self.brass)
        self.box((-.28,.48,.56),(.29,.15,.024),self.frame)
        self.sign((-.28,.48,.576),(.26,.125),5)

    def _bench(self,position,angle,scale=1.):
        root=transform(position,(scale,)*3,rotation=angle,axis=(0,1,0))
        for x in (-.21,.21):
            for z in (-.07,.07):self.rod((x,.02,z),(x,.21,z),.012,self.frame,root)
            self.rod((x,.20,-.08),(x,.44,-.10),.011,self.frame,root)
        for z in (-.075,-.025,.025,.075):
            self.box((0,.22,z),(.61,.027,.038),self.wood,root)
        for y in (.32,.39):self.box((0,y,-.10),(.61,.045,.024),self.wood,root)
        for x in (-.26,.26):
            self.rod((x,.24,-.07),(x,.31,.075),.010,self.brass,root)

    def _benches_and_plants(self):
        self._bench((-1.22,.01,.96),.10,.83)
        self._bench((1.43,.01,-.64),-pi/2)
        for x,z in ((-1.49,1.23),(1.40,-1.48)):
            self.node('cylinder',transform((x,.10,z),(.105,.105,.17),pi/2,(1,0,0)),self.red)
            self.node('torus',transform((x,.19,z),(.107,.107,.107),pi/2,(1,0,0)),self.ivory)
            self.rod((x,.18,z),(x,.48,z),.014,self.wood)
            for dx,dy,dz in ((0,.45,0),(-.035,.48,.018),(.027,.54,-.015),(0,.60,0)):
                self.ball((x+dx,dy,z+dz),(.072,.095,.070),self.Material((.055,.19,.085),0,.85))
        # A bin at the rest-area edge adds scale and a lived-in detail.
        self.node('cylinder',transform((-1.44,.12,-.27),(.063,.063,.21),pi/2,(1,0,0)),self.teal)
        self.node('torus',transform((-1.44,.228,-.27),(.064,.064,.064),pi/2,(1,0,0)),self.brass)

    def _lamps(self):
        for x,z,height in ((-1.48,-.25,1.22),(1.46,-.96,1.35)):
            self.node('cylinder',transform((x,.035,z),(.070,.070,.05),pi/2,(1,0,0)),self.frame)
            self.rod((x,.06,z),(x,height,z),.015,self.frame)
            self.rod((x,height,z),(x*.93,height,z),.011,self.brass)
            self.ball((x,height-.025,z),(.04,.013,.04),self.brass)
            self.glow('sphere',transform((x*.93,height-.018,z),(.048,.065,.048)),strength=5.5)
            self.lights.append(PropLight((x*.93,height-.018,z),.095))

    def _person(self,position,color,scale=1.,rotation=0.):
        root=transform(position,(scale,scale,scale),rotation,(0,1,0))
        clothing=self.Material(color,0,.64)
        skin=self.Material((.54,.31,.18),0,.72)
        hair=self.Material((.035,.022,.020),0,.80)
        trousers=self.Material((.035,.065,.095),0,.78)
        for x in (-.027,.027):
            self.rod((x,.045,0),(x,.155,0),.015,trousers,root)
            self.box((x,.026,.014),(.035,.023,.059),self.frame,root)
        self.rod((0,.15,0),(0,.25,0),.043,clothing,root)
        self.ball((0,.25,0),(.047,.022,.036),clothing,root)
        self.rod((0,.255,0),(0,.283,0),.013,skin,root)
        self.ball((0,.313,0),(.033,.040,.032),skin,root)
        self.ball((0,.339,-.006),(.034,.019,.031),hair,root)
        for side in (-1,1):
            self.rod((side*.041,.242,0),(side*.065,.16,.014),.013,clothing,root)
            self.ball((side*.066,.153,.016),(.013,.016,.013),skin,root)

    def _visitors(self):
        self._person((-.64,.015,.94),(.55,.27,.055),rotation=-.5)
        self._person((-.43,.015,.91),(.055,.28,.38),.73,.1)
        self._person((.77,.015,.70),(.32,.065,.11),.95,-.8)

    def build(self,colors,enabled):
        from scene import Node,Light,glow
        nodes=list(self.nodes)
        for item in self.emitters:
            color=item.color if item.palette_index is None else colors[item.palette_index%len(colors)]
            nodes.append(Node(item.mesh,item.model,glow(color,item.strength*enabled),'emission',False))
        lights=[]
        for item in self.lights:
            color=item.color if item.palette_index is None else colors[item.palette_index%len(colors)]
            lights.append(Light(item.position,color,item.power*enabled,item.radius))
        return nodes,lights
