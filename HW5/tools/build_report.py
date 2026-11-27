"""Build a measured Korean report and A1 poster (optional: reportlab).

Run after final rendering, compare, benchmark and build_figures.py. System
Malgun Gothic is embedded as a subset; no font installation is performed.
"""

import json
import os
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
ASSETS = ROOT / "report/assets"
INK = colors.HexColor("#193149")
TEAL = colors.HexColor("#147D92")
MUTED = colors.HexColor("#5B6877")
PALE = colors.HexColor("#EDF3F6")


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def register_fonts():
    font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    regular, bold = font_dir / "malgun.ttf", font_dir / "malgunbd.ttf"
    if not regular.is_file() or not bold.is_file():
        raise SystemExit("Report generation needs Malgun Gothic regular/bold in the Windows Fonts directory")
    pdfmetrics.registerFont(TTFont("Korean", str(regular)))
    pdfmetrics.registerFont(TTFont("KoreanBold", str(bold)))
    pdfmetrics.registerFontFamily("Korean", normal="Korean", bold="KoreanBold")


class Report:
    def __init__(self, path):
        self.width, self.height = A4
        self.margin, self.page_number = 47., 0
        self.body_width = self.width - 2 * self.margin
        self.c = canvas.Canvas(str(path), pagesize=A4)
        self.c.setTitle("Computer Graphics HW5 - Ray Tracing")
        self.c.setAuthor("한재준 (2024-10189); implementation assistance: Codex")

    def page(self, title, subtitle=None):
        if self.page_number:
            self.c.showPage()
        self.page_number += 1
        self.c.setFillColor(TEAL)
        self.c.rect(0, self.height - 9, self.width, 9, fill=1, stroke=0)
        self.c.setFillColor(MUTED)
        self.c.setFont("Korean", 8)
        self.c.drawString(self.margin, self.height - 34, "SNU COMPUTER GRAPHICS 2026 | PROGRAMMING ASSIGNMENT 5")
        self.c.setFillColor(INK)
        self.c.setFont("KoreanBold", 22)
        self.c.drawString(self.margin, self.height - 69, title)
        self.y = self.height - 89
        if subtitle:
            self.p(subtitle, size=9, color=MUTED)
        self.c.setStrokeColor(colors.HexColor("#D9E2E8"))
        self.c.line(self.margin, 35, self.width - self.margin, 35)
        self.c.setFont("Korean", 8)
        self.c.setFillColor(MUTED)
        self.c.drawString(self.margin, 22, "한재준 | 2024-10189 | Ray Tracing")
        self.c.drawRightString(self.width - self.margin, 22, str(self.page_number))

    def space(self, amount=8):
        self.y -= amount

    def p(self, text, size=10.2, bold=False, color=INK, gap=7):
        style = ParagraphStyle("body", fontName="KoreanBold" if bold else "Korean", fontSize=size,
                               leading=size * 1.48, textColor=color, wordWrap="CJK")
        paragraph = Paragraph(text, style)
        _, height = paragraph.wrap(self.body_width, 1000)
        if self.y - height < 45:
            raise ValueError(f"Report page {self.page_number} overflows: {text[:45]}")
        paragraph.drawOn(self.c, self.margin, self.y - height)
        self.y -= height + gap

    def heading(self, text):
        self.p(text, size=12.5, bold=True, color=TEAL, gap=7)

    def image(self, path, caption=None, max_height=None):
        source = ImageReader(str(path))
        width, height = source.getSize()
        draw_width = self.body_width
        draw_height = draw_width * height / width
        if max_height and draw_height > max_height:
            draw_width *= max_height / draw_height
            draw_height = max_height
        if self.y - draw_height < 45:
            raise ValueError(f"Report page {self.page_number}: image does not fit: {path}")
        self.c.drawImage(source, self.margin + (self.body_width - draw_width) / 2,
                         self.y - draw_height, draw_width, draw_height, preserveAspectRatio=True, mask="auto")
        self.y -= draw_height + 5
        if caption:
            self.p(caption, size=8.3, color=MUTED, gap=10)

    def table(self, headers, rows, widths, font_size=9):
        style = ParagraphStyle("cell", fontName="Korean", fontSize=font_size,
                               leading=font_size * 1.4, wordWrap="CJK", textColor=INK)
        header_style = ParagraphStyle("head", parent=style, fontName="KoreanBold", textColor=colors.white)
        cells = [[Paragraph(str(x), header_style) for x in headers]]
        cells += [[Paragraph(str(x), style) for x in row] for row in rows]
        table = Table(cells, colWidths=widths, hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), INK),
                                   ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                                   ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        _, height = table.wrap(self.body_width, 1000)
        if self.y - height < 45:
            raise ValueError(f"Report page {self.page_number}: table does not fit")
        table.drawOn(self.c, self.margin, self.y - height)
        self.y -= height + 10

    def code(self, text):
        self.p('<font name="Courier" size="8.4">' + escape(text).replace("\n", "<br/>") + "</font>", size=9, gap=10)


def report():
    final = load("cornell.json")
    benchmark = load("benchmark/timings.json")
    comparison = load("comparison/results.json")
    penumbra = load("penumbra_validation.json")
    options, stats = final["options"], final["scene"]
    cases = comparison["cases"]
    config = stats["config"]
    path = ROOT / "report/HW5_Report.pdf"
    path.parent.mkdir(exist_ok=True)
    doc = Report(path)
    w = doc.body_width

    doc.page("HW5: Ray Tracing", "2024-10189 한재준 | 구현·실험 검증본 | 2026-11-26")
    doc.p("HW2에서 제작한 Cornell Box를 CPU ray tracing으로 렌더링하였다. 픽셀에서 시작한 광선의 교차점과 후속 경로를 직접 계산한다. NumPy/Pillow/Numba를 사용하며 OpenGL, PyGlet, Blender 렌더러 및 GPU ray tracing 엔진은 사용하지 않는다.")
    doc.image(OUT / "reference.png", "그림 1. 실물 사진 / HW4 OpenGL / HW5 노이즈 제거 사본. 전체 프레임을 같은 크기로 표시했다.")
    doc.table(["명세", "구현·증거", "상태"], [
        ["Ray casting·그림자 (10)", "삼각형 교차, shadow ray, 면 광원, penumbra 확대 비교", "구현·검증"],
        ["재귀 반사·굴절 (10)", "Fresnel/Snell/TIR, 매질 스택, 실제 반사·굴절 경로 테스트", "구현·검증"],
        ["사진 재현 기능 (10)", "텍스처, 광택, 다중 반사 GI, 흡수 및 기능별 비교", "구현·실험"],
        ["추가 기능 (10)", "Supersampling AA, thin-lens DOF, 선택형 노이즈 제거", "구현·실험"],
        ["공간 자료구조 (10)", "SAH BVH/전체 순회 시간과 동일 영상 확인", "구현·실험"],
        ["보고서 (10)", "구현, 실행법, 사진·렌더, 실험 및 출처", "본 문서"],
        ["Demo Day (30)", "A1 포스터와 시연 순서 준비", "현장 참여 필요"]], [117, 302, w - 419], 8.7)
    doc.p("제출용 단일 ZIP은 별도 패키징 도구로 만들고 무결성을 검사한다. Demo Day 현장 전시와 ETL 업로드는 사용자 수행 항목이며, 파일을 생성한 것만으로 완료했다고 보지 않는다.", size=9)

    doc.page("1. Ray casting과 면 광원 그림자")
    doc.p("카메라의 시선·수평·수직 기저로 픽셀을 통과하는 광선을 만든다. Möller-Trumbore 교차로 가장 가까운 삼각형과 barycentric 좌표를 구하고 법선·UV를 보간한다. 삼각형은 양면을 검사한다. 경계에서 생기는 자기 교차는 작은 origin offset으로 줄인다.")
    light = config["light"]
    doc.p(f"광원은 천장 위치 {light['center']}의 {light['width']} × {light['depth']} 사각형이다. 면적에서 위치를 균일하게 샘플링하며 정사각 샘플 수에는 층화 격자를 사용한다. 직접광은 BRDF, 입사 cosine, 광원 cosine, 거리 제곱 및 면적 PDF로 계산한다.")
    doc.code("L_direct = average[ f_r * L_e * cos(theta) * visibility / p_light ]\np_light(solid angle) = distance^2 / (light_area * cos(theta_light))")
    doc.image(OUT / "comparison/detail_shadows.png", "그림 2. 실제 Cornell 장면의 면 광원(왼쪽)과 광원 중앙점(오른쪽) 그림자. 같은 좌표를 nearest-neighbor로 확대했다.")
    doc.image(ASSETS / "penumbra_validation.png", "그림 3. 독립된 평면 occluder 장면에서 계산한 가시성. 주황 점은 실제 shadow ray, 실선은 해석적인 면 광원 가시성이다.", max_height=172)
    doc.p(f"검증 장면은 광원 y=2, occluder y=1, 수광선 y=0이다. |x|≤0.2에서 umbra, 0.2&lt;|x|&lt;1.2에서 penumbra가 생긴다. 수광점마다 256개의 광원 샘플을 추적했으며 해석값과의 최대 차이는 {penumbra['maximum_visibility_error']:.6f}였다.", size=9)

    doc.page("2. 재귀 반사·굴절과 매질")
    doc.p("입사 방향과 표면 법선에서 반사 방향을 계산하고, 굴절 방향은 Snell 법칙으로 구한다. 정확한 비편광 Fresnel 반사율을 반사/굴절 경로의 선택 확률로 사용한다. 임계각을 넘으면 전반사하며, 투과 시 radiance의 굴절률 제곱 보정을 적용한다.")
    doc.code("eta_i * sin(theta_i) = eta_t * sin(theta_t)\nF = (R_s^2 + R_p^2) / 2;   T_absorb(d) = exp(-sigma_a * d)\nradiance throughput on transmission *= (eta_i / eta_t)^2")
    doc.p("컵은 외벽·내벽·바닥·입구 띠가 닫힌 속 빈 셸이다. 물은 meniscus 수면과 측면·바닥이 이어진 부피다. 매질 ID 스택으로 현재 IOR와 흡수 계수를 관리하고, 물질 내부에서 이동한 실제 거리에 Beer-Lambert 흡수를 적용한다. 컵 IOR=1.49, 물 IOR=1.333이며 흡수 값은 사진 조절값이다.")
    doc.image(OUT / "comparison/detail_refraction.png", "그림 4. 재귀 투명 경로(왼쪽) / 컵·물을 회색 불투명 재질로 바꾼 대조(오른쪽).")
    doc.image(OUT / "comparison/detail_reflections.png", "그림 5. 광택 반사 사용(왼쪽) / 광택과 Fresnel 반사 비활성화(오른쪽).")
    doc.p("통합 테스트는 직접광을 끈 작은 장면에서 반사 후 emitter에 도달하는 경로와 유전체 앞/뒤 두 경계를 통과해야 emitter를 볼 수 있는 경로를 검사한다. 컵·물의 모든 모서리가 두 삼각형에 연결되고 signed volume이 양수인지도 확인한다. 재귀 rendering equation은 함수 호출 스택 대신 광선 상태를 갱신하는 루프로 계산한다.", size=9)

    doc.page("3. 사진 재현: 텍스처와 간접광")
    doc.p("포장지의 여섯 면에 HW4의 보정된 UV와 이미지를 적용한다. sRGB 텍스처를 먼저 선형 RGB로 변환한 다음 bilinear 보간한다. 상자 모서리 bevel과 윗면 능선에도 동일한 UV를 보존한다. 난반사는 Lambert, 코팅 광택은 정규화된 수정 Phong lobe를 사용한다.")
    doc.code("f_r = albedo * (1-Ks)/pi + Ks*(n+2)/(2*pi) * max(R dot L, 0)^n")
    doc.image(OUT / "comparison/detail_textures.png", "그림 6. 같은 형상에서 인쇄 텍스처 사용(왼쪽) / 텍스처 비활성화(오른쪽).")
    doc.p("간접광은 임의 ambient 색이나 베이크된 조명 대신 표면 사이의 실제 후속 경로로 계산한다. cosine-weighted 난반사와 Phong 방향을 혼합 샘플링하고, next-event estimation과 BSDF 샘플의 직접광을 power-heuristic MIS로 결합한다. 깊이 4 이후에는 Russian roulette를 사용한다.")
    doc.image(OUT / "comparison/detail_indirect.png", "그림 7. 다중 반사 GI와 색 번짐(왼쪽) / 난반사 후속 경로 비활성화(오른쪽).")
    doc.p("재검증 중 난반사 경로 한도에 도달했을 때 glossy 경로용 MIS 가중치를 난반사 직접광에도 곱하던 문제를 수정했다. 난반사는 광원 샘플의 전체 기여를 유지하고, 후속 경로로도 추정하는 성분에만 MIS를 적용한다. 직접광만 추정한 값과 glossy 경로를 함께 추정한 값의 에너지 일치를 별도 테스트로 확인했다.", size=9)

    doc.page("4. 추가 기능: AA, DOF, 노이즈 제거")
    doc.heading("Supersampling antialiasing")
    doc.p("픽셀 안에서 서로 다른 위치로 카메라 광선을 보내 선형 radiance를 평균한다. 정사각 spp에는 층화 격자를 사용하고 그 외에는 jittered supersampling을 사용한다. AA 대조는 광원·경로 샘플 수를 그대로 두고 카메라 광선만 픽셀 중앙에 고정한다.")
    doc.image(OUT / "comparison/detail_aa.png", "그림 8. Supersampling AA(왼쪽) / 픽셀 중앙 광선(오른쪽). 밝기나 노이즈 제거를 추가로 적용하지 않았다.")
    doc.heading("Thin-lens depth of field")
    doc.p("렌즈 원판을 균일하게 샘플링하고 pinhole 광선이 초점면과 만나는 점을 향해 새 광선을 보낸다. 서로 다른 렌즈 위치의 광선이 같은 초점면 점에 수렴하는지 테스트했다. 기본 사진 비교는 pinhole이며 DOF는 렌즈 반지름 0.045, 초점 거리 6.9인 별도 변형이다.")
    doc.image(OUT / "comparison/detail_dof.png", "그림 9. Pinhole 기준(왼쪽) / thin-lens DOF(오른쪽).")
    doc.heading("선택형 guide 기반 노이즈 제거")
    doc.p("선형 RGB와 샘플 분산을 저장하고 albedo로 나눈 조명을 normal/depth/material guide와 함께 à trous 필터로 여과한다. 재질 경계를 넘는 번짐을 제한한다. 이 과정은 편향된 후처리이므로 원본과 사본을 함께 보존한다. 일정한 두 재질에 인위적 노이즈를 더한 테스트에서 오차 감소와 경계 보존을 확인했다. BVH 시간 비교 및 기능별 원본 비교에는 필터를 적용하지 않는다.", size=9.5)

    doc.page("5. SAH BVH와 렌더링 시간")
    doc.p(f"장면에는 {stats['triangles']:,}개 삼각형이 있다. 각 삼각형의 AABB와 centroid를 계산하고 12-bin surface area heuristic으로 이진 분할한다. 기본 leaf 크기는 4개 이하이며 평탄화 배열에 저장한다. 현재 트리는 {stats['bvh_nodes']:,}개 노드, 깊이 {stats['bvh_depth']}다. AABB slab test와 가까운 자식 우선 순회로 불필요한 삼각형 교차를 줄인다.")
    doc.p("대조 경로는 같은 삼각형 교차 공식을 사용해 모든 삼각형을 검사한다. 두 경로에서 같은 카메라·광학 옵션·seed를 사용하고 실행 순서를 교대로 바꾸며 3회 측정했다. 같은 거리의 삼각형은 ID 순서로 정해 순회 순서에 따른 표면 선택 차이를 막았다.")
    median = benchmark["median_render_seconds"]
    doc.table(["측정", "시간 / 결과"], [
        ["BVH 렌더 중앙값", f"{median['bvh']:.6f} s"], ["전체 삼각형 순회 중앙값", f"{median['brute_force']:.6f} s"],
        ["BVH 구축", f"{benchmark['bvh_build_seconds']:.6f} s"],
        ["구축 + BVH 렌더", f"{benchmark['bvh_build_plus_median_render_seconds']:.6f} s"],
        ["렌더만 비교한 가속 비율", f"{benchmark['speedup']:.2f}x"],
        ["선형 RGB 최대 차이", str(benchmark['linear_max_abs_difference'])]], [270, w - 270])
    doc.image(ASSETS / "bvh_timing.png", "그림 10. 렌더만 비교한 시간과 BVH 구축을 더한 시간을 구분했다.", max_height=156)
    bopts = benchmark["runs"]["bvh"][0]["options"]
    doc.p(f"조건: {bopts['width']}×{bopts['height']}, {bopts['spp']} spp, 최대 깊이 {bopts['max_depth']}, 난반사 경로 {bopts['diffuse_bounces']}, {benchmark['runs']['bvh'][0]['threads']} CPU 스레드. JIT·준비·파일 저장은 렌더 시간에서 제외한다. 작은 이미지에서는 구축 비용이 크므로 렌더 가속 비율을 전체 실행 속도로 해석하면 안 된다.", size=9)
    doc.p(f"환경: Python {benchmark['python']}, NumPy {benchmark['numpy']}, Numba {benchmark['numba']}. 운영체제: {escape(benchmark['platform'])}.", size=8.8)

    doc.page("6. 최종 결과와 기능별 실험")
    doc.p(f"최종 원본은 {options['width']}×{options['height']}, {options['spp']} spp, 최대 깊이 {options['max_depth']}, 난반사 경로 {options['diffuse_bounces']}이다. CPU 렌더 시간은 {final['render_seconds']:.2f}초이며, {final['rays']:,}개 광선과 {final['triangle_tests']:,}회 삼각형 검사를 수행했다. JIT/준비 시간은 {final['warmup_seconds']:.2f}초로 분리해 기록했다.")
    doc.image(ASSETS / "final_detail.png", "그림 11. 최종 raw 영상(왼쪽)과 같은 샘플에서 만든 노이즈 제거 사본(오른쪽). 두 영상에 같은 Cornell 영역 crop을 적용했다.", max_height=233)
    copt = cases["full"]["options"]
    doc.p(f"기능별 비교는 {copt['width']}×{copt['height']}, {copt['spp']} spp, 같은 seed·노출로 실행했다. 아래 RMSE는 기준 영상과의 차이이며, 사진 오차나 화질 점수가 아니다. 경로 변경 후 난수 사용도 달라지므로 Monte Carlo 변동이 포함된다.", size=9.3)
    names = {"full": "기준", "indirect": "GI 끔", "shadows": "중앙점 그림자", "reflections": "광택 반사 끔",
             "refraction": "불투명 컵·물", "textures": "텍스처 끔", "aa": "AA 끔", "dof": "DOF 켬", "absorption": "흡수 끔"}
    doc.table(["변형", "렌더 시간 (s)", "기준과 선형 RMSE"],
              [[names[name], f"{data['render_seconds']:.3f}", f"{data['linear_rmse_from_full']:.6f}"] for name, data in cases.items()],
              [210, 140, w - 350], 8.5)
    doc.p("사진과 비교했을 때 전체 배치·인쇄·색 번짐은 재현되지만 바닥의 나뭇결, 플라스틱의 실제 미세 산란, 촬영 WB·렌즈·센서 응답까지 측정한 결과는 아니다. 필터는 미세 반사를 부드럽게 할 수 있으므로 raw 영상도 함께 검토한다.", size=9)

    doc.page("7. 설치, 실행, 실험 재현과 제출")
    doc.heading("기본 실행은 python main.py")
    doc.p("기존 snu_graphics_hjj 환경을 활성화하고 HW5 폴더에서 다음을 실행한다. NumPy/Pillow/Numba는 이 환경에서 사용한다. 첫 실행은 Numba JIT 컴파일 때문에 시간이 더 걸리며 이후에는 캐시를 사용한다.")
    doc.code("conda activate snu_graphics_hjj\ncd HW5\npython main.py")
    doc.p("저장소 루트에서는 python HW5/main.py도 가능하다. 자산 경로는 main.py의 위치를 기준으로 찾는다.", size=9.4)
    doc.heading("최종 영상과 대조 실험")
    doc.code("python main.py render --preset final --denoise --save-linear\n  --output outputs/cornell.png\npython main.py compare --width 480 --height 360 --spp 144\n  --max-depth 20 --diffuse-bounces 5\n  --features indirect shadows reflections refraction textures aa dof absorption\n  --save-linear\npython main.py benchmark --repeats 3 --save-linear")
    doc.p("위의 줄 바꿈은 읽기 편하게 나눈 것이므로 각 명령의 옵션은 한 줄에 이어 입력한다. --width/--height/--spp로 품질을 바꾸고 --threads로 CPU 사용량을 정한다. --aperture는 렌즈 반지름, --focus-distance는 초점 거리다. --no-* 옵션과 --hard-shadows로 기능을 비교한다. --checkpoint는 중간 미리보기를 갱신하고, --save-linear는 tone mapping 전 NPY를 저장한다. 장면·재질은 scene.json에서 바꾼다.", size=9.2)
    doc.heading("검증과 ZIP")
    doc.code("python -m unittest discover -s tests -v\npython tools/verify.py\npython tools/package_submission.py")
    doc.p("코드/설정/자산/사진/보고서/시연 자료/주요 PNG·JSON은 ZIP에 포함하고 다른 과제 폴더·캐시·임시 파일·대용량 선형 NPY는 제외한다. ZIP 내부 manifest의 SHA-256과 CRC를 확인한다. outputs/verification.json과 test_results.txt에 실제 로컬 검증 결과를 남긴다. ZIP을 풀어서 main.py가 실행되는지도 검사한다.", size=9.2)
    doc.p("PDF 재생성 도구는 선택적 reportlab/matplotlib/pypdf와 시스템 맑은 고딕을 사용한다. 완성된 PDF 열기나 렌더러 실행에는 이 추가 도구가 필요하지 않다. 세부 명령과 폴더 구성은 README.md를 참조한다.", size=9)

    doc.page("8. 검증 범위, 출처와 남은 현장 작업")
    doc.heading("검증과 근사")
    doc.p("16개 테스트에서 Fresnel/Snell/전반사, 매질 스택, 삼각형/AABB, BVH 동등성, 같은 거리의 교차점, 컵·물의 닫힘, 텍스처 UV, DOF 초점, seed 재현성, 필터 경계 보존 및 실제 반사·굴절·penumbra 경로를 확인했다. 단위 테스트만으로 사진과의 완전한 일치나 모든 장면에서의 무편향성을 보장하지는 않는다.", size=9.3)
    doc.p("투명 물체를 통과하는 shadow connection은 직선의 Fresnel·흡수 근사다. 카메라 경로는 실제로 굴절하지만, 광원까지 연결되는 굴절 caustic 경로는 정확히 풀지 않는다. 컵의 흐림은 8% Lambert 계면 혼합으로 근사하며 부피 산란, 스펙트럼 분산, 모션 블러는 포함하지 않는다. 재질과 흡수 계수는 실측값이 아닌 사진 보정값이다.", size=9.3)
    doc.heading("참고 자료와 외부 자산")
    refs = [
        ("[1] SNU Computer Graphics - Programming Assignment #5", "https://sites.google.com/view/snucse-graphics2026/programming-assignment-5"),
        ("[2] PBRT 4e - A Better Path Tracer", "https://pbr-book.org/4ed/Light_Transport_I_Surface_Reflection/A_Better_Path_Tracer"),
        ("[3] PBRT 4e - Dielectric BSDF", "https://pbr-book.org/4ed/Reflection_Models/Dielectric_BSDF"),
        ("[4] PBRT 4e - Bounding Volume Hierarchies", "https://pbr-book.org/4ed/Primitives_and_Intersection_Acceleration/Bounding_Volume_Hierarchies"),
        ("[5] Möller &amp; Trumbore (1997), Fast, Minimum Storage Ray-Triangle Intersection", "https://doi.org/10.1080/10867651.1997.10487468"),
        ("[6] Lafortune &amp; Willems (1994), Using the Modified Phong Reflectance Model", "https://graphics.cs.kuleuven.be/publications/Phong/"),
        ("[7] NumPy / Pillow / Numba 공식 문서", "https://numba.readthedocs.io/en/stable/"),
        ("[8] 기존 HW4에 기록한 포장지 상품 사진 출처", "https://www.coupang.com/vp/products/6659185462?vendorItemId=82501992251")]
    for label, url in refs:
        doc.p(f'<link href="{escape(url, quote=True)}" color="#147D92">{label}</link>', size=8.7, gap=5)
    doc.p("광선 교차, 적분기, BSDF, 가시성 및 BVH는 과제 코드로 작성했다. PBRT에서는 알고리즘 개념을 참고했으며 구현 코드를 복사하지 않았다. 모델은 기존 HW2와 동일한 OBJ이며 컵/물 생성 코드는 HW4의 비-OpenGL 코드를 재사용했다. 사진과 텍스처의 면별 출처는 assets/README.md 및 References.md에 기록하였다.", size=9)
    doc.p("Codex를 코드 작성·수정, 렌더링·테스트 검증 및 보고서/시연 자료 작성에 사용했다. 제출자는 AI가 작성한 부분까지 검토하고 설명할 수 있어야 한다.", size=9)
    doc.heading("Demo Day와 제출")
    doc.p("A1 포스터와 demo/README.md의 시연 순서를 준비하였다. 포스터 인쇄·실물 Cornell Box 설치·현장 참여는 직접 수행해야 한다. 단일 ZIP 무결성 검사는 로컬 준비 상태를 확인하는 것이며 ETL 업로드 완료를 뜻하지 않는다.", size=9.3)
    doc.c.save()
    print(f"Saved {path} ({doc.page_number} pages)")


def poster():
    final, benchmark = load("cornell.json"), load("benchmark/timings.json")
    path = ROOT / "demo/HW5_A1_Poster.pdf"
    path.parent.mkdir(exist_ok=True)
    width, height = 594 * mm, 841 * mm
    c = canvas.Canvas(str(path), pagesize=(width, height))
    c.setTitle("HW5 Cornell Box - A1 Demo Poster")
    c.setAuthor("한재준 / 2024-10189")
    margin, gap = 65., 30.
    usable = width - 2 * margin
    c.setFillColor(TEAL)
    c.rect(0, height - 20, width, 20, fill=1, stroke=0)

    def text(x, y, value, size=24, bold=False, color=INK):
        c.setFillColor(color)
        c.setFont("KoreanBold" if bold else "Korean", size)
        c.drawString(x, y, value)

    def para(x, y, value, w, size=23, color=INK):
        style = ParagraphStyle("poster", fontName="Korean", fontSize=size, leading=size * 1.55,
                               wordWrap="CJK", textColor=color)
        p = Paragraph(value, style)
        _, h = p.wrap(w, 2000)
        p.drawOn(c, x, y - h)
        return h

    def image(path, x, top, w, h):
        c.drawImage(str(path), x, top - h, w, h, preserveAspectRatio=True, anchor="c", mask="auto")

    text(margin, height - 105, "CORNELL BOX / RAY TRACING", 55, True)
    text(margin, height - 157, "HW2 장면에서 출발한 CPU 광선 추적 | 2024-10189 한재준", 26, color=MUTED)
    text(margin, height - 221, "실물 사진 · HW4 · HW5", 30, True, TEAL)
    image(OUT / "reference.png", margin, height - 247, usable, usable * 522 / 1920)
    y = height - 247 - usable * 522 / 1920 - 56
    text(margin, y, "광선을 따라 계산한 효과", 31, True, TEAL)
    card_w = (usable - gap * 2) / 3
    cards = [("01  그림자", "면 광원을 나눠 shadow ray를 추적한다. 가려진 비율이 umbra와 penumbra를 만든다."),
             ("02  반사 · 굴절", "Fresnel, Snell, 전반사와 매질 스택으로 컵·물을 통과하는 실제 경로를 잇는다."),
             ("03  간접광", "텍스처와 BRDF를 평가하고 다중 반사 경로를 적분해 벽의 색 번짐을 만든다.")]
    for i, (title, body) in enumerate(cards):
        x = margin + i * (card_w + gap)
        text(x, y - 57, title, 27, True)
        para(x, y - 80, body, card_w - 8, 21)
    y -= 252
    half = (usable - gap) / 2
    text(margin, y, "면 광원 / 중앙점 광원", 26, True)
    text(margin + half + gap, y, "재귀 투명 경로 / 불투명 대조", 26, True)
    pair_h = half * 342 / 960
    image(OUT / "comparison/detail_shadows.png", margin, y - 24, half, pair_h)
    image(OUT / "comparison/detail_refraction.png", margin + half + gap, y - 24, half, pair_h)
    y -= pair_h + 90
    text(margin, y, "GI 켬 / 끔", 26, True)
    text(margin + half + gap, y, "AA 켬 / 끔", 26, True)
    image(OUT / "comparison/detail_indirect.png", margin, y - 24, half, pair_h)
    image(OUT / "comparison/detail_aa.png", margin + half + gap, y - 24, half, pair_h)
    y -= pair_h + 92
    text(margin, y, "같은 영상, 다른 교차 검색 비용", 31, True, TEAL)
    image(ASSETS / "bvh_timing.png", margin, y - 25, usable * .62, 258)
    text(margin + usable * .66, y - 100, f"{benchmark['speedup']:.2f}x", 65, True, TEAL)
    para(margin + usable * .66, y - 135,
         "BVH / 전체 순회 렌더 중앙값 비교<br/>선형 RGB 최대 차이: 0<br/>JIT·구축·저장 시간은 별도", usable * .34, 21)
    y -= 335
    opts = final["options"]
    para(margin, y, f"최종 영상 {opts['width']} × {opts['height']} / {opts['spp']} spp / 경로 깊이 {opts['max_depth']} / CPU 렌더 {final['render_seconds']:.1f}초. "
         "Pinhole 기준 영상과 thin-lens DOF, raw 영상과 선택형 노이즈 제거 사본을 함께 제공한다.", usable, 22)
    y -= 113
    para(margin, y, "투명 shadow 연결은 직선 Fresnel·흡수 근사이며 caustics를 정확히 풀지는 않는다. "
         "노이즈 제거 영상은 라벨로 구분했다. 과제 코드·자료 작성과 검증에 Codex를 사용했다. 상세 구현·실험·자산 출처는 보고서와 References.md에 있다.", usable, 19, MUTED)
    text(margin, 45, "SNU Computer Graphics 2026 | Demo Day 전시 자료 | 실제 현장 참여는 별도", 17, color=MUTED)
    if y < 150:
        raise ValueError("Poster layout overflows")
    c.save()
    print(f"Saved {path} (A1 portrait)")


if __name__ == "__main__":
    register_fonts()
    report()
    poster()
