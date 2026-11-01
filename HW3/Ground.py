import pyglet
from pyglet.gl import GL_TRIANGLES, GL_LINES

class Ground :

    def __init__(self, s=20, y=-0.05):
        self.program = pyglet.graphics.get_default_shader()

        self.plane = self.program.vertex_list_indexed(
            4,
            GL_TRIANGLES,
            [0, 1, 2, 0, 2, 3],
            position=("f", (
                -s, y, -s,
                -s, y,  s,
                 s, y,  s,
                 s, y, -s,
            )),
            colors=("Bn", (50, 65, 50, 255) * 4),
        )

    def draw(self) :
        self.program.use()
        self.plane.draw(GL_TRIANGLES)
        self.program.stop()