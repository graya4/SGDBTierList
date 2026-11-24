import random
import os
import json
import ast
import math
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
from datetime import datetime


DECAY_FACTOR = 0.65
FIRST_TIER_BONUS = 1.50
# How much a tier's game count grows its share of rolls: 1.0 = linear (a big tier
# swamps a small tier above it), 0.0 = ignore size.
SIZE_EXPONENT = 0.55
# Guardrails vs the nearest non-empty tier above (strict, so tiers never tie):
MIN_GAME_DROP = 0.80   # a game's chance is at most 80% of a game's chance one tier up
MIN_TIER_DROP = 0.90   # a tier's share of rolls is at most 90% of the tier above


def tier_weight(index):
    """Base weight for the tier at this position (0 = top tier)."""
    weight = math.exp(-DECAY_FACTOR * index)
    if index == 0:
        weight *= FIRST_TIER_BONUS  # first tier gets a higher weight
    return weight


def per_game_weights(counts):
    """Unnormalised pick weight for one game in each tier.

    A tier's total share is tier_weight * count^SIZE_EXPONENT, so stuffing a lower
    tier with games can't make it outdraw the tiers above. Then, top-down, each tier
    is clamped so its per-game chance and its total share both stay strictly below
    the nearest non-empty tier above it (see MIN_GAME_DROP / MIN_TIER_DROP)."""
    weights = [tier_weight(i) * n ** SIZE_EXPONENT / n if n else 0.0
               for i, n in enumerate(counts)]
    prev = None
    for i, n in enumerate(counts):
        if not n:
            continue
        if prev is not None:
            prev_w, prev_n = prev
            weights[i] = min(weights[i],
                             prev_w * MIN_GAME_DROP,
                             prev_w * prev_n * MIN_TIER_DROP / n)
        prev = (weights[i], n)
    return weights


def compute_odds(tiers):
    """Chance of the roulette picking each tier / each game in it.
    tiers: [{tier, color, images:[...]}] -> list of dicts, same order."""
    counts = [len(t.get("images") or []) for t in tiers]
    weights = per_game_weights(counts)
    total = sum(w * n for w, n in zip(weights, counts))
    odds = []
    for t, n, w in zip(tiers, counts, weights):
        per_game = w / total if total and n else 0.0
        odds.append({
            "tier": str(t.get("tier", "")).strip(),
            "color": t.get("color") or "#FFFFFF",
            "count": n,
            "perGame": per_game,
            "tierTotal": per_game * n,
        })
    return odds


def roulette(inserted_json):
    game_list = []
    game_image_list = []
    weight_list = []
    tier_info_list = []

    with open("tierlist.json", "r", encoding="utf-8") as f:
        fulljson = json.load(f)

    # Same odds the Roulette tab shows
    odds = compute_odds(fulljson)
    for tier, tier_odds in zip(fulljson, odds):
        for game in tier["images"]:
            game_list.append(game['alt'])
            game_image_list.append(game['src'])
            weight_list.append(tier_odds["perGame"])
            tier_info_list.append((tier['tier'], tier['color']))

    # Pick by index so duplicate titles can't resolve to the wrong entry
    selected_index = random.choices(range(len(game_list)), weights=weight_list, k=1)[0]
    selected_name = game_list[selected_index]
    selected_image = game_image_list[selected_index]
    selected_tier, selected_color = tier_info_list[selected_index]

    # Calculate normalized probability
    total_weight = sum(weight_list)
    probabilities = [w / total_weight for w in weight_list]
    selection_probability = probabilities[selected_index]

    total_games = len(game_list)
    selected_number = selected_index + 1  # 1-based index

    return (
        selected_name,
        selected_image,
        selection_probability,
        selected_tier,
        selected_color,
        selected_number,
        total_games
    )


def get_scaled_font(text, max_width, initial_font_size, font_path):
    font_size = initial_font_size
    font = ImageFont.truetype(font_path, font_size)
    while font.getlength(text) > max_width and font_size > 10:
        font_size -= 1
        font = ImageFont.truetype(font_path, font_size)
    return font


def roulettescript(inserted_json):
    fixed_json = ast.literal_eval(inserted_json)

    with open("tierlist.json", "w", encoding="utf-8") as f:
        json.dump(fixed_json, f, ensure_ascii=False)

    game_name, game_image, probability, tier_label, tier_color, selected_number, total_games = roulette(fixed_json)

    ## VISUAL ##
    # Load image from URL
    response = requests.get(game_image)
    box_image = Image.open(BytesIO(response.content)).convert("RGB")

    # Scale factor
    scale = 2

    # Original canvas size
    original_canvas_width, original_canvas_height = 700, 660
    title_max_width = int(650 * scale)
    canvas_width = int(original_canvas_width * scale)
    canvas_height = int(original_canvas_height * scale)

    # Create canvas
    canvas = Image.new('RGB', (canvas_width, canvas_height), 'black')
    draw = ImageDraw.Draw(canvas)

    # Font loading
    try:
        title_font = ImageFont.truetype("AGaramondPro-Bold.otf", int(60 * scale))
        game_font_path = "AGaramondPro-Bold.otf"
        game_font = get_scaled_font(game_name, title_max_width, int(60 * scale), game_font_path)
        percent_font = ImageFont.truetype("AGaramondPro-Bold.otf", int(32 * scale))
        regular_font = ImageFont.truetype("AGaramondPro-Regular.otf", int(24 * scale))
        red_font = ImageFont.truetype("AGaramondPro-Bold.otf", int(72 * scale))
        timestamp_font = ImageFont.truetype("AGaramondPro-Regular.otf", int(7 * scale))
    except IOError:
        title_font = game_font = percent_font = regular_font = red_font = timestamp_font = ImageFont.load_default()

    text_width = game_font.getlength(game_name)

    draw.text((int(50 * scale), int(20 * scale)), "YOUR GAME IS...", font=title_font, fill="white")
    draw.text(((canvas_width - text_width) / 2, int(100 * scale)), game_name, font=game_font, fill="green")

    box_x, box_y = int(20 * scale), int(200 * scale)
    canvas.paste(box_image, (box_x, box_y))

    draw.text((int(360 * scale), int(220 * scale)), "This game only had a", font=regular_font, fill="white")
    draw.text((int(570 * scale), int(215 * scale)), "{:.2%}".format(probability), font=percent_font, fill="gold")
    draw.text((int(360 * scale), int(250 * scale)), "chance of being chosen!", font=regular_font, fill="white")
    draw.text((int(360 * scale), int(360 * scale)), "YOU\nCANNOT\nTURN\nBACK", font=red_font, fill="red")
    draw.text((int(615 * scale), int(650 * scale)), "{}".format(datetime.now()), font=timestamp_font, fill="white")

    # Draw tier info at bottom
    tier_text = f"{tier_label}"
    try:
        tier_font = ImageFont.truetype("AGaramondPro-Regular.otf", int(12 * scale))
    except IOError:
        tier_font = ImageFont.load_default()

    tier_text_x = int(box_x + box_image.width + 13 * scale)
    tier_text_y = int(645 * scale)
    draw.text((tier_text_x, tier_text_y), tier_text, font=tier_font, fill=tier_color)

    game_count_text = f"{selected_number} of {total_games}"
    try:
        small_font = ImageFont.truetype("AGaramondPro-Regular.otf", int(16 * scale))
    except IOError:
        small_font = ImageFont.load_default()

    text_width = small_font.getlength(game_count_text)
    padding = int(10 * scale)
    text_x = canvas_width - text_width - padding
    text_y = padding
    draw.text((text_x, text_y), game_count_text, font=small_font, fill="white")

    # ✅ Save canvas into memory buffer
    buffer = BytesIO()
    
    canvas.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer
