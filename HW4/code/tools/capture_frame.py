"""완성된 화면의 색 버퍼를 이미지 파일로 저장한다."""

from pathlib import Path

import pyglet


def save_frame(path):
    """on_draw() 끝에서, 화면 버퍼가 교환되기 전에 호출한다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pyglet.image.get_buffer_manager().get_color_buffer().get_image_data().save(str(path))
