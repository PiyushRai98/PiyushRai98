#!/usr/bin/env python3
"""
generate_stats.py
=================
Fetches contribution data from the GitHub GraphQL API and renders
four SVG files — all using only the Python standard library.

Output files (written to ./generated/)
---------------------------------------
  streak.svg  — current streak, longest streak, weekly bar chart
  langs.svg   — top languages by bytes (stacked horizontal bars)
  year.svg    — 52-week contribution calendar (ASCII-cell grid)
  hero.svg    — total contributions + weekly sparkline

Environment variables (required)
----------------------------------
  GITHUB_TOKEN  — personal access token with `read:user` scope
  GH_LOGIN      — your GitHub username  (e.g. PiyushRai98)

Usage
-----
    GITHUB_TOKEN=ghp_xxx GH_LOGIN=PiyushRai98 python scripts/generate_stats.py

Dependencies: Python standard library only (urllib, json, datetime, os, base64).
"""

import base64
import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ── Configuration ─────────────────────────────────────────────────────────────
OUT_DIR   = Path("generated")
FONT_PATH = Path("fonts") / "JetBrainsMono-Regular.woff2"

# Visual palette
C_BG      = "#ffffff"    # background
C_BG_DARK = "#0d1117"    # dark-mode background
C_FG      = "#24292e"    # foreground text
C_FG_DARK = "#c9d1d9"
C_ACCENT  = "#2ea043"    # GitHub green
C_GRID    = "#ebedf0"    # empty contribution cell
C_MED     = "#9be9a8"
C_HIGH    = "#40c463"
C_MAX     = "#216e39"
C_STREAK  = "#f78166"    # streak highlight
C_MUTED   = "#8b949e"

# ASCII ramp for year.svg cells
ASCII_RAMP = " .`:-=+*cs#%@"

# ── GitHub GraphQL ─────────────────────────────────────────────────────────────

GRAPHQL_URL = "https://api.github.com/graphql"


def _graphql(query: str, variables: dict | None = None) -> dict:
    """Execute a GitHub GraphQL query and return the parsed JSON body."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        sys.exit("GITHUB_TOKEN environment variable is not set.")

    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
    except HTTPError as exc:
        sys.exit(f"GitHub API error {exc.code}: {exc.read().decode()}")
    except URLError as exc:
        sys.exit(f"Network error: {exc.reason}")

    if "errors" in body:
        sys.exit(f"GraphQL errors: {body['errors']}")

    return body["data"]


def fetch_contributions(login: str) -> dict:
    """
    Return the ContributionCalendar for the past 364 days, pinned to
    whole UTC days so the result is deterministic.
    """
    today = date.today()
    start = today - timedelta(days=363)     # 364 days inclusive
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    variables = {
        "login": login,
        "from":  f"{start.isoformat()}T00:00:00Z",
        "to":    f"{today.isoformat()}T23:59:59Z",
    }
    data = _graphql(query, variables)
    return data["user"]["contributionsCollection"]["contributionCalendar"]


def fetch_languages(login: str) -> dict[str, int]:
    """
    Return {language_name: total_bytes} across all non-forked public repos.
    Paginates automatically (100 repos per page, up to 10 pages).
    """
    query = """
    query($login: String!, $after: String) {
      user(login: $login) {
        repositories(
          first: 100
          after: $after
          ownerAffiliations: [OWNER]
          isFork: false
          privacy: PUBLIC
          orderBy: {field: UPDATED_AT, direction: DESC}
        ) {
          pageInfo { hasNextPage endCursor }
          nodes {
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges { size node { name } }
            }
          }
        }
      }
    }
    """
    totals: dict[str, int] = {}
    cursor = None
    for _ in range(10):   # max pages guard
        data  = _graphql(query, {"login": login, "after": cursor})
        repos = data["user"]["repositories"]
        for repo in repos["nodes"]:
            for edge in repo["languages"]["edges"]:
                lang  = edge["node"]["name"]
                totals[lang] = totals.get(lang, 0) + edge["size"]
        if repos["pageInfo"]["hasNextPage"]:
            cursor = repos["pageInfo"]["endCursor"]
        else:
            break
    return totals


# ── Font embedding ─────────────────────────────────────────────────────────────

def _font_face_css() -> str:
    if FONT_PATH.exists():
        b64 = base64.b64encode(FONT_PATH.read_bytes()).decode()
        src = f"url('data:font/woff2;base64,{b64}') format('woff2')"
    else:
        src = "local('JetBrains Mono'), local('Courier New')"
    return (
        "@font-face {"
        "  font-family: 'JetBrains Mono';"
        "  font-style: normal; font-weight: 400;"
        f" src: {src}; }}"
    )


_SHARED_CSS = """
  body, text, tspan {{
    font-family: 'JetBrains Mono', 'Courier New', monospace;
  }}
  @media (prefers-color-scheme: dark) {{
    .bg {{ fill: {bg_dark}; }}
    .fg {{ fill: {fg_dark}; }}
    .muted {{ fill: {muted}; }}
  }}
""".format(bg_dark=C_BG_DARK, fg_dark=C_FG_DARK, muted=C_MUTED)


def _svg_wrap(width: float, height: float, inner: str, title: str = "") -> str:
    font_css  = _font_face_css()
    title_tag = f"<title>{title}</title>" if title else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' width="{width:.0f}" height="{height:.0f}"'
        f' viewBox="0 0 {width:.0f} {height:.0f}">\n'
        f'  {title_tag}\n'
        f'  <style>{font_css}{_SHARED_CSS}</style>\n'
        f'  <rect class="bg" width="100%" height="100%" fill="{C_BG}"/>\n'
        f'{inner}'
        f'</svg>\n'
    )


# ── Streak SVG ─────────────────────────────────────────────────────────────────

def _compute_streaks(days: list[dict]) -> tuple[int, int, str, str]:
    """
    Returns (current_streak, longest_streak, streak_start_iso, streak_end_iso).
    days: list of {date, contributionCount} sorted ascending.
    """
    current = 0
    longest = 0
    streak_start = ""
    streak_end   = ""
    temp_start   = ""
    run = 0

    for day in reversed(days):
        if day["contributionCount"] > 0:
            run += 1
            if run == 1:
                streak_end = day["date"]
            temp_start = day["date"]
            if run > longest:
                longest      = run
                streak_start = temp_start
        else:
            if run > 0:
                current = run
                break
            run = 0

    if current == 0:
        current = run

    return current, longest, streak_start, streak_end


def generate_streak_svg(calendar: dict) -> str:
    weeks = calendar["weeks"]
    # Flatten to sorted list of days
    days = [d for w in weeks for d in w["contributionDays"]]
    days.sort(key=lambda d: d["date"])

    cur, lng, s_start, s_end = _compute_streaks(days)

    # Weekly aggregates for the bar chart
    weekly = []
    for w in weeks:
        weekly.append(sum(d["contributionCount"] for d in w["contributionDays"]))

    W, H    = 760.0, 160.0
    pad_l   = 16.0
    pad_r   = 16.0
    pad_top = 50.0
    chart_h = 70.0
    bar_area_w = W - pad_l - pad_r - 180   # leave right panel for stats
    n_bars  = len(weekly)
    bar_gap = 1.0
    bar_w   = (bar_area_w - bar_gap * (n_bars - 1)) / n_bars
    max_val = max(weekly) if any(weekly) else 1

    inner = []

    # ── Stats panel (right side) ─────────────────────────────────────────────
    rx = W - 175
    inner.append(
        f'  <text x="{rx}" y="28" font-size="11" class="fg" fill="{C_MUTED}">Current Streak</text>\n'
        f'  <text x="{rx}" y="52" font-size="26" font-weight="bold" fill="{C_STREAK}">{cur}</text>\n'
        f'  <text x="{rx+38}" y="52" font-size="11" fill="{C_STREAK}"> days</text>\n'
        f'  <text x="{rx}" y="76" font-size="11" class="fg" fill="{C_MUTED}">Longest Streak</text>\n'
        f'  <text x="{rx}" y="98" font-size="22" font-weight="bold" fill="{C_ACCENT}">{lng}</text>\n'
        f'  <text x="{rx+34}" y="98" font-size="11" fill="{C_ACCENT}"> days</text>\n'
    )
    if s_start and s_end:
        inner.append(
            f'  <text x="{rx}" y="118" font-size="9" fill="{C_MUTED}">'
            f'{s_start} → {s_end}</text>\n'
        )

    # ── Section label ────────────────────────────────────────────────────────
    inner.append(
        f'  <text x="{pad_l}" y="20" font-size="11" font-weight="bold"'
        f' class="fg" fill="{C_FG}">Weekly contributions (past 52 weeks)</text>\n'
    )

    # ── Bars ─────────────────────────────────────────────────────────────────
    for i, val in enumerate(weekly):
        x      = pad_l + i * (bar_w + bar_gap)
        bar_h  = (val / max_val) * chart_h if max_val else 0
        y      = pad_top + chart_h - bar_h
        color  = C_ACCENT if val > 0 else C_GRID
        inner.append(
            f'  <rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}"'
            f' height="{bar_h:.1f}" fill="{color}" rx="1"/>\n'
        )

    # ── Baseline ─────────────────────────────────────────────────────────────
    baseline_y = pad_top + chart_h
    inner.append(
        f'  <line x1="{pad_l}" y1="{baseline_y}" x2="{pad_l+bar_area_w}" y2="{baseline_y}"'
        f' stroke="{C_MUTED}" stroke-width="0.5"/>\n'
    )

    return _svg_wrap(W, H, "".join(inner), "GitHub contribution streak")


# ── Languages SVG ──────────────────────────────────────────────────────────────

# Mapping of well-known languages to colours
LANG_COLORS: dict[str, str] = {
    "Python":     "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#2b7489",
    "C++":        "#f34b7d",
    "HTML":       "#e34c26",
    "CSS":        "#563d7c",
    "Jupyter Notebook": "#DA5B0B",
    "Shell":      "#89e051",
    "Dockerfile": "#384d54",
    "SCSS":       "#c6538c",
}
DEFAULT_COLOR = "#8b949e"

TOP_N = 8


def generate_langs_svg(lang_bytes: dict[str, int]) -> str:
    # Sort descending, take top N
    sorted_langs = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)[:TOP_N]
    total = sum(b for _, b in sorted_langs) or 1

    W, H  = 760.0, 160.0
    pad   = 20.0
    bar_y = 48.0
    bar_h = 14.0
    bar_w = W - 2 * pad

    inner = []
    inner.append(
        f'  <text x="{pad}" y="24" font-size="12" font-weight="bold"'
        f' class="fg" fill="{C_FG}">Top Languages by repository bytes</text>\n'
    )

    # Stacked bar
    x_cursor = pad
    for lang, size in sorted_langs:
        pct    = size / total
        seg_w  = pct * bar_w
        color  = LANG_COLORS.get(lang, DEFAULT_COLOR)
        inner.append(
            f'  <rect x="{x_cursor:.2f}" y="{bar_y}" width="{seg_w:.2f}"'
            f' height="{bar_h}" fill="{color}"/>\n'
        )
        x_cursor += seg_w

    # Legend (2 columns)
    col_w   = (W - 2 * pad) / 2
    leg_y   = bar_y + bar_h + 20
    for idx, (lang, size) in enumerate(sorted_langs):
        pct   = size / total * 100
        color = LANG_COLORS.get(lang, DEFAULT_COLOR)
        col   = idx % 2
        row   = idx // 2
        lx    = pad + col * col_w
        ly    = leg_y + row * 22
        inner.append(
            f'  <circle cx="{lx+6}" cy="{ly-4}" r="5" fill="{color}"/>\n'
            f'  <text x="{lx+16}" y="{ly}" font-size="11" fill="{C_FG}" class="fg">'
            f'{lang} <tspan fill="{C_MUTED}">{pct:.1f}%</tspan></text>\n'
        )

    rows_legend = math.ceil(len(sorted_langs) / 2)
    H = leg_y + rows_legend * 22 + pad
    return _svg_wrap(W, H, "".join(inner), "Top languages")


# ── Year calendar SVG ──────────────────────────────────────────────────────────

def generate_year_svg(calendar: dict) -> str:
    """52-week grid, 7 rows, each cell = one ASCII character from ramp."""
    weeks = calendar["weeks"]
    days  = [d for w in weeks for d in w["contributionDays"]]
    days.sort(key=lambda d: d["date"])

    max_count = max((d["contributionCount"] for d in days), default=1) or 1
    ramp      = ASCII_RAMP
    ramp_len  = len(ramp)

    cell_size  = 13.0    # px (matches JetBrains Mono metrics)
    gap        = 2.0
    step       = cell_size + gap
    n_weeks    = len(weeks)
    W          = n_weeks * step + 40.0
    H          = 7 * step + 56.0
    pad_left   = 32.0
    pad_top    = 36.0

    # Month labels
    month_labels: list[tuple[int, str]] = []
    last_month = -1
    for wi, week in enumerate(weeks):
        for di, day_data in enumerate(week["contributionDays"]):
            m = int(day_data["date"].split("-")[1])
            if m != last_month:
                month_labels.append((wi, datetime.strptime(day_data["date"], "%Y-%m-%d").strftime("%b")))
                last_month = m
            break

    inner = []
    inner.append(
        f'  <text x="{pad_left}" y="20" font-size="12" font-weight="bold"'
        f' class="fg" fill="{C_FG}">Contribution calendar — past year</text>\n'
    )

    # Month labels
    for wi, label in month_labels:
        inner.append(
            f'  <text x="{pad_left + wi * step:.1f}" y="{pad_top - 6:.1f}"'
            f' font-size="9" fill="{C_MUTED}">{label}</text>\n'
        )

    # Day labels (Mon / Wed / Fri)
    for di, label in [(1, "M"), (3, "W"), (5, "F")]:
        inner.append(
            f'  <text x="4" y="{pad_top + di * step + cell_size - 2:.1f}"'
            f' font-size="9" fill="{C_MUTED}">{label}</text>\n'
        )

    # Build a week→day lookup
    for wi, week in enumerate(weeks):
        for di, day_data in enumerate(week["contributionDays"]):
            count = day_data["contributionCount"]
            ratio = count / max_count
            # ASCII char
            char_idx = int(ratio * (ramp_len - 1))
            char     = ramp[char_idx]
            # Color
            if count == 0:
                color = C_GRID
            elif ratio < 0.25:
                color = C_MED
            elif ratio < 0.60:
                color = C_HIGH
            else:
                color = C_MAX

            cx = pad_left + wi * step
            cy = pad_top  + di * step

            inner.append(
                f'  <rect x="{cx:.1f}" y="{cy:.1f}" width="{cell_size}" height="{cell_size}"'
                f' fill="{color}" rx="2">'
                f'<title>{day_data["date"]}: {count} contributions</title></rect>\n'
                f'  <text x="{cx + 2:.1f}" y="{cy + cell_size - 2:.1f}"'
                f' font-size="9" fill="rgba(0,0,0,0.45)">{char}</text>\n'
            )

    return _svg_wrap(W, H, "".join(inner), "Yearly contribution calendar")


# ── Hero SVG (sparkline + total) ───────────────────────────────────────────────

def generate_hero_svg(calendar: dict) -> str:
    total  = calendar["totalContributions"]
    weeks  = calendar["weeks"]
    weekly = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks]

    W, H     = 760.0, 120.0
    pad      = 20.0
    spark_h  = 50.0
    spark_y0 = 55.0
    spark_w  = W - 2 * pad - 200
    n        = len(weekly)
    max_v    = max(weekly) if any(weekly) else 1

    # Build polyline points
    pts = []
    for i, v in enumerate(weekly):
        x = pad + (i / (n - 1)) * spark_w if n > 1 else pad
        y = spark_y0 + spark_h - (v / max_v) * spark_h
        pts.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(pts)

    # Fill area (close path)
    fill_pts = (
        f"{pad:.1f},{spark_y0 + spark_h:.1f} "
        + polyline
        + f" {pad + spark_w:.1f},{spark_y0 + spark_h:.1f}"
    )

    inner = [
        # Total label
        f'  <text x="{W - 190}" y="36" font-size="11" fill="{C_MUTED}" class="fg">'
        f'Total contributions (past year)</text>\n'
        f'  <text x="{W - 190}" y="70" font-size="36" font-weight="bold"'
        f' fill="{C_ACCENT}">{total:,}</text>\n',

        # Section label
        f'  <text x="{pad}" y="24" font-size="12" font-weight="bold"'
        f' class="fg" fill="{C_FG}">Weekly activity sparkline</text>\n',

        # Fill polygon
        f'  <polygon points="{fill_pts}" fill="{C_ACCENT}" opacity="0.15"/>\n',

        # Line
        f'  <polyline points="{polyline}" fill="none"'
        f' stroke="{C_ACCENT}" stroke-width="2" stroke-linejoin="round"/>\n',
    ]

    return _svg_wrap(W, H, "".join(inner), "Contribution sparkline")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    login = os.environ.get("GH_LOGIN", "").strip()
    if not login:
        sys.exit("GH_LOGIN environment variable is not set.")

    print(f"[stats] Fetching data for @{login} …")
    calendar   = fetch_contributions(login)
    lang_bytes = fetch_languages(login)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    files = {
        "streak.svg": generate_streak_svg(calendar),
        "langs.svg":  generate_langs_svg(lang_bytes),
        "year.svg":   generate_year_svg(calendar),
        "hero.svg":   generate_hero_svg(calendar),
    }

    for name, svg in files.items():
        path = OUT_DIR / name
        path.write_text(svg, encoding="utf-8")
        print(f"[stats] Written: {path}  ({len(svg):,} bytes)")

    print("[stats] Done.")


if __name__ == "__main__":
    main()
