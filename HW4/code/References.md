chocopie_front, left
- https://www.coupang.com/vp/products/6659185462?vendorItemId=82501992251

## 과제 요구사항 확인

- [Programming Assignment #4: Shading and Texture Mapping](https://sites.google.com/view/snucse-graphics2026/programming-assignment-4)
  - 매개변수 BRDF를 사진에 맞추는 것이 기본 경로이고, 온라인 실측 BRDF 데이터 사용도 선택할 수 있다.
  - 참고 문헌과 외부 자료·코드·모델은 보고서에 출처를 적어야 한다.
  - AI가 작성한 코드를 포함하여 사용한 방법을 이해하고 설명할 수 있어야 한다.

## 현재 구현한 BRDF 모델의 참고 문헌

- Eric P. Lafortune and Yves D. Willems, *Using the Modified Phong Reflectance Model for Physically Based Rendering*, Report CW 197, 1994.
  - https://graphics.cs.kuleuven.be/publications/Phong/
  - 현재 `evaluate_brdf()`는 Lambert 난반사와 정규화된 수정 Phong 정반사를 사용한다.

## BRDF 확장 참고 자료

- [Google Filament: Physically Based Rendering](https://google.github.io/filament/main/filament.html)
  - Standard model summary의 GLSL 예제: Cook–Torrance, GGX 분포, Smith-GGX 가시성, Schlick Fresnel, Lambert 난반사.
  - 현재 물의 계면에는 Schlick Fresnel을 적용했다. GGX/Smith와 Filament의 전체 재질 모델은 적용하지 않았다.
- Brent Burley, [Physically-Based Shading at Disney](https://disneyanimation.com/publications/physically-based-shading-at-disney/), SIGGRAPH 2012.
  - 실측 재질 관찰을 바탕으로 BRDF 모델과 조절용 파라미터를 설계한 자료다.
- [MERL BRDF Database](https://merl.com/research/downloads/BRDF)
  - [공식 데이터와 라이선스: Zenodo](https://zenodo.org/records/8101681)
  - 100개 재질의 실측 BRDF 및 `readBRDF.cpp` 예제. 전체 ZIP 약 1.3 GB, 압축 해제 약 3.25 GB, CC-BY-SA-4.0.
  - 단순한 Ks/n 목록이 아닌 방향별 반사 데이터이므로, 좌표 변환과 셰이더 조회 구현이 별도로 필요하다.

## 물의 반사·굴절 — 현재 구현

- [NVIDIA GPU Gems 2, Chapter 19: Generic Refraction Simulation](https://developer.nvidia.com/gpugems/gpugems2/part-ii-shading-lighting-and-shadows/chapter-19-generic-refraction-simulation), Tiago Sousa, 2005.
  - 물을 제외한 배경을 별도 텍스처에 저장하고, UV를 이동해 굴절을 근사하는 방법과 실루엣 마스크를 참고했다.
  - 현재 코드는 GLSL `refract()`로 구한 방향과 직진 방향을 투영한 차이로 UV 이동량을 정한다. 깊이와 물의 실루엣을 검사해 앞 물체의 색이 잘못 들어오는 현상을 줄인다.
- [Khronos OpenGL: refract](https://registry.khronos.org/OpenGL-Refpages/gl4/html/refract.xhtml)
  - 입력 방향과 법선을 정규화하고, 굴절률 비율을 공기→물에서는 `1 / IOR`로 사용한다. 전반사에서는 반환 방향이 0이 되는 것을 처리한다.
- [Google Filament: Fresnel](https://google.github.io/filament/main/filament.html#materialsystem/specularbrdf/fresnel(specularf))
  - `F0=((IOR-1)/(IOR+1))²`, `F=F0+(1-F0)(1-N·V)^5`를 매끄러운 물 계면의 반사/투과 비율로 사용한다.

현재 파라미터는 `water_optics.py`의 IOR 1.333, 굴절 강도 1.0, RGB 흡수 계수 (0.18, 0.07, 0.035)다. 흡수 계수는 사진에 맞춘 장면 단위의 조절값이며 실측값이 아니다.

물의 닫힌 경계를 앞/뒤 깊이 맵으로 래스터화해 두께를 근사한다. 뒤쪽 컵 → 배경 복사 → 물 → 앞쪽 컵 순서로 그린다. 주변 반사는 물 중앙의 256×256×6 HDR cubemap에 불투명 장면을 저장해 사용한다. 환경맵에서 발광판은 제외하고, 16개 점 광원의 직접 정반사는 shininess 128의 정규화 Phong lobe와 Fresnel로 별도 계산하며 opaque shadow visibility를 적용한다. 최종 색은 `F × 환경 반사색 + (1-F) × 굴절색 × exp(-흡수계수 × 두께) + 직접 정반사광`이다. 물의 발광·흰 난반사 항은 사용하지 않는다.

삼각형 교차 검색, ray marching, ray tracing을 사용하지 않는다. 화면에 보이지 않는 배경의 정확한 복원, 실제로 굽은 경로의 출구 위치, 컵 재질과 물을 모두 통과하는 다중 계면, caustics는 계산하지 않는다. 단일 cubemap의 위치 오차도 남아 있으므로 실시간 근사로 설명해야 한다. 고정 장면의 환경맵은 캐시하며 장면을 바꾸면 `water.environment_dirty=True`로 갱신한다.

## 천장의 밝은 부분 — 현재 구현한 간접광 근사

- [KIT: Reflective Shadow Map Clustering for Real-Time Global Illumination](https://cg.ivd.kit.edu/publications/2012/RSMC/RSMC.pdf), Prutkin, Kaplanyan, Dachsbacher, 2012.
  - 반사 표면에 가상 광원을 배치해 한 번의 간접광을 근사하는 VPL 개념을 참고했다. 논문의 RSM 생성·클러스터링 알고리즘을 구현한 것은 아니다.

`ceiling_bounce.py`는 상자 윗면과 빨간 벽·초록 벽의 안쪽 면을 각각 32개, 총 96개 패치로 나눈다. 실제 윗면 텍스처의 평균 선형 RGB 또는 벽 재질색, 패치 면적, 천장 광원의 직접광, 수정 Phong 난반사·정반사 항으로 패치의 반사광을 정한다. 천장 셰이더는 패치에서 받은 빛을 거리 감쇠와 두 면의 법선 cosine으로 합산한다. 면 광원 입사 방향의 분산만큼 정반사 lobe를 넓혀 개별 점이 드러나는 것을 줄였다. 천장 재질 자체는 RGB (0.68, 0.68, 0.68)로 중립적인 흰색이며, 붉고 초록인 빛은 이 간접광에서 더한다.

윗면 코팅 파라미터는 `Pie_top`의 Ks=(0.04, 0.04, 0.04), shininess=48이며, 보이는 윗면과 간접광 계산에서 같은 값을 쓴다. 전체 간접광 강도는 `BOUNCE_STRENGTH=1.0`이다. 상자와 벽에서 천장으로 가는 한 번의 반사를 계산하고 패치 사이 가림·여러 번의 반사는 생략한다. 사진 속 밝은 부분의 원인이 오직 상자 반사라고 입증한 것은 아니며, 사진을 재현하기 위한 근사다.

## 물이 바닥에 만드는 투과 그림자

- [Physically Based Rendering 4e: Transmittance](https://pbr-book.org/4ed/Volume_Scattering/Transmittance)
  - 빛의 투과율과 Beer-Lambert 감쇠의 개념을 참고했다. 이 책의 ray tracing 코드를 사용한 것은 아니다.

`transmission_shadow.py`는 같은 16개 광원 시점에서 물의 앞/뒤 경계를 512×512×16 RG32F 배열 두 개에 래스터화한다. R에는 광원까지의 거리, G에는 계면 Fresnel을 저장한다. 물 뒤의 수광면에 대해 `T=(1-F_in)(1-F_out) exp(-σd)`를 직접광에 곱한다. 불투명 그림자와 별개의 옅은 감쇠이며, 굴절에 의한 caustics는 계산하지 않는다.

## 상자 모서리와 HDR 출력

`box_geometry.py`의 bevel은 중심을 옮긴 local 좌표에서 `q=clamp(p,-h+r,h-r)`, `p'=q+r normalize(p-q)`를 사용한다. 반지름은 0.012 scene unit(약 1.2 mm), 가장자리 4단계, 각 면 기본 24분할이다. UV는 기존 면의 affine map으로 보존하고, 앞면 평면 영역에는 최대 0.008의 휨을 추가한다. 최종 형상은 카메라와 opaque shadow 패스에서 공유한다.

`linear_target.py`는 선형 RGBA16F 버퍼에 장면을 저장하고, 노출 2.4의 Reinhard tone mapping과 sRGB 변환을 적용한다. 4× MSAA와 최종 화면의 FXAA 방식 필터는 유지한다.

## Coding agent 활용

Codex를 이용해 코드 작성과 수정, 렌더링 검증 및 보고서 초안을 작성했다. 보고서에는 실제 구현한 계산, 외부 자료의 사용 범위, 생략한 효과와 근사를 구분해 기재했다. 제출자는 AI가 작성한 부분을 포함한 코드를 검토하고 설명할 수 있어야 한다.

