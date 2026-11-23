# THE GREAT HALL — HW4 Extra

Cornell Box 안에 만든 **해리 포터 대연회장 오마주**다. 두 줄의 긴 목제 식탁과 중앙 통로, 벤치, 은잔과 접시, 뒤쪽의 높은 식탁과 아치 창을 구성했다. 공중 촛불 32개와 식탁 위 촛불 14개가 따뜻하게 빛난다. Cornell Box의 빨간 왼쪽 벽·초록 오른쪽 벽·천장 면 광원·열린 앞면을 유지한다.

양쪽 벽에는 네 기숙사의 긴 세로 배너를 벽과 평행하게 달았다. 왼쪽은 그리핀도르·후플푸프, 오른쪽은 슬리데린·래번클로다. 기숙사 이름의 기본 글꼴은 사용자가 선택한 **Cinzel Decorative Bold**이며 자간은 0.14 em이다. 한 줄로 쓴 단어 전체를 **시계 방향 90도** 회전시켰으며 문장 아래의 여백을 확보했다. 촛불 가까이에는 방향과 펼친 정도가 다른 책 6권이 떠다닌다. 기존 촛불을 배치해 활용하므로 광원 수는 52개로 유지한다.

## 실행

Python 3.12, pyglet 2.1.16, OpenGL 3.3 이상이 필요하다. 목재 텍스처를 포함한 모든 파일을 이 폴더에 동봉했으므로 실행 시 네트워크 연결이 필요하지 않다. 기존 `HW4`와도 독립적으로 실행된다.

`HW4` 폴더에서 다음과 같이 실행한다. 상위의 공통 환경을 사용하면 기본 장면과 Extra를 모두 실행할 수 있다.

```powershell
conda env create -f environment.yml
conda activate snu_graphics_hjj_hw4
python .\code_extra\main.py
```

이미 환경이 준비되어 있으면 환경 생성은 생략한다. 이 폴더의 `environment.yml`과 `requirements.txt`로 Extra만을 위한 환경을 만들 수도 있다.

## 조작

| 입력 | 기능 |
|---|---|
| 왼쪽 드래그 / 휠 | 카메라 회전 / 확대·축소 |
| 오른쪽·가운데 드래그, Shift + 왼쪽 드래그 | 카메라 이동 |
| Space | 촛불과 책의 부유·불꽃 흔들림 정지·재생 |
| R / F / V | 초기 시점 / 정면 / 사선 시점 |
| C | The Feast / Quiet Evening / After Hours 조명 설정 |
| 1 | 촛불의 emission과 실제 조명 켜기·끄기 |
| 3 / 4 | 반사 / shadow map 켜기·끄기 |
| 5 / 6 | 유리 용기 / normal·bump mapping 켜기·끄기 |
| 7 / 8 | 식기·음식 등 식탁 소품 / 화면 공간 접촉 명암 켜기·끄기 |
| 9 | 공중에 떠다니는 책 켜기·끄기 |
| + / - | 노출 조절 |
| [ / ] | 애니메이션 속도 조절 |
| H / S | HUD 숨기기 / 현재 PNG와 설정 JSON 저장 |
| Q / Esc | 종료 |

`1`은 촛불 46개를 제어한다. 천장 조명과 약한 창가 보조광은 비교를 위해 남긴다. 캡처는 `captures/`에 저장한다.

## 구현

### 모델링과 재질

- 외부 3D 모델을 사용하지 않았다. box, 실제 둥근 모서리를 가진 box, sphere, cylinder, torus와 회전체로 형상을 만든다.
- 은잔·접시·피처는 단면을 회전시킨 mesh다. 그릇의 내부와 가장자리 두께도 모델링했다. 접시의 금테, 포크·나이프, 접힌 냅킨, 빵·사과, 유리 용기를 추가했다.
- 촛대·심지·흐른 촛농과 물방울 형태의 불꽃을 별도 형상으로 그린다. 부유와 깜빡임은 작은 진폭의 시간 함수이며 유체·연소 시뮬레이션은 아니다.
- 목재는 Poly Haven **Wood Table 001**의 1K diffuse / OpenGL normal / 표면 광택 조절용 JPEG를 사용한다. 원본 파일 이름이 `rough.jpg`인 맵은 `gloss = 1 - texture.r`로 읽고, Phong의 `shininess`에 `mix(0.55, 1.10, gloss)`를 곱하는 용도로만 쓴다. 각 부품의 축척을 고려한 좌표로 샘플링하고 화면 미분으로 접선 좌표계를 복원한다. 색 텍스처만 선형화하고 나머지는 선형 데이터로 읽는다.
- 석재의 줄눈·색 변화·bump, 린넨의 미세 조직, 음식 표면은 절차적으로 계산한다. 표면의 광택은 재질별 `Ks`와 `shininess`로 조절한다.
- 문장은 참고 상품 사진과 같은 장식형 디자인의 투명 PNG 4장을 일반 UV mapping으로 표시한다. 원본 RGBA 파일을 사용하며, 텍스처의 투명 여백은 UV 범위로 피하고 alpha가 0.5 미만인 픽셀을 버린다. 문장에는 emission을 주지 않아 실제 장면의 조명을 받아 보인다. 폭 0.78·높이 2.45의 긴 배너를 각각 측면 벽에 평행하게 고정했으며, 천과 테두리가 바닥 높이 0.54까지 내려온다. `BANNER_BOTTOM`으로 아래쪽 길이를 조절한다. 원본 파일과 비상업적 사용 표기를 포함한 출처는 `assets/crests/README.md`에 기록했다.
- 기숙사 이름은 기본적으로 `assets/lettering/house_names_cinzel.png`의 4열 alpha atlas를 쓴다. `Material.pattern`의 0~3으로 해당 열을 선택해 배너의 평면 quad에 붙인다. 글자별 advance에 0.14 em을 더해 자간을 넓혔다. 글자 quad는 높이 1.18·중심 높이 1.26으로, 위쪽 시작 위치는 1.85다. `house_names.png`는 선택 가능한 Harry P 비교 글꼴이다. 비스듬한 시점에서 가는 획이 사라지지 않도록 alpha cutoff를 0.16으로 두었다. 금빛·은빛 글씨와 후플푸프의 짙은 글씨는 모두 일반 조명을 받으며 emission은 없다. 글자 PNG를 동봉하므로 실행 시 글꼴을 설치할 필요가 없다.
- `_book_nodes()`는 기존 box와 cylinder mesh로 표지·종이 묶음·인쇄선·표지의 금박 테두리를 만든다. 책마다 pitch·yaw·roll과 힌지 각도 `opening`이 달라, 비스듬히 열린 책·반쯤 접힌 책·거의 닫혀 표지가 보이는 책이 섞인다. `book_transform()`의 작은 이동·회전과 양쪽 힌지의 시간 변화로 책을 부유시킨다. 첫 공중 촛불 4개는 책보다 위쪽·앞쪽에 놓았다. 책에는 emission을 주지 않으며, 별도의 조명 알고리즘을 추가하지 않았다.
- 직접광은 Lambert diffuse와 Phong specular를 합산한다. 재질은 난반사색 `diffuse`, 정반사색 `specular`, 지수 `shininess`를 직접 지정한다.

### Phong 조명

현재 실행 코드는 Phong 조명 모델 하나를 사용한다. `main.py`를 그대로 실행하면 Phong으로 렌더링된다.

`shaders.py`의 `phong_direct()`는 반사 벡터 `R = reflect(-L, N)`을 쓴다. 광원을 향하는 면에 대해 `kd * max(N·L, 0) + ks * max(R·V, 0)^shininess`를 계산하고, 거리 감쇠·광원 세기·그림자를 곱해 합산한다. `kd = diffuse / PI`, `ks = specular`이며 균일한 ambient는 `0.011 * diffuse`다.

`great_hall.py`에서 은·금·나무·종이 등의 `diffuse`, `specular`, `shininess`를 직접 정한다. 예를 들어 금은 갈색 계열 난반사색과 노란 정반사색을 사용한다. `shininess`가 클수록 정반사 하이라이트가 좁아진다. 값은 이 장면에 맞춘 조절값이다.

인스턴스 자료는 모델 행렬 16개, diffuse·alpha 4개, specular·shininess 4개, emission·surface 4개, pattern과 padding 4개로 총 32개 float다. 정점 셰이더가 이 재질 계수를 fragment 셰이더로 전달한다.

그림자·normal mapping·유리 합성·AO와 환경 반사는 각각 독립적인 추가 기능이다. 반사 효과는 `3` 또는 `--disable reflections`로 제어한다.

### 조명과 그림자

총 **52개 조명**을 계산한다: 천장 면 광원의 2×2 샘플 4개, 공중 촛불 32개, 식탁 위 촛불 14개, 창가 보조광 2개다. 광원 색과 세기는 촛불·흰 천장광·약한 청색 보조광으로 제한했다. 불꽃 자체의 emission과 실제 주변을 비추는 조명은 별도로 계산한다.

직접광은 `power / (distance² + radius²)`로 감쇠한다. 천장에는 아래 방향 cosine을 추가한다. 조절값은 장면 단위의 상대 세기이며 실제 lumen이나 candela로 보정한 값은 아니다.

천장 4개 샘플과 주요 공중 촛불 4개, 총 **8개**의 아래쪽 시점에서 depth map을 만든다. 기본 1024², 3×3 PCF, polygon offset과 기울기 기반 bias를 사용한다. 주요 촛불이 움직이면 광원 행렬도 갱신한다. 나머지 44개 조명에는 shadow map이 없고, 촛불의 위쪽 방향도 omnidirectional shadow로 계산하지 않는다.

### 반사와 유리

- 방과 장면을 256²×6 HDR cubemap으로 캡처한다. box projection으로 방 벽의 위치를 보정하고 `shininess`에 따라 mip level과 반사 세기를 정해 환경 반사를 근사한다. 반사색에는 재질의 `specular`를 곱한다. 0.4초 간격으로 갱신한다.
- 바닥에는 반사된 카메라로 절반 해상도 planar reflection을 만들고, 고정 비율 0.003으로 약하게 합성한다.
- 유리 용기는 불투명 패스 뒤에 그린다. 물체를 view-space Z로 정렬하고, 각 물체의 뒷면 → 앞면 순서로 고정 alpha blending한다. depth test는 유지하고 depth write는 끈다. 유리의 alpha는 재질에 직접 지정하며, 두꺼운 유리의 굴절·caustics·다중 계면을 추적하지 않는다.
- cubemap의 mipmap은 반사를 흐리는 근사이며, 가까운 물체의 parallax와 자기 반사에는 오차가 있다.

### 접촉 명암과 HDR

RGBA16F의 4× MSAA 장면을 색·깊이 텍스처로 resolve한다. 깊이로 view-space 위치와 법선을 복원하고, 반구의 16개 샘플을 사용해 주변 차폐를 추정한다. 절반 해상도에서 계산한 결과는 깊이 차이를 고려해 필터링한다.

`8`의 효과는 합성된 장면을 약하게 어둡게 만드는 **화면 공간 접촉 명암 근사**다. 밝은 불꽃은 보존하지만 간접광만 분리해 적용하는 물리적인 AO나 완전한 GI는 아니다. 화면 밖의 가림과 투명 유리의 깊이는 반영하지 못한다.

최종 패스에서는 FXAA 방식의 경계 필터와 접촉 명암을 적용한 뒤, 노출·톤매핑·sRGB 변환으로 화면에 표시한다. 톤매핑은 밝은 값이 모두 흰색으로 잘리는 것을 줄이는 과정이다.

## 화면 저장과 실행 옵션

`S`를 누르면 현재 화면과 설정 JSON을 `captures/`에 저장한다. 저장 폴더가 없으면 실행 중에 만든다. 미리 정한 시점의 화면을 저장하거나 효과를 선택해 실행할 수도 있다. 아래 명령은 `HW4` 폴더 기준이다.

```powershell
python .\code_extra\main.py --hidden --no-hud --capture .\code_extra\captures\hall.png --frames 5
python .\code_extra\main.py --banner-font harry
python .\code_extra\main.py --disable reflections
```

`--disable`은 `lights,reflections,shadows,glass,bump,dressing,ao,receivers`를 쉼표로 조합한다. `--banner-font cinzel/harry`의 기본값은 `cinzel`이다. `--palette 0/1/2`, `--time`, `--width`, `--height`, `--shadow-size 512/1024/2048`도 지원한다. 각 PNG 옆의 JSON에는 조명 모델, 설정과 장면 정보를 저장한다.

## 파일 구성

`great_hall.py`는 모델·조명·애니메이션, `scene_data.py`는 공통 자료형, `geometry.py`는 형상과 instancing, `shaders.py`는 GLSL, `renderer.py`는 렌더 패스, `textures.py`는 동봉 재질 로드를 담당한다.

출처와 AI 사용 범위는 `References.md`, 목재·문장·글자 atlas의 출처는 각각 `assets/wood/README.md`, `assets/crests/README.md`, `assets/lettering/README.md`에 적었다. 제출 보고서에는 실제 구현과 위의 근사를 구분해 설명해야 한다.
