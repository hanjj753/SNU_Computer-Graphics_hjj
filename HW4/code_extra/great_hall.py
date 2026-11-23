"""The Great Hall: a candlelit banquet homage contained by a Cornell box.

All geometry is generated locally. The scene uses consistent furniture/tableware
dimensions, explicit Phong materials and photographed wood textures.
"""
from dataclasses import dataclass
from math import cos,sin,pi
import random

from pyglet.math import Vec3
from geometry import beam,transform
from scene_data import (Material,Node,Light,MAX_LIGHTS,FLOOR_Y,emissive,
                        GRYFFINDOR_CREST,SLYTHERIN_CREST,RAVENCLAW_CREST,HUFFLEPUFF_CREST,
                        HOUSE_CRESTS,HOUSE_LETTERING)

PALETTES=('THE FEAST','QUIET EVENING','AFTER HOURS')
WOOD=Material((.82,.78,.69),shininess=58.,surface=13)
DARK_WOOD=Material((.46,.42,.34),shininess=49.,surface=13)
SILVER=Material((.27,.27,.26),specular=(.69,.69,.66),shininess=86.)
PEWTER=Material((.21,.21,.20),specular=(.43,.44,.42),shininess=70.)
GOLD=Material((.27,.17,.062),specular=(.59,.39,.14),shininess=82.)
STONE=Material((.39,.385,.365),shininess=21.,surface=15)
WAX=Material((.72,.66,.50),shininess=46.,surface=18)
CERAMIC=Material((.68,.66,.58),shininess=98.)
LINEN=Material((.55,.49,.35),shininess=20.,surface=16)
IRON=Material((.016,.017,.016),specular=(.046,.047,.046),shininess=68.)
WICK=Material((.014,.009,.005),shininess=14.)
GLASS=Material((.52,.61,.61),shininess=116.,surface=4,alpha=.16)
BANNER_TOP=.95
BANNER_BOTTOM=-1.50
BANNER_HEIGHT=BANNER_TOP-BANNER_BOTTOM
BANNER_FONTS={
    'harry':('Harry P','house_names.png'),
    'cinzel':('Cinzel Decorative Bold','house_names_cinzel.png'),
}
DEFAULT_BANNER_FONT='cinzel'


@dataclass(frozen=True)
class Candle:
    position: tuple  # bottom of the wax
    height: float
    radius: float
    phase: float
    floating: bool=True


@dataclass(frozen=True)
class FloatingBook:
    position: tuple
    rotation: tuple  # pitch, yaw, roll, in radians
    opening: float   # each half's hinge angle: 0 is flat, pi/2 is closed
    phase: float
    cover: tuple


class GreatHallScene:
    name='THE GREAT HALL'
    subtitle='A candlelit banquet inside a Cornell box.'
    shadow_count=8
    probe_position=Vec3(0,1.24,-.28)
    probe_categories=('room','ceiling','hall','solid','emission','receivers')
    exposure=1.60
    camera_target=Vec3(0,1.53,-.25)

    def __init__(self):
        self.static=[]
        self.dressing=[]
        self.receivers=[]
        self.candles=[]
        self.palette=0
        self.local_lights=True
        self.dressing_enabled=True
        self.receivers_enabled=True
        self.banner_font=DEFAULT_BANNER_FONT
        self.time=0.
        self._room()
        self._windows()
        self._tables()
        self._table_settings()
        self._floating_books()
        self._floating_candles()
        self.nodes=[]
        self.lights=[]
        self.update(6.)

    @property
    def palette_name(self):return PALETTES[self.palette]

    @property
    def lettering_file(self):return BANNER_FONTS[self.banner_font][1]

    def add(self,mesh,model,material,category='solid',shadow=True,dressing=False):
        (self.dressing if dressing else self.static).append(Node(mesh,model,material,category,shadow))

    def box(self,p,size,material=WOOD,dressing=False):
        self.add('rounded_box',transform(p,size),material,dressing=dressing)

    def rod(self,a,b,r,material=IRON,dressing=False):
        self.add('cylinder',beam(a,b,r),material,dressing=dressing)

    def _room(self):
        self.add('quad',transform((0,FLOOR_Y,-.25),(3.3,3.2,1),-pi/2,(1,0,0)),
                 Material((.33,.34,.35),shininess=15.,surface=1),'floor',False)
        for x,color in ((-1.70,(.30,.042,.032)),(1.70,(.038,.185,.067))):
            self.add('box',transform((x,1.675,-.25),(.10,3.35,3.2)),
                     Material(color,shininess=19.,surface=3),'room',False)
        self.add('box',transform((0,1.675,-1.90),(3.5,3.35,.1)),STONE,'room',False)
        self.add('box',transform((0,3.40,-.25),(3.5,.10,3.2)),
                 Material((.40,.40,.37),shininess=15.,surface=3),'room',False)
        edge=Material((.49,.47,.42),shininess=32.)
        for x in (-1.71,1.71):
            self.add('box',transform((x,1.675,1.37),(.07,3.4,.075)),edge,'room',False)
        for y in (-.035,3.38):
            self.add('box',transform((0,y,1.37),(3.5,.075,.075)),edge,'room',False)
        self.add('box',transform((0,-.045,-.25),(3.5,.10,3.2)),edge,'room',False)
        self.add('box',transform((0,3.325,-.35),(.66,.012,.50)),
                 emissive((.98,.96,.88),1.6),'ceiling',False)
        # Corners and skirting ground the room without hiding its red/green walls.
        for x in (-1.56,1.56):
            self.box((x,1.65,-1.76),(.15,3.276,.15),STONE)
            self.box((x,.085,-.25),(.075,.145,3.12),STONE)
            self.box((x,3.16,-.25),(.13,.16,3.12),STONE)
        for x in (-1.0,0.,1.0):
            self.box((x,3.08,-1.79),(.14,.26,.12),STONE)
        # Two long house banners on each wall; all four planes stay wall-parallel.
        banners=(
            (-1,.63,(.24,.022,.028),GRYFFINDOR_CREST,GOLD),
            (-1,-.73,(.32,.215,.022),HUFFLEPUFF_CREST,GOLD),
            (1,.63,(.018,.105,.045),SLYTHERIN_CREST,SILVER),
            (1,-.73,(.016,.046,.15),RAVENCLAW_CREST,GOLD),
        )
        for side,z,color,surface,border in banners:
            root=transform((side*1.632,2.04,z),rotation=-side*pi/2,axis=(0,1,0))
            self.add('quad',root@transform((0,(BANNER_TOP+BANNER_BOTTOM)/2,0),(.78,BANNER_HEIGHT,1)),
                     Material(color,shininess=14.,surface=16),'hall',False)
            for x in (-.38,.38):
                self.add('cylinder',root@beam((x,BANNER_BOTTOM,.002),(x,BANNER_TOP,.002),.004),border)
            self.add('cylinder',root@beam((-.43,.98,0),(.43,.98,0),.009),IRON)
            for x in (-.34,.34):
                self.add('cylinder',root@beam((x,.98,-.014),(x,.98,.010),.008),IRON)
            # Keep the shield's proportions; the cloth, rather than the logo, is long.
            self.add('quad',root@transform((0,.48,.003),(.64,.78,1)),
                     Material((.94,.94,.94),shininess=19.,surface=surface),'hall',False)
            ink=(.94,.78,.47)
            if surface==SLYTHERIN_CREST:ink=(.94,.96,.91)
            if surface==HUFFLEPUFF_CREST:ink=(.018,.014,.009)
            self.add('quad',root@transform((0,-.78,.004),(.30,1.18,1)),
                     Material(ink,shininess=20.,surface=HOUSE_LETTERING,pattern=HOUSE_CRESTS.index(surface)),
                     'hall',False)
            for x in (-.27,.27):
                stripe_bottom=BANNER_BOTTOM+.13
                self.add('quad',root@transform((x,stripe_bottom/2,.002),(.018,-stripe_bottom,1)),border,'hall',False)
            self.add('cylinder',root@beam((-.38,BANNER_BOTTOM+.04,.002),(.38,BANNER_BOTTOM+.04,.002),.003),border)

    def _windows(self):
        for x in (-.91,0.,.91):
            self.add('arch',transform((x,1.96,-1.822),(.76,1.73,1)),
                     Material((.43,.40,.34),shininess=20.,surface=15),'hall',False)
            self.add('arch',transform((x,1.98,-1.806),(.61,1.53,1)),
                     Material((.014,.024,.039),shininess=90.,surface=20,emission=(.006,.010,.017)),'hall',False)
            for dx in (-.30,.30):
                self.rod((x+dx,1.20,-1.785),(x+dx,2.10,-1.785),.014,STONE)
            for side in (-1,1):
                points=[]
                for i in range(17):
                    t=i/16
                    points.append((x+side*.305*(1-t*t),2.102+.643*t,-1.783))
                for a,b in zip(points,points[1:]):self.rod(a,b,.017,STONE)
            for dx in (-.105,.105):self.rod((x+dx,1.22,-1.77),(x+dx,2.60,-1.77),.008,STONE)
            for y in (1.59,1.96,2.30):self.rod((x-.286,y,-1.766),(x+.286,y,-1.766),.007,STONE)
            self.box((x,1.17,-1.77),(.75,.055,.12),STONE)

    def _tables(self):
        for x in (-.71,.71):
            # Four separate planks expose end grain and small construction gaps.
            for i in range(4):
                self.box((x-.255+i*.17,.712,-.13),(.167,.067,2.04),WOOD)
            for z in (-.87,.61):
                for dx in (-.245,.245):
                    self.box((x+dx,.327,z),(.065,.63,.075),DARK_WOOD)
                self.box((x,.23,z),(.59,.065,.075),DARK_WOOD)
            for dx in (-.25,.25):self.box((x+dx,.63,-.13),(.047,.105,1.94),DARK_WOOD)
            self.rod((x,.24,-.87),(x,.24,.61),.018,IRON)
            for bx in (x-.45,x+.45):
                self.box((bx,.375,-.13),(.165,.046,2.08),WOOD)
                for z in (-.86,.60):
                    self.box((bx,.182,z),(.055,.34,.075),DARK_WOOD)
                self.box((bx,.24,-.13),(.035,.055,1.60),DARK_WOOD)
            # A narrow linen runner leaves most of the photographed oak visible.
            self.box((x,.748,-.13),(.105,.004,1.95),Material((.23,.043,.041),shininess=18.,surface=16),True)
            for z in (-.89,-.36,.17,.66):self._candlestick((x,.752,z),.16)
        # Head table, raised very slightly above the two long tables.
        for i in range(3):self.box((0,.813,-1.49+i*.12),(2.72,.060,.117),WOOD)
        for x in (-1.10,1.10):self.box((x,.402,-1.39),(.075,.78,.12),DARK_WOOD)
        for x in (-.78,0.,.78):
            self.box((x,.47,-1.69),(.34,.05,.27),DARK_WOOD)
            for dx in (-.125,.125):
                self.box((x+dx,.230,-1.69),(.035,.436,.035),DARK_WOOD)
                self.box((x+dx,.81,-1.77),(.035,.67,.035),DARK_WOOD)
            self.box((x,.98,-1.77),(.28,.12,.035),WOOD)
            for dx in (-.075,0,.075):self.box((x+dx,.79,-1.77),(.020,.31,.018),DARK_WOOD)
        for x in (-1.04,1.04):
            self.add('plate',transform((x,.85,-1.40),(.65,.65,.65)),PEWTER)
            self.rod((x,.855,-1.40),(x,1.05,-1.40),.010,GOLD)
            for dx in (-.09,0.,.09):
                self.rod((x,1.02,-1.40),(x+dx,1.07,-1.40),.007,GOLD)
                self._candlestick((x+dx,1.055,-1.40),.12,False)

    def _candlestick(self,p,height,stand=True):
        x,y,z=p
        if stand:
            self.add('plate',transform((x,y,z),(.38,.38,.38)),PEWTER)
            self.rod((x,y+.006,z),(x,y+.065,z),.009,PEWTER)
            self.add('plate',transform((x,y+.067,z),(.26,.26,.26)),PEWTER)
            y+=.076
        self.candles.append(Candle((x,y,z),height,.013,1.7*len(self.candles),False))

    def _table_settings(self):
        for table_x in (-.71,.71):
            for z in (-.70,-.10,.49):
                for side in (-1,1):
                    x=table_x+side*.205
                    self.add('plate',transform((x,.747,z)),CERAMIC,dressing=True)
                    self.add('torus',transform((x,.770,z),(.106,.106,.106),pi/2,(1,0,0)),GOLD,dressing=True)
                    self.add('goblet',transform((table_x+side*.126,.747,z-.172)),SILVER,dressing=True)
                    self.add('torus',transform((table_x+side*.126,.951,z-.172),(.048,.048,.048),pi/2,(1,0,0)),GOLD,dressing=True)
                    self.add('napkin',transform((table_x+side*.205,.749,z+.194),(.055,.058,.087)),LINEN,dressing=True)
                    # Fork and knife sit on the near/far sides of each place setting.
                    for offset in (-.128,.128):
                        self.box((x,.751,z+offset),(.082,.004,.009),SILVER,True)
                    for tooth in range(4):
                        self.rod((x+.036,.752,z-.141+tooth*.008),
                                 (x+.065,.752,z-.141+tooth*.008),.0018,SILVER,True)
                    self.box((x+.048,.752,z+.128),(.045,.002,.013),SILVER,True)
            self.add('pitcher',transform((table_x,.75,-.42)),PEWTER,dressing=True)
            self.add('torus',transform((table_x+.070,.88,-.42),(.047,.072,.047)),PEWTER,dressing=True)
            # Serving platters, bread, and apples give the tables a believable use.
            self.add('plate',transform((table_x,.75,.38),(1.05,1.,.70)),PEWTER,dressing=True)
            self.box((table_x,.79,.38),(.16,.066,.10),Material((.40,.20,.055),shininess=30.,surface=17),True)
            for i in range(3):
                self.add('sphere',transform((table_x+(i-1)*.041,.795,-.04),(.027,.028,.027)),
                         Material((.28,.035+.02*i,.016),shininess=82.,surface=17),dressing=True)
        for x in (-.61,.61):
            self.add('pitcher',transform((x,.85,-1.40)),GLASS,'glass',False,True)
            self.add('sphere',transform((x,.915,-1.40),(.051,.052,.051)),
                     Material((.085,.009,.017),shininess=108.),dressing=True)
        for x in (-.30,0.,.30):
            self.add('plate',transform((x,.85,-1.36),(.75,.75,.75)),CERAMIC,dressing=True)

    def _floating_candles(self):
        # Four principal candles follow the four ceiling samples in the light list.
        # These principal candles also receive downward-facing shadow maps.
        # Place the flames above and just in front of the open book pages.
        heroes=tuple((x+(-.17 if x<0 else .17),y+.13,z+.20)
                     for x,y,z in (book.position for book in self.books[:4]))
        self.floating=[]
        rng=random.Random(352)
        for i,p in enumerate(heroes):self.floating.append(Candle(p,.21+.016*i,.016,i*1.7))
        for row in range(7):
            for col in range(4):
                x=(-1.22,-.42,.42,1.22)[col]+rng.uniform(-.065,.065)
                z=-1.20+row*.325+rng.uniform(-.055,.055)
                y=1.88+rng.random()*.94
                if any((x-c.position[0])**2+(z-c.position[2])**2<.060 and abs(y-c.position[1])<.33
                       for c in self.floating):y=2.84
                self.floating.append(Candle((x,y,z),rng.uniform(.14,.255),rng.uniform(.011,.017),rng.uniform(0,6.28)))

    def _floating_books(self):
        self.books=[
            FloatingBook((-1.02,1.43,.62),(.16,-.80,-.48),.52,.2,(.16,.025,.018)),
            FloatingBook((1.00,1.72,.48),(1.10,1.16,.26),.97,1.9,(.025,.060,.085)),
            FloatingBook((-.54,2.20,-.66),(-.58,-.45,.67),1.28,3.7,(.095,.047,.020)),
            FloatingBook((.70,2.57,-.80),(.40,-1.18,-.68),.37,5.3,(.028,.080,.044)),
            FloatingBook((-.09,2.65,.36),(.30,.88,.24),.74,2.8,(.095,.018,.042)),
            FloatingBook((.20,1.76,-.17),(.84,-.72,-.26),.61,4.6,(.040,.048,.105)),
        ]

    def book_transform(self,book,time):
        """Small translations and rotations make the open books gently float."""
        x,y,z=book.position
        p=book.phase
        pitch,yaw,roll=book.rotation
        return (transform((x+.040*sin(time*.46+p),y+.035*sin(time*.67+p),
                           z+.025*cos(time*.52+p)))
                @transform(rotation=yaw+.12*sin(time*.27+p),axis=(0,1,0))
                @transform(rotation=pitch+.08*sin(time*.37+p),axis=(1,0,0))
                @transform(rotation=roll+.10*sin(time*.31+p),axis=(0,0,1)))

    def _book_nodes(self,time):
        """Existing boxes form the covers, page blocks and printed lines."""
        nodes=[]
        def add(mesh,model,material):
            nodes.append(Node(mesh,model,material,'receivers'))

        paper=Material((.82,.77,.65),shininess=22.)
        ink=Material((.12,.085,.050),shininess=15.)
        for book in self.books:
            root=self.book_transform(book,time)
            cover=Material(book.cover,shininess=28.,surface=16)
            add('cylinder',root@beam((0,-.016,-.143),(0,-.016,.143),.010),cover)
            for side in (-1,1):
                opening=book.opening+.055*sin(time*.75+book.phase+side*.55)
                wing=root@transform(rotation=side*opening,axis=(0,0,1))
                add('rounded_box',wing@transform((side*.098,-.020,0),(.205,.012,.292)),cover)
                add('rounded_box',wing@transform((side*.094,0,0),(.184,.025,.268)),paper)
                for row in range(6):
                    width=.105 if row in (0,5) else .135
                    add('box',wing@transform((side*.096,.0135,-.090+row*.035),
                                            (width,.001,.0025)),ink)
                # A simple gilt frame makes a turned-away cover read as a book.
                for z in (-.126,.126):
                    add('box',wing@transform((side*.098,-.027,z),(.17,.002,.0025)),GOLD)
                for x in (-.084,.084):
                    add('box',wing@transform((side*.098+x,-.027,0),(.0025,.002,.252)),GOLD)
        return nodes

    def _candle_nodes(self,candle,time):
        x,y,z=candle.position
        if candle.floating:
            y+=.009*sin(time*.65+candle.phase)
            x+=.003*sin(time*.38+candle.phase)
        h,r=candle.height,candle.radius
        result=[Node('wax',transform((x,y,z),(r,h,r)),WAX)]
        # Two irregular wax runs, attached to rather than floating off the body.
        for i,a in enumerate((candle.phase,candle.phase+2.2)):
            dr=r*.96
            top=(x+dr*cos(a),y+h*.94,z+dr*sin(a))
            bottom=(top[0],top[1]-h*(.18+.12*i),top[2])
            result.append(Node('cylinder',beam(top,bottom,r*.16),WAX))
            result.append(Node('sphere',transform(bottom,(r*.20,r*.26,r*.20)),WAX))
        result.append(Node('cylinder',beam((x,y+h*.957,z),(x+.001,y+h+.009,z),r*.105),WICK))
        flicker=1.+.045*sin(time*8.3+candle.phase)+.020*sin(time*17.1+candle.phase*2.3)
        flame_height=.048+.008*sin(candle.phase)
        if self.local_lights:
            flame_color=(1.,.79,.48)
            result.append(Node('flame',transform((x,y+h+.003,z),(.043,flame_height,.043),
                                                .045*sin(time*5.+candle.phase),(0,0,1)),
                               Material(flame_color,shininess=32.,surface=14,emission=(22.*flicker,15.*flicker,6.*flicker)),
                               'emission',False))
        light=Light((x,y+h+flame_height*.32,z),(1.,.83,.62),
                    .026*flicker*(1. if self.local_lights else 0.),.024)
        return result,light

    def update(self,time_seconds):
        self.time=time_seconds
        self.receivers=self._book_nodes(time_seconds)
        self.nodes=list(self.static)
        if self.dressing_enabled:self.nodes.extend(self.dressing)
        if self.receivers_enabled:self.nodes.extend(self.receivers)
        self.lights=[]
        ceiling_power=(.40,.52,.18)[self.palette]
        for x in (-.22,.22):
            for z in (-.52,-.18):self.lights.append(Light((x,3.29,z),(.94,.95,1.),ceiling_power,.17))
        # Keep the principal floating candles at indices 4..7 for shadow mapping.
        for candle in [*self.floating,*self.candles]:
            nodes,light=self._candle_nodes(candle,time_seconds)
            self.nodes.extend(nodes)
            self.lights.append(light)
        for x in (-.91,.91):
            self.lights.append(Light((x,2.10,-1.73),(.48,.63,1.),(.085,.10,.12)[self.palette],.22))
        if len(self.lights)>MAX_LIGHTS:raise RuntimeError('Scene exceeds light budget')

    def light_uniforms(self):
        positions=[(*l.position,l.radius) for l in self.lights]
        colors=[(*(c**2.2 for c in l.color),l.power) for l in self.lights]
        positions.extend([(0.,0.,0.,1.)]*(MAX_LIGHTS-len(positions)))
        colors.extend([(0.,0.,0.,0.)]*(MAX_LIGHTS-len(colors)))
        return positions,colors

    def metadata(self):
        return {'floating_candles':len(self.floating),'table_candles':len(self.candles),
                'banquet_tables':2,'head_table':1,'house_crests':4,
                'house_banner_height':BANNER_HEIGHT,'house_banner_bottom':2.04+BANNER_BOTTOM,
                'vertical_house_names':4,'banner_font':BANNER_FONTS[self.banner_font][0],
                'banner_name_rotation_degrees':90,
                'banner_lettering_center_height':1.26,'banner_lettering_height':1.18,
                'banner_letter_spacing_em':.14,
                'floating_books':len(self.books) if self.receivers_enabled else 0,
                'wood_textures':'Poly Haven wood_table_001 / CC0'}
