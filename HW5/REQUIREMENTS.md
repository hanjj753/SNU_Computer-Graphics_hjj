# 과제 5 요구사항 재검증

원문: [Programming Assignment #5: Ray Tracing](https://sites.google.com/view/snucse-graphics2026/programming-assignment-5)

이 문서는 구현·실험·파일 준비와 현장에서 직접 수행해야 하는 항목을 구분한다. 채점 점수나 Demo Day 참여 완료를 보장하는 문서는 아니다.

| 원문 항목 | 현재 상태 및 근거 |
| --- | --- |
| HW2에서 만든 장면을 ray tracing으로 렌더링 | 원본 OBJ의 SHA-256이 HW2/HW4/HW5에서 동일함을 확인했다. 값은 `assets/source_manifest.json`에 기록했다. 컵·물의 닫힌 부피와 상자 모서리는 ray tracing을 위해 재구성한다. |
| OpenGL/PyGlet 없이 픽셀별 radiance 계산 | `code/tracer.py`의 `render_pass`가 카메라 광선을 생성하고 `trace_path`가 실제 삼각형 교차와 radiance를 누적한다. AST 검사로 GPU/래스터화 렌더러 import가 없는지 검증한다. Pillow는 이미지 입출력에 사용한다. |
| [10] Ray casting, shadow rays, area-light penumbra | `bvh.py`의 삼각형/AABB 교차, `shadow_transmittance`의 가시성, 천장 면 광원의 층화 샘플링. `detail_shadows.png`에 면 광원/중앙점 광원 비교가 있다. 별도 occluder 테스트로 umbra, 부분 가시성 penumbra, 완전 조명 영역을 확인한다. |
| [10] 재귀 반사·굴절 | 매끄러운 유전체의 Fresnel/Snell/전반사, 매질 스택, 실제 경계 사이 Beer-Lambert 흡수, glossy 후속 경로를 구현했다. 독립된 장면에서 반사 후 emitter에 도달하는 경로와 앞/뒤 두 경계를 통과해 emitter에 도달하는 굴절 경로를 검사한다. 재귀 적분은 경로 루프로 실행한다. |
| 광택/투명 물체가 없으면 synthetic 물체 추가 | 원래 장면의 PVC/포장지에 광택이 있고 컵·물이 투명하므로 추가 의무 조건에 해당하지 않는다. `detail_reflections.png`, `detail_refraction.png`로 효과를 보여 준다. |
| [10] 사진에 필요한 수업 내용 구현 및 on/off 효과 비교 | 선형 RGB 텍스처, 수정 Phong 광택, 실제 shadow ray, 다중 반사 GI/색 번짐, 재귀 굴절/흡수를 적용했다. 480×360, 144 spp, 동일 카메라/seed/노출의 기준과 8개 변형을 렌더링하고 확대 비교를 저장한다. 수치 차이는 `results.json`에 기록하며 이를 사진 일치의 점수로 해석하지 않는다. |
| [10] 추가 효과: supersampling, DOF, motion blur 등 | supersampling AA와 thin-lens DOF를 구현했다. `detail_aa.png`, `detail_dof.png`와 초점면 테스트로 확인한다. 노이즈 제거는 원본을 보존하는 선택형 후처리다. 예시로 제시된 모든 추가 효과를 구현하라는 조건은 아니므로 motion blur는 미구현이다. |
| [10] 공간 자료구조와 사용 전/후 렌더링 시간 비교 | 12-bin SAH BVH와 전체 삼각형 순회가 같은 교차 공식을 사용한다. 같은 scene/options/seed에서 교대로 3회 측정한다. `timings.json`은 렌더 중앙값, 구축 시간, 두 영상의 차이를 기록한다. |
| 실물 사진 및 HW4 렌더와 최종 결과 비교 | `outputs/reference.png`와 보고서에 3개 영상을 나란히 제시한다. 원본과 노이즈 제거 사본을 명확히 구분한다. 실물 사진과 HW4는 사용자/기존 과제 파일을 보존해 사용한다. |
| [10] 보고서: 구현/명세 대응, 상세 실행법, 사진/렌더, 추가 기능 설명과 실험, 참고 자료/외부 자산 | `report/HW5_Report.pdf`에 포함했다. 편집·재생성용 `tools/build_report.py`와 참고 문헌/자산 출처도 포함한다. 코드 및 AI 사용을 검토하고 설명할 수 있어야 한다. |
| [30] Demo Day에서 작품 전시 | **현장 수행 필요.** A1 PDF 포스터와 `demo/README.md`의 시연 순서를 준비했다. 실물 설치·인쇄·현장 참여는 이 코드나 파일 생성으로 완료할 수 없다. |
| 코드/데이터/보고서/실행에 필요한 파일을 단일 ZIP으로 ETL 제출 | `python tools/package_submission.py`가 `dist/HW5_Submission.zip`을 만들고 CRC 및 파일별 SHA-256을 검사한다. ZIP을 풀어 실행하는 독립성 확인도 수행한다. **ETL 업로드는 사용자 수행 필요.** |

## 재검증에서 보완한 내용

1. 난반사 경로 제한 후 glossy 경로만 이어 갈 때, MIS 가중치를 난반사 직접광까지 곱하던 문제를 수정했다. 직접광 전용 추정과 glossy 경로를 함께 쓰는 추정이 같은 에너지로 수렴하는 회귀 테스트를 추가했다.
2. Fresnel/Snell 함수 단위 테스트에 더해 실제 반사·굴절·penumbra 경로를 확인하는 통합 테스트를 추가했다.
3. 기존 전체 프레임 비교에 같은 좌표의 확대 비교를 더하고 해상도와 spp를 높였다.
4. 기존 `snu_graphics_hjj` 환경에서 `python main.py`로 실행한다. 별도 설치 목록이나 환경 탐색 스크립트는 사용하지 않는다.
5. 보고서, A1 시연 포스터, 실행/자산/테스트 검증 도구, 단일 ZIP 패키징 및 무결성 검사를 추가했다.

## 정확도와 검증 범위

유전체를 통과하는 shadow connection은 직선 경로의 Fresnel·흡수·산란 소광 근사다. 광원까지 이어지는 굴절 caustic 경로를 푸는 적분기는 아니다. 최신 컵 재질은 균질·등방성 부피 산란과 표면 Lambert 혼합을 사용한다. 산란점의 직접광 연결에는 수직 입사 Fresnel과 얇은 셸의 광학 길이 근사가 있으므로 편향 없는 완전한 부피 적분기는 아니다. 재질·흡수·산란 계수와 광원 배광은 사진 보정값이다. 저 spp 간접광에는 Monte Carlo 노이즈가 있고 필터 사본은 편향된 후처리다. 분산·motion blur·정확한 caustics는 구현하지 않았다. 기존 보고서·ZIP의 영상과 설명은 이전 재질 버전이며, 최신 보정 결과와 한계는 `README.md` 및 `outputs/cornell_pvc_reflection.json`에 기록한다.

`outputs/verification.json`이 소프트웨어/파일 검사의 실제 결과를 기록한다. Demo Day 참여 및 ETL 업로드는 그 안에서도 사람의 후속 작업으로 남긴다.
