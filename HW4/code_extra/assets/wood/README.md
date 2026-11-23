# Wood Table 001

Source: [Poly Haven — Wood Table 001](https://polyhaven.com/a/wood_table_001)

Authors: Dimitrios Savva (photography), Rico Cilliers (processing).

License: [CC0](https://polyhaven.com/license). Redistribution with this assignment is permitted.

Bundled 1K JPEG maps, downloaded without modification:

- `diffuse.jpg`: `wood_table_001_diff_1k.jpg` (sRGB color, decoded in shader).
- `nor_gl.jpg`: `wood_table_001_nor_gl_1k.jpg` (OpenGL tangent-space normal, linear data).
- `rough.jpg`: `wood_table_001_rough_1k.jpg` (roughness, linear data).

The original public API response, including source URLs and MD5 checksums, is preserved in `source.json`. The renderer applies a dark oak tint and reduced normal strength. The third map is used as `gloss = 1 - sample.r` and scales the material's Phong shininess by `mix(0.55, 1.10, gloss)`; it does not alter the source image.
