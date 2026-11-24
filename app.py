import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, wait
from io import BytesIO

import requests
from flask import Flask, request, jsonify, render_template, send_file, Response
from flask_cors import CORS
from steam_web_api import Steam

import image_fetch
from image_fetch import FetchError, get_steam_items, steam_asset_url, STEAM_TYPE_GAME
from static import TheRoulette
from tier_render import render_tierlist, estimate_render

api_file = open('API_KEY.txt')
API_KEY = api_file.readline().strip()
CLIENT_ID = api_file.readline().strip()
SECRET = api_file.readline().strip()
STEAM_KEY = api_file.readline().strip()
VNDB_API_KEY = api_file.readline().strip()

app = Flask(__name__)
steam = Steam(STEAM_KEY)
CORS(app)

image_fetch.STEAM_KEY = STEAM_KEY
http = image_fetch.session          # pooled connections + retries, shared with /proxy
API_TIMEOUT = (5, 10)               # (connect, read) seconds for search APIs
SEARCH_TIMEOUT = 12                 # overall budget per search; slow sources are skipped
MAX_RESULTS = 100
SGDB_MAX_GAMES = 15
SGDB_GRIDS_PER_GAME = 4

SEARCH_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="search")
DETAIL_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="detail")


# --- IGDB auth (refreshed automatically when the token expires) ---------------

_igdb_lock = threading.Lock()
headers = {'Client-ID': CLIENT_ID}


def refresh_igdb_token():
    r = http.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": CLIENT_ID,
        "client_secret": SECRET,
        "grant_type": "client_credentials",
    }, timeout=API_TIMEOUT)
    r.raise_for_status()
    headers['Authorization'] = f'Bearer {r.json()["access_token"]}'


refresh_igdb_token()


def igdb_post(endpoint, body):
    r = http.post(f'https://api.igdb.com/v4/{endpoint}', headers=headers, data=body, timeout=API_TIMEOUT)
    if r.status_code == 401:
        with _igdb_lock:
            refresh_igdb_token()
        r = http.post(f'https://api.igdb.com/v4/{endpoint}', headers=headers, data=body, timeout=API_TIMEOUT)
    r.raise_for_status()
    return r.json()


headers_sgdb = {
    'Authorization': f'Bearer {API_KEY}'
}

headers_vndb = {
    'Authorization': f'token {VNDB_API_KEY}',
    'Content-Type': 'application/json'
}


# --- API calls -----------------------------------------------------------------

def search_game_vndb(query):
    payload = {
        "filters": ["search", "=", query],
        "fields": "id,title,alttitle,released,description,image.url"
    }
    r = http.post('https://api.vndb.org/kana/vn', headers=headers_vndb, json=payload, timeout=API_TIMEOUT)
    r.raise_for_status()
    return r.json()


def search_game_igdb(query, limit=20):
    # One request: cover is expanded inline instead of a second call per game
    safe = query.replace('\\', '\\\\').replace('"', '\\"')
    body = f'search "{safe}"; fields name, cover.image_id; where cover != null; limit {limit};'
    return igdb_post('games', body)


def search_game_sgdb(query):
    encoded_query = urllib.parse.quote(query, safe='')
    r = http.get(f'https://www.steamgriddb.com/api/v2/search/autocomplete/{encoded_query}',
                 headers=headers_sgdb, timeout=API_TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_game_grids_sgdb(game_id):
    # Let SGDB filter to 600x900 static grids instead of downloading every size
    r = http.get(f'https://www.steamgriddb.com/api/v2/grids/game/{game_id}',
                 params={'dimensions': '600x900', 'types': 'static'},
                 headers=headers_sgdb, timeout=API_TIMEOUT)
    r.raise_for_status()
    return r.json()


# --- per-source searches ----------------------------------------------------------

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
        games = search_game_sgdb(user_input).get('data', [])[:SGDB_MAX_GAMES]

        def process_game(game):
            try:
                grids = get_game_grids_sgdb(game['id']).get('data', [])
            except Exception:
                return []
            # SGDB returns grids ordered by score; keep the best few per game
            return [[g['url'], game['name']] for g in grids
                    if g.get('width') == 600 and g.get('height') == 900][:SGDB_GRIDS_PER_GAME]

        for result in DETAIL_POOL.map(process_game, games):
            boxarts.extend(result)
    except Exception as e:
        print(f"SGDB search failed: {e}")

    search_term = user_input.lower().strip()
    boxarts.sort(key=lambda x: (x[1].lower() != search_term, x[1].lower()))  # exact match first
    return boxarts


def igdb_search_boxarts(user_input):
    boxarts = []
    try:
        for game in search_game_igdb(user_input):
            image_id = (game.get('cover') or {}).get('image_id')
            if image_id:
                boxarts.append([
                    f'https://images.igdb.com/igdb/image/upload/t_cover_big_2x/{image_id}.jpg',
                    game.get('name', '')
                ])
    except Exception as e:
        print(f"IGDB search failed: {e}")
    return boxarts


def vndb_search_boxarts(user_input):
    boxarts = []
    try:
        for game in search_game_vndb(user_input).get('results', []):
            url = (game.get('image') or {}).get('url')
            if url:
                boxarts.append([url, game.get('title', '')])
    except Exception as e:
        print(f"VNDB search failed: {e}")
    return boxarts


# --- search result cache --------------------------------------------------------

SEARCH_CACHE_TTL = 15 * 60
SEARCH_CACHE_MAX = 200
_search_cache = {}
_search_cache_lock = threading.Lock()


def _cached_search(key):
    with _search_cache_lock:
        hit = _search_cache.get(key)
        if hit and time.time() - hit[0] < SEARCH_CACHE_TTL:
            return hit[1]
    return None


def _store_search(key, value):
    with _search_cache_lock:
        if len(_search_cache) >= SEARCH_CACHE_MAX:
            oldest = min(_search_cache, key=lambda k: _search_cache[k][0])
            _search_cache.pop(oldest, None)
        _search_cache[key] = (time.time(), value)


# Route for serving the HTML file
@app.route('/')
def home():
    return render_template('newindex.html')


@app.route('/submit', methods=['POST'])
def submit():
    user_input = str(request.form.get('searchbar', '')).strip()
    if not user_input:
        return jsonify({'response': "Type something to search.", 'boxarts': []})

    key = ' '.join(user_input.lower().split())
    cached = _cached_search(key)
    if cached is not None:
        return jsonify(cached)

    sources = [steam_search, sgdb_search, vndb_search_boxarts, igdb_search_boxarts]  # display order
    futures = [SEARCH_POOL.submit(fn, user_input) for fn in sources]
    done, not_done = wait(futures, timeout=SEARCH_TIMEOUT)

    boxarts, seen, skipped = [], set(), []
    for fn, future in zip(sources, futures):
        if future not in done:
            skipped.append(fn.__name__)
            continue
        for url, title in future.result():
            if url not in seen:
                seen.add(url)
                boxarts.append([url, title])
    if skipped:
        print(f"Search {user_input!r}: timed out waiting for {', '.join(skipped)}")

    result = {
        'response': f"{min(len(boxarts), MAX_RESULTS)} boxart(s).",
        'boxarts': boxarts[:MAX_RESULTS]
    }
    if not skipped:  # don't cache incomplete results
        _store_search(key, result)
    return jsonify(result)


# Proxy route for handling CORS issues
@app.route('/proxy')
def proxy():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400
    try:
        data, content_type = image_fetch.fetch_image(url)
    except FetchError as e:
        status = e.status if e.status in (400, 404, 413, 415) else 502
        return jsonify({"error": str(e)}), status
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502

    resp = Response(data, mimetype=content_type)
    # Image URLs are content-addressed in practice; let the browser keep them
    resp.headers['Cache-Control'] = 'public, max-age=2592000, immutable'
    return resp


@app.route("/render_png", methods=["POST"])
def render_png():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("tiers"), list):
        return jsonify({"error": "Expected JSON with a 'tiers' list"}), 400
    try:
        buffer, mimetype, ext = render_tierlist(data)
    except Exception as e:
        print(f"Render failed: {e}")
        return jsonify({"error": "Render failed"}), 500
    return send_file(buffer, mimetype=mimetype, download_name=f"tierlist.{ext}")


@app.route("/render_estimate", methods=["POST"])
def render_estimate():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("tiers"), list):
        return jsonify({"error": "Expected JSON with a 'tiers' list"}), 400
    try:
        return jsonify(estimate_render(data))
    except Exception as e:
        print(f"Estimate failed: {e}")
        return jsonify({"error": "Estimate failed"}), 500


@app.route("/roulette_odds", methods=["POST"])
def roulette_odds():
    data = request.get_json(silent=True)
    tiers = data.get("tiers") if isinstance(data, dict) else None
    if not isinstance(tiers, list):
        return jsonify({"error": "Expected JSON with a 'tiers' list"}), 400
    return jsonify({"odds": TheRoulette.compute_odds(tiers)})


@app.route("/roulette_choose", methods=["POST"])
def roulette_choose():
    user_input = request.get_json()
    user_input = str(user_input)
    buffer = TheRoulette.roulettescript(user_input)
    return send_file(buffer, mimetype='image/png', download_name='roulette.png')


if __name__ == '__main__':
    app.run(debug=True, threaded=True)
