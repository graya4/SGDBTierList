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
API_KEY = api_file.readline()

sgdb = SteamGridDB(API_KEY)
app = Flask(__name__)
CORS(app)

from flask import Flask, request, render_template_string
API_URL = 'https://www.steamgriddb.com/api/v2'
GAME_ID = 0

headers = {
    "Authorization" : f"Bearer {API_KEY}"
}

params = {
    "gameid" : GAME_ID,
    "platformdata" : "steam"
}

# Route for serving the HTML file
@app.route('/')
def home():
    return render_template('index.html')  # Ensure this file is in the 'templates' folder

# Endpoint to handle form submission
@app.route('/submit', methods=['POST'])
def submit():
    user_input = request.form['input_data']  # Retrieve the input data from the form
    processed_data = f"Received input: {user_input}"

    try:
    #print(user_input)
        game = sgdb.search_game(user_input)
        #print(game)
        boxarts = []
        for x in game:
            print(x.id)
            current_grids = sgdb.get_grids_by_gameid([x.id])
            game_name = sgdb.get_game_by_gameid(x.id).name 
            for y in current_grids:
                if y.width == 600 and y.height == 900:
                    boxarts.append([y.url, game_name])
        
    except:
        processed_data = "This game does not exist!"

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