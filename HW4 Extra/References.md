# References and scope

- [SNU Computer Graphics — Programming Assignment #4](https://sites.google.com/view/snucse-graphics2026/programming-assignment-4): 별도의 Cornell-box 장면, 여러 작은 광원, 복잡한 재질, mapping, shadow mapping의 과제 요구사항.
- [The Great Hall — Official Harry Potter Encyclopedia](https://www.harrypotter.com/fact-file/locations/the-great-hall): 공중 촛불과 연회장을 시각적 모티프로 사용했다. 영화의 전체 세트나 공식 3D 모델을 복제한 것은 아니다.
- [Logoshirt — Four Houses breakfast boards](https://www.logoshirt-shop.de/en/Breakfast-Boards/Harry-Potter-Four-Houses-Set-of-4-Breakfast-Boards-Retro.html): 사용자가 지정한 문장 디자인과 리본 글씨의 시각적 참고다. 단순한 핀 모양 방패를 동물·투구·장식·리본이 있는 문장으로 교체했다.
- [Gryffindor](https://www.pngaaa.com/detail/2317673), [Slytherin](https://www.pngaaa.com/detail/99898), [Ravenclaw](https://www.pngaaa.com/detail/3441416), [Hufflepuff](https://www.pngaaa.com/detail/4381685): 실제 사용한 투명 PNG의 배포 페이지다. 저작권·상표는 Warner Bros.와 J.K. Rowling에 귀속된다. 원본 URL과 비상업적 사용 표기는 `assets/crests/README.md`에 기록했으며, 목재의 CC0와 구분한다.
- [Wood Table 001 — Poly Haven](https://polyhaven.com/a/wood_table_001): Dimitrios Savva(photography), Rico Cilliers(processing)의 1K diffuse, OpenGL normal, roughness maps. [CC0 license](https://polyhaven.com/license). `assets/wood/`에 동봉하고 식탁·벤치·의자에 사용했다. 원본 API metadata는 `source.json`에 보존했다.
- [Physically Based Rendering in Filament](https://google.github.io/filament/main/filament.html): Cook–Torrance, GGX, height-correlated Smith visibility, Schlick Fresnel, metallic/roughness와 normal mapping의 수식·개념. Filament 엔진을 사용한 것은 아니다. 화면 공간 차폐는 자체 소규모 구현이며 물리적인 간접광 전용 AO와 구분한다.
- [Khronos — glDrawElementsInstanced](https://registry.khronos.org/OpenGL-Refpages/gl4/html/glDrawElementsInstanced.xhtml): 반복 형상에 model/material instance attributes를 적용한다.
- [Khronos — glFramebufferTextureLayer](https://registry.khronos.org/OpenGL-Refpages/gl4/html/glFramebufferTextureLayer.xhtml): 8개 shadow depth map을 texture array에 저장한다.
- [Khronos — glFramebufferTexture2D](https://registry.khronos.org/OpenGL-Refpages/gl4/html/glFramebufferTexture2D.xhtml): 평면 반사, cubemap face, HDR render target.
- [Khronos — glBlitFramebuffer](https://registry.khronos.org/OpenGL-Refpages/gl4/html/glBlitFramebuffer.xhtml): 4× MSAA의 색·깊이를 단일 sample texture로 resolve한다.
- [Khronos — glBlendFunc](https://registry.khronos.org/OpenGL-Refpages/gl4/html/glBlendFunc.xhtml): 유리의 standard alpha composition.
- [NVIDIA GPU Gems — Real-Time Glow](https://developer.nvidia.com/gpugems/gpugems/part-iv-image-processing/chapter-21-real-time-glow): 밝은 영역을 추출·축소·blur한 뒤 원본 HDR에 더하는 bloom의 기본 흐름.
- [Krzysztof Narkowicz — ACES Filmic Tone Mapping Curve](https://knarkowicz.wordpress.com/2016/01/06/aces-filmic-tone-mapping-curve/): 계수 2.51, 0.03, 2.43, 0.59, 0.14의 fitted display curve. 전체 ACES 색 관리 파이프라인은 아니다.
- [NVIDIA — FXAA white paper](https://developer.download.nvidia.com/assets/gamedev/files/sdk/11/FXAA_WhitePaper.pdf): 주변 휘도로 방향을 추정하는 edge filtering 개념. 공식 FXAA 전체 구현을 이식한 것은 아니다.
- [pyglet documentation](https://docs.pyglet.org/en/latest/): 창·입력·OpenGL 바인딩·수학·HUD·PNG 저장.

## Assets and coding agent

외부 모델을 다운로드하지 않았으며, 회전체와 기본 mesh를 코드로 생성했다. 외부 bitmap은 위에 적은 Poly Haven 목재 재질 3장과 문장 PNG 4장이다. 기숙사 이름의 글자 atlas는 사용자가 선택한 **Cinzel Decorative Bold**를 기본으로 System.Drawing으로 렌더링했다. 비교용 Harry P는 Phoenix Phonts & GeM / GemFonts가 제작했으며 [배포 페이지](https://www.dafont.com/harry_p.font)와 원본 readme도 기록했다. 생성 스크립트·PNG·원본 글꼴은 `assets/lettering/`에 동봉했다. 각 단어 전체를 90도 회전시켰으며 시스템에 글꼴을 설치하지 않고도 실행된다. 나머지 석재·천·음식 표면은 절차적으로 계산한다. 떠다니는 책 6권은 기존 mesh와 material을 재사용하며, 책마다 다른 방향·힌지 각도를 설정하고 위치·회전·펼친 각도를 시간 함수로 바꾼다. HUD에는 설치된 Segoe UI 글꼴을 사용한다.

Codex를 이용해 코드·GLSL·문서를 작성하고 GPU 렌더링·형상 검증을 수행했다. 제출자는 AI가 작성한 부분을 포함해 코드를 검토하고, BRDF·normal mapping·광원과 그림자의 범위·반사·유리 합성·접촉 명암·HDR 근사를 설명할 수 있어야 한다.

기본 글꼴 [Cinzel Decorative Bold](https://github.com/google/fonts/tree/main/ofl/cinzeldecorative)는 Natanael Gama의 글꼴이며 SIL Open Font License 1.1로 배포된다. 원본 TTF와 라이선스를 `assets/lettering/fonts/`에 포함했다. Harry P 비교 글꼴은 `--banner-font harry`로 볼 수 있다.
