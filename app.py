from urllib import response

import requests
from static import TheRoulette
from tier_render import render_tierlist
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from io import BytesIO
from steam_web_api import Steam
import urllib.parse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

api_file = open('API_KEY.txt')
API_KEY = api_file.readline().strip()
CLIENT_ID = api_file.readline().strip()
SECRET = api_file.readline().strip()
STEAM_KEY = api_file.readline().strip()
VNDB_API_KEY = api_file.readline().strip()

app = Flask(__name__)
steam = Steam(STEAM_KEY)
CORS(app)


STEAM_ASSET_BASE = "https://shared.akamai.steamstatic.com/store_item_assets/"
STEAM_TYPE_GAME = 0  # EStoreAppType: 0 = game, 1 = demo, 4 = DLC, ...


def get_steam_items(appids):
    """Fetch store items (with assets) for many appids in one request."""
    payload = {
        "ids": [{"appid": int(a)} for a in appids],
        "context": {"language": "english", "country_code": "US"},
        "data_request": {"include_assets": True},
    }
    r = requests.get(
        "https://api.steampowered.com/IStoreBrowseService/GetItems/v1/",
        params={"key": STEAM_KEY, "input_json": json.dumps(payload)},
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("response", {}).get("store_items", [])


def steam_asset_url(item, *asset_keys):
    """Build a full image URL from a store item's assets.

    Newer games store art under a content hash (e.g. "<sha1>/library_600x900_2x.jpg"),
    and some use different filenames entirely, so the path must come from the API
    rather than being guessed. Returns the first key that exists, or None.
    """
    assets = item.get("assets") or {}
    fmt = assets.get("asset_url_format")
    if not fmt:
        return None
    for key in asset_keys:
        filename = assets.get(key)
        if filename:
            return STEAM_ASSET_BASE + fmt.replace("${FILENAME}", filename)
    return None

# Function to get OAuth token for IGDB
def get_igdb_access_token():
    url = "https://id.twitch.tv/oauth2/token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": SECRET,
        "grant_type": "client_credentials"
    }
    response = requests.post(url, data=payload)
    response.raise_for_status()
    return response.json()["access_token"]

ACCESS_TOKEN = get_igdb_access_token()

headers = {
    'Client-ID': CLIENT_ID,
    'Authorization': f'Bearer {ACCESS_TOKEN}'
}

headers_sgdb = {
    'Authorization': f'Bearer {API_KEY}'
}

headers_vndb = {
    'Authorization' : f'token {VNDB_API_KEY}',
    'Content-Type': 'application/json'
}



#VNDB API CALLS
def search_game_vndb(query):
    url = 'https://api.vndb.org/kana/vn'
    payload = {
        "filters": ["search", "=", query],  # text search
        "fields": "id,title,alttitle,released,description,image.url"
    }

    response = requests.post(url, headers=headers_vndb, json=payload)
    response.raise_for_status()
    return response.json()

def get_vn_covers(vn_ids):
    url = "https://api.vndb.org/kana/vn"
    payload = {
        "filters": ["id", "=", vn_ids],    # multiple IDs allowed
        "fields": "id, title, image.url, image.sexual, image.violence",
    }

    response = requests.post(url, headers=headers_vndb, json=payload)
    response.raise_for_status()

    data = response.json()
    return data.get("results", [])

#IGDB API CALLS

def search_game_igdb(query, limit=20):
    url = 'https://api.igdb.com/v4/games'
    body = f'search "{query}"; fields name; limit {limit};'  # Use limit for pagination
    response = requests.post(url, headers=headers, data=body)
    response.raise_for_status()
    return response.json()

def get_game_covers(game_ids):
    url = 'https://api.igdb.com/v4/covers'
    body = f'fields game, image_id, url; where game = ({",".join(map(str, game_ids))});'
    response = requests.post(url, headers=headers, data=body)
    response.raise_for_status()
    return response.json()

#SGDB API CALLS

def search_game_sgdb(query):
    encoded_query = urllib.parse.quote(query, safe='')
    search_url = f'https://www.steamgriddb.com/api/v2/search/autocomplete/{encoded_query}'
    response = requests.get(search_url, headers=headers_sgdb)
    if response.status_code == 200:
        return response.json()
    else:
        return f"Error: {response.status_code}"

def get_game_grids_sgdb(game_id):
    grids_url = f'https://www.steamgriddb.com/api/v2/grids/game/{game_id}'
    response = requests.get(grids_url, headers=headers_sgdb)
    if response.status_code == 200:
        return response.json()
    else:
        return f"Error: {response.status_code}"


def steam_search(user_input):
    boxarts = []

    try:
        found_games = steam.apps.search_games(user_input)['apps']
        appids = [x['id'][0] for x in found_games if x.get('id')]
        if not appids:
            return boxarts

        # One batched call replaces per-game get_app_details + image probing
        for item in get_steam_items(appids):
            if item.get('success') != 1 or item.get('type') != STEAM_TYPE_GAME:
                continue
            artlink = steam_asset_url(item, 'library_capsule_2x', 'library_capsule')
            if artlink:
                boxarts.append([artlink, item.get('name', '')])

    except Exception as e:
        print(f"Steam search failed: {e}")

    return boxarts

def sgdb_search(user_input):
    boxarts = []

    try:
        games = search_game_sgdb(user_input)['data']

        def process_game(game):
            results = []

            try:
                grids = get_game_grids_sgdb(game['id'])['data']

                for grid in grids:
                    if grid['width'] == 600 and grid['height'] == 900:
                        results.append([grid['url'], game['name']])

            except Exception:
                pass

            return results

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(process_game, game) for game in games]

            for future in as_completed(futures):
                boxarts.extend(future.result())

    except Exception:
        pass

    search_term = user_input.lower().strip()

    boxarts.sort(
        key=lambda x: (
            x[1].lower() != search_term,  # exact match first
            x[1].lower()                  # then alphabetical
        )
    )

    return boxarts

def igdb_search_boxarts(user_input):
    boxarts = []

    try:
        games = search_game_igdb(user_input)

        def process_game(game):
            try:
                covers = get_game_covers([game['id']])

                if not covers:
                    return None

                return [
                    covers[0]['url']
                    .replace('t_thumb', 't_cover_big_2x')
                    .replace('//', 'https://'),
                    game['name']
                ]

            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(process_game, game) for game in games]

            for future in as_completed(futures):
                result = future.result()
                if result:
                    boxarts.append(result)

    except Exception:
        pass

    return boxarts

def vndb_search_boxarts(user_input):
    boxarts = []

    try:
        games = search_game_vndb(user_input)['results']

        for game in games:
            try:
                boxarts.append([
                    game['image']['url'],
                    game['title']
                ])
            except (KeyError, TypeError):
                continue

    except Exception:
        pass

    return boxarts




# Route for serving the HTML file
@app.route('/')
def home():
    return render_template('newindex.html')  # Ensure this file is in the 'templates' folder

# Endpoint to handle form submission
@app.route('/submit', methods=['POST'])
def submit():
    user_input = request.form['searchbar']
    user_input = str(user_input)
    boxarts = []
    
    with ThreadPoolExecutor(max_workers=4) as pool:
        steam_future = pool.submit(steam_search, user_input)
        sgdb_future = pool.submit(sgdb_search, user_input)
        vndb_future = pool.submit(vndb_search_boxarts, user_input)
        igdb_future = pool.submit(igdb_search_boxarts, user_input)

    boxarts = []

    boxarts.extend(steam_future.result())  # always first
    boxarts.extend(sgdb_future.result())   # always second
    boxarts.extend(vndb_future.result())   # always third
    boxarts.extend(igdb_future.result())   # always last      

    return jsonify({
        'response': f"{len(boxarts)} boxart(s).",
        'boxarts': boxarts[:100]
    })

# Proxy route for handling CORS issues
@app.route('/proxy')
def proxy():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400
    # Fetch and cache the image
    try:
        response = requests.get(url)
        response.raise_for_status()
        image_data = response.content
        return send_file(BytesIO(image_data), mimetype=response.headers['Content-Type'])
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500


@app.route("/render_png", methods=["POST"])
def render_png():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("tiers"), list):
        return jsonify({"error": "Expected JSON with a 'tiers' list"}), 400
    try:
        buffer = render_tierlist(data)
    except Exception as e:
        print(f"Render failed: {e}")
        return jsonify({"error": "Render failed"}), 500
    return send_file(buffer, mimetype="image/png", download_name="tierlist.png")


@app.route("/roulette_choose", methods=["POST"])
def roulette_choose():
    user_input = request.get_json()
    user_input = str(user_input)
    #print(user_input)
    buffer = TheRoulette.roulettescript(user_input)
    #print("dont!")
    return send_file(buffer, mimetype='image/png', download_name='roulette.png')

if __name__ == '__main__':
    app.run(debug=True)