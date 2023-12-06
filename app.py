from flask import Flask, redirect, request, session, jsonify, render_template, url_for
from requests_oauthlib import OAuth2Session
import os
from dotenv import load_dotenv
import json
from datetime import datetime

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # Only for development!

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Replace with a real secret key



# These values should be read from a config file or environment variables
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
SCOPE = ['identify', 'guilds']

discord = OAuth2Session(CLIENT_ID, redirect_uri=REDIRECT_URI, scope=SCOPE)

@app.route('/')
def home():
    return render_template('home_1.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/faq/<item_name>')
def faq_item(item_name):
    # Construct the template path dynamically based on the item name
    template_path = f"faq_items/faq_{item_name}.html"

    # Render the specific FAQ item template
    return render_template(template_path)

@app.route('/changelog')
def changelog():
    # Define the path to the changelog.json file
    # Load the changelog data from the JSON file
    with open('data/changelog/changelog.json', 'r') as f:
        changelog_data = json.load(f)
    # Convert string dates to datetime objects for sorting
    for update in changelog_data:
        update['date_added'] = datetime.strptime(update['date_added'], '%d/%m/%y %H:%M:%S')
    # Sort the changelog data by date_added in descending order
    changelog_data.sort(key=lambda x: x['date_added'], reverse=True)
    # Separate the latest update from the rest
    latest_update = changelog_data[0]
    past_updates = changelog_data[1:] if len(changelog_data) > 1 else []
    # Pass the data to the template
    return render_template('changelog.html', latest_update=latest_update, past_updates=past_updates)

@app.route('/login')
def login():
    authorization_url, state = discord.authorization_url('https://discord.com/api/oauth2/authorize')
    session['oauth2_state'] = state
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    discord.fetch_token('https://discord.com/api/oauth2/token',
                        client_secret=CLIENT_SECRET,
                        authorization_response=request.url)
    user_data = discord.get('https://discord.com/api/users/@me').json()
    user_profile = UserProfile(user_data)
    session['user_info'] = {
        'username': user_profile.username,
        'avatar_url': user_profile.avatar_url,
        'id': user_profile.id
    }
    return redirect(url_for('home'))

@app.route('/check_login')
def check_login():
    user_info = session.get('user_info', None)
    return jsonify({
        'logged_in': user_info is not None,
        'user_info': user_info or {}
    })

class UserProfile:
    def __init__(self, user_data):
        self.id = user_data.get('id')
        self.username = user_data.get('username')
        self.avatar_hash = user_data.get('avatar')
        self.discriminator = user_data.get('discriminator')
        self.public_flags = user_data.get('public_flags')
        self.premium_type = user_data.get('premium_type')
        self.flags = user_data.get('flags')
        self.banner_hash = user_data.get('banner')
        self.accent_color = user_data.get('accent_color')
        self.global_name = user_data.get('global_name')
        self.avatar_decoration_data = user_data.get('avatar_decoration_data')
        self.banner_color = user_data.get('banner_color')
        self.mfa_enabled = user_data.get('mfa_enabled')
        self.locale = user_data.get('locale')

    @property
    def avatar_url(self):
        if self.avatar_hash:
            return f"https://cdn.discordapp.com/avatars/{self.id}/{self.avatar_hash}.png"
        else:
            return None

    @property
    def banner_url(self):
        if self.banner_hash:
            return f"https://cdn.discordapp.com/banners/{self.id}/{self.banner_hash}.png"
        else:
            return None

if __name__ == '__main__':
    app.run(port=4200)
