"""Load the bundled, photographed Poly Haven CC0 wood material."""
from pathlib import Path
import json
import pyglet
from pyglet.gl import *


def load_wood_set():
    """Execution is entirely offline; the three 1K JPEGs ship with the scene."""
    directory=Path(__file__).resolve().parent/'assets'/'wood'
    textures=[]
    for name in ('diffuse','nor_gl','rough'):
        path=directory/f'{name}.jpg'
        if not path.is_file():raise FileNotFoundError(f'Missing bundled material map: {path}')
        texture=pyglet.image.load(str(path)).get_texture()
        glBindTexture(GL_TEXTURE_2D,texture.id)
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR)
        glGenerateMipmap(GL_TEXTURE_2D)
        textures.append(texture)
    return textures


def load_house_crests():
    """Skip transparent margins with UV bounds; keep the downloaded PNGs intact."""
    directory=Path(__file__).resolve().parent/'assets'/'crests'
    metadata=json.loads((directory/'metadata.json').read_text(encoding='utf-8'))
    textures,bounds=[],[]
    for house in ('gryffindor','slytherin','ravenclaw','hufflepuff'):
        info=metadata[house]
        texture=pyglet.image.load(str(directory/info['file'])).get_texture()
        glBindTexture(GL_TEXTURE_2D,texture.id)
        for axis in (GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T):
            glTexParameteri(GL_TEXTURE_2D,axis,GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR)
        glGenerateMipmap(GL_TEXTURE_2D)
        textures.append(texture)
        bounds.append(info['uv_bounds'])
    return textures,bounds


def load_banner_lettering(filename='house_names_cinzel.png'):
    """A baked font atlas keeps the banner lettering portable and offline."""
    path=Path(__file__).resolve().parent/'assets'/'lettering'/filename
    texture=pyglet.image.load(str(path)).get_texture()
    glBindTexture(GL_TEXTURE_2D,texture.id)
    for axis in (GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T):
        glTexParameteri(GL_TEXTURE_2D,axis,GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR_MIPMAP_LINEAR)
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR)
    glGenerateMipmap(GL_TEXTURE_2D)
    return texture
