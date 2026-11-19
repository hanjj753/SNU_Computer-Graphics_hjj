# References and implementation scope

- [SNU Computer Graphics — Programming Assignment #4](https://sites.google.com/view/snucse-graphics2026/programming-assignment-4)
  - Extra Credit의 복잡한 재질, 여러 작은 광원, shadow mapping을 목표로 별도의 Cornell-box 장면을 구현했다.
- [Google Filament — Physically Based Rendering](https://google.github.io/filament/main/filament.html)
  - Cook–Torrance, GGX distribution, height-correlated Smith visibility, Schlick Fresnel, metallic/roughness parameterization의 수식과 설명을 참고했다. Filament 엔진을 사용하거나 그 전체 IBL 파이프라인을 구현한 것은 아니다.
- [Khronos OpenGL — glDrawElementsInstanced](https://registry.khronos.org/OpenGL-Refpages/gl4/html/glDrawElementsInstanced.xhtml)
  - 같은 기본 형상에 model/material instance attributes를 적용하는 indexed instancing.
- [Khronos OpenGL — glFramebufferTextureLayer](https://registry.khronos.org/OpenGL-Refpages/gl4/html/glFramebufferTextureLayer.xhtml)
  - 네 광원의 depth map을 한 texture array에 저장한다. Depth comparison, bias, 3×3 PCF는 자체 GLSL로 구현했다.
- [Khronos OpenGL — glFramebufferTexture2D](https://registry.khronos.org/OpenGL-Refpages/gl4/html/glFramebufferTexture2D.xhtml)
  - 평면 반사용 render target과 cubemap의 각 face를 framebuffer에 연결한다.
- [Khronos OpenGL — glBlendFunc](https://registry.khronos.org/OpenGL-Refpages/gl4/html/glBlendFunc.xhtml)
  - 뒤에서 앞으로 정렬한 유리 quad의 standard alpha compositing.
- [Khronos OpenGL — glBlitFramebuffer](https://registry.khronos.org/OpenGL-Refpages/gl4/html/glBlitFramebuffer.xhtml)
  - 4× MSAA HDR renderbuffer를 단일 샘플 텍스처로 resolve한다.
- [NVIDIA GPU Gems — Real-Time Glow](https://developer.nvidia.com/gpugems/gpugems/part-iv-image-processing/chapter-21-real-time-glow)
  - 밝은 영역 추출 → 저해상도 blur → 원본 HDR에 가산하는 bloom의 기본 흐름.
- [Krzysztof Narkowicz — ACES Filmic Tone Mapping Curve](https://knarkowicz.wordpress.com/2016/01/06/aces-filmic-tone-mapping-curve/)
  - 최종 display transform에서 계수 2.51, 0.03, 2.43, 0.59, 0.14의 fitted curve를 사용한다. 전체 ACES 색 관리 파이프라인은 아니다.
- [NVIDIA — FXAA](https://developer.download.nvidia.com/assets/gamedev/files/sdk/11/FXAA_WhitePaper.pdf)
  - 주변 픽셀 휘도로 방향을 추정하는 소규모 edge filter의 개념을 참고했다. 공식 FXAA 구현 전체를 이식한 것은 아니다.
- [pyglet 2.1 documentation](https://docs.pyglet.org/en/latest/)
  - 창, 입력, OpenGL 바인딩, shader compilation, 수학 형식, HUD 글꼴 렌더링과 PNG 저장에 사용했다.

## External assets and coding agent

외부 모델·사진·텍스처를 다운로드하지 않았다. 관람차, 매표소, 팝콘 카트, 벤치, 식물, 간단한 방문객과 모든 형상을 코드로 생성했다. 전구 줄의 처짐은 포물선으로 근사했다. 8개 간판은 자체 bitmap 글꼴을 사용한 texture atlas로 만들고, 벤치의 나뭇결도 절차적으로 계산한다. HUD에는 컴퓨터에 설치된 Segoe UI 글꼴을 사용한다. 기존 HW4의 pyglet/OpenGL 작업 방식을 참고하되 새 폴더에서 독립 실행하도록 작성했다.

Codex를 이용해 장면·렌더러·GLSL·문서 작성과 검증을 수행했다. 제출자는 AI가 작성한 부분을 포함하여 실제 코드를 검토하고, 보고서에서 BRDF, 광원 근사, 반사, 투명 합성 순서, shadow mapping, HDR 후처리를 설명할 수 있어야 한다.
