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

uniform bool use_texture;
uniform sampler2D diffuse_texture;

// 한 텍스처 안에서 i번째 광원의 깊이 층을 선택한다.
uniform sampler2DArray shadow_map;
uniform mat4 light_view_projections[MAX_LIGHTS];

float shadow_visibility(int i, vec3 N)
{
    // 현재 표면을 i번째 광원의 시점으로 변환한다.
    vec4 light_position = (
        light_view_projections[i] * vec4(world_position, 1.0)
    );

    if (light_position.w <= 0.0)
        return 1.0;

    vec3 p = light_position.xyz / light_position.w;
    p = p * 0.5 + 0.5;

    if (
        p.x < 0.0 || p.x > 1.0 ||
        p.y < 0.0 || p.y > 1.0 ||
        p.z < 0.0 || p.z > 1.0
    )
        return 1.0;

    vec3 L = normalize(light_positions[i] - world_position);

    float bias = max(
        0.0002 * (1.0 - max(dot(N, L), 0.0)),
        0.00003
    );

    // textureSize의 z는 층 개수이며, xy가 깊이 맵 해상도다.
    vec2 texel_size = (
        1.0 / vec2(textureSize(shadow_map, 0).xy)
    );

    float visibility = 0.0;

    // i번째 광원의 깊이 맵에서 3×3 PCF를 수행한다.
    for (int y = -1; y <= 1; y++)
    {
        for (int x = -1; x <= 1; x++)
        {
            vec2 offset = vec2(x, y) * texel_size;

            float sample_depth = texture(
                shadow_map, vec3(p.xy + offset, float(i))
            ).r;

            visibility += (
                p.z - bias <= sample_depth
            ) ? 1.0 : 0.0;
        }
    }

    return visibility / 9.0;
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
    
    vec3 N = normalize(world_normal);
    if (vertex_color.a < 1.0 && !gl_FrontFacing)
    {
        N = -N;
    }
    vec3 V = normalize(camera_position - world_position);

    vec3 base_color = vertex_color.rgb;
    if (use_texture) {
        vec3 texture_srgb = texture(diffuse_texture, texcoord).rgb; //texture(sample, coord)하면 이미지의 u, v 좌표 읽어줌

        base_color *= pow(texture_srgb, vec3(2.2));
    }

    vec3 direct_lighting = vec3(0.0);

    // 광원 개수가 늘어나도 전체 광원 세기는 유지한다.
    float sample_intensity = (
        light_intensity / float(max(light_count, 1))
    );

    for (int i = 0; i < light_count; i++)
    {
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
        );
    }

    // 기존의 간접광 근사값은 BRDF 밖에서 별도로 더한다.
    vec3 ambient = ambient_strength * ambient_scale * base_color;

    vec3 linear_color = max(
        ambient + direct_lighting,
        vec3(0.0)
    );

    final_color = vec4(linear_color, vertex_color.a);
}

"""

def create_program():
    vertex_shader = Shader(VERTEX_SOURCE, "vertex")
    fragment_shader = Shader(FRAGMENT_SOURCE, "fragment")

    return ShaderProgram(vertex_shader, fragment_shader)

