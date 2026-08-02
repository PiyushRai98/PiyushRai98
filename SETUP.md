# Self-generating GitHub Profile — Setup Guide

This repository refreshes its own stats SVGs and ASCII portrait daily
via GitHub Actions. Follow the steps below to get it running on your fork.

---

## 1. Fork & clone

```bash
git clone https://github.com/<your-username>/<your-username>
cd <your-username>
```

> The repository name **must** match your GitHub username exactly for the
> profile README to display on your GitHub profile page.

---

## 2. Add your photo

Place your portrait photo at:

```
images/profile.jpg
```

Any JPEG or PNG works. Aim for a clean, front-facing headshot — rembg
works best when the subject is well-separated from the background.

---

## 3. Set up the font (optional but recommended)

Without the font file the SVGs fall back to the viewer's system monospace
font, which is usually fine. For pixel-perfect consistency:

1. Download **JetBrains Mono** from <https://www.jetbrains.com/lp/mono/>
2. Copy `JetBrainsMono-Regular.ttf` and `OFL.txt` into `fonts/`
3. Install fonttools + brotli:

   ```bash
   pip install fonttools brotli
   ```

4. Run the subsetting helper:

   ```bash
   python scripts/inline_font.py
   ```

   This writes `fonts/JetBrainsMono-Regular.woff2` (≈ 25 KB).

5. Commit the two font files:

   ```bash
   git add fonts/JetBrainsMono-Regular.woff2 fonts/OFL.txt
   git commit -m "chore: add JetBrains Mono subset"
   ```

---

## 4. Run scripts locally (first time)

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install Python dependencies
pip install pillow numpy opencv-python-headless rembg onnxruntime

# Generate the portrait
python scripts/generate_portrait.py \
    --input  images/profile.jpg \
    --output assets/portrait.svg \
    --cols   90

# Generate stats (needs a GitHub token)
export GITHUB_TOKEN="ghp_your_token_here"
export GH_LOGIN="PiyushRai98"
python scripts/generate_stats.py
```

Commit the generated files:

```bash
git add assets/ generated/
git commit -m "chore: initial stats & portrait"
git push
```

---

## 5. Enable the GitHub Actions workflow

The workflow at `.github/workflows/refresh.yml` needs:

| Secret / var | Where to set |
|---|---|
| `GITHUB_TOKEN` | Already provided by GitHub Actions automatically |
| `GH_LOGIN` | Automatically inferred from `github.repository_owner` |

No manual secrets are needed. Just make sure the workflow file is pushed
and that **Actions** are enabled in your repository settings
(*Settings → Actions → General → Allow all actions*).

The workflow runs daily at **05:17 UTC**. You can also trigger it manually
from the *Actions* tab → *Refresh profile stats & portrait* → *Run workflow*.

---

## 6. Customisation

| What | Where |
|---|---|
| Number of ASCII columns | `--cols` flag in `generate_portrait.py` or the workflow |
| Colour palette | `C_*` constants at the top of `generate_stats.py` |
| Cron schedule | `cron:` key in `.github/workflows/refresh.yml` |
| Top-N languages shown | `TOP_N` in `generate_stats.py` |
| Portrait animation speed | `STAGGER_S` / `DURATION_S` in `generate_portrait.py` |

---

## Project structure

```
.
├── .github/
│   └── workflows/
│       └── refresh.yml          # Daily automation
├── assets/
│   ├── portrait.svg             # Generated — animated ASCII portrait
│   └── processed.png            # Intermediate background-removed photo
├── fonts/
│   ├── JetBrainsMono-Regular.woff2   # Add manually (see step 3)
│   └── OFL.txt                       # Licence — required
├── generated/
│   ├── streak.svg               # Contribution streak + weekly bars
│   ├── langs.svg                # Top languages stacked bar
│   ├── year.svg                 # 52-week contribution calendar
│   └── hero.svg                 # Total contributions sparkline
├── images/
│   └── profile.jpg              # Your source photo — add manually
├── scripts/
│   ├── generate_portrait.py     # Photo → animated ASCII SVG
│   ├── generate_stats.py        # GitHub API → stats SVGs
│   └── inline_font.py           # TTF → subset WOFF2
└── README.md                    # The profile page itself
```

---

## Licence

Code: MIT.  
Font: SIL Open Font Licence 1.1 (see `fonts/OFL.txt`).
