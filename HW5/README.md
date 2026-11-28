# HW5 — CPU Ray Tracing

[과제 5 명세](https://sites.google.com/view/snucse-graphics2026/programming-assignment-5)에 맞춰 기존 Cornell Box 장면을 CPU에서 직접 ray tracing한다. OpenGL/PyGlet, Blender 렌더러, GPU ray tracing 라이브러리를 사용하지 않는다. NumPy/Pillow/Numba만 필요하다. Numba는 직접 작성한 광선 추적 루프를 CPU 기계어로 컴파일하고 여러 CPU 코어에서 실행한다.

## 바로 실행

기존 프로젝트 환경 `snu_graphics_hjj`를 활성화한 뒤 `HW5` 폴더에서 실행한다.

```powershell
conda activate snu_graphics_hjj
cd HW5
python main.py
```

필요한 NumPy/Pillow/Numba는 이 환경에서 사용한다. 처음에는 320×240, 16 spp 미리보기를 만들며, 결과는 `outputs/cornell_preview.png`와 같은 이름의 JSON으로 저장된다. 결과를 보려면 PNG를 연다. 렌더링 창은 만들지 않는다.

저장소 루트에서는 `python HW5/main.py`로 실행한다. 자산 경로는 `main.py` 위치를 기준으로 찾는다.

처음 실행할 때는 Numba JIT 컴파일이 추가로 필요하다. 이후 실행은 캐시를 사용한다. 렌더링 시간과 JIT 준비 시간은 JSON에 분리해 기록한다.

## 생성한 결과

- `outputs/cornell_material_match.png`: 컵의 부피 산란과 벽 색상·광원 배광을 보정한 현재 장면. 640×480, 256 spp 원본이며 denoising을 적용하지 않았다.
- `outputs/cornell_material_match_denoised.png`, `material_match_denoising_comparison.png`: 같은 256 spp 영상에 기존 3단계 denoising을 적용한 사본과 사진/원본/필터 사본 비교. 필터용 선형 RGB·분산을 동일 설정과 seed로 재생성하고 기존 원본과 픽셀 일치를 확인했다.
- `outputs/cornell_material_match_denoised_soft.png`: 256 spp 원본에 기본 2단계·강도 0.8의 약한 denoising을 적용한 사본. 필터 결과 80%와 원본 20%를 선형 RGB에서 혼합해 작은 수면 경계와 하이라이트를 남긴다.
- `outputs/cornell_material_match_ss2048.png`: 같은 장면·해상도에서 2048 spp로 렌더링한 원본. denoising을 적용하지 않는다. 비교는 `outputs/material_match_quality_comparison.png`에 저장한다.
- `outputs/material_match_denoising_strength.png`: 사진/이전의 강한 필터/약한 필터 및 컵 확대 비교. 이전 결과를 보존하기 위해 이번 약한 사본은 `_denoised_soft.png`에 따로 저장했다. CLI의 기본 필터 출력 이름은 계속 `*_denoised.png`다.
- `outputs/photo_vs_material_match.png`, `material_match_details.png`: 사진/현재 결과 및 사진/보정 전/보정 후 확대 비교. 보정 전은 기존 2048 spp 영상이다.
- `outputs/material_match_metrics.json`: 동일한 재질 영역에서 측정한 사진과의 RGB 차이. 구도가 완전히 정합된 품질 점수는 아니다.
- `outputs/cornell.png`: 기본 최종 설정으로 렌더링한 원본. 정확한 해상도·spp·시간은 `cornell.json`에 기록한다.
- `outputs/cornell_denoised.png`: 원본에서 guide 기반 노이즈를 줄인 사본.
- `outputs/reference.png`: 실물 사진 / HW4 / HW5 필터 사본 비교.
- `outputs/photo_vs_render.png`: 실물 사진 / 현재 HW5 필터 사본 비교.
- `outputs/denoising_comparison.png`: 같은 512 spp 원본과 필터 사본 비교.
- `outputs/comparison/features.png`: 8가지 효과의 비교.
- `outputs/benchmark/timings.json`, `timing.png`: 실제 BVH 성능 측정.

128×96, 4 spp, 3회 교대 실행의 중앙값과 두 선형 RGB 영상의 차이는 `outputs/benchmark/timings.json`을 참조한다. JIT·구축·저장 시간을 제외한 값과 BVH 구축 비용을 구분한다. 검증 결과는 `outputs/verification.json`, 항목별 요구사항 대조는 `REQUIREMENTS.md`에 기록한다.

`cornell_material_match` 이외의 기존 출력·보고서·제출 ZIP은 앞선 재질 설정으로 생성한 기록이다. 현재 기본 설정은 `scene.json`이며 `python main.py`에도 바로 적용된다. 현재 보정 결과를 다시 만들려면 다음을 실행한다.

```powershell
python main.py render --width 640 --height 480 --spp 256 --max-depth 24 --diffuse-bounces 6 --output outputs/cornell_material_match.png

# 약한 denoising: 필터 80% + 원본 20%, 작은 커널 두 단계
python main.py render --width 640 --height 480 --spp 256 --max-depth 24 --diffuse-bounces 6 --denoise --denoise-strength 0.8 --denoise-iterations 2 --output outputs/cornell_material_match.png

# denoising 없이 카메라·광원·경로 샘플만 증가
python main.py render --width 640 --height 480 --spp 2048 --max-depth 24 --diffuse-bounces 6 --output outputs/cornell_material_match_ss2048.png
```

## 렌더링 옵션

```powershell
# 중간 품질: 640×480, 64 samples/pixel
python main.py render --preset draft --output outputs/draft.png

# 640×480, 512 spp, 깊이 24, 난반사 경로 6회
python main.py render --width 640 --height 480 --spp 512 --max-depth 24 --diffuse-bounces 6 --checkpoint --denoise --save-linear --output outputs/cornell_640.png

# 높은 해상도: 960×720, 512 spp
python main.py render --preset final --checkpoint --denoise --save-linear --output outputs/cornell.png

# 얕은 심도: aperture는 장면 단위의 렌즈 반지름
python main.py render --preset draft --aperture 0.045 --focus-distance 6.9 --output outputs/dof.png
```

| 옵션 | 의미 |
| --- | --- |
| `--preset preview/draft/final` | 해상도·spp·경로 깊이 기본값. 개별 옵션이 우선한다. |
| `--width`, `--height`, `--spp` | 이미지 크기와 픽셀당 카메라 샘플 수 |
| `--max-depth` | 유전체 경계까지 포함한 최대 광선 경로 길이 |
| `--diffuse-bounces` | 난반사 방향으로 이어 가는 경로 횟수 상한 |
| `--light-samples` | 첫 표면의 직접 면 광원 샘플 수. 이후 표면은 1개. |
| `--threads` | 사용할 CPU 스레드 수 |
| `--seed` | 결과를 재현하기 위한 난수 seed |
| `--aperture`, `--focus-distance` | thin-lens 반지름과 초점 거리. aperture=0이면 pinhole. |
| `--exposure` | 저장 전 Reinhard tone mapping에 적용하는 노출 |
| `--config` | 기본 `scene.json` 대신 사용할 장면 설정 |
| `--checkpoint`, `--pass-spp` | 일정 spp마다 `*_progress.png` 갱신. 중단돼도 마지막 미리보기가 남는다. |
| `--save-linear` | PNG/JSON 외에 tone mapping 전 RGB `.npy` 저장 |
| `--denoise` | raw 결과를 보존하고 `*_denoised.png`와 JSON/선택적 NPY를 추가 저장 |
| `--denoise-strength` | 필터 혼합 비율 0~1. 기본 0.8, 0이면 원본, 1이면 필터 결과 전부. `--denoise`와 함께 사용. |
| `--denoise-iterations` | 필터 단계 수 1~5. 기본 2. 이전의 강한 설정은 `--denoise-strength 1 --denoise-iterations 3`. |

`--no-shadows`, `--hard-shadows`, `--no-reflections`, `--no-refraction`, `--no-indirect`, `--no-textures`, `--no-aa`, `--no-absorption`, `--no-bvh`로 효과를 끌 수 있다. `--no-refraction`에서는 컵과 물을 회색 불투명 재질로 바꿔 굴절 유무를 드러낸다. `--no-aa`는 광원·반사 샘플 수를 유지하면서 카메라 광선을 픽셀 중앙에 고정한다.

렌더의 기본 출력 이름은 `cornell_<preset>.png`다. 같은 명령을 다시 실행하면 동일 이름의 출력이 갱신되므로 여러 버전을 보관하려면 `--output`으로 이름을 지정한다.

## 구현과 과제 요구사항

| 명세 | 구현 |
| --- | --- |
| Ray casting, shadow rays, penumbra | Möller–Trumbore 삼각형 교차, 사각형 천장 면 광원의 층화 샘플링, RGB 가시성 검사 |
| 재귀 반사/굴절 | 광선이 맞은 실제 표면에서 후속 경로 추적. 정확한 비편광 Fresnel, Snell, 전반사, IOR 매질 스택, Beer–Lambert 흡수 |
| 사진에 필요한 효과와 on/off 비교 | 인쇄 텍스처의 선형 RGB bilinear 조회, 정규화된 수정 Phong 광택, 다중 반사 간접광·색 번짐, 컵·물의 유한 두께, 실제 가림, `compare` |
| 추가 영상 효과 | 층화 supersampling AA, thin-lens DOF, 선택적 guide 기반 노이즈 제거 |
| 공간 자료구조 및 시간 비교 | 12-bin SAH BVH, AABB slab test, 가까운 노드 우선 순회, 같은 광선을 쓰는 brute-force 경로와 `benchmark` 비교 |
| 실물/HW4와 비교 | 원본 사진과 HW4 사본을 사용한 `reference.png`, 같은 설정의 기능별 `features.png` |

재귀 rendering equation은 Python 함수 호출 대신 경로 상태를 갱신하는 루프로 계산한다. 광택 BRDF와 cosine 난반사를 확률적으로 샘플링하고, 면 광원 샘플과 BSDF 샘플을 power-heuristic MIS로 결합한다. 깊이 4 이후에는 Russian roulette로 경로를 끝낸다. 유전체에서는 Fresnel 비율에 따라 반사 또는 굴절 경로를 선택하며, 전반사는 항상 반사한다. 매질 진입/이탈과 `eta²` radiance 보정은 실제 경계를 통과할 때 처리한다.

컵은 내벽·외벽·바닥·입구 띠가 이어진 속이 빈 닫힌 메시다. 물도 수면의 작은 meniscus, 옆면, 바닥이 이어진 닫힌 부피다. 컵의 플라스틱 내부에서는 지수분포로 다음 산란 거리를 뽑고, 경계 전에 산란하면 균일한 구면 방향으로 경로를 이어 간다. 이 균질·등방성 부피 산란과 8% Lambert 계면 반사 혼합으로 뿌연 반투명을 표현한다. 경계 굴절과 RGB Beer 흡수는 유지하며 거친 유전체 microfacet 모델은 사용하지 않는다. 바닥과 정확히 겹치는 경계는 작은 간격으로 분리했고, 같은 거리의 교차점은 삼각형 ID 순서로 고정해 가속 순서에 따른 결과 차이를 막았다.

기본 장면은 12,196개 삼각형이며 카메라와 UV는 HW4의 보정값을 이어받는다. 실제 장면에 투명한 컵·물과 광택 PVC·포장지가 있으므로 별도 합성 구체를 추가하지 않았다. `scene.json`에서 카메라, 광원 radiance, 재질 반사율·광택·굴절률·흡수·산란 계수를 바꿀 수 있다. `plastic.scattering`은 장면 길이 단위당 산란 계수이며 0이면 기존의 맑은 유전체 경로다. 천장 광원의 `directional_power`는 `L_e(theta) = L_peak * cos(theta)^power`로 수직 아래 방향에 빛을 모으며, 생략하거나 0으로 설정하면 기존의 일정 radiance 면 광원이다. 광원 크기·위치와 바닥/나무 재질은 이번 보정에서 바꾸지 않았다. 모든 보정값은 사진에 맞춘 유효 매개변수이며 실측 데이터가 아니다.

## 기능별 비교

```powershell
python main.py compare --width 480 --height 360 --spp 144 --max-depth 20 --diffuse-bounces 5 --features indirect shadows reflections refraction textures aa dof absorption --save-linear
```

`outputs/comparison/`에 다음을 만든다.

- `full.png`와 효과별 이미지: 기준과 해당 옵션 하나만 달리해 렌더링
- `features.png`: 효과 on/off 비교 모음
- `detail_*.png`, `details.png`: 같은 좌표에서 자른 확대 비교. nearest-neighbor 확대이며 추가 밝기·노이즈 보정은 없다.
- `reference.png`: 실물 사진 / HW4 OpenGL / HW5 ray tracing
- `results.json`: 각 설정, 렌더링 시간, 광선·삼각형 검사 수, 기준과의 선형 RGB RMSE

사진과 HW4 이미지는 전체 프레임을 같은 크기로 줄이며, 구도나 밝기를 따로 보정하지 않는다. HW4 이미지의 기존 HUD도 보존한다. 특징별 비교는 동일한 해상도·spp·seed·노출을 쓴다. 효과 변경으로 경로가 달라지면 이후 난수 사용도 달라지므로 RMSE는 수렴 오차를 분리한 품질 점수가 아니다. 노이즈가 적은 비교가 필요하면 spp를 늘린다.

## BVH 성능 비교

```powershell
python main.py benchmark --repeats 3 --save-linear
```

기본 128×96, 4 spp, 깊이 12에서 동일한 광학 효과와 seed를 사용한다. BVH/전체 순회를 번갈아 실행한 뒤 중앙값과 속도 비율을 기록한다. 두 렌더의 선형 RGB가 일치하는지도 검사하고, 다르면 명령이 실패한다. `outputs/benchmark/`에 두 PNG, 16배 증폭 차이 이미지, 시간 막대 그림, `timings.json`을 저장한다.

`render_seconds`는 CPU 렌더링 시간이며 파일 저장·JIT·BVH 구축을 제외한다. JSON에는 BVH 구축 시간과 구축+렌더 시간도 별도로 기록한다. 작은 이미지에서는 구축 비용이 전체 시간의 큰 부분일 수 있다. CPU와 스레드 수에 따라 실제 시간은 달라진다.

## 검증

의존성이 있는 Python 환경에서:

```powershell
python -m unittest discover -s tests -v
```

광학 공식, 전반사와 매질 스택, 양면 삼각형/AABB 교차, 컵·물 메시의 닫힘과 바깥쪽 winding, BVH/전체 순회 교차 일치, 같은 거리의 교차점 처리, bilinear UV 방향, DOF 초점면, 고정 seed 재현성 및 실제 렌더 동등성을 확인한다. 독립적인 작은 장면에서는 실제 emitter까지의 반사 경로, 유전체 앞/뒤 두 경계를 통과하는 경로, umbra/penumbra/완전 조명 영역 및 경로 제한 시 직접광 에너지 일치를 추가로 검사한다. 부피 산란은 자유 비행 거리의 소광 분포, 위상함수의 정규화, 산란 없는 직결광의 감쇠, 자체 발광 없는 매질의 직접광 수신, 얇은 셸의 광학 길이와 굴절률 보정을 확인한다.

## 코드 위치

- `main.py`: Python 진입점
- `code/scene.py`, `scene.json`: 장면/재질/자산 로딩과 메시 구성
- `code/bvh.py`: SAH 구축 및 두 종류 교차 검색
- `code/tracer.py`, `sampling.py`: 카메라, 광학, BSDF, 광원, 경로 적분과 CPU 병렬화
- `code/volume.py`: 균질 플라스틱의 산란 거리·등방성 위상함수 및 얇은 셸 광학 길이 근사
- `code/cup_geometry.py`, `water_surface.py`: 실제 경계 메시 생성
- `code/denoise.py`: albedo로 나눈 조명을 normal/depth/material guide와 샘플 분산으로 여과하는 à trous 필터
- `code/image_io.py`, `experiments.py`, `cli.py`: 출력·비교·시간 측정·CLI
- `References.md`, `assets/README.md`: 참고 자료, AI 사용, 자산 출처

## 남아 있는 근사와 제출물 범위

유전체 그림자는 광원 샘플까지 직선으로 연결한 경로에 Fresnel·흡수·산란 소광을 누적한다. 산란점에서 광원으로 직접 연결할 때는 뿌연 플라스틱 경계의 수직 입사 Fresnel, 굴절률 제곱 보정과 메시에서 얻은 셸 두께에 따른 광학 길이를 사용한다. 이는 굴절 경계를 포함하는 직접광의 근사이며 정확한 굴절 caustic 적분기나 편향 없는 완전한 부피 적분기는 아니다. 카메라에서 시작한 경로의 자유 비행과 경계 반사·굴절은 실제 부피와 삼각형 경계에서 계산한다. 파장별 분산, 이방성 위상함수, 모션 블러는 포함하지 않는다.

낮은 spp의 간접광에는 Monte Carlo 노이즈가 남는다. `--denoise`는 albedo/normal/depth/material 안내를 쓰는 편향된 후처리이며, 미세 반사나 초점 흐림을 부드럽게 할 수 있다. 원본 PNG/NPY를 항상 함께 보존하고, 성능 비교와 기본 기능별 비교에는 필터를 적용하지 않는다.

`report/HW5_Report.pdf`에 구현 설명·실행법·실물 및 렌더 이미지·추가 기능의 실험·출처를 담았다. `demo/HW5_A1_Poster.pdf`와 `demo/README.md`는 현장 시연 준비용이다. 실제 Demo Day 전시·참여와 ETL 업로드는 사용자가 수행해야 하는 별도 항목이다.

제출 ZIP은 `python tools/package_submission.py`로 만들며 `dist/HW5_Submission.zip`에 코드·자산·사진·보고서·주요 결과·검증 기록을 포함한다. 다른 HW 폴더, 캐시, 임시 파일과 대용량 선형 `.npy`는 제외한다. `python tools/verify.py`는 표준 Python 진입점·테스트·자산과 보고서 파일을 다시 검사한다.
