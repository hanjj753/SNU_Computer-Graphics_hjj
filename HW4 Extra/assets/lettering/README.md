# Vertical house names

The default `house_names_cinzel.png` is a transparent, four-column text atlas in
**Cinzel Decorative Bold**, selected by the user. It contains
GRYFFINDOR, SLYTHERIN, RAVENCLAW and HUFFLEPUFF. Each complete word is typeset on one
line and rotated **90 degrees clockwise**, so reading proceeds down the banner.
The text starts lower on the cloth, with a larger gap below the crest.
The current atlas adds **0.14 em of tracking** between letters. Glyph advances and
the added tracking are computed explicitly in `build_lettering.ps1`.
It is lettering made for this scene, separate from the
crest artwork in `assets/crests/`.

The bundled PNG is all that the application needs. The original font and readme are
included in `fonts/` for rebuilding; no system font installation is needed.
`build_lettering.ps1` is an optional Windows/System.Drawing builder.
`metadata.json` records the font and column order.
The scene maps each column onto a flat banner quad and lights the ink as ordinary
cloth, without emission or extra light sources.

Source: [Harry P on DaFont](https://www.dafont.com/harry_p.font),
[author's clarification](https://www.dafont.com/font-comment.php?file=harry_p).
The original `harryp-readme.txt` is preserved unchanged.

`house_names.png` retains **Harry P** by Phoenix Phonts & GeM / GemFonts as an
optional comparison. Cinzel Decorative was designed by Natanael Gama. Its font
and unmodified SIL Open Font License are included as `fonts/CinzelDecorative-Bold.ttf`
and `fonts/CinzelDecorative-OFL.txt`.
Source: [Google Fonts repository](https://github.com/google/fonts/tree/main/ofl/cinzeldecorative).

The application and asset builder default to Cinzel Decorative Bold. Use
`--banner-font harry` to preview the alternative. Both PNGs are bundled, so runtime
font installation is unnecessary.
