from flask import Flask, redirect, request, session, jsonify, render_template, url_for, flash, current_app
from requests_oauthlib import OAuth2Session
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
import database
import threading
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

# recache in progress flag
cache_update_in_progress = False

discord = OAuth2Session(CLIENT_ID, redirect_uri=REDIRECT_URI, scope=SCOPE)

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
                server_quotes = refresh_server_quotes(server_id)
                return server_quotes
            else:
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


    sorted_quotes = []
    legacy_quotes = []

    for quote in quotes:
        user_profile = user_profiles[quote['uid']]

        if quote['date_added'] != 'legacy':
            # Parse and format the date
            date_obj = datetime.strptime(quote['date_added'], '%d/%m/%Y %H:%M:%S')
            formatted_date = date_obj.strftime('%m/%d/%y')

            # Create the formatted quote
            formatted_quote = {
                'text': quote['quote'],
                'author': user_profile.username,
                'profile_pic': user_profile.avatar_url,
                'date': formatted_date,
            }

            # Insert the formatted quote into the sorted list based on its date
            index = 0
            for sorted_quote in sorted_quotes:
                if date_obj > datetime.strptime(sorted_quote['date'], '%m/%d/%y'):
                    break
                index += 1
            sorted_quotes.insert(index, formatted_quote)
        else:
            # Add "legacy" quotes to a separate list
            legacy_quotes.append({
                'text': quote['quote'],
                'author': user_profile.username,
                'profile_pic': user_profile.avatar_url,
                'date': 'legacy',
            })

    # Combine sorted and legacy quotes
    formatted_quotes = sorted_quotes + legacy_quotes

    
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

@app.route('/get_cache_update_status')
def get_cache_update_status():
    global cache_update_in_progress
    print(f"Cache update in progress: {cache_update_in_progress}")
    return jsonify({'cache_update_in_progress': cache_update_in_progress})


def get_quotebot_server_cache_path():
    return os.path.join(app.root_path, 'data', 'quotebot_servers.json')

def _update_quotebot_servers_cache_thread(app):
    global cache_update_in_progress
    print("Starting cache update thread.")  # Debug statement
    with app.app_context():
        cache_path = get_quotebot_server_cache_path()
        server_list = []
        last_id = None  # Used for pagination
        headers = {"Authorization": f"Bot {os.getenv('qb_token')}"}

        while True:
            params = {'limit': 100}
            if last_id:
                params['after'] = last_id

            response = requests.get('https://discord.com/api/v9/users/@me/guilds', headers=headers, params=params)
            print(f"Fetching servers, last_id: {last_id}")  # Debug statement

            if response.status_code == 200:
                servers = response.json()
                if not servers:
                    print("No more servers to fetch.")  # Debug statement
                    break
                server_list.extend([server['id'] for server in servers])
                last_id = servers[-1]['id']
                print(f"Added {len(servers)} servers to the list.")  # Debug statement
            else:
                print(f"Failed to fetch quotebot servers: {response.status_code}, {response.text}")
                break
            
            # Implementing rate limit handling
            if 'X-RateLimit-Remaining' in response.headers and int(response.headers['X-RateLimit-Remaining']) == 0:
                reset_after = float(response.headers.get('X-RateLimit-Reset-After', 0))
                print(f"Rate limit reached. Sleeping for {reset_after} seconds.")  # Debug statement
                time.sleep(reset_after)
            
        # Cache the new data
        with open(cache_path, 'w') as cache_file:
            json.dump({'servers': server_list, 'last_updated': time.time()}, cache_file, indent=4)
            print("Cache updated successfully.")  # Debug statement

        cache_update_in_progress = False
        print("Cache update completed. Setting cache_update_in_progress to False.")  # Debug statement



def is_cache_up_to_date():
    cache_path = get_quotebot_server_cache_path()
    try:
        with open(cache_path, 'r') as cache_file:
            cache_data = json.load(cache_file)
            last_updated = cache_data.get('last_updated')

            # Check if last_updated is not None and within the 2-hour window
            if last_updated is not None:
                return datetime.now() - datetime.fromtimestamp(last_updated) < timedelta(hours=2)
            else:
                # last_updated is None or not present, indicating an empty or invalid cache
                return False
    except (FileNotFoundError, json.JSONDecodeError):
        # If the file doesn't exist or is corrupted, return False
        return False

def update_quotebot_servers_cache():
    global cache_update_in_progress

    # Only start a new thread if one isn't already running
    if not is_cache_up_to_date() and not cache_update_in_progress:
        cache_update_in_progress = True
        print('Updating quotebot server cache')
        thread = threading.Thread(target=_update_quotebot_servers_cache_thread, args=(app,))
        thread.start()

def get_quotebot_servers():
    cache_path = get_quotebot_server_cache_path()
    try:
        # Try to read from the cache file
        with open(cache_path, 'r') as cache_file:
            cache_data = json.load(cache_file)
            return cache_data.get('servers', [])
    except (FileNotFoundError, json.JSONDecodeError):
        # If the file doesn't exist or is corrupted, we'll return an empty list
        return []

@app.route('/profile')
def profile():
    user_id = session.get('user_info', {}).get('id')
    if not user_id:
        return 'You must be logged in to view this page', 403

    # Load the server details from the JSON file
    server_details = load_server_details(user_id)
    # Sort by highest quote count
    server_details = dict(sorted(server_details.items(), key=lambda x: x[1]['quotes'], reverse=True))

    # Check if the cache is up to date
    update_quotebot_servers_cache()
    # Fetch QuoteBot server list
    quotebot_servers = get_quotebot_servers()

    # sort server details by quote count where servers that aren't in quotebot server are at the bottom
    quotebot_server_details = {}
    non_quotebot_server_details = {}
    for server_id, details in server_details.items():
        if server_id in quotebot_servers:
            quotebot_server_details[server_id] = details
        else:
            non_quotebot_server_details[server_id] = details
    server_details = {**quotebot_server_details, **non_quotebot_server_details}

    # Pass the updated server details to the template
    return render_template('profile.html', server_details=server_details, quotebot_servers=quotebot_servers)

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

def fetch_server_data(server_id, user_id):
    # Fetch server data from ../data/server_details.json
    with open('data/server_details.json', 'r') as f:
        server_details = json.load(f)
        
    return server_details[user_id][server_id]

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
    server_profile = ServerProfile(fetch_server_data(server_id, user_info['id']))
    
    return render_template('server_quotes.html', server_id=server_id, server_quotes=quotes, server_name=server_profile.name, server_icon_url=server_profile.icon_url)


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

@app.route('/devlock', methods=['GET'])
def devlock():
    return render_template('devlock.html')

@app.route('/devlock_login', methods=['POST'])
def devlock_login():
    username = request.form.get('username')
    password = request.form.get('password')

    valid_credentials = (
        (username == os.getenv('DEV_LOGIN') and password == os.getenv('DEV_PASSWORD')) or
        (username == os.getenv('TESTER_LOGIN') and password == os.getenv('TESTER_PASSWORD'))
    )

    if valid_credentials:
        session['authenticated'] = True
        return redirect(url_for('home'))
    else:
        return "Invalid Credentials", 403
    
@app.before_request
def before_request():
    session.setdefault('theme', 'dark')
    if 'authenticated' not in session and request.endpoint not in ['devlock', 'devlock_login']:
        return redirect(url_for('devlock'))

if __name__ == '__main__':
    app.run(port=4200)
