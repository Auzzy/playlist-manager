import json

from flask import g, jsonify, redirect, render_template, request, session, url_for

# from playlist_manager.lib import createplaylist, pandora
from playlistmanager import createplaylist, pandora

from playlist_manager.playlist_manager import app


'''
{
    "message": "Auth Token is Expired - BIgeNY+PS2XimOsGeHs7Afe1KeiS4rtepYMfnDim0fHPsiI80IsPPl5w==",
    "errorCode": 1001,
    "errorString": "INVALID_REQUEST"
}
'''

@app.route("/")
def show_playlists():
    pandora_client = pandora.Pandora.connect()
    pandora_playlists = pandora_client.get_all_playlists()
    playlist_info = [{"name": playlist["name"], "id": playlist["pandoraId"]} for playlist in pandora_playlists["items"]]
    return render_template("index.html", playlists=playlist_info)

@app.route("/create")
def create_playlist():
    if request.method == "POST":
        artist_name = request.form.get("artistName")
        createplaylist.main(artist_name, 90)
        
    return redirect(show_playlists)

@app.route("/display/<id>")
def display_playlist(id):
    pandora_client = pandora.Pandora.connect()
    playlist_info = pandora_client.get_playlist_info(id)
    return render_template("playlist.html", playlist_id=id, tracks=pandora_client.get_playlist_tracks(playlist_info))

@app.route("/save/<id>", methods=["POST"])
def save_playlist(id):
    new_tracks = json.loads(request.form["tracks"])

    pandora_client = pandora.Pandora.connect()
    playlist_info = pandora_client.get_playlist_info(id)
    pandora_client.update_playlist(playlist_info, new_tracks)

    return ""
