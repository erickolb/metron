"""Build the experimental report site without publishing raw feedback records."""
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Report"
SITE = ROOT / "_site"
DEST = SITE / "Metron-CPH-Experiment"
DEST.mkdir(parents=True, exist_ok=True)
report = (SOURCE / "perceptual-hash-experiment-report.html").read_text(encoding="utf-8")
report = re.sub(r"<title>.*?</title>", "<title>Metron-CPH-Experiment</title>", report, count=1)
(DEST / "index.html").write_text(report, encoding="utf-8")
# Publish only resources actually linked by the self-contained report.
for name in set(re.findall(r'href="([^"#]+)"', report)):
    if ":" in name:
        continue
    source = (SOURCE / name).resolve()
    assert source.parent == SOURCE.resolve(), name
    assert source.suffix in {".csv", ".json", ".md"}, name
    shutil.copy2(source, DEST / name)
(SITE / ".nojekyll").write_text("", encoding="utf-8")
(SITE / "index.html").write_text(
    '<!doctype html><html lang="en"><meta charset="utf-8">'
    '<meta http-equiv="refresh" content="0;url=Metron-CPH-Experiment/">'
    '<title>Metron-CPH-Experiment</title>'
    '<a href="Metron-CPH-Experiment/">View Metron-CPH-Experiment</a></html>',
    encoding="utf-8",
)
print(f"Built {DEST}")
