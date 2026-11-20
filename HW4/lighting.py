"""일반 재질과 물에서 공유하는 GLSL 그림자 함수."""

SHADOW_SOURCE = """
uniform sampler2DArray shadow_map;
uniform mat4 light_view_projections[MAX_LIGHTS];
uniform sampler2DArray water_shadow_front;
uniform sampler2DArray water_shadow_back;
uniform vec3 shadow_absorption;
uniform sampler2DArray cup_shadow_tau;
uniform sampler2DArray cup_shadow_exit;

float shadow_visibility(int i, vec3 N) {
    vec4 clip = light_view_projections[i] * vec4(world_position, 1.0);
    if (clip.w <= 0.0) return 1.0;
    vec3 p = clip.xyz / clip.w * 0.5 + 0.5;
    if (any(lessThan(p,vec3(0.0))) || any(greaterThan(p,vec3(1.0)))) return 1.0;
    vec3 L = normalize(light_positions[i] - world_position);
    float bias = max(0.0002*(1.0-max(dot(N,L),0.0)),0.00003);
    vec2 texel = 1.0 / vec2(textureSize(shadow_map,0).xy);
    float visibility = 0.0;
    for(int y=-1;y<=1;y++) for(int x=-1;x<=1;x++) {
        float d = texture(shadow_map,vec3(p.xy+vec2(x,y)*texel,float(i))).r;
        visibility += p.z-bias <= d ? 1.0 : 0.0;
    }
    return visibility/9.0;
}

vec3 water_transmission(int i) {
    vec4 clip = light_view_projections[i] * vec4(world_position,1.0);
    if (clip.w <= 0.0) return vec3(1.0);
    vec3 p = clip.xyz/clip.w*0.5+0.5;
    if (any(lessThan(p,vec3(0.0))) || any(greaterThan(p,vec3(1.0)))) return vec3(1.0);
    vec2 entry = texture(water_shadow_front,vec3(p.xy,float(i))).rg;
    vec2 exit = texture(water_shadow_back,vec3(p.xy,float(i))).rg;
    float receiver = length(world_position-light_positions[i]);
    if (entry.r>=999.0 || exit.r>=999.0 || receiver<=entry.r+0.001) return vec3(1.0);
    float thickness = max(min(receiver,exit.r)-entry.r,0.0);
    float interfaces = (1.0-entry.g)*(receiver>=exit.r ? 1.0-exit.g : 1.0);
    vec3 transmission = interfaces*exp(-shadow_absorption*thickness);
    return transmission;
}

float cup_transmission(int i) {
    vec4 clip=light_view_projections[i]*vec4(world_position,1.0);
    if(clip.w<=0.0)return 1.0;
    vec3 p=clip.xyz/clip.w*0.5+0.5;
    if(any(lessThan(p,vec3(0)))||any(greaterThan(p,vec3(1))))return 1.0;
    vec3 uv=vec3(p.xy,float(i));
    float exit_depth=texture(cup_shadow_exit,uv).r;
    if(exit_depth<=0.0||p.z+0.00003<exit_depth)return 1.0;
    // 광학 두께가 아닌 투과율을 평균해 입구 띠의 가는 그림자를 부드럽게 한다.
    vec2 texel=1.5/vec2(textureSize(cup_shadow_tau,0).xy);
    float transmission=0.0;
    for(int y=-1;y<=1;y++) for(int x=-1;x<=1;x++) {
        vec3 sample_uv=vec3(p.xy+vec2(x,y)*texel,float(i));
        float depth=texture(cup_shadow_exit,sample_uv).r;
        float T=1.0;
        if(depth>0.0 && p.z+0.00003>=depth)
            T=exp(-max(texture(cup_shadow_tau,sample_uv).r,0.0));
        float weight=(x==0?2.0:1.0)*(y==0?2.0:1.0);
        transmission+=weight*T;
    }
    return transmission/16.0;
}
"""
