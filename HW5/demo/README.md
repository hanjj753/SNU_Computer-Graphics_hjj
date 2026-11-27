# Demo Day 시연

과제의 Demo Day 항목은 현장 참여가 필요한 별도 배점이다. 이 폴더의 포스터를 만들었다는 사실만으로 전시·참여 완료를 주장하지 않는다.

1. `HW5_A1_Poster.pdf`를 A1(594 × 841 mm) 크기로 인쇄한다. 화면으로 보여 줄 경우 PDF를 열어 전체 화면으로 표시한다.
2. 실물 Cornell Box와 사진 촬영 때 사용한 천장 광원을 준비한다.
3. `outputs/reference.png`로 실물 사진/HW4/HW5를 비교한다. 필터를 적용한 영상은 라벨을 유지한다.
4. `outputs/comparison/detail_shadows.png`, `detail_refraction.png`, `detail_reflections.png`, `detail_indirect.png`를 열어 soft shadow, 재귀 굴절·반사와 색 번짐을 설명한다.
5. AA와 DOF는 `detail_aa.png`, `detail_dof.png`로 보여 준다. 원본/필터 차이는 `outputs/denoising_comparison.png`로 설명한다.
6. `outputs/benchmark/timing.png`와 `timings.json`으로 BVH/전체 순회 시간과 동일 영상 검증을 보여 준다. JIT와 구축 시간의 포함 여부도 함께 말한다.
7. 현장에서 짧게 실행하려면 HW5 폴더에서 `python main.py --preset preview`를 실행한다.

컵과 물의 카메라 경로는 실제 경계에서 굴절한다. 투명 물체의 shadow 연결은 직선 근사이며 굴절 caustics는 정확히 계산하지 않는다는 한계를 설명한다. 보고서의 AI 사용 및 자산 출처도 검토한다.
