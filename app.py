import requests
from static import TheRoulette
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from io import BytesIO
from steam_web_api import Steam
import urllib.parse

api_file = open('API_KEY.txt')
API_KEY = api_file.readline().strip()
CLIENT_ID = api_file.readline().strip()
SECRET = api_file.readline().strip()
STEAM_KEY = api_file.readline().strip()
VNDB_API_KEY = api_file.readline().strip()

app = Flask(__name__)
steam = Steam(STEAM_KEY)
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
    game_igdb = search_game_igdb(user_input)
    
    #Official Steam Cover Search
    try:
        user = steam.apps.search_games(user_input)
        found_games = user['apps']
        for x in found_games:
            gameid = x['id'][0]
            artlink = "https://cdn.cloudflare.steamstatic.com/steam/apps/{}/library_600x900_2x.jpg".format(gameid)
            #print(steam.apps.get_app_details(gameid)[str(gameid)]['data'])
            if steam.apps.get_app_details(gameid)[str(gameid)]['data']['type'] == "game" and requests.get(artlink).status_code != 404:
                #print(artlink)
                boxarts.append([artlink, x['name']])
    except:
        pass
    
    #SGDB Search
    game = search_game_sgdb(user_input)['data']
    try:
        for x in game:
            current_grids = get_game_grids_sgdb(x['id'])['data']
            game_name = x['name']
            #print(game_name)
            for y in current_grids:
                if y['width'] == 600 and y['height'] == 900 and len(boxarts) < 100:
                    boxarts.append([y['url'], game_name])
    except:
        pass
    

    #VNDB Search
    game_vndb = search_game_vndb(user_input)['results']
    #print(game_vndb)
    try:
        for x in game_vndb:
            vndb_name = x['title']
            vn_cover = x['image']['url']
            boxarts.append([vn_cover, vndb_name])

    except:
        pass

    #IGDB Search
    for x in game_igdb:
        try:
            igdb_name = x['name']
            game_id = x['id']
            game_covers = get_game_covers([game_id])
            cover_url = game_covers[0]['url'].replace('t_thumb', 't_cover_big_2x').replace('//', 'https://')
            if len(boxarts) < 50:
                boxarts.append([cover_url, igdb_name])
        except (IndexError, KeyError):
            continue

    return jsonify({'response': f"{len(boxarts)} boxart(s).", 'boxarts': boxarts})

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