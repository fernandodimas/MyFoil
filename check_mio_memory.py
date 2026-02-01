
import sys, os
sys.path.append(os.path.join(os.getcwd(), 'app'))
import titles
import state
from settings import load_settings
# Mock app context if needed
from flask import Flask
app = Flask(__name__)
with app.app_context():
    titles.load_titledb(force=True)
    mio = titles._titles_db.get('01000A001E978000')
    print(f"MIO Info: {mio}")
    if mio:
        print(f"Icon URL: {mio.get('iconUrl')}")
        print(f"Screenshots: {mio.get('screenshots')}")
