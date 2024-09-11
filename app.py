import os
import time
from steamgrid import SteamGridDB, StyleType, PlatformType, MimeType, ImageType
import requests
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from io import BytesIO

#https://github.com/ZebcoWeb/python-steamgriddb

#TO DO LIST
#figure out some fucking way to get official steam covers working
##On my phone so can't go into detail but basically you need to log into steam as an anonymous user then query the Steam PICS API and grab appinfo via GetProductInfo()
##There seems to be a working example here using a port of SteamKit2 to python: https://github.com/ValvePython/steam/blob/master/recipes%2F2.SimpleWebAPI%2Frun_webapi.py

api_file = open('API_KEY.txt')
API_KEY = api_file.readline().strip()
CLIENT_ID = api_file.readline().strip()
SECRET = api_file.readline().strip()

sgdb = SteamGridDB(API_KEY)
app = Flask(__name__)
CORS(app)

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

def search_games(query, limit=10):
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

def cache_image(url):
    response = requests.get(url)
    response.raise_for_status()
    
    # Use a hash of the URL as the filename
    file_hash = hashlib.md5(url.encode()).hexdigest()
    file_path = os.path.join(CACHE_DIR, file_hash + '.jpg')
    
    if not os.path.exists(file_path):
        with open(file_path, 'wb') as f:
            f.write(response.content)
    
    return file_path


# Route for serving the HTML file
@app.route('/')
def home():
    return render_template('index.html')  # Ensure this file is in the 'templates' folder

# Endpoint to handle form submission
@app.route('/submit', methods=['POST'])
def submit():
    user_input = request.form['input_data']
    boxarts = []
    game_igdb = search_games(user_input)
    
    try:
        game = sgdb.search_game(user_input)
        for x in game:
            current_grids = sgdb.get_grids_by_gameid([x.id])
            game_name = sgdb.get_game_by_gameid(x.id).name 
            for y in current_grids:
                if y.width == 600 and y.height == 900 and len(boxarts) < 100:
                    boxarts.append([y.url, game_name])
    except:
        pass

    for x in game_igdb:
        try:
            igdb_name = x['name']
            game_id = x['id']
            game_covers = get_game_covers([game_id])
            cover_url = game_covers[0]['url'].replace('t_thumb', 't_cover_big_2x').replace('//', 'https://')
            if len(boxarts) < 100:
                boxarts.append([cover_url, igdb_name])
        except (IndexError, KeyError):
            continue

    return jsonify({'response': f"There are {len(boxarts)} boxart(s) for this search", 'boxarts': boxarts})

# Image caching
@app.route('/cache_image')
def cache_image_route():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    file_path = cache_image(url)
    return send_file(file_path, mimetype='image/jpeg')


# Proxy route for handling CORS issues
# Cache dictionary to store images with their expiration time
image_cache = {}
CACHE_EXPIRATION_TIME = 15 * 24 * 60 * 60  # 15 days in seconds

@app.route('/proxy')
def proxy():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400

    # Check cache
    if url in image_cache:
        cached_image, timestamp = image_cache[url]
        if time.time() - timestamp < CACHE_EXPIRATION_TIME:
            return send_file(BytesIO(cached_image), mimetype='image/jpeg')  # Adjust MIME type if necessary

    # Fetch and cache the image
    try:
        response = requests.get(url)
        response.raise_for_status()
        image_data = response.content
        image_cache[url] = (image_data, time.time())
        return send_file(BytesIO(image_data), mimetype=response.headers['Content-Type'])
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)