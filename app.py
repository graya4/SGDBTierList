from steamgrid import SteamGridDB
import requests
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from io import BytesIO
from steam_web_api import Steam

api_file = open('API_KEY.txt')
API_KEY = api_file.readline().strip()
CLIENT_ID = api_file.readline().strip()
SECRET = api_file.readline().strip()
STEAM_KEY = api_file.readline().strip()

sgdb = SteamGridDB(API_KEY)
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
    try:
        game = sgdb.search_game(user_input)
        for x in game:
            current_grids = sgdb.get_grids_by_gameid([x.id])
            #print(current_grids)
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

    return jsonify({'response': f"{len(boxarts)} boxart(s) found.", 'boxarts': boxarts})

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

if __name__ == '__main__':
    app.run(debug=True)