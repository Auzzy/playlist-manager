import os

from playlist_manager.playlist_manager import app

HOST = os.getenv("IP", "0.0.0.0")
PORT = int(os.getenv("PORT", 8080))

app.run(host=HOST, port=PORT, debug=os.environ.get("DEBUG", "True") == "True")
