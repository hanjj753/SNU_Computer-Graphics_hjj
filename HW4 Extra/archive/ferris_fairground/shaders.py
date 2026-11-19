"""GLSL 3.30 shaders for instanced PBR, shadow maps, and HDR postprocessing."""

SURFACE_VERTEX = """#version 330 core
layout(location=0) in vec3 position;
layout(location=1) in vec3 normal;
layout(location=2) in vec2 texcoord;
layout(location=3) in vec4 model0;
layout(location=4) in vec4 model1;
layout(location=5) in vec4 model2;
layout(location=6) in vec4 model3;
layout(location=7) in vec4 base_color;
layout(location=8) in vec4 parameters;
layout(location=9) in vec4 emission;
uniform mat4 view_projection;
out vec3 P;
out vec3 N0;
out vec2 uv;
flat out vec4 material_color;
flat out vec4 material_parameters;
flat out vec3 material_emission;
void main(){
    mat4 model=mat4(model0,model1,model2,model3);
    vec4 p=model*vec4(position,1.);
    P=p.xyz;
    // Our transforms contain orthogonal columns (rotation + nonuniform scale).
    // This is the inverse-transpose normal transform without a matrix inverse.
    mat3 basis=mat3(model);
    vec3 squared_scale=vec3(dot(model0.xyz,model0.xyz),dot(model1.xyz,model1.xyz),dot(model2.xyz,model2.xyz));
    N0=basis*(normal/max(squared_scale,vec3(1e-8)));
    uv=texcoord;
    material_color=base_color;
    material_parameters=parameters;
    material_emission=emission.rgb;
    gl_Position=view_projection*p;
}
"""

SURFACE_FRAGMENT = """#version 330 core
const float PI=3.14159265359;
const int MAX_LIGHTS=80;
in vec3 P;
in vec3 N0;
in vec2 uv;
flat in vec4 material_color;
flat in vec4 material_parameters;
flat in vec3 material_emission;
out vec4 final_color;
uniform vec3 camera_position;
uniform vec4 light_positions[MAX_LIGHTS];
uniform vec4 light_colors[MAX_LIGHTS];
uniform int light_count;
uniform mat4 shadow_vp[4];
uniform sampler2DArray shadow_map;
uniform samplerCube environment_map;
uniform sampler2D floor_reflection;
uniform sampler2D sign_texture;
uniform mat4 reflection_vp;
uniform bool shadows_enabled;
uniform bool reflections_enabled;
uniform bool bump_enabled;
uniform int capture_pass; // 0 main, 1 planar reflection, 2 room/emitter probe
uniform float floor_y;
uniform vec3 probe_position;
uniform vec3 room_min;
uniform vec3 room_max;

float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
vec3 fresnel(vec3 f0,float cosine){return f0+(1.-f0)*pow(1.-clamp(cosine,0.,1.),5.);}

float visibility(int i,vec3 n,vec3 l){
    if(!shadows_enabled || i>=4) return 1.;
    vec4 clip=shadow_vp[i]*vec4(P,1.);
    vec3 q=clip.xyz/clip.w*.5+.5;
    if(clip.w<=0. || any(lessThan(q,vec3(0.))) || any(greaterThan(q,vec3(1.)))) return 1.;
    float bias=max(.00012,.00065*(1.-max(dot(n,l),0.)));
    vec2 texel=1./vec2(textureSize(shadow_map,0).xy);
    float result=0.;
    for(int y=-1;y<=1;y++) for(int x=-1;x<=1;x++){
        float stored=texture(shadow_map,vec3(q.xy+vec2(x,y)*texel,float(i))).r;
        result+=q.z-bias<=stored?1.:0.;
    }
    return result/9.;
}

vec3 brdf(vec3 n,vec3 v,vec3 l,vec3 base,float metal,float rough){
    vec3 h=normalize(v+l);
    float nv=max(dot(n,v),.001),nl=max(dot(n,l),0.);
    float nh=max(dot(n,h),0.),vh=max(dot(v,h),0.);
    float a=rough*rough,a2=a*a;
    float denom=nh*nh*(a2-1.)+1.;
    float D=a2/max(PI*denom*denom,1e-7);
    // Height-correlated Smith-GGX visibility, with alpha = roughness^2.
    float gv=nl*sqrt(nv*nv*(1.-a2)+a2);
    float gl=nv*sqrt(nl*nl*(1.-a2)+a2);
    float V=.5/max(gv+gl,1e-5);
    vec3 F=fresnel(mix(vec3(.04),base,metal),vh);
    return (1.-F)*(1.-metal)*base/PI+D*V*F;
}

vec3 probe_direction(vec3 ray){
    // Box projection corrects the room-wall parallax of a single probe.
    vec3 d=mix(vec3(.0001),ray,greaterThan(abs(ray),vec3(.0001)));
    vec3 t0=(room_min-P)/d,t1=(room_max-P)/d;
    vec3 far_t=max(t0,t1);
    float t=min(far_t.x,min(far_t.y,far_t.z));
    return P+ray*t-probe_position;
}

void main(){
    float surface=material_parameters.z;
    if(capture_pass==1 && P.y<floor_y+.001) discard;
    vec3 n=normalize(N0);
    if(!gl_FrontFacing) n=-n;
    vec3 v=normalize(camera_position-P);
    vec3 base=material_color.rgb;
    float metal=material_parameters.x;
    float rough=clamp(material_parameters.y,.09,1.);
    bool is_floor=surface>.5 && surface<1.5;
    bool is_glass=surface>3.5 && surface<4.5;
    bool is_sign=surface>4.5 && surface<12.5;
    if(is_sign){
        float index=floor(surface-5.+.1);
        vec2 tile=vec2(mod(index,2.),3.-floor(index/2.));
        vec2 atlas_uv=(mix(vec2(.002),vec2(.998),uv)+tile)/vec2(2.,4.);
        vec3 tex=texture(sign_texture,atlas_uv).rgb;
        base=pow(tex,vec3(2.2));
    }
    if(surface>12.5 && surface<13.5){
        float phase=uv.x*120.+5.*sin(uv.y*12.);
        float grain=sin(phase)*exp(-fwidth(phase));
        base*=.85+.15*grain;
    }
    if(surface>2.5 && surface<3.5){
        float grain=hash(floor(uv*780.));
        base*=.992+.016*grain;
        if(bump_enabled) n=normalize(n+.004*vec3(sin(P.y*110.),sin(P.z*103.),sin(P.x*117.)));
    }
    if(surface>1.5 && surface<2.5 && bump_enabled){
        float phase=(uv.y+uv.x*.07)*280.;
        float filtering=exp(-2.*fwidth(phase));
        rough=clamp(rough+.018*sin(phase)*filtering,.1,.8);
    }
    if(is_floor){
        vec2 grid=abs(fract(P.xz*2.)-.5);
        float seam=smoothstep(.486,.497,max(grid.x,grid.y));
        base*=mix(1.,.68,seam);
        float speckle=hash(floor(P.xz*530.));
        base*=.985+.03*speckle;
        if(bump_enabled){
            // A procedural height field with its analytic X/Z derivatives.
            float dx=.013*cos(P.x*39.+P.z*7.)+.006*cos(P.x*91.);
            float dz=.0023*cos(P.x*39.+P.z*7.)+.010*cos(P.z*48.);
            n=normalize(n+vec3(dx,0.,dz));
        }
    }
    // Geometric specular antialiasing broadens subpixel metal highlights.
    vec3 ndx=dFdx(n),ndy=dFdy(n);
    float variance=.15*(dot(ndx,ndx)+dot(ndy,ndy));
    rough=sqrt(clamp(rough*rough+min(.20,variance),.0081,1.));
    vec3 color=base*(1.-metal)*.024;
    for(int i=0;i<light_count;i++){
        if(light_colors[i].a<=0.) continue;
        vec3 delta=light_positions[i].xyz-P;
        float distance2=max(dot(delta,delta),.0001);
        vec3 l=delta*inversesqrt(distance2);
        float nl=max(dot(n,l),0.);
        if(nl<=0.) continue;
        float emitter=i<4?max(l.y,0.):1.;
        float radius=light_positions[i].w;
        vec3 incoming=light_colors[i].rgb*light_colors[i].a/(distance2+radius*radius);
        color+=brdf(n,v,l,base,metal,rough)*incoming*nl*emitter*visibility(i,n,l);
    }
    vec3 F=fresnel(mix(vec3(.04),base,metal),max(dot(n,v),0.));
    if(reflections_enabled && capture_pass!=2){
        vec3 ray=reflect(-v,n);
        vec3 reflected=textureLod(environment_map,probe_direction(ray),rough*6.).rgb;
        color+=reflected*F*(1.-.5*rough);
        vec3 ambient=textureLod(environment_map,n,7.).rgb;
        color+=ambient*base*(1.-metal)*.10;
    }
    if(is_floor && reflections_enabled && capture_pass==0){
        vec4 clip=reflection_vp*vec4(P,1.);
        vec2 reflected_uv=clip.xy/clip.w*.5+.5;
        if(bump_enabled) reflected_uv+=n.xz*.011;
        if(all(greaterThanEqual(reflected_uv,vec2(0.))) && all(lessThanEqual(reflected_uv,vec2(1.)))){
            vec2 texel=1./vec2(textureSize(floor_reflection,0));
            vec3 reflected=texture(floor_reflection,reflected_uv).rgb*.4;
            reflected+=(texture(floor_reflection,reflected_uv+texel*vec2(1.5,0)).rgb
                       +texture(floor_reflection,reflected_uv-texel*vec2(1.5,0)).rgb
                       +texture(floor_reflection,reflected_uv+texel*vec2(0,1.5)).rgb
                       +texture(floor_reflection,reflected_uv-texel*vec2(0,1.5)).rgb)*.15;
            float weight=clamp(.10+.72*F.r,.10,.72);
            color=mix(color,reflected,weight);
        }
    }
    float alpha=material_color.a;
    if(is_glass){
        // Thin tinted glazing: sorted alpha composition plus Fresnel highlights.
        // No thick-glass refraction or physically based transmission is claimed.
        alpha=clamp(alpha+.48*F.r,.08,.65);
        color+=base*.035;
    }
    color+=material_emission;
    if(is_sign) color+=base*.16;
    final_color=vec4(max(color,vec3(0.)),alpha);
}
"""

DEPTH_VERTEX = """#version 330 core
layout(location=0) in vec3 position;
layout(location=3) in vec4 model0;
layout(location=4) in vec4 model1;
layout(location=5) in vec4 model2;
layout(location=6) in vec4 model3;
uniform mat4 light_vp;
void main(){gl_Position=light_vp*mat4(model0,model1,model2,model3)*vec4(position,1.);}
"""
DEPTH_FRAGMENT = """#version 330 core
void main(){}
"""

FULLSCREEN_VERTEX = """#version 330 core
out vec2 uv;
void main(){
    vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);
    uv=p;
    gl_Position=vec4(p*2.-1.,0.,1.);
}
"""

BRIGHT_FRAGMENT = """#version 330 core
in vec2 uv;
out vec4 final_color;
uniform sampler2D source;
uniform vec2 texel;
void main(){
    vec3 c=vec3(0.);
    for(int y=0;y<4;y++)for(int x=0;x<4;x++)c+=texture(source,uv+(vec2(x,y)-1.5)*texel).rgb/16.;
    float brightness=max(c.r,max(c.g,c.b));
    float soft=clamp(brightness-.5,0.,1.);
    float weight=max(brightness-1.,soft*soft*.5)/max(brightness,.0001);
    final_color=vec4(c*weight,1.);
}
"""

BLUR_FRAGMENT = """#version 330 core
in vec2 uv;
out vec4 final_color;
uniform sampler2D source;
uniform vec2 step_uv;
void main(){
    float weights[5]=float[](.227027,.1945946,.1216216,.054054,.016216);
    vec3 c=texture(source,uv).rgb*weights[0];
    for(int i=1;i<5;i++)c+=(texture(source,uv+step_uv*i).rgb+texture(source,uv-step_uv*i).rgb)*weights[i];
    final_color=vec4(c,1.);
}
"""

POST_FRAGMENT = """#version 330 core
in vec2 uv;
out vec4 final_color;
uniform sampler2D source;
uniform sampler2D bloom_texture;
uniform float bloom_strength;
uniform float exposure;
uniform vec2 resolution;
vec3 to_srgb(vec3 c){return mix(12.92*c,1.055*pow(c,vec3(1./2.4))-.055,greaterThan(c,vec3(.0031308)));}
vec3 filmic(vec3 x){return clamp((x*(2.51*x+.03))/(x*(2.43*x+.59)+.14),0.,1.);}
vec3 sample_scene(vec2 p){return texture(source,p).rgb;}
void main(){
    // A compact FXAA-style edge filter operates before the display transform.
    vec2 px=1./resolution;
    vec3 c=sample_scene(uv);
    vec3 nw=sample_scene(uv+px*vec2(-1,-1)),ne=sample_scene(uv+px*vec2(1,-1));
    vec3 sw=sample_scene(uv+px*vec2(-1,1)),se=sample_scene(uv+px*vec2(1,1));
    vec3 lum=vec3(.299,.587,.114);
    float lnw=dot(nw,lum),lne=dot(ne,lum),lsw=dot(sw,lum),lse=dot(se,lum),lc=dot(c,lum);
    vec2 dir=vec2(-((lnw+lne)-(lsw+lse)),((lnw+lsw)-(lne+lse)));
    float reduction=max((lnw+lne+lsw+lse)*.03125,.0078125);
    dir=clamp(dir/(min(abs(dir.x),abs(dir.y))+reduction),vec2(-5),vec2(5))*px;
    vec3 a=.5*(sample_scene(uv+dir*(-1./6.))+sample_scene(uv+dir*(1./6.)));
    vec3 b=a*.5+.25*(sample_scene(uv-dir*.5)+sample_scene(uv+dir*.5));
    float low=min(lc,min(min(lnw,lne),min(lsw,lse))),high=max(lc,max(max(lnw,lne),max(lsw,lse)));
    float lb=dot(b,lum);
    c=(lb<low || lb>high)?a:b;
    c+=texture(bloom_texture,uv).rgb*bloom_strength;
    c=filmic(max(c,vec3(0.))*exposure);
    // Very subtle display-space dither limits visible gradients on dim walls.
    float dither=fract(sin(dot(gl_FragCoord.xy,vec2(12.9898,78.233)))*43758.5453)-.5;
    final_color=vec4(clamp(to_srgb(c)+dither/255.,0.,1.),1.);
}
"""
