from flask import Flask, redirect, request, session, jsonify, render_template, url_for, flash
from requests_oauthlib import OAuth2Session
import os
from dotenv import load_dotenv
import json
from datetime import datetime
import database
import requests
import time

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # Only for development!

load_dotenv()

app = Flask(__name__)
#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv Replace with a real secret key vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
app.secret_key = "thisisanubersecretkey123123123134901u5401485035u4jghiulbhdnaoiuRVGHC09paomp9cy4hg-92pGHMUIPGCHMPIHUPigco-r"  
#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


# These values should be read from a config file or environment variables
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
SCOPE = ['identify', 'guilds']

discord = OAuth2Session(CLIENT_ID, redirect_uri=REDIRECT_URI, scope=SCOPE)

@app.template_filter('dateformat')
def dateformat_filter(s, format='%Y-%m-%d'):
    if isinstance(s, int):
        # Assuming `s` is a timestamp
        return datetime.fromtimestamp(s).strftime(format)
    elif isinstance(s, str):
        # If `s` is already a string, return as it is or convert it to date object and format
        return s  # Or return datetime.strptime(s, '%Y-%m-%d').strftime(format)
    return s

def get_server_details_file_path():
    return os.path.join(app.root_path, 'data', 'server_details.json')

def save_server_details(user_id, server_details):
    file_path = get_server_details_file_path()
    
    # Assume quote_counts_list is already a dictionary with integer keys
    quote_counts = database.get_quote_counts([int(guild_id) for guild_id in server_details.keys()])

    # Now merge the quote counts into the server details
    for server_id, details in server_details.items():
        # Convert server_id to an integer to match keys in quote_counts
        details['quotes'] = quote_counts.get(int(server_id), 0)

    # Save the combined data to the JSON file
    try:
        with open(file_path, 'r+') as file:
            data = json.load(file)
            data[user_id] = server_details
            file.seek(0)
            json.dump(data, file, indent=4)
    except FileNotFoundError:
        with open(file_path, 'w') as file:
            json.dump({user_id: server_details}, file, indent=4)

def load_server_details(user_id):
    file_path = get_server_details_file_path()
    try:
        with open(file_path, 'r') as file:
            data = json.load(file)
            return data.get(user_id, {})
    except FileNotFoundError:
        return {}  # Return empty if file not found

def get_server_quotes_file_path():
    return os.path.join(app.root_path, 'data', 'server_quotes.json')

def load_or_refresh_server_quotes(server_id):
    file_path = get_server_quotes_file_path()
    try:
        with open(file_path, 'r') as file:
            server_quotes_data = json.load(file)
            server_quotes = server_quotes_data.get(server_id, {})
            last_refreshed = server_quotes.get("date_refreshed", 0)
            # Check if data is older than 2 hours
            if time.time() - last_refreshed > 7200:
                raise ValueError("Data is old, needs refresh.")
            return server_quotes.get("quotes", [])
    except (FileNotFoundError, ValueError):
        server_quotes = refresh_server_quotes(server_id)
        return server_quotes

def refresh_server_quotes(server_id):

    quotes = database.get_server_quotes(server_id)

    unique_user_ids = {quote['uid'] for quote in quotes}

    user_profiles = {}
    for user_id in unique_user_ids:
        user_data = fetch_user_data(user_id)
        if user_data:
            user_profiles[user_id] = UserProfile(user_data)
        else:
            # If user data could not be fetched, create a default UserProfile
            user_profiles[user_id] = UserProfile({"username": "Unknown", "avatar": None})

    
    formatted_quotes = []
    for quote in quotes:
        user_profile = user_profiles[quote['uid']]
        formatted_quote = {
            'text': quote['quote'],
            'author': user_profile.username,
            'profile_pic': user_profile.avatar_url,
            'date': quote['date_added'],
        }
        formatted_quotes.append(formatted_quote)
    
    # Save the refreshed data
    server_quotes_data = {
        server_id: {
            "date_refreshed": time.time(),
            "quotes": formatted_quotes,
        }
    }
    with open(get_server_quotes_file_path(), 'w') as file:
        json.dump(server_quotes_data, file, indent=4)

    return formatted_quotes

@app.route('/')
def home():
    return render_template('home_1.html')

@app.route('/logout')
def logout():
    session.clear()  # This clears all data in the session
    # You can redirect to the home page or a logout confirmation page
    return redirect(url_for('home'))


@app.route('/profile')
def profile():
    user_id = session.get('user_info', {}).get('id')
    if not user_id:
        return 'You must be logged in to view this page', 403

    # Load the server details from the JSON file
    server_details = load_server_details(user_id)

    # Sort by highest quote count
    server_details = dict(sorted(server_details.items(), key=lambda x: x[1]['quotes'], reverse=True))

    # Pass the updated server details to the template
    return render_template('profile.html', server_details=server_details)

@app.route('/about')
def about():
    return render_template('about.html')

def fetch_user_data(user_id):
    headers = {
        "Authorization": f"Bot {os.getenv('qb_token')}"
    }
    try:
        response = requests.get(f'https://discord.com/api/v9/users/{user_id}', headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to fetch user data: {response.status_code}, {response.text}")
            return {}
    except Exception as e:
        print(f"Error fetching user data: {e}")
        return {}

def fetch_server_data(server_id):
    # Fetch server data from ../data/server_details.json
    with open('data/server_details.json', 'r') as f:
        server_details = json.load(f)
        
    return server_details.get(server_id, {})

@app.route('/quotes/<server_id>')
def view_server(server_id):
    user_info = session.get('user_info')
    if not user_info:
        flash('You must be logged in to view this page.')
        return redirect(url_for('login'))

    discord = OAuth2Session(CLIENT_ID, token=session.get('oauth2_token'))
    response = discord.get('https://discord.com/api/users/@me/guilds')

    if response.status_code != 200:
        flash('Unable to verify server membership.')
        return redirect(url_for('home'))

    guilds = response.json()
    if not any(guild['id'] == server_id for guild in guilds):
        flash('You are not a member of this server.')
        return redirect(url_for('home'))

    quotes = load_or_refresh_server_quotes(server_id)
    
    # Fetch server details
    server_profile = ServerProfile(fetch_server_data(server_id))
    
    return render_template('server_quotes.html', server_id=server_id, server_quotes=quotes)


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
    token = discord.fetch_token('https://discord.com/api/oauth2/token',
                        client_secret=CLIENT_SECRET,
                        authorization_response=request.url)
    
    session['oauth2_token'] = token

    user_data = discord.get('https://discord.com/api/users/@me').json()
    user_profile = UserProfile(user_data)
    
    # Instead of storing all user info in the session, just store the user ID and avatar URL
    session['user_info'] = {
        'username': user_profile.username,
        'avatar_url': user_profile.avatar_url,
        'id': user_profile.id
    }

    server_data_response = discord.get('https://discord.com/api/users/@me/guilds').json()
    global session_server_details
    user_servers = {
        server['id']: {
            'name': server['name'],
            'icon_url': f"https://cdn.discordapp.com/icons/{server['id']}/{server['icon']}.png" if server['icon'] else url_for('static', filename='images/default_icon.png')
        }
        for server in server_data_response
    }
    save_server_details(user_profile.id, user_servers)

    return redirect(url_for('home'))


@app.route('/check_login')
def check_login():
    user_info = session.get('user_info', None)
    return jsonify({
        'logged_in': user_info is not None,
        'user_info': user_info or {}
    })

class ServerProfile:
    def __init__(self, server_data):
        self.id = server_data.get('id')
        self.name = server_data.get('name')
        self.icon_hash = server_data.get('icon')

    @property
    def icon_url(self):
        if self.icon_hash:
            return f"https://cdn.discordapp.com/icons/{self.id}/{self.icon_hash}.png"
        else:
            # Return a default icon if none is set
            return url_for('static', filename='images/default_server_icon.png')


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
