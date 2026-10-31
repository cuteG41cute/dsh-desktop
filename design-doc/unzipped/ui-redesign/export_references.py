from pathlib import Path
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "references"
OUTPUT.mkdir(exist_ok=True)
THEMES = [
    ("frost", "毛玻璃"),
    ("liquid", "液态玻璃"),
    ("crystal", "水晶"),
    ("flat", "扁平化"),
    ("alpine", "雪山"),
    ("dawn", "晨光"),
    ("sea", "静海"),
]

options = Options()
options.add_argument("--headless")
options.add_argument("--window-size=1440,900")
options.add_argument("--force-device-scale-factor=1")
driver = webdriver.Edge(options=options)
driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
    "width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False
})
try:
    for index, (theme, _) in enumerate(THEMES, 1):
        for mode in ("day", "night"):
            driver.get(f"http://127.0.0.1:8765/?theme={theme}&mode={mode}")
            driver.execute_script("document.fonts.ready")
            filename = OUTPUT / f"{index:02d}-{theme}-{mode}.png"
            driver.save_screenshot(str(filename))
            print(filename.name)
finally:
    driver.quit()

font_paths = [
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
]
font_path = next((path for path in font_paths if path.exists()), None)
font = ImageFont.truetype(str(font_path), 22) if font_path else ImageFont.load_default()
small_font = ImageFont.truetype(str(font_path), 15) if font_path else ImageFont.load_default()
thumb_w, thumb_h = 648, 405
label_h, gap, margin, header_h = 42, 18, 24, 78
sheet_w = margin * 2 + thumb_w * 2 + gap
sheet_h = header_h + margin + (thumb_h + label_h + gap) * len(THEMES) + margin
sheet = Image.new("RGB", (sheet_w, sheet_h), "#f2f3f7")
draw = ImageDraw.Draw(sheet)
draw.text((margin, 20), "DeepSeek Harness 管理器 · 主题总览", fill="#242333", font=font)
draw.text((margin, 50), "7 套主题 / 日间与夜间模式 / 1440 × 900", fill="#777586", font=small_font)
for row, (theme, label) in enumerate(THEMES):
    y = header_h + row * (thumb_h + label_h + gap)
    for col, mode in enumerate(("day", "night")):
        x = margin + col * (thumb_w + gap)
        image = Image.open(OUTPUT / f"{THEMES.index((theme, label)) + 1:02d}-{theme}-{mode}.png").convert("RGB")
        image = image.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        sheet.paste(image, (x, y))
        mode_label = "日间模式" if mode == "day" else "夜间模式"
        draw.text((x + 2, y + thumb_h + 10), f"{label} · {mode_label}", fill="#403e4d", font=small_font)
sheet.save(OUTPUT / "00-all-themes-overview.png", optimize=True)
print("00-all-themes-overview.png")
