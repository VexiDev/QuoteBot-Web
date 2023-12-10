import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

load_dotenv()

def connect():
    conn = psycopg2.connect(        
        host=os.getenv('db_host'),
        database=os.getenv('db_name'),
        user=os.getenv('db_user'),
        password=os.getenv('db_pass'),
        sslmode='require')
    return conn

def get_quote_counts(guild_ids):
    conn = connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    formatted_guild_ids = ','.join(["%s"] * len(guild_ids))
    cur.execute(f"SELECT guild_id, COUNT(*) as quote_count FROM quotes WHERE hidden=false AND guild_id IN ({formatted_guild_ids}) GROUP BY guild_id", tuple(guild_ids))
    quote_counts = cur.fetchall()
    cur.close()
    conn.close()
    # convert into a dict with {'guild_id': quote_count}
    quote_counts_list = {}
    for quote_count in quote_counts:
        quote_counts_list[quote_count['guild_id']] = quote_count['quote_count']
    print(quote_counts_list)
    return quote_counts_list

def get_server_quotes(guild_id):
    conn = connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM quotes WHERE guild_id = %s AND hidden=false", (guild_id,))
    quotes = cur.fetchall()
    cur.close()
    conn.close()
    print(quotes)
    return quotes
