from pathlib import Path
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "references"
OUTPUT.mkdir(exist_ok=True)
SECTIONS = [
    ("foundations", "design-01-foundations.png"),
    ("components", "design-02-components.png"),
    ("icons", "design-03-icons.png"),
    ("palettes", "design-04-theme-palettes.png"),
    ("layout", "design-05-layout.png"),
]

options = Options()
options.add_argument("--headless")
options.add_argument("--window-size=1440,1000")
options.add_argument("--force-device-scale-factor=1")
driver = webdriver.Edge(options=options)
driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
    "width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False
})
try:
    driver.get("http://127.0.0.1:8765/design-system.html")
    assert len(driver.find_elements(By.CSS_SELECTOR, ".icon-item")) == 25
    assert len(driver.find_elements(By.CSS_SELECTOR, ".palette-group")) == 7
    assert driver.execute_script("return document.documentElement.scrollWidth <= innerWidth")
    for section_id, filename in SECTIONS:
        import base64
        element = driver.find_element(By.ID, section_id)
        rect = driver.execute_script("""
            const r = arguments[0].getBoundingClientRect();
            return {x:r.left + scrollX, y:r.top + scrollY, width:r.width, height:r.height};
        """, element)
        result = driver.execute_cdp_cmd("Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": True,
            "clip": {**rect, "scale": 1},
        })
        (OUTPUT / filename).write_bytes(base64.b64decode(result["data"]))
        print(filename, element.size)
    logs = driver.get_log("browser")
    severe = [entry for entry in logs if entry["level"] == "SEVERE" and "favicon.ico" not in entry["message"]]
    assert not severe, severe
finally:
    driver.quit()
