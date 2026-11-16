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

## 추가로 검토한 BRDF 자료 — 현재 코드에는 미적용

- [Google Filament: Physically Based Rendering](https://google.github.io/filament/main/filament.html)
  - Standard model summary의 GLSL 예제: Cook–Torrance, GGX 분포, Smith-GGX 가시성, Schlick Fresnel, Lambert 난반사.
  - Roughness와 Fresnel을 쓰는 실시간 BRDF로 확장할 때 우선 참고할 자료다. Clear coat 절에는 코팅층 모델도 있다.
- Brent Burley, [Physically-Based Shading at Disney](https://disneyanimation.com/publications/physically-based-shading-at-disney/), SIGGRAPH 2012.
  - 실측 재질 관찰을 바탕으로 BRDF 모델과 조절용 파라미터를 설계한 자료다.
- [MERL BRDF Database](https://merl.com/research/downloads/BRDF)
  - [공식 데이터와 라이선스: Zenodo](https://zenodo.org/records/8101681)
  - 100개 재질의 실측 BRDF 및 `readBRDF.cpp` 예제. 전체 ZIP 약 1.3 GB, 압축 해제 약 3.25 GB, CC-BY-SA-4.0.
  - 단순한 Ks/n 목록이 아닌 방향별 반사 데이터이므로, 좌표 변환과 셰이더 조회 구현이 별도로 필요하다.


