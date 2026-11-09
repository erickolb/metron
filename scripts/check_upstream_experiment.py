# ruff: noqa: INP001
"""Fail upstream preparation while deliberately temporary feedback code remains."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
blockers = []
for relative in [
    "api/experimental_notetaker.py",
    "android/app/src/main/java/cloud/metron/cphtest/FeedbackNote.kt",
]:
    if (root / relative).exists():
        blockers.append(relative)
for relative, marker in [
    ("metron/settings.py", "COVER_EXPERIMENT_NOTETAKER_ENABLED"),
    ("api/urls.py", "ExperimentalNotetaker"),
    ("android/app/src/main/java/cloud/metron/cphtest/MetronApi.kt", "/api/experimental/notetaker/"),
    ("android/app/src/main/java/cloud/metron/cphtest/MainActivity.kt", "submitFeedback("),
]:
    path = root / relative
    if path.exists() and marker in path.read_text(encoding="utf-8"):
        blockers.append(relative)
if blockers:
    print(
        "STOP: remove the temporary notetaker route/module/settings and client feedback "
        "before upstream submission. Keep captured research data private.",
        file=sys.stderr,
    )
    print("Remaining temporary code: " + ", ".join(blockers), file=sys.stderr)
    sys.exit(1)
print("Temporary notetaker route/module/settings and client feedback have been removed.")
