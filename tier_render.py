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
from urllib.parse import urlparse, parse_qs

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

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

BG = "#1A1A17"
TIER_BG = "#262626"
BORDER = "#0A0A0A"
TITLE_COLOR = "white"
TOTAL_COLOR = "#008000"
PLACEHOLDER = "#333333"

# --- image fetching with a small in-memory cache -----------------------------

_CACHE_MAX = 400
_cache = OrderedDict()
_cache_lock = threading.Lock()
_session = requests.Session()
_session.headers["User-Agent"] = "TierListMaker/1.0"


def _unwrap_proxy(src):
    """'https://any-host/proxy?url=X' -> X, so we fetch the source directly
    regardless of which domain the list was saved on."""
    try:
        parsed = urlparse(src)
        if parsed.path.rstrip("/").endswith("/proxy"):
            inner = parse_qs(parsed.query).get("url")
            if inner:
                return inner[0]
    except ValueError:
        pass
    return src


def _fetch_image(src):
    url = _unwrap_proxy(src)
    with _cache_lock:
        if url in _cache:
            _cache.move_to_end(url)
            return _cache[url]
    try:
        r = _session.get(url, timeout=10)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content))
        img.load()
        img = img.convert("RGB")
    except Exception as e:
        print(f"Render: failed to load {url}: {e}")
        return None
    with _cache_lock:
        _cache[url] = img
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
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

def render_tierlist(data):
    """data = {title, scale, showText, showPlaytimes, tiers:[{tier,color,images:[{src,alt,hours,minutes,seconds}]}]}
    Returns a BytesIO containing the PNG."""
    s = float(data.get("scale") or 2)
    s = min(max(s, 0.5), 4)
    show_text = bool(int(data.get("showText", 1)))
    show_times = bool(int(data.get("showPlaytimes", 1)))
    title = str(data.get("title") or "Tier List")
    tiers = data.get("tiers") or []

    def px(v):
        return round(v * s)

    # Fetch all distinct images in parallel
    srcs = list(dict.fromkeys(img["src"] for t in tiers for img in t.get("images", []) if img.get("src")))
    with ThreadPoolExecutor(max_workers=16) as pool:
        loaded = dict(zip(srcs, pool.map(_fetch_image, srcs)))

    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    f_title = _font(FONT_BOLD, TITLE_SIZE * s)
    f_label = _font(FONT_REGULAR, LABEL_FONT * s)
    f_name = _font(FONT_REGULAR, NAME_SIZE * s)
    f_time = _font(FONT_BOLD, NAME_SIZE * s)
    f_total = _font(FONT_BOLD, TOTAL_SIZE * s)

    # --- tier list geometry (CSS px) ---
    max_count = max((len(t.get("images", [])) for t in tiers), default=0)
    if show_text:
        # Same heuristic as before: 75% of the single-row width, min 3 cards
        cells = math.floor((0.75 * (LABEL_W + LABEL_GAP + max_count * CELL_W) - LABEL_W - LABEL_GAP) / CELL_W)
        per_row = max(cells, MIN_TIER_CELLS)
    else:
        per_row = max(max_count, 1)
    tier_w = LABEL_W + LABEL_GAP + per_row * CELL_W

    row_heights = []
    for t in tiers:
        rows = math.ceil(len(t.get("images", [])) / per_row)
        row_heights.append(max(MIN_ROW_H, rows * CELL_H))
    tier_h = sum(row_heights) + DIVIDER * max(len(tiers) - 1, 0)

    # --- title columns (scaled px, measured with real fonts) ---
    columns = []  # list of (width, [entries]); entry = (kind, payload)
    col_area_w = 0
    if show_text:
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

    # --- canvas ---
    title_w = math.ceil(measure.textlength(title, font=f_title))
    content_w = max(px(tier_w) + col_area_w, title_w)
    width = px(PAD) * 2 + content_w
    height = px(PAD) * 2 + px(TITLE_SIZE * 1.2) + px(TITLE_MARGIN) + px(tier_h)

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

    buf = BytesIO()
    # optimize=True only saves ~2% on photo-heavy output but doubles encode time
    canvas.save(buf, format="PNG", compress_level=6)
    buf.seek(0)
    return buf
