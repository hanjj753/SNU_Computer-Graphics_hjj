import pyglet
from pyglet.math import Mat4
from pyglet.gl import (
    GL_DEPTH_TEST,
    glIsEnabled,
    glDisable,
    glEnable,
)


HELP_TEXT = """[조작 안내]
왼쪽 드래그: 회전
Shift + 왼쪽 드래그: 화면 이동
Ctrl + 왼쪽 드래그: 확대/축소
R: 카메라 초기화
Q: 종료"""


class HUD:
    def __init__(self, window):
        self.window = window
        self.batch = pyglet.graphics.Batch()

        self.help_label = pyglet.text.Label(
            HELP_TEXT,
            font_name="Malgun Gothic",
            font_size=10,
            width=240,
            multiline=True,
            anchor_x="right",
            anchor_y="top",
            color=(255, 255, 255, 255),
            batch=self.batch,
        )

        self.resize(window.width, window.height)

    def resize(self, width, height):
        self.help_label.x = width - 12
        self.help_label.y = height - 12

    def draw(self):
        window = self.window

        projection = window.projection
        view = window.view
        depth_enabled = bool(glIsEnabled(GL_DEPTH_TEST))

        glDisable(GL_DEPTH_TEST)

        try:
            window.projection = Mat4.orthogonal_projection(
                0, window.width,
                0, window.height,
                -1, 1,
            )
            window.view = Mat4()
            self.batch.draw()
        finally:
            window.projection = projection
            window.view = view

            if depth_enabled:
                glEnable(GL_DEPTH_TEST)