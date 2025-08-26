import random
import os
import json
import ast
import math
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
from datetime import datetime


def roulette(inserted_json):
    game_list = []
    game_image_list = []
    weight_list = []
    tier_info_list = []
    decay_factor = 0.7777777

    with open("tierlist.json", "r", encoding="utf-8") as f:
        fulljson = json.load(f)

        for i, tier in enumerate(fulljson):
            if i == 0:
                # First tier boosted by 25%
                weight = 1.30 * math.exp(-decay_factor * i)
            else:
                # Subsequent tiers use normal decay
                weight = math.exp(-decay_factor * i)

            for game in tier["images"]:
                game_list.append(game['alt'])
                game_image_list.append(game['src'])
                weight_list.append(weight)
                tier_info_list.append((tier['tier'], tier['color']))

    # Random selection based on weights
    selected_name = random.choices(game_list, weights=weight_list, k=1)[0]
    selected_index = game_list.index(selected_name)
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
