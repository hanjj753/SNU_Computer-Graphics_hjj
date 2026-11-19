"""원본 컵의 치수를 읽어 얇은 평평한 입구 띠가 연결된 회전체를 만든다."""

from dataclasses import dataclass
import math


ANGULAR_SEGMENTS = 96
LIP_OVERHANG = 0.025     # 몸체보다 바깥으로 2.5 mm 돌출.
LIP_THICKNESS = 0.010   # 띠 두께 1.0 mm.
LIP_RAISE = 0.005       # 기존 바깥쪽 입구 높이보다 0.5 mm 위.


@dataclass
class CupMesh:
    positions: list
    normals: list
    rim_base_y: float
    center: tuple
    inner_radius: float
    outer_radius: float
    rim_top_y: float
    outer_profile: tuple
    inner_profile: tuple
    base_thickness: float

    def wall_thickness(self, y):
        """입구 띠를 제외한 실제 내벽·외벽 반지름의 차이."""
        def radius(profile):
            (y0,r0),(y1,r1)=profile
            t=max(0.0,min(1.0,(y-y0)/(y1-y0)))
            return r0+(r1-r0)*t
        return max(0.0,radius(self.outer_profile)-radius(self.inner_profile))


def build_cup_mesh(positions):
    points = list(zip(positions[0::3], positions[1::3], positions[2::3]))
    cx = (min(p[0] for p in points) + max(p[0] for p in points)) / 2
    cz = (min(p[2] for p in points) + max(p[2] for p in points)) / 2
    levels = sorted(set(p[1] for p in points))
    bottom, inner_bottom, outer_top, inner_top = levels

    def radius_at(y):
        return max(math.hypot(x-cx,z-cz) for x,py,z in points if py==y)

    r_bottom, r_inner_bottom = radius_at(bottom), radius_at(inner_bottom)
    r_top, r_inner_top = radius_at(outer_top), radius_at(inner_top)
    top = outer_top + LIP_RAISE
    base = top - LIP_THICKNESS
    body_radius = r_bottom + (r_top-r_bottom)*(base-bottom)/(outer_top-bottom)
    inner_base = r_inner_bottom + (r_inner_top-r_inner_bottom)*(base-inner_bottom)/(inner_top-inner_bottom)
    outer_lip = r_top + LIP_OVERHANG

    # (반지름, 높이)의 닫힌 단면이다. 컵 입구의 중앙은 뚫려 있다.
    # 바닥에서 외벽을 올라가 평평한 띠를 지난 뒤 내벽과 안쪽 바닥으로 돌아온다.
    profile = [
        (0.0,bottom), (r_bottom,bottom), (body_radius,base),
        (outer_lip,base), (outer_lip,top), (r_inner_top,top),
        (inner_base,base), (r_inner_bottom,inner_bottom), (0.0,inner_bottom),
    ]
    result_positions, result_normals = [], []

    def vertex(r,y,angle,dr,dy,length):
        c,s = math.cos(angle),math.sin(angle)
        return (cx+r*c,y,cz+r*s), (dy*c/length,-dr/length,dy*s/length)

    def triangle(a,b,c):
        for p,n in (a,b,c):
            result_positions.extend(p)
            result_normals.extend(n)

    for (ra,ya),(rb,yb) in zip(profile,profile[1:]):
        dr,dy = rb-ra,yb-ya
        length = math.hypot(dr,dy)
        for i in range(ANGULAR_SEGMENTS):
            a = 2*math.pi*i/ANGULAR_SEGMENTS
            b = 2*math.pi*((i+1)%ANGULAR_SEGMENTS)/ANGULAR_SEGMENTS
            ai,aj = vertex(ra,ya,a,dr,dy,length),vertex(ra,ya,b,dr,dy,length)
            bi,bj = vertex(rb,yb,a,dr,dy,length),vertex(rb,yb,b,dr,dy,length)
            if rb>0: triangle(ai,bi,bj)
            if ra>0: triangle(ai,bj,aj)

    return CupMesh(result_positions,result_normals,base,(cx,cz),r_inner_top,outer_lip,top,
                   ((bottom,r_bottom),(base,body_radius)),
                   ((inner_bottom,r_inner_bottom),(base,inner_base)),inner_bottom-bottom)
