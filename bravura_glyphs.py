#!/usr/bin/env python3
"""
Export every glyph of the Bravura music font as an SVG and/or PNG file,
named after the SMuFL glyph names listed in Bravura.json.

    pip install fonttools pillow
    python bravura_glyphs.py                      # SVG + PNG into ./bravura_glyphs
    python bravura_glyphs.py --format svg         # SVG only
    python bravura_glyphs.py --size 256 --color "#1e1e1e" --padding 8
    python bravura_glyphs.py --canvas 256 --padding 24          # 256x256 icons, glyph fills the box
    python bravura_glyphs.py --canvas 256 --scale fixed --size 160   # 256x256, same scale for all
    python bravura_glyphs.py --font Bravura.otf --json Bravura.json   # use local files
    python bravura_glyphs.py --all                                     # every glyph (~3400)

By default only the glyphs in common_glyphs.json (next to this script) are
exported; pass --glyph-list other.json for a different selection.

What it does
  1. Downloads the latest release from github.com/steinbergmedia/bravura
     (falls back to the files on the master branch if the release API is
     unreachable), and SMuFL's glyphnames.json for name -> codepoint mapping.
  2. Collects every glyph name in Bravura.json (glyphBBoxes / glyphAdvanceWidths)
     and resolves its codepoint from glyphnames.json plus Bravura.json's own
     optionalGlyphs, ligatures, sets and alternates.
  3. Writes svg/<name>.svg (vector outlines, cropped to the glyph) and/or
     png/<name>.png (cropped, transparent background by default), plus an
     index.json listing every exported name and codepoint.
     --size is the font size in px; in SMuFL 1 em = 4 staff spaces.
"""
import argparse
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = "steinbergmedia/bravura"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RAW = f"https://raw.githubusercontent.com/{REPO}/master/redist"
GLYPHNAMES_URL = "https://raw.githubusercontent.com/w3c/smufl/gh-pages/metadata/glyphnames.json"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "bravura-glyph-export"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def download_bravura(cache: Path):
    """Return (otf_path, json_path), downloading into `cache` if needed."""
    cache.mkdir(parents=True, exist_ok=True)
    otf, js = cache / "Bravura.otf", cache / "Bravura.json"
    if otf.exists() and js.exists():
        return otf, js

    try:
        rel = json.loads(fetch(API_LATEST))
        zips = [a["browser_download_url"] for a in rel.get("assets", [])
                if a["name"].lower().endswith(".zip")]
        url = zips[0] if zips else rel["zipball_url"]
        print(f"Downloading release {rel.get('tag_name')}: {url}")
        zf = zipfile.ZipFile(io.BytesIO(fetch(url)))
        names = zf.namelist()
        pick = lambda pat: next(n for n in names if re.search(pat, n, re.I))
        otf.write_bytes(zf.read(pick(r"(^|/)Bravura\.otf$")))
        js.write_bytes(zf.read(pick(r"(^|/)Bravura\.json$")))
    except Exception as e:
        print(f"Release download failed ({e}); using files from master branch")
        otf.write_bytes(fetch(f"{RAW}/otf/Bravura.otf"))
        js.write_bytes(fetch(f"{RAW}/Bravura.json"))
    return otf, js


def load_glyphnames(cache: Path):
    p = cache / "glyphnames.json"
    if not p.exists():
        p.write_bytes(fetch(GLYPHNAMES_URL))
    return json.loads(p.read_text(encoding="utf-8"))


def cp(s):
    return int(s.replace("U+", ""), 16)


def name_to_codepoint(meta, glyphnames):
    m = {n: cp(v["codepoint"]) for n, v in glyphnames.items()}
    for n, v in meta.get("optionalGlyphs", {}).items():
        m[n] = cp(v["codepoint"])
    for n, v in meta.get("ligatures", {}).items():
        m[n] = cp(v["codepoint"])
    for s in meta.get("sets", {}).values():
        for g in s["glyphs"]:
            m[g["name"]] = cp(g["codepoint"])
    for v in meta.get("glyphsWithAlternates", {}).values():
        for a in v["alternates"]:
            m[a["name"]] = cp(a["codepoint"])
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="bravura_glyphs", help="output folder")
    ap.add_argument("--format", choices=["svg", "png", "both"], default="both")
    ap.add_argument("--size", type=int, default=128,
                    help="PNG font size in px (1 em = 4 staff spaces). Default 128")
    ap.add_argument("--padding", type=int, default=4, help="PNG padding in px")
    ap.add_argument("--color", default="#000000", help="glyph colour (SVG fill / PNG)")
    ap.add_argument("--background", default=None,
                    help="PNG background colour, e.g. '#ffffff' (default transparent)")
    ap.add_argument("--square", action="store_true", help="pad PNGs to a square canvas")
    ap.add_argument("--canvas", type=int, default=None,
                    help="fixed square icon size in px, e.g. 256. Glyph is centred on the canvas")
    ap.add_argument("--scale", choices=["fit", "fixed"], default="fit",
                    help="with --canvas: 'fit' scales every glyph to fill the canvas (minus padding); "
                         "'fixed' keeps all glyphs at --size so they stay proportional to each other, "
                         "shrinking only glyphs that would not fit. Default fit")
    ap.add_argument("--font", help="local Bravura.otf (skip download)")
    ap.add_argument("--json", help="local Bravura.json (skip download)")
    ap.add_argument("--glyph-list", default=None,
                    help="JSON file limiting which glyphs to export: a list of names, or a list of "
                         "{name, category, ...} objects. Defaults to common_glyphs.json next to this "
                         "script if present")
    ap.add_argument("--all", action="store_true", help="export every glyph, ignoring any glyph list")
    ap.add_argument("--by-category", action="store_true",
                    help="with a glyph list that has categories: put files in <format>/<category>/")
    ap.add_argument("--cache", default=".bravura_cache", help="download cache folder")
    args = ap.parse_args()

    from fontTools.ttLib import TTFont
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.boundsPen import BoundsPen

    cache = Path(args.cache)
    if args.font and args.json:
        otf_path, json_path = Path(args.font), Path(args.json)
    else:
        otf_path, json_path = download_bravura(cache)
    meta = json.loads(Path(json_path).read_text(encoding="utf-8"))
    cpmap = name_to_codepoint(meta, load_glyphnames(cache))

    font = TTFont(otf_path)
    cmap = font.getBestCmap()
    gs = font.getGlyphSet()
    upem = font["head"].unitsPerEm

    names = sorted(set(meta.get("glyphBBoxes", {})) | set(meta.get("glyphAdvanceWidths", {})))
    category = {}
    list_path = args.glyph_list
    if list_path is None and not args.all:
        default = Path(__file__).with_name("common_glyphs.json")
        list_path = default if default.exists() else None
    if list_path and not args.all:
        entries = json.loads(Path(list_path).read_text(encoding="utf-8"))
        wanted = []
        for e in entries:
            n = e if isinstance(e, str) else e["name"]
            wanted.append(n)
            if isinstance(e, dict) and e.get("category"):
                category[n] = e["category"]
        unknown = [n for n in wanted if n not in set(names)]
        if unknown:
            print(f"Not in Bravura.json, skipped: {', '.join(unknown)}")
        names = [n for n in dict.fromkeys(wanted) if n not in unknown]
        print(f"Using glyph list {list_path}: {len(names)} glyphs")
    out = Path(args.out)
    (out / "svg").mkdir(parents=True, exist_ok=True) if args.format in ("svg", "both") else None
    (out / "png").mkdir(parents=True, exist_ok=True) if args.format in ("png", "both") else None

    pil_font = None
    if args.format in ("png", "both"):
        from PIL import Image, ImageDraw, ImageFont, ImageColor
        pil_font = ImageFont.truetype(str(otf_path), args.size)
        _fonts = {}

        def font_at(px):
            px = round(px, 2)
            if px not in _fonts:
                _fonts[px] = ImageFont.truetype(str(otf_path), px)
            return _fonts[px]
        fg = ImageColor.getrgb(args.color)
        bg = ImageColor.getrgb(args.background) + (255,) if args.background else (0, 0, 0, 0)

    index, missing, empty = [], [], []
    for name in names:
        code = cpmap.get(name)
        gname = cmap.get(code) if code is not None else None
        if gname is None:
            missing.append(name)
            continue
        glyph = gs[gname]
        bp = BoundsPen(gs)
        glyph.draw(bp)
        if bp.bounds is None:          # blank glyph (spaces etc.)
            empty.append(name)
            continue
        xmin, ymin, xmax, ymax = bp.bounds
        w, h = xmax - xmin, ymax - ymin

        # px per font unit
        if args.canvas:
            fit = (args.canvas - 2 * args.padding) / max(w, h)
            scale = fit if args.scale == "fit" else min(args.size / upem, fit)
        else:
            scale = args.size / upem

        if args.format in ("svg", "both"):
            pen = SVGPathPen(gs)
            glyph.draw(pen)
            if args.canvas:
                side = args.canvas / scale                     # canvas size in font units
                vx = xmin + w / 2 - side / 2
                vy = -(ymin + h / 2) - side / 2
                box = f'viewBox="{vx:g} {vy:g} {side:g} {side:g}" width="{args.canvas}" height="{args.canvas}"'
            else:
                box = (f'viewBox="{xmin:g} {-ymax:g} {w:g} {h:g}" '
                       f'width="{w * scale:.2f}" height="{h * scale:.2f}"')
            svg = (
                f'<svg xmlns="http://www.w3.org/2000/svg" {box}>\n'
                f'  <title>{name} (U+{code:04X})</title>\n'
                f'  <path transform="scale(1,-1)" fill="{args.color}" d="{pen.getCommands()}"/>\n'
                f'</svg>\n'
            )
            dest = out / "svg" / (category.get(name, "") if args.by_category else "")
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"{name}.svg").write_text(svg, encoding="utf-8")

        if pil_font is not None:
            ch = chr(code)
            pf = font_at(scale * upem) if args.canvas else pil_font
            l, t, r, b = pf.getbbox(ch, anchor="ls")
            if args.canvas:
                pw = ph = args.canvas
            else:
                pw, ph = r - l + 2 * args.padding, b - t + 2 * args.padding
                if args.square:
                    pw = ph = max(pw, ph)
            img = Image.new("RGBA", (pw, ph), bg)
            ox = (pw - (r - l)) // 2 - l
            oy = (ph - (b - t)) // 2 - t
            ImageDraw.Draw(img).text((ox, oy), ch, font=pf, fill=fg + (255,), anchor="ls")
            dest = out / "png" / (category.get(name, "") if args.by_category else "")
            dest.mkdir(parents=True, exist_ok=True)
            img.save(dest / f"{name}.png")

        entry = {"name": name, "codepoint": f"U+{code:04X}"}
        if name in category:
            entry["category"] = category[name]
        index.append(entry)

    (out / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"Exported {len(index)} glyphs to {out.resolve()}")
    if empty:
        print(f"Skipped {len(empty)} blank glyphs: {', '.join(empty[:10])}{' ...' if len(empty) > 10 else ''}")
    if missing:
        print(f"No codepoint/glyph found for {len(missing)} names: "
              f"{', '.join(missing[:10])}{' ...' if len(missing) > 10 else ''}")


if __name__ == "__main__":
    sys.exit(main())
