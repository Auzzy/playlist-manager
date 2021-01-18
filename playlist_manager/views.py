import json

import requests
import traceback
from flask import g, jsonify, redirect, render_template, request, session, url_for

from playlistmanager import createplaylist, pandora, musicbrainz

from playlist_manager.playlist_manager import app


@app.errorhandler(requests.exceptions.HTTPError)
def handle_pandora_error(err):
    traceback.print_tb(err.__traceback__)

    if not request.headers.get("X-PandoraAuthToken"):
        return jsonify({}), 401

    return jsonify({}), err.response.status_code


@app.route("/")
def home():
    return redirect(url_for("show_playlists"))

@app.route("/login/")
def login_page():
    return render_template("login.html")

@app.route("/show-all", methods=["GET", "POST"])
def show_playlists():
    if request.method == "POST":
        pandora_client = pandora.Pandora.connect(auth_token=request.headers.get("X-PandoraAuthToken"))
        pandora_playlists = pandora_client.get_all_playlists()
        playlist_info = [{"name": playlist["name"], "id": playlist["pandoraId"]} for playlist in pandora_playlists["items"]]
        return jsonify({"playlists": playlist_info})
    elif request.method == "GET":
        return render_template("index.html")

@app.route("/create", methods=["POST"])
def create_playlist():
    if not request.headers.get("X-PandoraAuthToken"):
        return jsonify({}), 401

    release_filter = musicbrainz.Filter.create(
        include_eps=request.form.get("eps", "False") == "True",
        include_singles=request.form.get("singles", "False") == "True",
        include_compilations=request.form.get("compilations", "False") == "True",
        include_remixes=request.form.get("remixes", "False") == "True",
        include_live=request.form.get("live", "False") == "True",
        include_soundtracks=request.form.get("soundtracks", "False") == "True")

    artist_name = request.form.get("artistName")
    artist_id = request.form.get("artistId")

    if not artist_id:
        search_result = musicbrainz.MusicBrainz.connect().search_artist(artist_name, 85)
        if not search_result:
            return jsonify({"error": f"Could not find {artist_name}"}), 404
        elif len(search_result) > 1:
            choices = []
            for artist in search_result:
                choices.append({
                    "id": artist["id"],
                    "name": artist["name"],
                    "disambiguation": artist.get("disambiguation") or artist.get("country")
                })
            return jsonify({"choices": choices, "artist": artist_name})

        artist_id = search_result[0]["id"]

    created_playlist_name = createplaylist.discography_playlist(
        artist_name,
        artist_id,
        release_filter=release_filter,
        pandora_config={"auth_token": request.headers.get("X-PandoraAuthToken")})
    return jsonify({"created": created_playlist_name})
       

@app.route("/display", methods=["GET", "POST"])
def display_playlist():
    if request.method == "POST":
        id = request.form["id"]
        pandora_client = pandora.Pandora.connect(auth_token=request.headers.get("X-PandoraAuthToken"))
        playlist_info = pandora_client.get_playlist_info(id)
        return jsonify({"tracks": pandora_client.get_playlist_tracks(playlist_info)})
    elif request.method == "GET":
        id = request.args.get("id")
        return render_template("playlist.html", playlist_id=id)

@app.route("/save/<id>", methods=["POST"])
def save_playlist(id):
    new_tracks = json.loads(request.form["tracks"])

    pandora_client = pandora.Pandora.connect(auth_token=request.headers.get("X-PandoraAuthToken"))
    playlist_info = pandora_client.get_playlist_info(id)
    pandora_client.update_playlist(playlist_info, new_tracks)

    return ""

@app.route("/library/add", methods=["POST"])
def library_add_from_playlist():
    playlist_id = request.form["playlistId"]
    tracks = json.loads(request.form["tracks"])

    pandora_client = pandora.Pandora.connect(auth_token=request.headers.get("X-PandoraAuthToken"))
    playlist_info = pandora_client.get_playlist_info(playlist_id)
    pandora_client.library_add_from_playlist(playlist_info, tracks)

    return ""
