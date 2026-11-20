"""래스터화한 패치 전달률로 벽·상자·바닥·천장의 다중 난반사를 계산한다."""

from dataclasses import dataclass
from types import SimpleNamespace
import math

import pyglet
from pyglet.gl import *
from pyglet.math import Vec3
from hemicube import Hemicube

MAX_BOUNCE_LIGHTS=128
BOUNCE_COUNT=4       # 직접 조명을 받은 패치에서 시작해 다른 패치로 세 차례 더 전달한다.
PATCH_SUBDIVISIONS=2
CEILING_MAP_SIZE=32


def average_linear_color(texture):
    """면별 포장 사진의 평균 선형 RGB. 간접광에도 인쇄된 빨강이 반영된다."""
    image=texture.get_image_data();pixels=image.get_data('RGB',image.width*3)
    samples=[]
    for y in range(0,image.height,max(1,image.height//24)):
        for x in range(0,image.width,max(1,image.width//24)):
            index=(y*image.width+x)*3
            samples.append(tuple((pixels[index+c]/255.)**2.2 for c in range(3)))
    return tuple(sum(p[c] for p in samples)/len(samples) for c in range(3))


@dataclass
class Patch:
    # 평면 패치는 한 삼각형, 곡면 패치는 같은 영역에 속한 실제 메시 삼각형들이다.
    vertices: tuple
    center: Vec3
    normal: Vec3
    area: float
    reflectance: tuple
    specular: tuple
    shininess: float


class CeilingBounce:
    def __init__(self,light_positions,light_color,light_intensity):
        self.light_positions=[Vec3(*p) for p in light_positions]
        self.light_color=light_color;self.light_intensity=light_intensity
        self.patches=[];self.occluders=[];self.hemicube=None
        self.ceiling_factors=None;self.ceiling_maps=None
        self.bounce_count=BOUNCE_COUNT

    def add_box_face(self,data,material,texture):
        """실제 곡면을 UV 영역별로 묶어, 가림 형상은 보존하고 반사광만 패치로 근사한다."""
        color=average_linear_color(texture)
        ks=tuple(min(1.,max(0.,material.specular[c])) for c in range(3))
        rho=tuple(min(1.,max(0.,color[c]*material.diffuse[c]))*(1-ks[c]) for c in range(3))
        # 윗면은 아치를 가로지르는 짧은 방향을 더 잘게 나눈다.
        # 윗면 24 + 나머지 5면 각각 8 + 방 64 = 최대 128 패치.
        is_top=material.name=='Pie_top'
        columns,rows=(8,3) if is_top else (2,2)
        groups={}
        positions,normals,uvs=data['positions'],data['normals'],data['uvs']
        for i in range(0,len(positions),9):
            vertices=tuple(Vec3(*positions[i+j:i+j+3]) for j in (0,3,6))
            a,b,c=vertices;area=(b-a).cross(c-a).length()*.5
            if area<1e-12:continue
            k=2*(i//3)
            u=sum(uvs[k+j] for j in (0,2,4))/3
            v=sum(uvs[k+j] for j in (1,3,5))/3
            x=min(columns-1,max(0,int(u*columns)))
            y=min(rows-1,max(0,int(v*rows)))
            diagonal=0 if is_top or u*columns-x>=v*rows-y else 1
            normal=sum((Vec3(*normals[i+j:i+j+3]) for j in (0,3,6)),Vec3()).normalize()
            groups.setdefault((x,y,diagonal),[]).append((area,(a+b+c)/3,normal,vertices))
        for triangles in groups.values():
            area=sum(t[0] for t in triangles)
            centroid=sum((t[1]*t[0] for t in triangles),Vec3())/area
            # 평균점이 볼록한 메시 안으로 들어가지 않도록 실제 삼각형 위에 대표점을 둔다.
            representative=min(triangles,key=lambda t:(t[1]-centroid).length_squared())
            vertices=tuple(v for t in triangles for v in t[3])
            self.patches.append(Patch(vertices,representative[1],representative[2],area,rho,
                                      ks,material.shininess))
        if len(self.patches)>MAX_BOUNCE_LIGHTS:raise ValueError('간접광 패치 수가 128을 넘었습니다.')

    def add_room_surface(self,positions,normals,material,inward):
        self._add_surface(positions,normals,material,inward)

    def add_occluder(self,positions):
        # 도넛은 가림에는 포함한다. 곡면의 추가 패치 반사는 이번 근사에서 생략한다.
        self.occluders.append(list(positions))

    def _add_surface(self,positions,normals,material,normal):
        # 방의 단색 면도 shader.evaluate_brdf와 같은 Kd = clamp(base_color) * (1-Ks)를 쓴다.
        ks=tuple(min(1.,max(0.,material.specular[c])) for c in range(3))
        rho=tuple(min(1.,max(0.,material.diffuse[c]))*(1-ks[c]) for c in range(3))
        n=PATCH_SUBDIVISIONS
        for i in range(0,len(positions),9):
            if Vec3(*normals[i:i+3]).dot(normal)<.99:continue
            a,b,c=[Vec3(*positions[i+j:i+j+3]) for j in (0,3,6)]
            grid={(u,v):a+(b-a)*(u/n)+(c-a)*(v/n) for u in range(n+1) for v in range(n+1-u)}
            triangles=[]
            for u in range(n):
                for v in range(n-u):
                    triangles.append((grid[u,v],grid[u+1,v],grid[u,v+1]))
                    if u+v<n-1:triangles.append((grid[u+1,v],grid[u+1,v+1],grid[u,v+1]))
            for p,q,r in triangles:
                # ID 캡처에서도 법선 쪽이 삼각형의 앞면이 되게 한다.
                if (q-p).cross(r-p).dot(normal)<0:q,r=r,q
                area=(q-p).cross(r-p).length()*.5
                self.patches.append(Patch((p,q,r),(p+q+r)/3,normal,area,rho,
                                          ks,material.shininess))
        if len(self.patches)>MAX_BOUNCE_LIGHTS:raise ValueError('간접광 패치 수가 128을 넘었습니다.')

    def prepare(self):
        if self.hemicube is None:
            self.hemicube=Hemicube(self.patches,self.occluders,self.light_positions,.60,.60)
        self.solve(self.bounce_count)
        if self.ceiling_factors is None:
            # 천장은 패치 중심 하나만 보는 대신, 각 위치에서 보이는 표면 면적을
            # 다시 적분한다. 상자가 바닥의 일부만 가리는 경우도 공간적으로 반영한다.
            size=CEILING_MAP_SIZE
            self.ceiling_receivers=[SimpleNamespace(
                center=Vec3(2.9*(x+.5)/size,3.,-3.*(y+.5)/size),normal=Vec3(0,-1,0))
                for y in range(size) for x in range(size)]
            gather=Hemicube(self.patches,self.occluders,self.light_positions,.60,.60,
                           receivers=self.ceiling_receivers,keep_depth=False,resolution=48)
            self.ceiling_factors=gather.factors
            gather.delete()
            self._update_ceiling_maps()

    def solve(self,bounce_count=BOUNCE_COUNT):
        """이전 차수의 빛만 다시 반사시켜 누적한다. 같은 에너지를 중복 합산하지 않는다."""
        self.bounce_count=max(1,int(bounce_count))
        # F는 cosine/입체각과 실제 가림을 포함한다. B는 표면에서 나오는 난반사 radiance.
        light_radiance=tuple(c*self.light_intensity/self.hemicube.light_area for c in self.light_color)
        first=[tuple(p.reflectance[c]*f*light_radiance[c] for c in range(3))
               for p,f in zip(self.patches,self.hemicube.direct_factors)]
        orders=[first]
        for _ in range(1,self.bounce_count):
            previous=orders[-1];order=[]
            for patch,row in zip(self.patches,self.hemicube.factors):
                received=[sum(f*value[c] for f,value in zip(row,previous)) for c in range(3)]
                order.append(tuple(patch.reflectance[c]*received[c] for c in range(3)))
            orders.append(order)
        self.radiance=[tuple(sum(order[i][c] for order in orders) for c in range(3)) for i in range(len(first))]
        if self.ceiling_factors is not None:self._update_ceiling_maps()

    def _update_ceiling_maps(self):
        # 난반사와 코팅된 물체에서 온 정반사를 분리해 저장한다.
        # 다중 반사 횟수를 바꿀 때 가림을 다시 그릴 필요 없이 색만 갱신할 수 있다.
        source_spec=[self._specular_source(p,f) for p,f in zip(self.patches,self.hemicube.direct_factors)]
        diffuse=[];specular=[]
        for receiver,row in zip(self.ceiling_receivers,self.ceiling_factors):
            diffuse.extend([sum(f*value[c] for f,value in zip(row,self.radiance)) for c in range(3)]+[1.])
            value=[0.,0.,0.]
            for patch,f,(flux,reflection,power) in zip(self.patches,row,source_spec):
                if f<=0:continue
                delta=receiver.center-patch.center;distance_squared=max(delta.length_squared(),.0025)
                direction=delta.normalize();emit=max(patch.normal.dot(direction),0.)
                variance=patch.area*emit/(2*math.pi*distance_squared)
                filtered=max(1.,1./(1./(power+2)+variance)-2)
                normalization=(filtered+2)/(power+2)
                lobe=normalization*max(reflection.dot(direction),0.)**filtered
                for ch in range(3):value[ch]+=f*flux[ch]/patch.area*lobe
            specular.extend(value+[1.])
        if self.ceiling_maps is None:
            self.ceiling_maps=[]
            for _ in range(2):
                tex=pyglet.image.Texture.create(CEILING_MAP_SIZE,CEILING_MAP_SIZE,internalformat=GL_RGBA16F,
                                              min_filter=GL_LINEAR,mag_filter=GL_LINEAR,blank_data=False)
                for axis in (GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T):
                    glTexParameteri(GL_TEXTURE_2D,axis,GL_CLAMP_TO_EDGE)
                self.ceiling_maps.append(tex)
        glActiveTexture(GL_TEXTURE0)
        for tex,values in zip(self.ceiling_maps,(diffuse,specular)):
            glBindTexture(GL_TEXTURE_2D,tex.id)
            data=(GLfloat*len(values))(*values)
            glTexSubImage2D(GL_TEXTURE_2D,0,0,0,CEILING_MAP_SIZE,CEILING_MAP_SIZE,GL_RGBA,GL_FLOAT,data)
        glBindTexture(GL_TEXTURE_2D,0)

    def _specular_source(self,patch,direct_factor):
        # 코팅된 상자 등의 직접 정반사는 방향성이 있으므로 radiosity의 확산 피드백과 분리한다.
        samples=[];direction=Vec3()
        for light in self.light_positions:
            v=light-patch.center;L=v.normalize()
            weight=max(patch.normal.dot(L),0.)*max(L.y,0.)/max(v.length_squared(),1e-5)
            samples.append((L,weight));direction+=L*weight
        total=sum(weight for _,weight in samples)
        L=direction.normalize() if total>1e-8 else patch.normal
        variance=sum(w*(1-d.dot(L)) for d,w in samples)/max(total,1e-8)
        power=max(1.,1./(1./(patch.shininess+2)+variance)-2)
        irradiance=math.pi*direct_factor*self.light_intensity/self.hemicube.light_area
        flux=tuple(self.light_color[c]*irradiance*patch.specular[c]*(power+2)/(2*math.pi)*patch.area for c in range(3))
        return flux,patch.normal*(2*patch.normal.dot(L))-L,power

    def bind_to(self,program):
        if self.hemicube is None:self.prepare()
        count=len(self.patches);padding=MAX_BOUNCE_LIGHTS-count
        spec=[self._specular_source(p,f) for p,f in zip(self.patches,self.hemicube.direct_factors)]
        program['bounce_count']=count
        program['bounce_positions']=[tuple(p.center) for p in self.patches]+[(0.,0.,0.)]*padding
        program['bounce_normals']=[tuple(p.normal) for p in self.patches]+[(0.,1.,0.)]*padding
        program['bounce_diffuse_flux']=[tuple(c*p.area for c in value) for p,value in zip(self.patches,self.radiance)]+[(0.,0.,0.)]*padding
        program['bounce_specular_flux']=[s[0] for s in spec]+[(0.,0.,0.)]*padding
        program['bounce_reflections']=[tuple(s[1]) for s in spec]+[(0.,1.,0.)]*padding
        program['bounce_parameters']=[(s[2],p.area) for p,s in zip(self.patches,spec)]+[(1.,0.)]*padding
        self.bind_depth(program)

    def bind_depth(self,program):
        self.hemicube.bind(program)
        for unit,name,tex in zip((3,4),('ceiling_diffuse_map','ceiling_specular_map'),self.ceiling_maps):
            glActiveTexture(GL_TEXTURE0+unit);glBindTexture(GL_TEXTURE_2D,tex.id)
            program[name]=unit
        glActiveTexture(GL_TEXTURE0)
