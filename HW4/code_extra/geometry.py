"""Procedural meshes and OpenGL instancing. No downloaded models are used."""
from __future__ import annotations

from array import array
from ctypes import byref, c_void_p, sizeof
from dataclasses import dataclass
from math import cos, sin, pi, sqrt

from pyglet.gl import *
from pyglet.math import Mat4, Vec3


@dataclass
class MeshData:
    vertices: list[float]  # position (3), normal (3), uv (2)
    indices: list[int]


def quad() -> MeshData:
    return MeshData([
        -.5, -.5, 0, 0, 0, 1, 0, 0,
        .5, -.5, 0, 0, 0, 1, 1, 0,
        .5, .5, 0, 0, 0, 1, 1, 1,
        -.5, .5, 0, 0, 0, 1, 0, 1,
    ], [0, 1, 2, 0, 2, 3])


def box() -> MeshData:
    vertices, indices = [], []
    faces = [
        ((0, 0, 1), ((-.5,-.5,.5),(.5,-.5,.5),(.5,.5,.5),(-.5,.5,.5))),
        ((0, 0,-1), ((.5,-.5,-.5),(-.5,-.5,-.5),(-.5,.5,-.5),(.5,.5,-.5))),
        ((1, 0, 0), ((.5,-.5,.5),(.5,-.5,-.5),(.5,.5,-.5),(.5,.5,.5))),
        ((-1,0, 0), ((-.5,-.5,-.5),(-.5,-.5,.5),(-.5,.5,.5),(-.5,.5,-.5))),
        ((0, 1, 0), ((-.5,.5,.5),(.5,.5,.5),(.5,.5,-.5),(-.5,.5,-.5))),
        ((0,-1, 0), ((-.5,-.5,-.5),(.5,-.5,-.5),(.5,-.5,.5),(-.5,-.5,.5))),
    ]
    for normal, points in faces:
        start = len(vertices) // 8
        for point, uv in zip(points, ((0,0),(1,0),(1,1),(0,1))):
            vertices.extend((*point, *normal, *uv))
        indices.extend(start + i for i in (0,1,2,0,2,3))
    return MeshData(vertices, indices)


def sphere(slices: int = 16, stacks: int = 10) -> MeshData:
    vertices, indices = [], []
    for j in range(stacks + 1):
        v = j / stacks
        latitude = pi * v
        for i in range(slices + 1):
            u = i / slices
            longitude = 2 * pi * u
            n = (sin(latitude)*cos(longitude), cos(latitude), sin(latitude)*sin(longitude))
            vertices.extend((*n, *n, u, v))
    for j in range(stacks):
        for i in range(slices):
            a, b = j*(slices+1)+i, (j+1)*(slices+1)+i
            indices.extend((a,a+1,b,a+1,b+1,b))
    return MeshData(vertices, indices)


def cylinder(sides: int = 24) -> MeshData:
    """Radius one, length one, local Z axis."""
    vertices, indices = [], []
    for i in range(sides + 1):
        u = i / sides
        x, y = cos(2*pi*u), sin(2*pi*u)
        for z, v in ((-.5,0),(.5,1)):
            vertices.extend((x,y,z,x,y,0,u,v))
    for i in range(sides):
        a = 2*i
        indices.extend((a,a+2,a+1,a+1,a+2,a+3))
    for z, sign in ((-.5,-1),(.5,1)):
        center = len(vertices)//8
        vertices.extend((0,0,z,0,0,sign,.5,.5))
        for i in range(sides + 1):
            x, y = cos(2*pi*i/sides), sin(2*pi*i/sides)
            vertices.extend((x,y,z,0,0,sign,.5+.5*x,.5+.5*y))
        for i in range(sides):
            tri = (center,center+i+1,center+i+2)
            indices.extend(tri if sign > 0 else reversed(tri))
    return MeshData(vertices, indices)


def torus(segments: int = 128, sides: int = 8, tube: float = .015) -> MeshData:
    """Major radius one, in the XY plane."""
    vertices, indices = [], []
    for i in range(segments + 1):
        a = 2*pi*i/segments
        for j in range(sides + 1):
            b = 2*pi*j/sides
            normal = (cos(a)*cos(b),sin(a)*cos(b),sin(b))
            point = ((1+tube*cos(b))*cos(a),(1+tube*cos(b))*sin(a),tube*sin(b))
            vertices.extend((*point,*normal,i/segments,j/sides))
    for i in range(segments):
        for j in range(sides):
            a, b = i*(sides+1)+j, (i+1)*(sides+1)+j
            indices.extend((a,b,a+1,a+1,b,b+1))
    return MeshData(vertices,indices)


def rounded_box(radius=.055,steps=4) -> MeshData:
    """A unit box with actual rounded edges, not just interpolated face normals."""
    coordinates=[-.5+radius*i/steps for i in range(steps+1)]
    coordinates += [.5-radius+radius*i/steps for i in range(steps+1)]
    vertices,indices=[],[]
    for axis,sign in ((0,1),(0,-1),(1,1),(1,-1),(2,1),(2,-1)):
        axes=[i for i in range(3) if i!=axis]
        start=len(vertices)//8
        for v in coordinates:
            for u in coordinates:
                p=[0.,0.,0.]
                p[axis]=sign*.5
                p[axes[0]],p[axes[1]]=u,v
                q=[max(-.5+radius,min(.5-radius,x)) for x in p]
                d=[p[i]-q[i] for i in range(3)]
                length=sqrt(sum(x*x for x in d))
                n=[x/length for x in d]
                point=[q[i]+radius*n[i] for i in range(3)]
                vertices.extend((*point,*n,u+.5,v+.5))
        count=len(coordinates)
        for j in range(count-1):
            for i in range(count-1):
                a=start+j*count+i
                p0=vertices[a*8:a*8+3]
                p1=vertices[(a+1)*8:(a+1)*8+3]
                p2=vertices[(a+count)*8:(a+count)*8+3]
                u=[p1[k]-p0[k] for k in range(3)]
                v=[p2[k]-p0[k] for k in range(3)]
                cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                normal=vertices[a*8+3:a*8+6]
                forward=sum(cross[k]*normal[k] for k in range(3))>0
                ids=(a,a+1,a+count,a+1,a+count+1,a+count)
                if not forward:ids=(a,a+count,a+1,a+1,a+count,a+count+1)
                indices.extend(ids)
    return MeshData(vertices,indices)


def lathe(profile,sides=64) -> MeshData:
    """Revolve a radius/Y cross-section. Reversed inner profiles create real bowls."""
    vertices,indices=[],[]
    low=min(p[1] for p in profile)
    span=max(p[1] for p in profile)-low or 1.
    for j,(radius,y) in enumerate(profile):
        previous=profile[max(0,j-1)]
        following=profile[min(len(profile)-1,j+1)]
        dr,dy=following[0]-previous[0],following[1]-previous[1]
        length=sqrt(dr*dr+dy*dy) or 1.
        for i in range(sides+1):
            a=2*pi*i/sides
            vertices.extend((radius*cos(a),y,radius*sin(a),
                             dy*cos(a)/length,-dr/length,dy*sin(a)/length,i/sides,(y-low)/span))
    for j in range(len(profile)-1):
        for i in range(sides):
            a=j*(sides+1)+i
            b=a+sides+1
            indices.extend((a,b,a+1,a+1,b,b+1))
    return MeshData(vertices,indices)


def goblet():
    return lathe(((0,0),(.036,0),(.044,.003),(.045,.007),(.039,.012),(.018,.017),
                  (.008,.024),(.005,.035),(.005,.096),(.010,.109),(.023,.116),
                  (.035,.132),(.044,.158),(.049,.193),(.049,.204),(.046,.207),
                  (.044,.199),(.040,.159),(.030,.134),(.018,.124),(0,.121)))


def plate():
    return lathe(((0,0),(.071,0),(.090,.002),(.104,.009),(.112,.018),(.112,.022),
                  (.108,.024),(.102,.019),(.089,.010),(.072,.007),(0,.007)))


def pitcher():
    return lathe(((0,0),(.050,0),(.060,.007),(.066,.025),(.068,.075),(.060,.145),
                  (.043,.205),(.040,.242),(.047,.251),(.045,.258),(.039,.254),
                  (.034,.241),(.037,.206),(.054,.142),(.061,.075),(.057,.027),(0,.016)))


def wax():
    return lathe(((0,0),(.89,0),(1.,.02),(1.,.92),(.97,.985),(.80,1.),
                  (.55,.965),(0,.96)),40)


def flame():
    return lathe(((0,0),(.19,.025),(.32,.13),(.33,.25),(.25,.51),(.15,.72),(.055,.91),(0,1.)),32)


def arch():
    # A pointed, rather than semicircular, window silhouette.
    points=[(-.5,-.5),(.5,-.5),(.5,.08)]
    for i in range(1,17):
        t=i/16
        points.append((.5*(1-t*t),.08+.42*t))
    for i in range(1,17):
        t=1-i/16
        points.append((-.5*(1-t*t),.08+.42*t))
    vertices=[0,0,0,0,0,1,.5,.5]
    for x,y in points:vertices.extend((x,y,0,0,0,1,x+.5,y+.5))
    indices=[]
    for i in range(len(points)):indices.extend((0,i+1,(i+1)%len(points)+1))
    return MeshData(vertices,indices)


def napkin():
    points=((-1,0,-.5),(1,0,-.5),(0,.50,.25),(-1,0,.5),(1,0,.5))
    triangles=((0,1,2),(1,4,2),(4,3,2),(3,0,2),(0,3,4),(0,4,1))
    vertices,indices=[],[]
    for tri in triangles:
        tri=tri[::-1]
        a,b,c=[Vec3(*points[i]) for i in tri]
        n=(b-a).cross(c-a).normalize()
        start=len(vertices)//8
        for p in (a,b,c):vertices.extend((*p,*n,p.x*.5+.5,p.z+.5))
        indices.extend((start,start+1,start+2))
    return MeshData(vertices,indices)


def mesh_library():
    return {name:globals()[name]() for name in (
        'quad','box','rounded_box','sphere','cylinder','torus','goblet','plate','pitcher','wax','flame','arch','napkin')}


def transform(position=(0,0,0), scale=(1,1,1), rotation=0., axis=(0,0,1)) -> Mat4:
    return (Mat4.from_translation(Vec3(*position))
            @ Mat4.from_rotation(rotation,Vec3(*axis))
            @ Mat4.from_scale(Vec3(*scale)))


def beam(a, b, radius: float) -> Mat4:
    a, b = Vec3(*a), Vec3(*b)
    direction = b-a
    length = direction.length()
    if length < 1e-8:
        raise ValueError("A beam must have distinct endpoints")
    z = direction/length
    reference = Vec3(1,0,0) if abs(z.y) > .95 else Vec3(0,1,0)
    x = z.cross(reference).normalize()*radius
    y = z.cross(x).normalize()*radius
    mid = (a+b)*.5
    return Mat4(*x,0,*y,0,*(z*length),0,*mid,1)


class InstancedMesh:
    """One static mesh + one streamed buffer of model/material records.

    Explicit attribute locations are shared by the depth and surface shaders.
    This reduces hundreds of small bulbs/struts to a few draw calls per pass.
    """
    FLOATS = 32

    def __init__(self, data: MeshData):
        self.vao, self.vbo, self.ebo, self.instances = GLuint(), GLuint(), GLuint(), GLuint()
        glGenVertexArrays(1,byref(self.vao))
        glGenBuffers(1,byref(self.vbo))
        glGenBuffers(1,byref(self.ebo))
        glGenBuffers(1,byref(self.instances))
        self.count = len(data.indices)
        self.triangles = self.count//3
        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER,self.vbo)
        v = (GLfloat*len(data.vertices))(*data.vertices)
        glBufferData(GL_ARRAY_BUFFER,sizeof(v),v,GL_STATIC_DRAW)
        for location, count, offset in ((0,3,0),(1,3,3),(2,2,6)):
            glEnableVertexAttribArray(location)
            glVertexAttribPointer(location,count,GL_FLOAT,GL_FALSE,32,c_void_p(offset*4))
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,self.ebo)
        ids = (GLuint*len(data.indices))(*data.indices)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER,sizeof(ids),ids,GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER,self.instances)
        glBufferData(GL_ARRAY_BUFFER,self.FLOATS*4,None,GL_STREAM_DRAW)
        for location, offset in ((3,0),(4,4),(5,8),(6,12),(7,16),(8,20),(9,24),(10,28)):
            glEnableVertexAttribArray(location)
            glVertexAttribPointer(location,4,GL_FLOAT,GL_FALSE,self.FLOATS*4,c_void_p(offset*4))
            glVertexAttribDivisor(location,1)
        glBindVertexArray(0)
        self.instance_count = 0

    def upload(self, records: list[float]):
        self.instance_count = len(records)//self.FLOATS
        if not records:
            return
        packed = array('f',records)
        raw = (GLfloat*len(packed)).from_buffer(packed)
        glBindBuffer(GL_ARRAY_BUFFER,self.instances)
        glBufferData(GL_ARRAY_BUFFER,len(packed)*4,raw,GL_STREAM_DRAW)

    def draw(self):
        if self.instance_count:
            glBindVertexArray(self.vao)
            glDrawElementsInstanced(GL_TRIANGLES,self.count,GL_UNSIGNED_INT,None,self.instance_count)
            glBindVertexArray(0)

    def delete(self):
        glDeleteVertexArrays(1,byref(self.vao))
        for buffer in (self.vbo,self.ebo,self.instances):
            glDeleteBuffers(1,byref(buffer))
