import pyglet

from pyglet.gl import *
from pyglet.image.buffer import Framebuffer, Renderbuffer


class SrgbTarget:
    def __init__(self):
        # 첫 begin() 호출 또는 창 크기 변경을 감지하기 위한 값.
        self.size = (0, 0)

        # FBO와 실제 저장소는 첫 begin()에서 생성한다.
        self.fbo = None

    def begin(self, window):
        # 창의 논리 크기 대신 실제 framebuffer 픽셀 크기를 사용한다.
        # 고해상도 디스플레이에서는 두 크기가 다를 수 있다.
        w, h = window.get_framebuffer_size()

        # GPU 저장소의 크기가 0이 되지 않도록 한다.
        w, h = max(1, w), max(1, h)

        # 첫 프레임 또는 창 크기가 바뀐 경우에만 다시 만든다.
        if self.size != (w, h):
            if self.fbo is not None:
                # 이전 크기의 GPU 저장소를 먼저 해제한다.
                self.fbo.delete()
                self.color.delete()
                self.depth.delete()

            # 최종 색을 저장할 텍스처.
            # RGB는 sRGB 형식의 각 8비트, alpha는 8비트다.
            #
            # blank_data=False이므로 초기 픽셀값은 채우지 않는다.
            # main의 window.clear()가 매 프레임 초기화한다.
            self.color = pyglet.image.Texture.create(
                w, h,
                internalformat=GL_SRGB8_ALPHA8,
                min_filter=GL_NEAREST,
                mag_filter=GL_NEAREST,
                blank_data=False,
            )

            # 가까운 표면을 판별하기 위한 24비트 깊이 저장소.
            # 셰이더에서 읽을 필요가 없으므로 Renderbuffer를 사용한다.
            self.depth = Renderbuffer(
                w, h, GL_DEPTH_COMPONENT24
            )

            # FBO는 색과 깊이 저장소를 연결하는 '묶음'이다.
            # 실제 픽셀 데이터는 위의 color와 depth에 저장된다.
            self.fbo = Framebuffer()

            # 기본 색 attachment인 COLOR_ATTACHMENT0에 연결한다.
            self.fbo.attach_texture(self.color)

            self.fbo.attach_renderbuffer(
                self.depth,
                attachment=GL_DEPTH_ATTACHMENT,
            )

            # 완전성 검사는 현재 연결된 FBO를 대상으로 한다.
            self.fbo.bind()

            if not self.fbo.is_complete:
                raise RuntimeError(self.fbo.get_status())

            self.size = (w, h)

        # 이후 draw 호출의 목적지를 이 FBO로 지정한다.
        # 따라서 main에서 호출하는 window.clear()도 여기를 지운다.
        self.fbo.bind()

        # 그릴 픽셀 영역을 저장소 크기에 맞춘다.
        glViewport(0, 0, w, h)

        # 셰이더는 조명을 계산한 선형 RGB를 출력한다.
        #
        # GPU는:
        # 1. 기존 sRGB 색을 선형 값으로 읽고
        # 2. 선형 공간에서 alpha blending을 수행한 뒤
        # 3. 결과를 다시 sRGB 형식으로 저장한다.
        #
        # alpha에는 감마 변환을 적용하지 않는다.
        glEnable(GL_FRAMEBUFFER_SRGB)

    def present(self):
        w, h = self.size

        # 색은 이미 sRGB로 저장되어 있다.
        # 창으로 복사하면서 추가 변환하지 않도록 끈다.
        glDisable(GL_FRAMEBUFFER_SRGB)

        # 읽을 곳: 계산용 FBO
        glBindFramebuffer(GL_READ_FRAMEBUFFER, self.fbo.id)

        # 쓸 곳: 실제 창의 기본 framebuffer
        # OpenGL에서 framebuffer 0은 기본 framebuffer를 의미한다.
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0)

        # 계산용 화면의 색을 창 전체에 복사한다.
        # 앞 사각형은 원본 영역, 뒤 사각형은 목적지 영역이다.
        # 깊이는 복사하지 않고 색만 복사한다.
        glBlitFramebuffer(
            0, 0, w, h,
            0, 0, w, h,
            GL_COLOR_BUFFER_BIT,
            GL_NEAREST,
        )

        # 읽기와 쓰기 대상을 모두 창으로 돌린다.
        # 이후 HUD가 계산용 화면이 아닌 실제 창에 그려진다.
        glBindFramebuffer(GL_FRAMEBUFFER, 0)