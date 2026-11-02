import pyglet
from pyglet.math import Mat4
from pyglet.gl import GL_DEPTH_TEST, glIsEnabled, glDisable, glEnable

HELP_TEXT = """
[조작 안내]
마우스 드래그: 회전
Shift + 드래그: 화면 이동
Ctrl + 드래그: 확대/축소
R: 카메라 초기화
Q: 종료
F: Frame 껐다 키기
W: Watch Mode 껐다 키기
T: Timer 껐다 키기

[편집 모드에서]
점 드래그: XZ 이동
Alt + 점 드래그: 높이 조절
Enter: 점 추가
N: 다음 점
X: 점 삭제
Ctrl+S: 저장
"""

class HUD:
    def __init__(self, window):
        self.window = window
        self.show_frames = True
        self.watch_mode = True
        self.batch = pyglet.graphics.Batch()

        self.u_label = pyglet.text.Label("u = 0.000, t = 0.000", font_size=13, anchor_x="left", anchor_y="top", color=(255, 220, 80, 255), batch=self.batch)
        self.help_label = pyglet.text.Label(HELP_TEXT, font_size=10, width=200, multiline=True, anchor_x="right", anchor_y="top", batch=self.batch)

        self.resize(window.width, window.height)

    def resize(self, width, height):
        self.u_label.x, self.u_label.y = 12, height - 12
        self.help_label.x, self.help_label.y = width - 12, height - 12

    def toggleFrames(self):
        self.show_frames = not self.show_frames

    def toggleWatchmode(self) :
        self.watch_mode = not self.watch_mode

    def setU(self, u, t):
        self.u_label.text = f"u = {u:.3f}, t = {t:.3f}"

    def draw(self):
        window = self.window
        projection, view = window.projection, window.view
        depth_enabled = bool(glIsEnabled(GL_DEPTH_TEST))

        glDisable(GL_DEPTH_TEST)
        try: # UI는 화면 좌표로 그리기
            window.projection = Mat4.orthogonal_projection(0, window.width, 0, window.height, -1, 1)
            window.view = Mat4()
            self.batch.draw()
        finally: # 다음 3D 렌더링을 위해 원래 상태 복구
            window.projection, window.view = projection, view
            if depth_enabled: glEnable(GL_DEPTH_TEST)