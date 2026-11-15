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
out vec4 shadow_position;

uniform mat4 light_view_projection;

uniform WindowBlock
{
    mat4 projection;
    mat4 view;
} window;

uniform mat4 model;

void main() 
{
    vec4 position_world = model * vec4(POSITION, 1.0);
    shadow_position = light_view_projection * position_world;

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

const int MAX_LIGHTS = 64;

uniform vec3 light_positions[MAX_LIGHTS];
uniform int light_count;

uniform vec3 light_color;
uniform float light_intensity;
uniform float ambient_strength;

uniform vec3 camera_position;
uniform vec3 specular_color;
uniform float shininess;

uniform bool use_texture;
uniform sampler2D diffuse_texture;

in vec4 shadow_position;

uniform sampler2D shadow_map;

float shadow_visibility(vec3 N)
{
    // 광원의 뒤쪽은 이 shadow map의 범위 밖이다.
    if (shadow_position.w <= 0.0)
        return 1.0;

    // Clip 좌표 → NDC → 텍스처 좌표 0~1
    vec3 p = shadow_position.xyz / shadow_position.w;
    p = p * 0.5 + 0.5;

    if (
        p.x < 0.0 || p.x > 1.0 ||
        p.y < 0.0 || p.y > 1.0 ||
        p.z < 0.0 || p.z > 1.0
    )
        return 1.0;

    // 광원에서 봤을 때 이 위치에 저장된 가장 가까운 깊이
    float closest_depth = texture(shadow_map, p.xy).r;

    vec3 L = normalize(
        light_positions[0] - world_position
    );

    // 수치 오차로 자기 자신을 그림자로 판단하는 현상을 완화한다.
    float bias = max(
        0.0002 * (1.0 - max(dot(N, L), 0.0)),
        0.00003
    );

    // 현재 표면이 저장된 깊이보다 뒤라면 다른 물체에 가려진 것이다.
    return p.z - bias <= closest_depth ? 1.0 : 0.0;
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

    vec3 diffuse = vec3(0.0);
    vec3 specular = vec3(0.0);

    // 전체 광원의 세기를 각 점광원에 나눠준다.
    float sample_intensity = (
        light_intensity / float(max(light_count, 1))
    );

    for (int i=0;i<light_count;i++) {
        // 표면에서 광원을 향하는 벡터
        vec3 light_vector = light_positions[i] - world_position;
        float distance_to_light = max(length(light_vector), 0.001);
        vec3 L = light_vector / distance_to_light;   
    
        float lambert = max(dot(N, L), 0.0);
        
        float attenuation = 1.0 / (distance_to_light * distance_to_light);
        
        vec3 incoming_light = light_color * sample_intensity * attenuation;
        
        diffuse += base_color * incoming_light * lambert;

        // 빛을 받고 카메라를 향하는 면에서 광택 계산
        if (lambert > 0.0 && dot(N, V) > 0.0) {
            vec3 R = reflect(-L, N); // 법선 기준으로 반사시킴

            float highlight = pow(
                max(dot(R, V), 0.0),
                shininess
            );

            specular += ( //RenderingBasics 30p에 있는 식
                specular_color * incoming_light * highlight
            );
        }
    }

    vec3 ambient = ambient_strength * base_color;

    float visibility = shadow_visibility(N);

    vec3 linear_color = max(
        ambient + visibility * (diffuse + specular),
        vec3(0.0)
    );

    final_color = vec4(linear_color, vertex_color.a);
}

"""

def create_program():
    vertex_shader = Shader(VERTEX_SOURCE, "vertex")
    fragment_shader = Shader(FRAGMENT_SOURCE, "fragment")

    return ShaderProgram(vertex_shader, fragment_shader)

