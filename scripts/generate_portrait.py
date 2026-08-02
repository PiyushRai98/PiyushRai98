#!/usr/bin/env python3
"""
generate_portrait.py
====================
Converts a portrait photo into an animated ASCII-art SVG.

Pipeline
--------
1.  Remove background with rembg (ONNX-based, runs offline).
2.  Composite onto white, apply bilateral filter + CLAHE.
3.  Apply darkening curve  v_out = (v_in/255)^1.7 * 255.
4.  Resize to COLS columns (aspect-ratio-aware, 0.48 row-scaling).
5.  Map each pixel to one character from ASCII_RAMP.
6.  Write an SVG where each text row is revealed by an animating
    clipPath (stagger = 0.09 s/row, duration = 0.7 s, fill="freeze").
7.  JetBrains Mono is inlined as a base64 WOFF2 @font-face so the
    character widths are consistent on every viewer.

Usage
-----
    python scripts/generate_portrait.py \
        --input  images/profile.jpg   \
        --output assets/portrait.svg  \
        --cols   90

Dependencies (install via pip or the workflow):
    pillow  numpy  opencv-python-headless  rembg  onnxruntime
"""

import argparse
import base64
import os
import sys
from pathlib import Path

import cv2
import numpy as np

try:
    from rembg import remove as rembg_remove
except ImportError:
    sys.exit("rembg is required: pip install rembg onnxruntime")

# ── Character ramp ──────────────────────────────────────────────────────────
# Ordered from lightest (space) to darkest (@).
ASCII_RAMP = " .`:-=+*cs#%@"

# ── Layout constants ─────────────────────────────────────────────────────────
FONT_SIZE   = 13      # px — must match the monospace glyph metrics below
CHAR_WIDTH  = 7.8     # px — JetBrains Mono Regular at 13 px
LINE_HEIGHT = 15      # px
ROW_SCALE   = 0.48    # compensates for non-square terminal "pixels"

# ── Animation ────────────────────────────────────────────────────────────────
STAGGER_S  = 0.09    # seconds between row reveals
DURATION_S = 0.70    # seconds for each row wipe

# ── Font path (optional — skip embedding if file not found) ─────────────────
FONT_PATH = Path(__file__).parent.parent / "fonts" / "JetBrainsMono-Regular.woff2"


# ────────────────────────────────────────────────────────────────────────────
def load_and_prepare(input_path: str, output_png: str) -> np.ndarray:
    """Remove background, composite on white, return BGR uint8 array."""
    with open(input_path, "rb") as fh:
        raw = fh.read()

    processed = rembg_remove(raw)

    os.makedirs(os.path.dirname(output_png) or ".", exist_ok=True)
    with open(output_png, "wb") as fh:
        fh.write(processed)

    img = cv2.imread(output_png, cv2.IMREAD_UNCHANGED)
    if img is None:
        sys.exit(f"Could not read processed image: {output_png}")

    # Composite RGBA onto white
    if img.shape[2] == 4:
        alpha = img[:, :, 3] / 255.0
        rgb   = img[:, :, :3].astype(float)
        white = np.ones_like(rgb) * 255.0
        img   = (rgb * alpha[..., np.newaxis] + white * (1.0 - alpha[..., np.newaxis])).astype(np.uint8)

    return img


def enhance(img: np.ndarray) -> np.ndarray:
    """Bilateral filter → CLAHE → darkening curve → uint8 grayscale."""
    # Edge-preserving smoothing
    img = cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)

    # Convert to grayscale for CLAHE
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Contrast-limited adaptive histogram equalisation
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray  = clahe.apply(gray)

    # Darkening power curve: v_out = (v_in/255)^1.7 * 255
    gray = (np.power(gray.astype(float) / 255.0, 1.7) * 255.0).astype(np.uint8)

    return gray


def to_ascii(gray: np.ndarray, cols: int) -> list[str]:
    """Resize to `cols` columns and map pixels to ASCII_RAMP characters."""
    h, w = gray.shape
    rows = max(1, int(cols * (h / w) * ROW_SCALE))

    resized = cv2.resize(gray, (cols, rows), interpolation=cv2.INTER_AREA)

    ramp_len = len(ASCII_RAMP)
    ascii_rows = []
    for row in resized:
        line = ""
        for pixel in row:
            idx = int(pixel / 256 * ramp_len)
            idx = min(idx, ramp_len - 1)
            line += ASCII_RAMP[idx]
        ascii_rows.append(line)

    return ascii_rows


# ── Font embedding ────────────────────────────────────────────────────────────

def _font_face_css() -> str:
    """
    Return a @font-face CSS block.

    If fonts/JetBrainsMono-Regular.woff2 exists it is base64-encoded and
    inlined so the SVG is fully self-contained.  Otherwise a system
    monospace fallback is used.
    """
    if FONT_PATH.exists():
        b64 = base64.b64encode(FONT_PATH.read_bytes()).decode()
        src = f"url('data:font/woff2;base64,{b64}') format('woff2')"
        print(f"[portrait] Embedding font: {FONT_PATH}")
    else:
        # Fallback: rely on the viewer's system monospace font
        src = "local('JetBrains Mono'), local('Courier New')"
        print("[portrait] Font file not found — using system monospace fallback.")

    return f"""@font-face {{
      font-family: 'JetBrains Mono';
      font-style: normal;
      font-weight: 400;
      src: {src};
    }}"""


# ── SVG builder ──────────────────────────────────────────────────────────────

def build_svg(ascii_rows: list[str]) -> str:
    """
    Assemble the animated SVG string.

    Each row gets its own <clipPath> containing a <rect> whose width
    animates from 0 → full, staggered by STAGGER_S seconds per row.
    fill="freeze" keeps the row visible after the animation completes.
    """
    rows        = len(ascii_rows)
    cols        = max(len(r) for r in ascii_rows)
    svg_width   = cols  * CHAR_WIDTH
    svg_height  = rows  * LINE_HEIGHT + 20   # 20 px top margin

    font_css = _font_face_css()

    # ── Preamble ────────────────────────────────────────────────────────────
    parts = [f"""<svg xmlns="http://www.w3.org/2000/svg"
     width="{svg_width:.1f}"
     height="{svg_height:.1f}"
     viewBox="0 0 {svg_width:.1f} {svg_height:.1f}"
     role="img"
     aria-label="Animated ASCII portrait of Piyush Kumar Rai">

  <title>Piyush Kumar Rai — ASCII portrait</title>

  <style>
    {font_css}
    text {{
      font-family: 'JetBrains Mono', 'Courier New', monospace;
      font-size: {FONT_SIZE}px;
      fill: #24292e;
      white-space: pre;
    }}
    @media (prefers-color-scheme: dark) {{
      text {{ fill: #c9d1d9; }}
      rect.bg {{ fill: #0d1117; }}
    }}
  </style>

  <rect class="bg" width="100%" height="100%" fill="#ffffff"/>

  <defs>"""]

    # ── One clipPath per row ─────────────────────────────────────────────────
    for i in range(rows):
        y_clip = i * LINE_HEIGHT
        begin  = f"{i * STAGGER_S:.3f}s"
        parts.append(f"""
    <clipPath id="cp{i}">
      <rect x="0" y="{y_clip:.1f}" width="0" height="{LINE_HEIGHT:.1f}">
        <animate attributeName="width"
                 from="0" to="{svg_width:.1f}"
                 begin="{begin}" dur="{DURATION_S}s"
                 fill="freeze"/>
      </rect>
    </clipPath>""")

    parts.append("\n  </defs>\n")

    # ── Text rows ────────────────────────────────────────────────────────────
    for i, line in enumerate(ascii_rows):
        y_text = 14 + i * LINE_HEIGHT   # baseline (14 px cap-height offset)
        # Escape XML special characters
        escaped = (line
                   .replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;"))
        parts.append(
            f'  <text x="0" y="{y_text:.1f}" clip-path="url(#cp{i})">'
            f'{escaped}</text>\n'
        )

    parts.append("</svg>\n")
    return "".join(parts)


# ── CLI entry-point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an animated ASCII SVG portrait from a photo."
    )
    parser.add_argument(
        "--input",  default="images/profile.jpg",
        help="Path to the source photo (default: images/profile.jpg)"
    )
    parser.add_argument(
        "--output", default="assets/portrait.svg",
        help="Destination SVG path (default: assets/portrait.svg)"
    )
    parser.add_argument(
        "--processed", default="assets/processed.png",
        help="Intermediate background-removed PNG (default: assets/processed.png)"
    )
    parser.add_argument(
        "--cols",   default=90, type=int,
        help="ASCII grid width in characters (default: 90)"
    )
    args = parser.parse_args()

    print(f"[portrait] Input  : {args.input}")
    print(f"[portrait] Output : {args.output}")
    print(f"[portrait] Cols   : {args.cols}")

    # 1. Remove background + composite
    img = load_and_prepare(args.input, args.processed)

    # 2. Enhance
    gray = enhance(img)

    # 3. ASCII conversion
    ascii_rows = to_ascii(gray, args.cols)
    print(f"[portrait] Grid   : {args.cols} × {len(ascii_rows)}")

    # 4. Build SVG
    svg_content = build_svg(ascii_rows)

    # 5. Write
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(svg_content)

    print(f"[portrait] Written: {args.output}  ({len(svg_content):,} bytes)")


if __name__ == "__main__":
    main()
