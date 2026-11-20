"""래스터화한 깊이·배경·환경맵으로 물의 반사와 굴절을 근사한다."""

from ctypes import byref

import pyglet
from pyglet.gl import *
from pyglet.graphics.shader import Shader, ShaderProgram
from pyglet.image.buffer import Framebuffer, Renderbuffer
from pyglet.math import Mat4, Vec3, Vec4

from water_surface import MENISCUS_HEIGHT, MENISCUS_WIDTH, meniscus_height
from lighting import SHADOW_SOURCE


WATER_IOR = 1.333
CUP_IOR = 1.49  # 실측값이 아닌 투명 플라스틱의 굴절률 근사값.
# 사진의 굴절량을 맞추는 화면 공간 보정값. 플라스틱의 산란은 cup_optics에서 처리한다.
REFRACTION_STRENGTH = 2.5
# 장면 단위당 RGB 흡수 계수. 실측값이 아닌 사진 조절용 값이다.
ABSORPTION = (0.18, 0.07, 0.035)
ENVIRONMENT_SIZE = 256
WATER_SHININESS = 128.0
REFLECTION_LOD = 1.0
# 넓게 퍼지는 접촉선 반사를 사진에 맞춘 시각적 보정값.
# 실제 접촉선의 복잡한 곡률을 단순화했으므로 세기는 사진에 맞춘 보정값이다.
MENISCUS_SPECULAR_STRENGTH = 80.0
MENISCUS_SHININESS = 8.0

WATER_VERTEX = """
#version 330 core
in vec3 POSITION;
in vec3 NORMAL;
out vec3 world_position;
out vec3 world_normal;
out float free_surface;
uniform WindowBlock { mat4 projection; mat4 view; } window;
void main() {
    world_position = POSITION;
    world_normal = NORMAL;
    // 수면만 공기와 접한다. 옆면/바닥은 컵의 플라스틱 안쪽에 접한다.
    free_surface = NORMAL.y >= 0.0 ? 1.0 : 0.0;
    gl_Position = window.projection * window.view * vec4(POSITION, 1.0);
}
"""

DEPTH_VERTEX = """
#version 330 core
in vec3 POSITION;
uniform WindowBlock { mat4 projection; mat4 view; } window;
void main() {
    gl_Position = window.projection * window.view * vec4(POSITION, 1.0);
}
"""

WATER_FRAGMENT = """
#version 330 core
in vec3 world_position;
in vec3 world_normal;
in float free_surface;
out vec4 final_color;
uniform WindowBlock { mat4 projection; mat4 view; } window;
uniform mat4 inverse_projection;
uniform vec3 camera_position;
uniform vec2 viewport_size;
uniform float water_ior;
uniform float cup_ior;
uniform vec4 cup_wall_profile; // lower y, upper y, lower thickness, upper thickness
uniform float cup_base_thickness;
uniform float water_top;
uniform vec2 water_center_xz;
uniform float water_radius;
uniform float refraction_strength;
uniform vec3 absorption;
uniform bool camera_inside;
uniform sampler2D scene_color;
uniform sampler2D scene_depth;
uniform sampler2D water_front_depth;
uniform sampler2D water_back_depth;
uniform samplerCube environment_map;
const int MAX_LIGHTS = 16;
uniform vec3 light_positions[MAX_LIGHTS];
uniform int light_count;
uniform vec3 light_color;
uniform vec3 light_normal;
uniform float light_intensity;
uniform float water_shininess;
uniform float reflection_lod;
uniform float meniscus_specular_strength;
uniform float meniscus_shininess;
// SHADOW_FUNCTIONS

vec3 direct_reflection(vec3 N,vec3 V,float f0,float power) {
    vec3 result=vec3(0.0);
    for(int i=0;i<light_count;i++) {
        vec3 vector=light_positions[i]-world_position;
        float distance_squared=max(dot(vector,vector),0.0001);
        vec3 L=normalize(vector);
        float cosine=max(dot(N,L),0.0);
        float emitter=max(dot(light_normal,-L),0.0);
        vec3 H=normalize(L+V);
        float F=f0+(1.0-f0)*pow(1.0-max(dot(V,H),0.0),5.0);
        float lobe=(power+2.0)/(2.0*3.141592653589793)
                   *pow(max(dot(reflect(-L,N),V),0.0),power);
        result+=F*lobe*cosine*emitter*light_color*light_intensity
                /float(max(light_count,1))/distance_squared*shadow_visibility(i,N);
    }
    return result;
}

vec3 view_position(vec2 uv, float depth) {
    vec4 p = inverse_projection * vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    return p.xyz / p.w;
}

vec2 project_uv(vec3 p) {
    vec4 clip = window.projection * vec4(p, 1.0);
    return clip.xy / clip.w * 0.5 + 0.5;
}

void main() {
    vec2 uv = gl_FragCoord.xy / viewport_size;
    vec3 N = normalize(world_normal);
    vec3 V = normalize(camera_position - world_position);
    if (dot(N, V) < 0.0) N = -N;

    // 공기→물은 eta=1/IOR, 물 안에서 밖을 보면 eta=IOR.
    float eta = camera_inside ? water_ior : 1.0 / water_ior;
    vec3 I = -V;
    vec3 T = refract(I, N, eta);
    bool through_cup=!camera_inside && free_surface<0.5 && cup_wall_profile.z>0.0;
    vec3 in_plastic=I;
    float plastic_path=0.0;
    float air_wall_path=0.0;
    if (through_cup) {
        // 얇은 평행 벽의 두 경계: 공기→플라스틱→물.
        // 방향의 합성은 공기→물과 같지만, 플라스틱 두께만큼 옆으로 이동한다.
        in_plastic=refract(I,N,1.0/cup_ior);
        T=refract(in_plastic,N,cup_ior/water_ior);
        float height_fraction=clamp((world_position.y-cup_wall_profile.x)
                                  /max(cup_wall_profile.y-cup_wall_profile.x,1e-5),0.0,1.0);
        float wall_thickness=mix(cup_wall_profile.z,cup_wall_profile.w,height_fraction);
        if (world_normal.y<-.5) wall_thickness=cup_base_thickness;
        plastic_path=wall_thickness/max(abs(dot(in_plastic,N)),0.2);
        air_wall_path=wall_thickness/max(abs(dot(I,N)),0.2);
    }
    float cosine = clamp(dot(N, V), 0.0, 1.0);
    // 얇은 컵을 거친 전체 굴절 방향은 위의 공기→물 근사를 유지한다.
    // 반사되는 몫은 실제 접촉 매질을 구분해, 옆면에 가짜 공기층이 생기는 것을 줄인다.
    float outside_ior = free_surface > 0.5 ? 1.0 : cup_ior;
    float f0 = pow((water_ior-outside_ior)/(water_ior+outside_ior), 2.0);
    float F = f0 + (1.0 - f0) * pow(1.0 - cosine, 5.0);
    if (abs(water_ior - 1.0) < 1e-5) F = 0.0;
    bool total_internal_reflection = dot(T, T) < 1e-6;
    if (total_internal_reflection) F = 1.0;

    vec3 p = (window.view * vec4(world_position, 1.0)).xyz;
    float exit_depth = texture(water_back_depth, uv).r;
    vec3 exit_position = view_position(uv, exit_depth);
    // 앞/뒤 경계의 거리는 굴절되기 전 경로의 두께 근사다.
    float thickness = exit_depth < 1.0 ? clamp(length(exit_position - p), 0.0, 1.0) : 0.0;
    if (camera_inside) thickness = min(length(p), 1.0);

    vec2 refracted_uv = uv;
    float refraction_weight = 0.0;
    if (!total_internal_reflection) {
        vec3 incident_view = mat3(window.view) * I;
        vec3 transmitted_view = mat3(window.view) * T;
        // 같은 두께를 진행했을 때 직진 경로와 굴절 경로의 투영 위치 차이.
        // 삼각형 교차 검색이나 ray marching 없이 배경 텍스처의 UV만 옮긴다.
        vec2 offset = project_uv(p + transmitted_view * thickness)
                    - project_uv(p + incident_view * thickness);
        float size = length(offset);
        offset *= min(1.0, 0.040 / max(size, 1e-6));
        // 경계에서 두께가 0에 가까워지면 왜곡도 연속적으로 줄인다.
        offset *= smoothstep(0.0, 0.025, thickness);
        // 접촉선 바로 아래에서 위쪽 배경이 두꺼운 띠로 늘어나는 것을 줄인다.
        // 경계를 실제로 추적하지 않는 화면 공간 굴절 근사에 대한 보정이다.
        if (free_surface < 0.5)
            offset *= smoothstep(0.0, 0.04, water_top-world_position.y);
        vec2 plastic_offset=vec2(0.0);
        if (through_cup) {
            vec3 plastic_view=mat3(window.view)*in_plastic;
            plastic_offset=project_uv(p+plastic_view*plastic_path)
                          -project_uv(p+incident_view*air_wall_path);
            float plastic_size=length(plastic_offset);
            plastic_offset*=min(1.0,0.004/max(plastic_size,1e-6));
        }
        vec2 candidate = uv + refraction_strength * offset + plastic_offset;
        bool in_screen = all(greaterThanEqual(candidate, vec2(0.0)))
                      && all(lessThanEqual(candidate, vec2(1.0)));
        // 물 앞의 불투명 물체와 물 실루엣 밖의 색이 굴절로 새어 들어오는 것을 막는다.
        if (in_screen && texture(scene_depth, candidate).r >= gl_FragCoord.z - 0.00002
                      && texture(water_front_depth, candidate).r < 1.0) {
            refracted_uv = candidate;
            // 실루엣 바깥을 읽을 때 갑자기 원래 UV로 돌아가는 대신,
            // 주변 4개 픽셀의 물 마스크로 굴절 색을 부드럽게 섞는다.
            vec2 texel = 1.0/viewport_size;
            for (int y=-1; y<=1; y+=2) for (int x=-1; x<=1; x+=2) {
                float depth = texture(water_front_depth,candidate+vec2(x,y)*texel).r;
                refraction_weight += depth < 1.0 ? 0.25 : 0.0;
            }
        }
    }

    vec3 transmitted = mix(texture(scene_color,uv).rgb,
                           texture(scene_color,refracted_uv).rgb,refraction_weight);
    transmitted *= exp(-absorption * thickness);
    // 환경맵에서 발광판을 제외했으므로 직접 반사와 광원을 중복 계산하지 않는다.
    vec3 reflected = textureLod(environment_map, reflect(I, N), reflection_lod).rgb;
    vec3 color = mix(transmitted,reflected,F)+direct_reflection(N,V,f0,water_shininess);

    // 사진의 밝은 수면 테두리: 접촉선의 복잡한 곡률을 유효 법선으로 근사한다.
    // 컵 alpha나 물의 난반사색을 올리지 않고, 광원에서 온 정반사만 더한다.
    vec2 radial = world_position.xz-water_center_xz;
    float radius = length(radial);
    float radial_band = 1.0-smoothstep(0.0015,0.010,abs(water_radius-radius));
    float line_width = max(0.006,1.25*fwidth(world_position.y));
    float height_band = exp(-pow((water_top-world_position.y)/line_width,2.0));
    float contact = radial_band*height_band;
    if (!camera_inside && contact>0.001 && meniscus_specular_strength>0.0) {
        vec2 radial_direction=radial/max(radius,1e-5);
        float facing=dot(radial_direction,V.xz/max(length(V.xz),1e-5));
        float front=smoothstep(-0.25,0.25,facing);
        // 뒤쪽 메니스커스는 컵 안쪽을 향해 기울어져 카메라 쪽으로 빛을 보낸다.
        vec3 front_normal=normalize(vec3(radial_direction.x,1.25,radial_direction.y));
        vec3 rear_normal=normalize(vec3(-radial_direction.x,1.25,-radial_direction.y));
        vec3 contact_normal=normalize(mix(rear_normal,front_normal,front));
        float air_f0 = pow((water_ior-1.0)/(water_ior+1.0),2.0);
        color += contact*meniscus_specular_strength
               * direct_reflection(contact_normal,V,air_f0,meniscus_shininess);
    }
    // 반사와 투과를 한 번에 계산한 색이며 추가 alpha 합성은 하지 않는다.
    final_color = vec4(color,1.0);
}
"""
WATER_FRAGMENT = WATER_FRAGMENT.replace("// SHADOW_FUNCTIONS",SHADOW_SOURCE)


class WaterRenderer:
    def __init__(self):
        self.program = ShaderProgram(Shader(WATER_VERTEX, "vertex"), Shader(WATER_FRAGMENT, "fragment"))
        self.depth_program = ShaderProgram(Shader(DEPTH_VERTEX, "vertex"), Shader("#version 330 core\nvoid main() {}", "fragment"))
        self.size = (0, 0)
        self.environment_dirty = True
        self.ior = WATER_IOR
        self.cup_ior = CUP_IOR
        self.cup_wall_profile = (0.0,1.0,0.0,0.0)
        self.cup_base_thickness = 0.0
        self.refraction_strength = REFRACTION_STRENGTH
        self.absorption = ABSORPTION
        self.meniscus_specular_strength = MENISCUS_SPECULAR_STRENGTH
        self._create_environment()

    def set_cup(self, cup_mesh):
        lo=cup_mesh.inner_profile[0][0]
        hi=cup_mesh.rim_base_y
        self.cup_wall_profile=(lo,hi,cup_mesh.wall_thickness(lo),cup_mesh.wall_thickness(hi))
        self.cup_base_thickness=cup_mesh.base_thickness

    def set_mesh(self, positions, normals):
        self.positions, self.normals = positions, normals
        self.vertices = self.program.vertex_list(
            len(positions) // 3, GL_TRIANGLES,
            POSITION=("f", positions), NORMAL=("f", normals),
        )
        self.depth_vertices = self.depth_program.vertex_list(
            len(positions) // 3, GL_TRIANGLES, POSITION=("f", positions),
        )
        bounds = [(min(positions[i::3]), max(positions[i::3])) for i in range(3)]
        self.center = Vec3(*((a + b) / 2 for a, b in bounds))
        self.bottom, self.top = bounds[1]
        self.radius = (bounds[0][1] - bounds[0][0]) / 2
        self.lower_radius = max(
            ((positions[i] - self.center.x)**2 + (positions[i + 2] - self.center.z)**2)**0.5
            for i in range(0, len(positions), 3) if abs(positions[i + 1] - self.bottom) < 1e-6
        )

    def _camera_inside(self, window):
        p = (~window.view) @ Vec4(0, 0, 0, 1)
        radius = ((p.x - self.center.x)**2 + (p.z - self.center.z)**2)**0.5
        height_fraction = (p.y - self.bottom) / (self.top - self.bottom)
        wall_radius = self.lower_radius + (self.radius - self.lower_radius) * height_fraction
        t = max(0.0, min(1.0, (radius - self.radius + MENISCUS_WIDTH) / MENISCUS_WIDTH))
        surface_y = self.top - MENISCUS_HEIGHT + meniscus_height(t)
        return self.bottom < p.y < surface_y and radius < wall_radius

    def _create_environment(self):
        self.environment = GLuint()
        glGenTextures(1, byref(self.environment))
        glBindTexture(GL_TEXTURE_CUBE_MAP, self.environment.value)
        for face in range(6):
            glTexImage2D(GL_TEXTURE_CUBE_MAP_POSITIVE_X + face, 0, GL_RGBA16F,
                         ENVIRONMENT_SIZE, ENVIRONMENT_SIZE, 0, GL_RGBA, GL_FLOAT, None)
        glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        for axis in (GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_TEXTURE_WRAP_R):
            glTexParameteri(GL_TEXTURE_CUBE_MAP, axis, GL_CLAMP_TO_EDGE)
        glBindTexture(GL_TEXTURE_CUBE_MAP, 0)
        self.environment_fbo = Framebuffer()
        self.environment_depth = Renderbuffer(ENVIRONMENT_SIZE, ENVIRONMENT_SIZE, GL_DEPTH_COMPONENT24)
        self.environment_fbo.attach_renderbuffer(self.environment_depth, attachment=GL_DEPTH_ATTACHMENT)

    def capture_environment(self, window, scene_program, draw_opaque):
        """고정 장면은 최초 한 번, 물 중앙에서 여섯 방향으로 래스터화한다."""
        if not self.environment_dirty:
            return
        projection, view = window.projection, window.view
        camera_position = scene_program["camera_position"]
        viewport = (GLint * 4)()
        glGetIntegerv(GL_VIEWPORT, viewport)
        previous_fbo = GLint()
        glGetIntegerv(GL_FRAMEBUFFER_BINDING, byref(previous_fbo))
        directions = (
            (Vec3(1, 0, 0), Vec3(0, -1, 0)), (Vec3(-1, 0, 0), Vec3(0, -1, 0)),
            (Vec3(0, 1, 0), Vec3(0, 0, 1)), (Vec3(0, -1, 0), Vec3(0, 0, -1)),
            (Vec3(0, 0, 1), Vec3(0, -1, 0)), (Vec3(0, 0, -1), Vec3(0, -1, 0)),
        )
        try:
            self.environment_fbo.bind()
            glViewport(0, 0, ENVIRONMENT_SIZE, ENVIRONMENT_SIZE)
            glDisable(GL_BLEND)
            glDisable(GL_CULL_FACE)
            glEnable(GL_DEPTH_TEST)
            glDepthMask(GL_TRUE)
            window.projection = Mat4.perspective_projection(1.0, z_near=0.01, z_far=100.0, fov=90)
            scene_program["camera_position"] = tuple(self.center)
            for face, (direction, up) in enumerate(directions):
                glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                                       GL_TEXTURE_CUBE_MAP_POSITIVE_X + face, self.environment.value, 0)
                if not self.environment_fbo.is_complete:
                    raise RuntimeError(self.environment_fbo.get_status())
                window.view = Mat4.look_at(self.center, self.center + direction, up)
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                draw_opaque()
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_CUBE_MAP, self.environment.value)
            glGenerateMipmap(GL_TEXTURE_CUBE_MAP)
            glBindTexture(GL_TEXTURE_CUBE_MAP, 0)
            self.environment_dirty = False
        finally:
            window.projection, window.view = projection, view
            scene_program["camera_position"] = camera_position
            glBindFramebuffer(GL_FRAMEBUFFER, previous_fbo.value)
            glViewport(*viewport)

    def _resize(self, window):
        size = tuple(max(1, n) for n in window.get_framebuffer_size())
        if size == self.size:
            return
        if self.size != (0, 0):
            for fbo in (self.front_fbo, self.back_fbo, self.scene_fbo):
                fbo.delete()
            for texture in (self.front_depth, self.back_depth, self.scene_depth, self.scene_color):
                texture.delete()
        self.size = size

        def texture(depth=False):
            tex = pyglet.image.Texture.create(
                *size, internalformat=GL_DEPTH_COMPONENT24 if depth else GL_RGBA16F,
                fmt=GL_DEPTH_COMPONENT if depth else GL_RGBA,
                min_filter=GL_NEAREST if depth else GL_LINEAR,
                mag_filter=GL_NEAREST if depth else GL_LINEAR, blank_data=False,
            )
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            return tex

        self.front_depth, self.back_depth = texture(True), texture(True)
        self.scene_depth, self.scene_color = texture(True), texture()
        self.front_fbo, self.back_fbo, self.scene_fbo = Framebuffer(), Framebuffer(), Framebuffer()
        for fbo, depth in ((self.front_fbo, self.front_depth), (self.back_fbo, self.back_depth), (self.scene_fbo, self.scene_depth)):
            fbo.attach_texture(depth, attachment=GL_DEPTH_ATTACHMENT)
            if fbo is self.scene_fbo:
                fbo.attach_texture(self.scene_color)
            fbo.bind()
            if fbo is not self.scene_fbo:
                glDrawBuffer(GL_NONE)
                glReadBuffer(GL_NONE)
            if not fbo.is_complete:
                raise RuntimeError(fbo.get_status())
        glBindTexture(GL_TEXTURE_2D, 0)

    def prepare_depth(self, window, render_target):
        """물의 앞/뒤 경계 깊이를 따로 래스터화한다."""
        self._resize(window)
        # 컵의 합성 순서를 나누고 물속을 통과하는 두께를 구할 때 쓴다.
        glViewport(0, 0, *self.size)
        glEnable(GL_CULL_FACE)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)
        self.depth_program.use()
        inside = self._camera_inside(window)
        try:
            for fbo, cull in ((self.front_fbo, GL_FRONT if inside else GL_BACK),
                              (self.back_fbo, GL_BACK if inside else GL_FRONT)):
                fbo.bind()
                glCullFace(cull)
                glClear(GL_DEPTH_BUFFER_BIT)
                self.depth_vertices.draw(GL_TRIANGLES)
        finally:
            glCullFace(GL_BACK)
            glDisable(GL_CULL_FACE)
            render_target.fbo.bind()

    def capture_scene(self, render_target):
        """그리는 HDR 텍스처를 동시에 읽지 않도록 별도 저장소에 복사한다."""
        glBindFramebuffer(GL_READ_FRAMEBUFFER, render_target.fbo.id)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, self.scene_fbo.id)
        glBlitFramebuffer(0, 0, *self.size, 0, 0, *self.size,
                          GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT, GL_NEAREST)
        render_target.fbo.bind()

    def draw(self, window):
        camera = (~window.view) @ Vec4(0, 0, 0, 1)
        inside = self._camera_inside(window)
        self.program.use()
        self.program["camera_position"] = (camera.x, camera.y, camera.z)
        self.program["inverse_projection"] = ~window.projection
        self.program["viewport_size"] = self.size
        self.program["water_ior"] = self.ior
        self.program["cup_ior"] = self.cup_ior
        self.program["cup_wall_profile"] = self.cup_wall_profile
        self.program["cup_base_thickness"] = self.cup_base_thickness
        self.program["water_top"] = self.top
        self.program["water_center_xz"] = (self.center.x,self.center.z)
        self.program["water_radius"] = self.radius
        self.program["refraction_strength"] = self.refraction_strength
        self.program["absorption"] = self.absorption
        self.program["camera_inside"] = inside
        self.program["water_shininess"] = WATER_SHININESS
        self.program["reflection_lod"] = REFLECTION_LOD
        self.program["meniscus_specular_strength"] = self.meniscus_specular_strength
        self.program["meniscus_shininess"] = MENISCUS_SHININESS
        textures = (("scene_color", self.scene_color.id), ("scene_depth", self.scene_depth.id),
                    ("water_front_depth", self.front_depth.id), ("water_back_depth", self.back_depth.id))
        for unit, (name, texture) in enumerate(textures, 2):
            glActiveTexture(GL_TEXTURE0 + unit)
            glBindTexture(GL_TEXTURE_2D, texture)
            self.program[name] = unit
        glActiveTexture(GL_TEXTURE6)
        glBindTexture(GL_TEXTURE_CUBE_MAP, self.environment.value)
        self.program["environment_map"] = 6
        glEnable(GL_TEXTURE_CUBE_MAP_SEAMLESS)
        glDisable(GL_BLEND)
        glEnable(GL_CULL_FACE)
        glCullFace(GL_FRONT if inside else GL_BACK)
        glDepthMask(GL_TRUE)
        try:
            self.vertices.draw(GL_TRIANGLES)
        finally:
            glCullFace(GL_BACK)
            glDisable(GL_CULL_FACE)
            for unit in range(2, 6):
                glActiveTexture(GL_TEXTURE0 + unit)
                glBindTexture(GL_TEXTURE_2D, 0)
            glActiveTexture(GL_TEXTURE6)
            glBindTexture(GL_TEXTURE_CUBE_MAP, 0)
            glActiveTexture(GL_TEXTURE0)
