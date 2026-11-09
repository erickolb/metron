# ruff: noqa: INP001
"""Regenerate deterministic golden vectors with the Metron Python environment.

Run from the repo root: .venv/Scripts/python.exe android/tools/generate_hash_vectors.py
"""

import json
from pathlib import Path

import imagehash
from PIL import Image

WHITE_VECTOR = 4
vectors = []
for index, (width, height) in enumerate(
    [(32, 32), (17, 41), (90, 137), (201, 300), (1, 1), (512, 320), (40, 29)]
):
    state = 712 + index
    rgb = bytearray()
    for _ in range(width * height * 3):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        rgb.append(state >> 24)
    if index == WHITE_VECTOR:
        rgb[:] = bytes([255]) * len(rgb)
    vectors.append(
        {
            "width": width,
            "height": height,
            "seed": 712 + index,
            "white": index == WHITE_VECTOR,
            "hash": str(imagehash.phash(Image.frombytes("RGB", (width, height), bytes(rgb)))),
        }
    )
target = Path(__file__).resolve().parents[1] / "app/src/test/resources/phash-vectors.json"
target.write_text(json.dumps(vectors, indent=2) + "\n", encoding="utf-8")
