# 장면 데이터 출처

- `models/cornell_scene.obj`, `.mtl`: 앞선 과제에서 Blender로 제작한 Cornell Box 장면의 독립 사본.
- `textures/front.jpg`: HW4의 `chocopie_front.jpg` 사본.
- 나머지 면 텍스처: HW4 `textures/color_matched/`에서 사용하던 파일을 실제 적용 면 이름으로 복사했다.
  - back ← chocopie_back, right ← chocopie_bottom, left ← chocopie_top
  - top ← chocopie_right, bottom ← chocopie_left
- 기존 HW4 출처 기록에 따르면 chocopie_front 및 chocopie_left의 외부 상품 사진 출처는 [쿠팡 상품 페이지](https://www.coupang.com/vp/products/6659185462?vendorItemId=82501992251)다.
- `pictures/Cornell Box.jpg`는 사용자가 넣어 둔 원본이며 수정하지 않았다. `pictures/HW4_render.png`는 HW4 결과의 사본이다.

HW5는 실행 중 HW2/HW4 폴더를 읽거나 가져오지 않는다. 원본 MTL은 출처와 형상 보존을 위해 포함했고, 실제 광학 재질은 `scene.json`에서 설정한다.
