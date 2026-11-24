"""Server-side PNG renderer for tier lists.

Rendering happens here (Pillow) instead of in the browser so the output can't be
altered by browser extensions (injected CSS, dark-mode filters, DOM overlays,
canvas anti-fingerprinting noise, etc.). Layout mirrors static/style.css.
"""
import math
import os
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps

import image_fetch
from static import TheRoulette

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_REGULAR = os.path.join(BASE_DIR, "AGaramondPro-Regular.otf")
FONT_BOLD = os.path.join(BASE_DIR, "AGaramondPro-Bold.otf")

# Layout constants in CSS px (multiplied by the quality scale at render time)
PAD = 6
TITLE_SIZE = 48
TITLE_MARGIN = 30
LABEL_W = 100
LABEL_GAP = 2            # .tier { gap: 2px }
LABEL_FONT = 14          # .label font-size: .875rem
LABEL_LINE = 16          # line-height: 1rem
LABEL_PAD = 8            # .label span padding: .5rem
MIN_ROW_H = 75           # --card-size
CARD_W = 100
CARD_H = CARD_W / 0.67   # img aspect-ratio: .67
CARD_MARGIN = 5
CELL_W = CARD_W + 2 * CARD_MARGIN
CELL_H = CARD_H + 2 * CARD_MARGIN
DIVIDER = 2              # .tier:not(:last-child) border-bottom
SECTION_GAP = 20         # gap between tier list and title columns
COLUMN_GAP = 40
NAME_SIZE = 16
NAME_ROW_H = NAME_SIZE * 1.3 + 6   # line-height 1.3 + padding 2px/4px
TIER_SPACER = NAME_ROW_H * 0.6
NAME_TIME_GAP = 6
TOTAL_SIZE = 36.8                  # 2.3rem
TOTAL_MARGIN = 8
MIN_TIER_CELLS = 3                 # old 458px minimum width
MAX_TIER_ASPECT = 16 / 9           # tier block width:height cap (wraps rows beyond this)
ODDS_GAP = 24                      # space between tier list and odds table
ODDS_HEAD_SIZE = 24
ODDS_LABEL_SIZE = 16
ODDS_SIZE = 16
ODDS_ROW_H = 24
ODDS_COL_GAP = 32
ODDS_SWATCH = 12
ODDS_HEAD_COLOR = "white"
ODDS_TEXT_COLOR = "#DDDDDD"
ODDS_MUTED_COLOR = "#999999"

BG = "#1A1A17"
TIER_BG = "#262626"
BORDER = "#0A0A0A"
TITLE_COLOR = "white"
TOTAL_COLOR = "#008000"
PLACEHOLDER = "#333333"

# --- image loading: bytes come from the shared fetch cache (also used by /proxy),
# decoded images are kept in a small LRU so repeat renders skip decoding ---------

_DECODED_MAX = 400
_decoded = OrderedDict()
_decoded_lock = threading.Lock()


def _fetch_image(src):
    url = image_fetch.unwrap_proxy(src)
    with _decoded_lock:
        if url in _decoded:
            _decoded.move_to_end(url)
            return _decoded[url]
    try:
        data, _ = image_fetch.fetch_image(url)
        img = Image.open(BytesIO(data))
        img.load()
        img = img.convert("RGB")
    except Exception as e:
        print(f"Render: failed to load {url}: {e}")
        return None
    with _decoded_lock:
        _decoded[url] = img
        while len(_decoded) > _DECODED_MAX:
            _decoded.popitem(last=False)
    return img


# --- helpers -----------------------------------------------------------------

def _font(path, size):
    try:
        return ImageFont.truetype(path, max(1, round(size)))
    except OSError:
        return ImageFont.load_default(size=max(1, round(size)))


def _to_seconds(item):
    total = 0
    for key, mult in (("hours", 3600), ("minutes", 60), ("seconds", 1)):
        try:
            total += int(str(item.get(key, 0)).strip() or 0) * mult
        except ValueError:
            pass
    return total


def _fmt(seconds):
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def _wrap(draw, text, font, max_w):
    """Word wrap; breaks overlong words (overflow-wrap: break-word)."""
    lines = []
    for paragraph in str(text).splitlines() or [""]:
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}" if line else word
            if draw.textlength(candidate, font=font) <= max_w:
                line = candidate
                continue
            if line:
                lines.append(line)
            line = ""
            for ch in word:
                if draw.textlength(line + ch, font=font) > max_w and line:
                    lines.append(line)
                    line = ch
                else:
                    line += ch
        lines.append(line)
    return lines


# --- main entry point --------------------------------------------------------

def _tier_height(counts, per_row):
    """Height (CSS px) of the tier block for a given cards-per-row."""
    rows = [max(MIN_ROW_H, math.ceil(n / per_row) * CELL_H) for n in counts]
    return rows, sum(rows) + DIVIDER * max(len(counts) - 1, 0)


def _choose_per_row(counts, show_text):
    """Cards per row: the old width heuristic, capped so the tier block never gets
    wider than MAX_TIER_ASPECT (keeps big lists rectangular instead of a long strip)."""
    max_count = max(counts, default=0)
    if max_count == 0:
        return MIN_TIER_CELLS
    if show_text:
        cells = math.floor((0.75 * (LABEL_W + LABEL_GAP + max_count * CELL_W) - LABEL_W - LABEL_GAP) / CELL_W)
        preferred = max(cells, MIN_TIER_CELLS)
    else:
        preferred = max_count
    floor = min(MIN_TIER_CELLS, max_count)
    # Aspect shrinks monotonically as per_row drops, so take the widest that fits
    for per_row in range(preferred, floor - 1, -1):
        _, h = _tier_height(counts, per_row)
        if (LABEL_W + LABEL_GAP + per_row * CELL_W) / h <= MAX_TIER_ASPECT:
            return per_row
    return max(floor, 1)


def _layout(data):
    """Compute all geometry (no image downloads)."""
    s = float(data.get("scale") or 2)
    s = min(max(s, 0.5), 4)
    L = {
        "s": s,
        "show_text": bool(int(data.get("showText", 1))),
        "show_times": bool(int(data.get("showPlaytimes", 1))),
        "title": str(data.get("title") or "Tier List"),
        "tiers": data.get("tiers") or [],
    }

    def px(v):
        return round(v * s)
    L["px"] = px
    tiers = L["tiers"]

    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    L["f_title"] = _font(FONT_BOLD, TITLE_SIZE * s)
    L["f_label"] = _font(FONT_REGULAR, LABEL_FONT * s)
    L["f_name"] = f_name = _font(FONT_REGULAR, NAME_SIZE * s)
    L["f_time"] = f_time = _font(FONT_BOLD, NAME_SIZE * s)
    L["f_total"] = f_total = _font(FONT_BOLD, TOTAL_SIZE * s)

    counts = [len(t.get("images", [])) for t in tiers]
    per_row = _choose_per_row(counts, L["show_text"])
    row_heights, tier_h = _tier_height(counts, per_row)
    tier_w = LABEL_W + LABEL_GAP + per_row * CELL_W
    L.update(per_row=per_row, row_heights=row_heights, tier_h=tier_h, tier_w=tier_w)

    # --- title columns (scaled px, measured with real fonts) ---
    columns = []
    col_area_w = 0
    show_times = L["show_times"]
    if L["show_text"]:
        entries = []
        total_seconds = 0
        for t in tiers:
            imgs = t.get("images", [])
            if not imgs:
                continue
            for img in imgs:
                secs = _to_seconds(img)
                total_seconds += secs
                entries.append(("name", (img.get("alt", ""), _fmt(secs), t.get("color", "#FFFFFF"))))
            entries.append(("spacer", None))
        if show_times:
            entries.append(("total", f"Time Wasted: {_fmt(total_seconds)}"))

        limit = px(tier_h)
        col, col_h, col_w = [], 0, 0
        for kind, payload in entries:
            if kind == "name":
                h = px(NAME_ROW_H)
                w = measure.textlength(payload[0], font=f_name)
                if show_times:
                    w += px(NAME_TIME_GAP) + measure.textlength(payload[1], font=f_time)
            elif kind == "spacer":
                h, w = px(TIER_SPACER), 0
            else:
                h = px(TOTAL_MARGIN) + px(TOTAL_SIZE * 1.25)
                w = measure.textlength(payload, font=f_total)
            if col and col_h + h > limit:
                columns.append((col_w, col))
                col, col_h, col_w = [], 0, 0
            if kind == "spacer" and not col:
                continue  # don't start a column with blank space
            col.append((kind, payload, h))
            col_h += h
            col_w = max(col_w, w)
        if col:
            columns.append((col_w, col))

        # Trailing spacers would leave a gap at the bottom of a column
        columns = [(w, c[:-1] if c and c[-1][0] == "spacer" else c) for w, c in columns]
        columns = [(w, c) for w, c in columns if c]

        # Stretch every full column (all but the last) so its final row sits on the
        # bottom edge of the tier list: spread the leftover (< 1 row) between rows.
        stretched = []
        for idx, (w, c) in enumerate(columns):
            gap = 0
            if idx < len(columns) - 1 and len(c) > 1:
                leftover = limit - sum(h for _, _, h in c)
                gap = max(leftover, 0) / (len(c) - 1)
            stretched.append((w, c, gap))
        columns = stretched
        if columns:
            col_area_w = px(SECTION_GAP) + sum(math.ceil(w) for w, _, _ in columns) + px(COLUMN_GAP) * (len(columns) - 1)
    L["columns"] = columns

    # --- roulette odds table (below the tier list) ---
    odds_w = odds_h = 0
    L["odds"] = None
    if bool(int(data.get("showOdds", 0))) and any(counts):
        L["f_odds_head"] = _font(FONT_BOLD, ODDS_HEAD_SIZE * s)
        L["f_odds_label"] = f_lbl = _font(FONT_BOLD, ODDS_LABEL_SIZE * s)
        L["f_odds"] = f_odds = _font(FONT_REGULAR, ODDS_SIZE * s)
        rows = []
        for o in TheRoulette.compute_odds(tiers):
            rows.append((o["tier"].replace("\n", " ") or "(unnamed)", o["color"], [
                f'{o["count"]} game{"" if o["count"] == 1 else "s"}',
                f'{o["perGame"]:.2%}' if o["count"] else "—",
                f'{o["tierTotal"]:.1%}' if o["count"] else "—",
            ]))
        headers = ["Tier", "Games", "Each", "Tier total"]
        swatch = px(ODDS_SWATCH) + px(8)
        col_ws = [max([measure.textlength(headers[0], font=f_lbl)] +
                      [swatch + measure.textlength(r[0], font=f_lbl) for r in rows])]
        for k in range(3):
            col_ws.append(max([measure.textlength(headers[k + 1], font=f_lbl)] +
                              [measure.textlength(r[2][k], font=f_odds) for r in rows]))
        col_ws = [math.ceil(w) for w in col_ws]
        odds_w = sum(col_ws) + px(ODDS_COL_GAP) * 3
        odds_h = (px(ODDS_GAP) + px(ODDS_HEAD_SIZE * 1.4) + px(ODDS_ROW_H)
                  + px(ODDS_ROW_H) * len(rows))
        L["odds"] = {"rows": rows, "headers": headers, "col_ws": col_ws}

    title_w = math.ceil(measure.textlength(L["title"], font=L["f_title"]))
    L["width"] = px(PAD) * 2 + max(px(tier_w) + col_area_w, title_w, odds_w)
    L["height"] = px(PAD) * 2 + px(TITLE_SIZE * 1.2) + px(TITLE_MARGIN) + px(tier_h) + odds_h
    L["card_area"] = sum(counts) * px(CARD_W) * px(CARD_H)
    return L


def _resolve_format(data, size):
    fmt = FORMATS.get(str(data.get("format", "png")).lower(), FORMATS["png"])
    if fmt["ext"] == "webp" and max(size) > 16383:  # WebP hard size limit
        fmt = FORMATS["png"]
    return fmt


def estimate_render(data):
    """Predict output dimensions and file size without downloading or drawing.
    Cover art dominates the file; the flat background and text compress to
    almost nothing. Coefficients in SIZE_MODEL are fitted on real renders."""
    L = _layout(data)
    fmt = _resolve_format(data, (L["width"], L["height"]))
    coef = SIZE_MODEL[fmt["ext"]]
    other = L["width"] * L["height"] - L["card_area"]
    est = coef["card"] * L["card_area"] * L["s"] ** coef["exp"] + coef["other"] * other
    return {
        "width": L["width"],
        "height": L["height"],
        "perRow": L["per_row"],
        "format": fmt["ext"],
        "bytes": int(est),
    }


def render_tierlist(data):
    """data = {title, scale, format, showText, showPlaytimes,
               tiers:[{tier,color,images:[{src,alt,hours,minutes,seconds}]}]}
    Returns (BytesIO, mimetype, extension)."""
    L = _layout(data)
    px, tiers = L["px"], L["tiers"]
    width, height = L["width"], L["height"]
    per_row, row_heights, tier_w = L["per_row"], L["row_heights"], L["tier_w"]
    f_title, f_label, f_name, f_time, f_total = (L[k] for k in ("f_title", "f_label", "f_name", "f_time", "f_total"))
    show_times, columns, title = L["show_times"], L["columns"], L["title"]

    # Fetch all distinct images in parallel
    srcs = list(dict.fromkeys(img["src"] for t in tiers for img in t.get("images", []) if img.get("src")))
    with ThreadPoolExecutor(max_workers=16) as pool:
        loaded = dict(zip(srcs, pool.map(_fetch_image, srcs)))

    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)

    # Title: vertically centered in the header band above the tier list
    header_top = px(PAD)
    header_bottom = px(PAD) + px(TITLE_SIZE * 1.2) + px(TITLE_MARGIN)
    draw.text((width / 2, (header_top + header_bottom) / 2), title, font=f_title,
              fill=TITLE_COLOR, anchor="mm")

    # Tiers
    x0 = px(PAD)
    y = px(PAD) + px(TITLE_SIZE * 1.2) + px(TITLE_MARGIN)
    card_w, card_h = px(CARD_W), px(CARD_H)
    for i, t in enumerate(tiers):
        rh = px(row_heights[i])
        color = t.get("color") or "#FF7F7F"
        try:
            draw.rectangle([x0, y, x0 + px(LABEL_W) - 1, y + rh - 1], fill=color)
        except ValueError:
            color = "#FF7F7F"
            draw.rectangle([x0, y, x0 + px(LABEL_W) - 1, y + rh - 1], fill=color)
        draw.rectangle([x0 + px(LABEL_W), y, x0 + px(tier_w) - 1, y + rh - 1], fill=TIER_BG)

        # Label text, centered and wrapped
        lines = _wrap(draw, t.get("tier", ""), f_label, px(LABEL_W - 2 * LABEL_PAD))
        line_h = px(LABEL_LINE)
        max_lines = max(1, (rh - 2 * px(LABEL_PAD)) // line_h)
        lines = lines[:max_lines]
        ty = y + (rh - line_h * len(lines)) / 2
        for line in lines:
            draw.text((x0 + px(LABEL_W) / 2, ty + line_h / 2), line, font=f_label, fill="black", anchor="mm")
            ty += line_h

        # Cards
        items_x = x0 + px(LABEL_W + LABEL_GAP)
        for j, img_data in enumerate(t.get("images", [])):
            r, c = divmod(j, per_row)
            cx = items_x + px(c * CELL_W + CARD_MARGIN)
            cy = y + px(r * CELL_H + CARD_MARGIN)
            src_img = loaded.get(img_data.get("src"))
            if src_img is not None:
                # object-fit: cover
                canvas.paste(ImageOps.fit(src_img, (card_w, card_h), Image.LANCZOS), (cx, cy))
            else:
                draw.rectangle([cx, cy, cx + card_w - 1, cy + card_h - 1], fill=PLACEHOLDER)

        y += rh
        if i < len(tiers) - 1:
            draw.rectangle([x0, y, x0 + px(tier_w) - 1, y + px(DIVIDER) - 1], fill=BORDER)
            y += px(DIVIDER)

    # Title columns
    if columns:
        cx = x0 + px(tier_w) + px(SECTION_GAP)
        top = px(PAD) + px(TITLE_SIZE * 1.2) + px(TITLE_MARGIN)
        for col_w, col, row_gap in columns:
            col_w = math.ceil(col_w)
            cy = top
            for kind, payload, h in col:
                if kind == "name":
                    name, time_text, color = payload
                    mid = cy + px(2) + px(NAME_SIZE * 1.3) / 2
                    try:
                        draw.text((cx, mid), name, font=f_name, fill=color, anchor="lm")
                    except ValueError:
                        color = "white"
                        draw.text((cx, mid), name, font=f_name, fill=color, anchor="lm")
                    if show_times:
                        draw.text((cx + col_w, mid), time_text, font=f_time, fill=color, anchor="rm")
                elif kind == "total":
                    draw.text((cx + col_w, cy + px(TOTAL_MARGIN)), payload, font=f_total,
                              fill=TOTAL_COLOR, anchor="ra")
                cy += h + row_gap
            cx += col_w + px(COLUMN_GAP)

    # Roulette odds table
    if L["odds"]:
        odds = L["odds"]
        f_head, f_lbl, f_odds = L["f_odds_head"], L["f_odds_label"], L["f_odds"]
        top = px(PAD) + px(TITLE_SIZE * 1.2) + px(TITLE_MARGIN) + px(L["tier_h"]) + px(ODDS_GAP)
        draw.text((x0, top), "Roulette Odds", font=f_head, fill=ODDS_HEAD_COLOR, anchor="la")
        y = top + px(ODDS_HEAD_SIZE * 1.4)
        row_h = px(ODDS_ROW_H)
        col_x = [x0]
        for w in odds["col_ws"][:-1]:
            col_x.append(col_x[-1] + w + px(ODDS_COL_GAP))

        def cell(k, text, font, color, mid):
            if k == 0:
                draw.text((col_x[0], mid), text, font=font, fill=color, anchor="lm")
            else:  # numbers right-aligned in their column
                draw.text((col_x[k] + odds["col_ws"][k], mid), text, font=font, fill=color, anchor="rm")

        mid = y + row_h / 2
        for k, h in enumerate(odds["headers"]):
            cell(k, h, f_lbl, ODDS_MUTED_COLOR, mid)
        y += row_h
        sw = px(ODDS_SWATCH)
        for name, color, values in odds["rows"]:
            mid = y + row_h / 2
            try:
                draw.rectangle([x0, mid - sw / 2, x0 + sw, mid + sw / 2], fill=color)
            except ValueError:
                color = "white"
                draw.rectangle([x0, mid - sw / 2, x0 + sw, mid + sw / 2], fill=color)
            draw.text((x0 + sw + px(8), mid), name, font=f_lbl, fill=color, anchor="lm")
            muted = values[1] == "—"
            for k, v in enumerate(values, start=1):
                cell(k, v, f_odds, ODDS_MUTED_COLOR if muted else ODDS_TEXT_COLOR, mid)
            y += row_h

    fmt = _resolve_format(data, canvas.size)
    buf = BytesIO()
    canvas.save(buf, **fmt["save"])
    buf.seek(0)
    return buf, fmt["mimetype"], fmt["ext"]


# Output encoders. PNG: optimize=True only saves ~2% on photo-heavy output but
# doubles encode time. JPEG/WebP quality chosen to keep small text crisp.
FORMATS = {
    "png":  {"save": {"format": "PNG", "compress_level": 6}, "mimetype": "image/png", "ext": "png"},
    "jpeg": {"save": {"format": "JPEG", "quality": 92, "subsampling": 0, "optimize": True},
             "mimetype": "image/jpeg", "ext": "jpg"},
    "webp": {"save": {"format": "WEBP", "quality": 90, "method": 4},
             "mimetype": "image/webp", "ext": "webp"},
}

# Size model: bytes ~= card * cover_pixels * scale^exp + other * remaining_pixels
# Least-squares fit on 72 real renders (4 lists x scale 1-3 x titles on/off).
# Mean error: PNG 2.5%, JPEG 6%, WebP 8% (covers vary in detail).
SIZE_MODEL = {
    "png":  {"card": 2.1044, "exp": -0.20, "other": 0.0947},
    "jpg":  {"card": 0.7626, "exp": -0.42, "other": 0.1241},
    "webp": {"card": 0.4174, "exp": -0.32, "other": 0.0452},
}
