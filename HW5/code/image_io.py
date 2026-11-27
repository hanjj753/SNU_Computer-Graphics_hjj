"""Linear radiance, explicit display conversion, and labeled comparisons."""

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def display_image(linear, exposure=2.4):
    mapped = np.maximum(linear, 0.0) * exposure
    mapped = mapped / (1.0 + mapped)
    srgb = np.where(mapped <= 0.0031308, mapped * 12.92,
                    1.055 * np.maximum(mapped, 0.0) ** (1.0 / 2.4) - 0.055)
    return Image.fromarray(np.uint8(np.clip(srgb * 255 + 0.5, 0, 255)))


def save_render(output, linear, stats, exposure, save_linear=False):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    display_image(linear, exposure).save(output)
    if save_linear:
        np.save(output.with_suffix(".npy"), linear.astype(np.float32))
    stats = {**stats, "exposure": exposure, "tone_mapping": "Reinhard, then exact sRGB transfer",
             "output": str(output.resolve())}
    output.with_suffix(".json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")


def contact_sheet(panels, output, panel_size=(480, 360), columns=3):
    width, height = panel_size
    label_height = 42
    rows = (len(panels) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * width, rows * (height + label_height)), (22, 25, 30))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=17)
    for i, (label, source) in enumerate(panels):
        image = source.copy() if isinstance(source, Image.Image) else Image.open(source).convert("RGB")
        image = image.resize(panel_size, Image.Resampling.LANCZOS)
        x, y = i % columns * width, i // columns * (height + label_height)
        sheet.paste(image, (x, y + label_height))
        draw.text((x + 12, y + 11), label, fill=(238, 241, 246), font=font)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    return output
