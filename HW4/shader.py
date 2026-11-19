from lighting import SHADOW_SOURCE
from cup_optics import CUP_OPTICS_SOURCE
from hemicube import VISIBILITY_SOURCE
from pyglet.graphics.shader import Shader, ShaderProgram

# POSITION : 
# COLOR_0 

VERTEX_SOURCE = """
#version 330 core

in vec3 POSITION;
in vec3 NORMAL;
in vec4 COLOR_0;
in vec2 TEXCOORD_0;

out vec3 world_position;
out vec3 world_normal;
out vec4 vertex_color;
out vec2 texcoord;

uniform WindowBlock
{
    mat4 projection;
    mat4 view;
} window;

uniform mat4 model;

void main() 
{
    vec4 position_world = model * vec4(POSITION, 1.0);

    mat3 normal_matrix = transpose(inverse(mat3(model)));

    world_position = position_world.xyz;
    world_normal = normal_matrix * NORMAL;
    vertex_color = COLOR_0;
    texcoord = TEXCOORD_0;

    gl_Position = (
        window.projection
        * window.view
        * position_world
    );  
    
    vertex_color = COLOR_0;
}
"""

FRAGMENT_SOURCE = """
#version 330 core

in vec3 world_position;
in vec3 world_normal;
in vec4 vertex_color;
in vec2 texcoord;

out vec4 final_color;

const int MAX_LIGHTS = 16;

uniform vec3 light_positions[MAX_LIGHTS];
uniform int light_count;

uniform vec3 light_color;
uniform vec3 light_normal;
uniform float light_intensity;
uniform float ambient_strength;
uniform float ambient_scale;

uniform vec3 camera_position;
uniform vec3 specular_color;
uniform float shininess;
uniform float contact_occlusion_height;
uniform float surface_grain;
uniform float indirect_diffuse_gain;
uniform bool baked_ceiling_surface;
uniform sampler2D ceiling_diffuse_map;
uniform sampler2D ceiling_specular_map;
uniform bool skip_reflection_surface;
uniform sampler2D planar_texture;
uniform mat4 planar_view_projection;
uniform float planar_strength;
uniform float planar_roughness;
uniform vec4 reflection_clip_plane;
uniform bool reflection_capture;

uniform bool use_texture;
uniform sampler2D diffuse_texture;

// 컵을 물의 앞/뒤에서 나눠 그리기 위한 화면 깊이 비교.
uniform int transparency_phase; // 0: 일반, -1: 물 뒤, +1: 물 앞
uniform sampler2D water_front_depth;
uniform vec2 viewport_size;

// CUP_OPTICS

const int MAX_BOUNCE_LIGHTS = 128;
uniform bool receive_ceiling_bounce;
uniform int bounce_count;
uniform vec3 bounce_positions[MAX_BOUNCE_LIGHTS];
uniform vec3 bounce_diffuse_flux[MAX_BOUNCE_LIGHTS];
uniform vec3 bounce_specular_flux[MAX_BOUNCE_LIGHTS];
uniform vec3 bounce_reflections[MAX_BOUNCE_LIGHTS];
uniform vec3 bounce_normals[MAX_BOUNCE_LIGHTS];
uniform vec2 bounce_parameters[MAX_BOUNCE_LIGHTS]; // x: power, y: area
uniform float bounce_strength;

// GI_VISIBILITY

vec3 ceiling_indirect(vec3 N, vec3 V, vec3 base_color)
{
    if (!receive_ceiling_bounce || bounce_strength<=0.0) return vec3(0.0);
    const float PI = 3.141592653589793;
    vec3 result = vec3(0.0);
    vec3 Ks = clamp(specular_color, vec3(0.0), vec3(1.0));
    vec3 Kd = clamp(base_color, vec3(0.0), vec3(1.0)) * (1.0-Ks);
    if(baked_ceiling_surface && N.y<-.9) {
        vec2 uv=vec2(world_position.x/2.9,-world_position.z/3.0);
        vec4 diffuse=texture(ceiling_diffuse_map,uv);
        // 기본 GI는 이미 실제 가림을 포함한다. 1보다 큰 사진 보정량만
        // 상자 뒤에서도 똑같이 적용되지 않도록 바닥 가시율로 제한한다.
        float gain=min(1.0,indirect_diffuse_gain)+max(0.0,indirect_diffuse_gain-1.0)*diffuse.a;
        vec3 irradiance=gain*diffuse.rgb
                        +texture(ceiling_specular_map,uv).rgb;
        // 저장값은 E/PI이므로 Lambert 수신면에서는 Kd만 곱한다.
        return bounce_strength*Kd*irradiance;
    }
    // 주변 물체의 정반사는 평면 반사 패스에서 받으므로 중복해서 더하지 않는다.
    bool glossy = planar_strength<=0.0 && any(greaterThan(Ks,vec3(0.0)));
    for (int i = 0; i < bounce_count; i++) {
        vec3 from_patch = world_position - bounce_positions[i];
        // 유한한 면적 패치가 가까운 곳에서 점 광원처럼 발산하지 않도록 한다.
        float distance_squared = max(dot(from_patch, from_patch), 0.0025)+bounce_parameters[i].y/PI;
        vec3 direction = normalize(from_patch);
        float emit = max(dot(bounce_normals[i], direction), 0.0);
        float receive = max(dot(N, -direction), 0.0);
        if (emit <= 0.0 || receive <= 0.0) continue;
        float visible=bounce_visibility(i,bounce_positions[i],bounce_normals[i],world_position,N);
        if(visible<=0.0) continue;
        float alignment = max(dot(bounce_reflections[i], direction), 0.0);
        // 가까운 바닥에서 광택 패치가 작은 점으로 찍히지 않도록 면적을 필터 폭에 반영한다.
        float angular_variance = bounce_parameters[i].y*emit/(2.0*PI*distance_squared);
        float source_power = max(1.0,1.0/(1.0/(bounce_parameters[i].x+2.0)+angular_variance)-2.0);
        float source_normalization = (source_power+2.0)/(bounce_parameters[i].x+2.0);
        vec3 flux = indirect_diffuse_gain*bounce_diffuse_flux[i] + bounce_specular_flux[i]
                  * source_normalization * pow(alignment,source_power);
        // 받는 PVC도 Lambert + Phong으로 평가한다. 시선이 변하면 반사 위치도 변한다.
        // 작은 패치를 점 광원으로 압축한 데서 오는 점무늬는 입체각만큼 lobe를 넓혀 줄인다.
        vec3 brdf = Kd/PI;
        // 무광인 바닥·뒷벽에서는 결과가 0인 정반사 계산을 생략한다.
        if (glossy) {
            float power = max(1.0, 1.0/(1.0/(shininess+2.0)+angular_variance)-2.0);
            float specular_lobe = (power+2.0)/(2.0*PI)
                               * pow(max(dot(reflect(direction,N),V),0.0),power);
            brdf += Ks*specular_lobe;
        }
        result += visible * brdf * flux * emit * receive / distance_squared;
    }
    // flux에는 패치 사이의 여러 차례 난반사가 누적되어 있다.
    // 현재 표면까지의 가림은 래스터화한 패치별 깊이 맵으로 확인한다.
    return bounce_strength * result;
}

// SHADOW_FUNCTIONS

float grain_hash(vec3 p) {
    p=fract(p*.1031);
    p+=dot(p,p.yzx+33.33);
    return fract((p.x+p.y)*p.z);
}

// 3D value noise와 그 해석적 기울기. 화면 크기에 따라 필터링해 떨림을 줄인다.
vec4 grain_value_gradient(vec3 p) {
    vec3 i=floor(p),f=fract(p),u=f*f*(3.0-2.0*f),du=6.0*f*(1.0-f);
    float a=grain_hash(i),b=grain_hash(i+vec3(1,0,0));
    float c=grain_hash(i+vec3(0,1,0)),d=grain_hash(i+vec3(1,1,0));
    float e=grain_hash(i+vec3(0,0,1)),f1=grain_hash(i+vec3(1,0,1));
    float g=grain_hash(i+vec3(0,1,1)),h=grain_hash(i+vec3(1,1,1));
    float k1=b-a,k2=c-a,k3=e-a,k4=a-b-c+d;
    float k5=a-b-e+f1,k6=a-c-e+g,k7=-a+b+c-d+e-f1-g+h;
    float value=a+k1*u.x+k2*u.y+k3*u.z+k4*u.x*u.y+k5*u.x*u.z+k6*u.y*u.z+k7*u.x*u.y*u.z;
    vec3 gradient=du*vec3(k1+k4*u.y+k5*u.z+k7*u.y*u.z,
                         k2+k4*u.x+k6*u.z+k7*u.x*u.z,
                         k3+k5*u.x+k6*u.y+k7*u.x*u.y);
    return vec4(gradient,value);
}

vec3 evaluate_brdf(vec3 N, vec3 V, vec3 L, vec3 base_color)
{
    const float PI = 3.141592653589793;

    // 표면 앞쪽에서 들어오고 나가는 빛만 다룬다.
    if (dot(N, L) <= 0.0 || dot(N, V) <= 0.0)
        return vec3(0.0);

    // Ks: 정반사에 할당할 반사율.
    vec3 Ks = clamp(
        specular_color, vec3(0.0), vec3(1.0)
    );

    // 정반사에 할당한 몫을 제외하고 난반사색을 정한다.
    // 각 RGB 성분에서 Kd + Ks가 1을 넘지 않게 한다.
    vec3 Kd = (
        clamp(base_color, vec3(0.0), vec3(1.0))
        * (vec3(1.0) - Ks)
    );

    // Lambert 난반사 BRDF.
    vec3 diffuse_brdf = Kd / PI;
    if (all(lessThanEqual(Ks,vec3(0.0)))) return diffuse_brdf;

    // R: 입사광이 거울처럼 반사되는 방향.
    vec3 R = reflect(-L, N);

    // n이 클수록 하이라이트가 좁아진다.
    float n = max(shininess, 1.0);
    float alignment = max(dot(R, V), 0.0);

    // 수정 Phong 모델의 정규화 계수를 적용한다.
    vec3 specular_brdf = (
        Ks
        * ((n + 2.0) / (2.0 * PI))
        * pow(alignment, n)
    );

    // 광원 세기, 거리 감쇠, N·L, 그림자는 밖에서 처리한다.
    return diffuse_brdf + specular_brdf;
}

void main() {
    if (skip_reflection_surface) discard;
    // 유한한 벽 한 겹의 입구·출구를 함수 안에서 함께 처리한다.
    if (cup_surface && cup_optics_enabled && !gl_FrontFacing) discard;
    if (dot(reflection_clip_plane,vec4(world_position,1.0))<0.0) discard;
    if (transparency_phase != 0 && cup_surface) {
        float water_depth = texture(water_front_depth, gl_FragCoord.xy / viewport_size).r;
        bool behind_water = gl_FragCoord.z > water_depth;
        if ((transparency_phase < 0 && !behind_water) ||
            (transparency_phase > 0 && behind_water)) discard;
    }
    vec3 N = normalize(world_normal);
    vec3 V = normalize(camera_position - world_position);
    // 보간된 alpha=1이 반올림으로 1보다 작아질 수 있으므로 재질로 구분한다.
    // 반사 카메라에서는 winding도 뒤집히므로 시선과 법선의 내적을 사용한다.
    if (cup_surface && dot(N,V)<0.0)
    {
        N = -N;
    }

    vec3 base_color = vertex_color.rgb;
    if (use_texture) {
        vec3 texture_srgb = texture(diffuse_texture, texcoord).rgb; //texture(sample, coord)하면 이미지의 u, v 좌표 읽어줌

        base_color *= pow(texture_srgb, vec3(2.2));
    }
    if (surface_grain>0.0) {
        vec3 coordinate=world_position*180.0;
        vec3 footprint=fwidth(coordinate);
        float filtering=1.0/(1.0+dot(footprint,footprint));
        // 윤곽에서 요철 법선이 시선 반대쪽으로 뒤집혀 검은 점이 되는 것을 막는다.
        filtering*=smoothstep(.035,.18,max(dot(N,V),0.0));
        vec4 grain=grain_value_gradient(coordinate);
        vec3 tangent_gradient=grain.xyz-N*dot(N,grain.xyz);
        N=normalize(N-surface_grain*filtering*tangent_gradient);
        // 매끈한 정점 법선도 메시의 윤곽에서 시선 뒤로 향할 수 있다.
        // 실제 보이는 표면의 음영 법선을 시선 반구 안에 유지한다.
        float facing=dot(N,V);
        if (facing<.01) N=normalize(N+(.01-facing)*V);
        base_color*=1.0+0.08*filtering*(grain.w-0.5);
    }

    vec3 direct_lighting = vec3(0.0);

    // 광원 개수가 늘어나도 전체 광원 세기는 유지한다.
    // 흐리게 쓸 반사 영상은 면 광원의 대표 샘플만 사용한다. 화면 본문은 모두 쓴다.
    int samples=reflection_capture ? min(light_count,4) : light_count;
    float sample_intensity=light_intensity/float(max(samples,1));

    for (int sample_index=0;sample_index<samples;sample_index++)
    {
        int i=reflection_capture && samples>1
              ? sample_index*(light_count-1)/(samples-1) : sample_index;
        vec3 light_vector = light_positions[i] - world_position;
        float distance_to_light = max(length(light_vector), 0.001);
        vec3 L = light_vector / distance_to_light;

        float NdotL = max(dot(N, L), 0.0);
        // 평평한 발광판의 뒤쪽으로는 빛을 보내지 않는다.
        float emitter_cosine = max(dot(light_normal, -L), 0.0);

        if (NdotL <= 0.0 || emitter_cosine <= 0.0)
            continue;

        float attenuation = (
            1.0 / (distance_to_light * distance_to_light)
        );

        vec3 incoming_light = (
            light_color * sample_intensity * attenuation * emitter_cosine
        );

        float visibility = shadow_visibility(i, N);

        // 재질이 이 방향의 빛을 얼마나 반사하는지 계산한다.
        vec3 brdf = evaluate_brdf(N, V, L, base_color);

        direct_lighting += (
            brdf * incoming_light * NdotL * visibility
            * water_transmission(i) * cup_transmission(i)
        );
    }

    // 기존의 간접광 근사값은 BRDF 밖에서 별도로 더한다.
    vec3 ambient = ambient_strength * ambient_scale * base_color;
    // 둥글게 처리한 아래 모서리에도 바닥과의 접촉 차폐를 적용한다.
    if (contact_occlusion_height>0.0)
        ambient *= smoothstep(0.0,contact_occlusion_height,world_position.y);

    vec3 linear_color = max(
        ambient + direct_lighting + ceiling_indirect(N, V, base_color),
        vec3(0.0)
    );

    if (planar_strength>0.0 && dot(N,V)>0.0) {
        vec4 clip=planar_view_projection*vec4(world_position,1.0);
        vec2 reflected_uv=clip.xy/clip.w*0.5+0.5;
        if (clip.w>0.0 && all(greaterThanEqual(reflected_uv,vec2(0.0)))
                       && all(lessThanEqual(reflected_uv,vec2(1.0)))) {
            vec3 reflected=textureLod(planar_texture,reflected_uv,planar_roughness*6.0).rgb;
            float F=0.04+0.96*pow(1.0-clamp(dot(N,V),0.0,1.0),5.0);
            float weight=clamp(planar_strength*F*(1.0-0.65*planar_roughness),0.0,0.24);
            linear_color=mix(linear_color,reflected,weight);
        }
    }

    final_color = cup_surface && cup_optics_enabled
                  ? cup_transmitted_color(N,V,linear_color,vertex_color.a)
                  : vec4(linear_color,vertex_color.a);
}

"""

FRAGMENT_SOURCE = FRAGMENT_SOURCE.replace("// SHADOW_FUNCTIONS", SHADOW_SOURCE)
FRAGMENT_SOURCE = FRAGMENT_SOURCE.replace("// CUP_OPTICS", CUP_OPTICS_SOURCE)
FRAGMENT_SOURCE = FRAGMENT_SOURCE.replace("// GI_VISIBILITY", VISIBILITY_SOURCE)

def create_program():
    vertex_shader = Shader(VERTEX_SOURCE, "vertex")
    fragment_shader = Shader(FRAGMENT_SOURCE, "fragment")

    return ShaderProgram(vertex_shader, fragment_shader)

