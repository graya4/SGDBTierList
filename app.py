from steamgrid import SteamGridDB, StyleType, PlatformType, MimeType, ImageType
import requests
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from io import BytesIO
from igdb.wrapper import IGDBWrapper


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

url = "https://id.twitch.tv/oauth2/token"

payload = {
    "client_id": CLIENT_ID,        # Replace with your client ID
    "client_secret": SECRET,  # Replace with your client secret
    "grant_type": "client_credentials",   # Common grant type for access tokens
}

response_igdb = requests.post(url, data=payload)
ACCESS_TOKEN = response_igdb.json()["access_token"]

headers = {
    'Client-ID': CLIENT_ID,
    'Authorization': f'Bearer {ACCESS_TOKEN}'
}

def search_games(query):
    url = 'https://api.igdb.com/v4/games'
    # Define your query
    body = f'search "{query}"; fields name;'
    
    response_igdb2 = requests.post(url, headers=headers, data=body)
    response_igdb2.raise_for_status()
    return response_igdb2.json()

def get_game_covers(game_ids):
    url = 'https://api.igdb.com/v4/covers'
    # Prepare the query to retrieve covers for specific game IDs
    body = f'fields game, image_id, url, game_localization; where game = ({",".join(map(str, game_ids))});'
    
    response_igdb2 = requests.post(url, headers=headers, data=body)
    response_igdb2.raise_for_status()
    return response_igdb2.json()


#clientID: oofxapi3vqhkq096jt2p295cteadjf
#secret: ikbreh2p9boykmva5udlbjool0xc0z

# Route for serving the HTML file
@app.route('/')
def home():
    return render_template('index.html')  # Ensure this file is in the 'templates' folder

# Endpoint to handle form submission
@app.route('/submit', methods=['POST'])
def submit():
    user_input = request.form['input_data']  # Retrieve the input data from the form
    processed_data = f"Received input: {user_input}"
    boxarts = []
    game_igdb = search_games(user_input)
    #print(game_igdb)
    try:
    #print(user_input)
        game = sgdb.search_game(user_input)
        #print(game)
        
        for x in game:
            current_grids = sgdb.get_grids_by_gameid([x.id])
            game_name = sgdb.get_game_by_gameid(x.id).name 
            for y in current_grids:
                if y.width == 600 and y.height == 900:
                    if len(boxarts) < 100:
                        boxarts.append([y.url, game_name])
    except:
        processed_data = "This game does not exist!"
    
    for x in game_igdb:
        igdb_name = x['name']
        game_id = x['id']
        game_covers = get_game_covers([game_id])
        try:
            cover_url = game_covers[0]['url'].replace('t_thumb', 't_cover_big_2x')
            cover_url = cover_url[2:]
            cover_url = "https://" + cover_url
            #print(cover_url)
            if len(boxarts) < 100:
                boxarts.append([cover_url, igdb_name])
        except:
            continue


    


    # Return a JSON response
    processed_data = "There are {} boxart(s) for this search".format(len(boxarts))
    #print(boxarts)
    return jsonify({'response': processed_data, 'boxarts' : boxarts})

# Proxy route for handling CORS issues
@app.route('/proxy')
def proxy():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        response = requests.get(url)
        response.raise_for_status()
        return send_file(BytesIO(response.content), mimetype=response.headers['Content-Type'])
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)