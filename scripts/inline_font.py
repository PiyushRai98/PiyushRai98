#!/usr/bin/env python3
"""
inline_font.py
==============
Subsets JetBrains Mono Regular to only the characters actually used by
the portrait and stats SVGs, then converts to WOFF2 and writes the file
to fonts/JetBrainsMono-Regular.woff2.

Run this ONCE locally before committing the font file.

Prerequisites
-------------
    pip install fonttools brotli
    # fonttools brings pyftsubset; brotli enables WOFF2 compression.

    Place the source TTF at:
        fonts/JetBrainsMono-Regular.ttf

    Also copy the licence file:
        fonts/OFL.txt          (from the JetBrains Mono release ZIP)

Usage
-----
    python scripts/inline_font.py

The script prints the final file size and base64-encodes a 32-byte
sample so you can sanity-check the output without opening a browser.

About the OFL licence
---------------------
JetBrains Mono is released under the SIL Open Font Licence 1.1.
You MAY embed, subset, and redistribute the font inside any file
(including SVGs committed to a public repo) provided:
  • The original copyright notice and OFL.txt are preserved in the repo.
  • The font is not sold on its own.
See fonts/OFL.txt for the full text.
"""

import base64
import subprocess
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent.parent
FONTS_DIR = ROOT / "fonts"
SRC_TTF   = FONTS_DIR / "JetBrainsMono-Regular.ttf"
OUT_WOFF2 = FONTS_DIR / "JetBrainsMono-Regular.woff2"
OFL_NOTE  = FONTS_DIR / "OFL.txt"

# ── Character set ─────────────────────────────────────────────────────────────
#
# Include:
#   • ASCII ramp used in portrait + year calendar cells
#   • Printable ASCII range needed for headings / labels in stats SVGs
#   • A few extras for safety
#
ASCII_RAMP   = " .`:-=+*cs#%@"
LATIN_UPPER  = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LATIN_LOWER  = "abcdefghijklmnopqrstuvwxyz"
DIGITS       = "0123456789"
PUNCTUATION  = "!\"#$%&'()*+,-./:;<=>?@[\\]^_{|}~"
EXTRAS       = "→←↑↓·•"

UNICODES = sorted(
    set(
        ASCII_RAMP
        + LATIN_UPPER
        + LATIN_LOWER
        + DIGITS
        + PUNCTUATION
        + EXTRAS
    )
)

# pyftsubset accepts a comma-separated list of Unicode code points (hex)
UNICODE_LIST = ",".join(f"U+{ord(c):04X}" for c in UNICODES)


def main() -> None:
    if not SRC_TTF.exists():
        sys.exit(
            f"Source TTF not found: {SRC_TTF}\n"
            "Download JetBrains Mono from https://www.jetbrains.com/lp/mono/ "
            "and place JetBrainsMono-Regular.ttf in the fonts/ directory."
        )

    if not OFL_NOTE.exists():
        print(
            "⚠  fonts/OFL.txt not found.\n"
            "   Please copy the OFL.txt from the JetBrains Mono release ZIP\n"
            "   so the licence is preserved in this repository."
        )

    FONTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[font] Subsetting {SRC_TTF.name} → {OUT_WOFF2.name} …")
    print(f"[font] Characters: {len(UNICODES)} unique code points")

    # Resolve the pyftsubset entry-point that lives inside the venv/Scripts dir.
    # Fallback order: pyftsubset binary → fonttools.subset module directly.
    import shutil
    pyftsubset_bin = shutil.which("pyftsubset")
    if pyftsubset_bin:
        cmd = [pyftsubset_bin]
    else:
        # Direct module invocation (works when the bin wrapper is absent)
        cmd = [sys.executable, "-c",
               "from fontTools.subset import main; main()"]

    cmd += [
        str(SRC_TTF),
        f"--unicodes={UNICODE_LIST}",
        "--layout-features=*",       # keep all OpenType features
        "--flavor=woff2",            # output format
        f"--output-file={OUT_WOFF2}",
        "--no-hinting",              # smaller file; screen rendering fine
        "--desubroutinize",          # slightly larger but more compatible
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr)
        sys.exit(f"pyftsubset failed (exit {result.returncode})")

    size_kb = OUT_WOFF2.stat().st_size / 1024
    print(f"[font] Written: {OUT_WOFF2}  ({size_kb:.1f} KB)")

    # Quick sanity-check: base64 the first 32 bytes
    sample = base64.b64encode(OUT_WOFF2.read_bytes()[:32]).decode()
    print(f"[font] Header (base64, first 32 B): {sample}")
    print("[font] Done — commit fonts/JetBrainsMono-Regular.woff2 and fonts/OFL.txt")


if __name__ == "__main__":
    main()
