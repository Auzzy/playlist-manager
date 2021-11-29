import functools
import json

import requests
import traceback
from flask import g, jsonify, redirect, render_template, request, session, url_for

from playlistmanager import musicbrainz
from playlistmanager.services import get_service, supported_services_info
from playlistmanager.discography_playlist import discography_playlist
from playlistmanager.similar_artists_playlist import similar_artists_playlist

from playlist_manager.playlist_manager import app


@app.url_defaults
def add_service_name(endpoint, values):
    if "service_name" not in values:
        values["service_name"] = g.service_name

@app.before_request
def extract_auth_token():
    g.auth_token = request.headers.get("X-AuthToken")
    g.service_name = request.args.get("service_name")

@app.errorhandler(requests.exceptions.HTTPError)
def handle_http_error(err):
    traceback.print_tb(err.__traceback__)

    if not request.headers.get("X-AuthToken"):
        return jsonify({}), 401

    return jsonify({}), err.response.status_code

def auth_token_required(func):
    @functools.wraps(func)
    def decorated_function(*args, **kwargs):
        # We only interact with services on POSTs (even info retrieval), so we
        # don't need to care about service info or auth unless it's a POST.
        if request.method == "POST":
            if not g.service_name:
                return jsonify({})
            if not g.auth_token:
                return jsonify({}), 401
        return func(*args, **kwargs)
    return decorated_function


def _search_musicbrainz(artist_name):
    search_result = musicbrainz.MusicBrainz.connect().search_artist(artist_name, 85)
    choices = []
    for artist in (search_result or []):
        choices.append({
            "id": artist["id"],
            "name": artist["name"],
            "disambiguation": artist.get("disambiguation") or artist.get("country")
        })
    return choices


@app.route("/")
def home():
    return redirect(url_for("show_playlists"))

@app.route("/supported-services")
def supported_services():
    def service_info(info):
        return {
            "display": info["display"],
            "name": info["names"][0]
        }
    return jsonify({
        "services": [service_info(info) for info in supported_services_info()]
    })

@app.route("/show-all", methods=["GET", "POST"])
@auth_token_required
def show_playlists():
    if request.method == "POST":
        service = get_service(g.service_name)
        client_config = service.auth_to_config(g.auth_token)

        playlists_info = service.get_playlists_info(client_config)
        return jsonify({"playlists": playlists_info})
    elif request.method == "GET":
        return render_template("index.html")

@app.route("/create/discography", methods=["POST"])
@auth_token_required
def create_discography_playlist():
    release_filter = musicbrainz.Filter.create(
        include_eps=request.form.get("eps", "False") == "True",
        include_singles=request.form.get("singles", "False") == "True",
        include_compilations=request.form.get("compilations", "False") == "True",
        include_remixes=request.form.get("remixes", "False") == "True",
        include_live=request.form.get("live", "False") == "True",
        include_soundtracks=request.form.get("soundtracks", "False") == "True")

    artist_name = request.form.get("artistName")
    artist_id = request.form.get("artistId")

    service = get_service(g.service_name)
    client_config = service.auth_to_config(g.auth_token)

    if not artist_id:
        search_result = _search_musicbrainz(artist_name)
        if not search_result:
            return jsonify({"error": f"Could not find {artist_name}"}), 404
        elif len(search_result) > 1:
            return jsonify({"choices": search_result, "artist": artist_name})

        artist_id = search_result[0]["id"]

    created_playlist_name = discography_playlist(
        g.service_name,
        artist_name,
        artist_id,
        release_filter=release_filter,
        client_config=client_config)
    return jsonify({"created": created_playlist_name})

@app.route("/create/similar", methods=["POST"])
@auth_token_required
def create_similar_artists_playlist():
    release_filter = musicbrainz.Filter.create(
        include_eps=request.form.get("eps", "False") == "True",
        include_singles=request.form.get("singles", "False") == "True",
        include_compilations=request.form.get("compilations", "False") == "True",
        include_remixes=request.form.get("remixes", "False") == "True",
        include_live=request.form.get("live", "False") == "True",
        include_soundtracks=request.form.get("soundtracks", "False") == "True")

    src_artist_name = request.form["artistName"]
    src_artist_id = request.form.get("artistId")
    similar_artist_ids = json.loads(request.form.get("similarArtistIds", "[]"))

    service = get_service(g.service_name)
    client_config = service.auth_to_config(g.auth_token)

    if not src_artist_id or not similar_artist_ids:
        src_artist_choices = service.search_artists(src_artist_name, client_config)
        for src_artist_choice in src_artist_choices:
            for similar_artist in src_artist_choice["similar"]:
                similar_artist["choices"] = _search_musicbrainz(similar_artist["name"])

        if len(src_artist_choices) != 1 or \
                any(len(similar_artist["choices"]) != 1 for similar_artist in src_artist_choices[0]["similar"]):
            return jsonify({"choices": src_artist_choices, "artist": src_artist_name})

        src_artist_id = src_artist_choices[0]["id"]
        similar_artist_ids = [similar["id"] for similar in src_artist_choices[0]["similar"].values()]

    created_playlist_name = similar_artists_playlist(
        g.service_name,
        src_artist_name,
        src_artist_id,
        similar_artist_ids,
        release_filter=release_filter,
        client_config=client_config)

    return jsonify({"created": created_playlist_name})

@app.route("/display", methods=["GET", "POST"])
@auth_token_required
def display_playlist():
    if request.method == "POST":
        id = request.form["id"]

        service = get_service(g.service_name)
        client_config = service.auth_to_config(g.auth_token)

        playlist_info = service.get_playlist_info(id, client_config)
        if not playlist_info:
            return jsonify({}), 404

        return jsonify(playlist_info)
    elif request.method == "GET":
        id = request.args.get("id")
        return render_template("playlist.html", playlist_id=id)

@app.route("/save/<id>", methods=["POST"])
@auth_token_required
def save_playlist(id):
    new_tracks = json.loads(request.form["tracks"])

    service = get_service(g.service_name)
    client_config = service.auth_to_config(g.auth_token)

    service.update_playlist(id, new_tracks, client_config)

    return ""

@app.route("/library/add", methods=["POST"])
@auth_token_required
def library_add_from_playlist():
    playlist_id = request.form["playlistId"]
    tracks = json.loads(request.form["tracks"])

    service = get_service(g.service_name)
    client_config = service.auth_to_config(g.auth_token)

    service.add_playlist_tracks_to_library(playlist_id, tracks, client_config)

    return ""

@app.route("/playlist/in-library", methods=["POST"])
def tracks_in_library():
    playlist_id = request.form["playlistId"]

    service = get_service(g.service_name)
    client_config = service.auth_to_config(g.auth_token)

    tracks_in_library = service.get_playlist_tracks_in_library(playlist_id, client_config)
    if not tracks_in_library:
        return jsonify({}), 404
    return jsonify({"tracks": tracks_in_library})
