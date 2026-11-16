from pyglet.gl import GL_TRIANGLES
from pyglet.graphics.shader import Shader, ShaderProgram


LIGHT_VERTEX = """
#version 330 core
in vec3 POSITION;

uniform WindowBlock
{
    mat4 projection;
    mat4 view;
} window;

void main()
{
    gl_Position = window.projection * window.view * vec4(POSITION, 1.0);
}
"""

LIGHT_FRAGMENT = """
#version 330 core
out vec4 final_color;
uniform vec3 emission;

void main()
{
    // 발광판은 아래쪽에서만 보인다.
    if (!gl_FrontFacing)
        discard;
    final_color = vec4(emission, 1.0);
}
"""


class CeilingLight:
    def __init__(self, center, width, depth, color, brightness=40.0):
        self.program = ShaderProgram(
            Shader(LIGHT_VERTEX, "vertex"),
            Shader(LIGHT_FRAGMENT, "fragment"),
        )
        self.emission = tuple(channel * brightness for channel in color)
        x, y, z = center
        x0, x1 = x - width / 2, x + width / 2
        z0, z1 = z - depth / 2, z + depth / 2

        # 아래쪽(-Y)이 앞면이 되도록 정점 순서를 지정한다.
        self.vertices = self.program.vertex_list(
            6, GL_TRIANGLES,
            POSITION=("f", (
                x0, y, z0, x1, y, z0, x1, y, z1,
                x0, y, z0, x1, y, z1, x0, y, z1,
            )),
        )

    def draw(self):
        # 이 면은 보이는 광원이고, 조명·그림자는 점 샘플들이 계산한다.
        self.program.use()
        self.program["emission"] = self.emission
        self.vertices.draw(GL_TRIANGLES)
