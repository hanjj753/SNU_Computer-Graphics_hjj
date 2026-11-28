# References

- [Programming Assignment #5: Ray Tracing](https://sites.google.com/view/snucse-graphics2026/programming-assignment-5)
  - OpenGL/PyGlet 없이 픽셀별 광선을 추적하고, 면 광원 그림자, 재귀 반사·굴절, 사진에 필요한 효과 및 기능별 비교, 추가 영상 효과, 공간 자료구조와 시간 비교를 구현하는 과제 명세.
- Pharr, Jakob, Humphreys, [Physically Based Rendering, 4e: A Better Path Tracer](https://pbr-book.org/4ed/Light_Transport_I_Surface_Reflection/A_Better_Path_Tracer)
  - 직접 광원 샘플링, BSDF 샘플링과 MIS, 경로 처리 및 Russian roulette 개념. 이 구현은 단일 사각형 면 광원과 RGB 재질을 사용하며 책의 코드를 가져오지 않았다.
- [PBRT 4e: Dielectric BSDF](https://pbr-book.org/4ed/Reflection_Models/Dielectric_BSDF)
  - 비편광 Fresnel, Snell 굴절, 전반사, radiance transport의 굴절률 제곱 보정 개념. 여기서는 매끄러운 경계만 추적하며 거친 유전체 microfacet 모델은 구현하지 않았다.
- [PBRT 4e: Volume Scattering Integrators](https://pbr-book.org/4ed/Light_Transport_II_Volume_Rendering/Volume_Scattering_Integrators)
  - 균질 매질의 자유 비행 거리 샘플링과 위상함수 개념. `volume.py`와 경로 루프를 직접 작성했으며 RGB 흡수·스칼라 산란·등방성 위상함수를 쓴다. 굴절 셸을 지나는 직접광은 수직 입사 Fresnel과 얇은 셸 광학 길이로 별도 근사한다.
- [PBRT 4e: Bounding Volume Hierarchies](https://pbr-book.org/4ed/Primitives_and_Intersection_Acceleration/Bounding_Volume_Hierarchies)
  - AABB 계층과 SAH 분할 개념. 여기서는 12-bin SAH, 기본 4개 이하 삼각형 leaf, 평탄화 배열, 가까운 노드 우선 순회를 직접 구현했다.
- Möller and Trumbore, [Fast, Minimum Storage Ray/Triangle Intersection](https://doi.org/10.1080/10867651.1997.10487468), 1997.
  - 두 면을 모두 검사하는 barycentric ray/triangle 교차 공식.
- Lafortune and Willems, [Using the Modified Phong Reflectance Model for Physically Based Rendering](https://graphics.cs.kuleuven.be/publications/Phong/), 1994.
  - Lambert 난반사와 정규화된 수정 Phong 정반사를 결합하는 모델.
- [Pillow](https://pillow.readthedocs.io/en/stable/), [NumPy](https://numpy.org/doc/stable/), [Numba](https://numba.readthedocs.io/en/stable/)
  - 이미지 입출력, 배열 처리 및 CPU JIT/병렬화에 사용하는 외부 라이브러리. 광선 교차, 가시성, BRDF, 적분기와 BVH는 과제 코드다.

## 앞선 과제에서 가져온 자산과 코드

장면 모델, UV 규칙, 텍스처, 보정된 초기 카메라는 HW4 장면을 기반으로 한다. `cup_geometry.py`, `water_surface.py`는 OpenGL 의존성이 없는 기존 HW4의 메시 생성 코드를 재사용했다. 상자 bevel/휨/윗면 능선은 NumPy 기반으로 다시 구성했다. 기존의 shadow map, planar reflection, cubemap, screen-space refraction, 베이크된 간접광 셰이더는 사용하지 않는다. 외부 상품 사진 출처와 면별 사본 관계는 `assets/README.md`에 기록했다.

## AI 사용

Codex를 이용해 HW5 코드와 문서를 작성하고, 광학/교차/메시 회귀 테스트, 실제 렌더링 및 성능 비교를 수행했다. 제출자는 AI가 작성한 부분을 포함해 코드를 검토하고 설명할 수 있어야 한다.
