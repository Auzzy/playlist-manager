import json

import requests
import traceback
from flask import g, jsonify, redirect, render_template, request, session, url_for

from playlistmanager import musicbrainz
from playlistmanager.services import get_service
from playlistmanager.services.pandora import client as pandora
from playlistmanager.discography_playlist import discography_playlist
from playlistmanager.similar_artists_playlist import similar_artists_playlist

from playlist_manager.playlist_manager import app


@app.url_defaults
def add_service_name(endpoint, values):
    if "service_name" not in values:
        values["service_name"] = g.service_name or "pandora"

@app.url_value_preprocessor
def pull_service_name(endpoint, values):
    if not values:
        values = {}

    g.service_name = values.pop("service_name", "pandora")
    # Should do something with this.
    # if g.service_name not in get_supported_services():
    #     pass



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

@app.errorhandler(requests.exceptions.HTTPError)
def handle_pandora_error(err):
    traceback.print_tb(err.__traceback__)

    if not request.headers.get("X-PandoraAuthToken"):
        return jsonify({}), 401

    return jsonify({}), err.response.status_code


@app.route("/")
def home():
    return redirect(url_for("show_playlists"))

@app.route("/show-all", methods=["GET", "POST"])
def show_playlists():
    def get_playlist_info(pandora_playlists, playlist):
        details = pandora_playlists["annotations"][playlist["pandoraId"]]
        return {
            "id": playlist["pandoraId"],
            "name": playlist["name"],
            "totalTracks": details["totalTracks"],
            "duration": details["duration"]  # Seconds
        }

    if request.method == "POST":
        pandora_client = pandora.Pandora.connect(auth_token=request.headers.get("X-PandoraAuthToken"))
        pandora_playlists = pandora_client.get_all_playlists()
        thumbs_up_ids = [info["pandoraId"] for key, info in pandora_playlists["annotations"].items() if info.get("linkedType") in ("StationThumbs", "MyThumbsUp", "SharedListening")]
        playlist_info = [get_playlist_info(pandora_playlists, playlist) for playlist in pandora_playlists["items"] if playlist["pandoraId"] not in thumbs_up_ids]
        return jsonify({"playlists": playlist_info})
    elif request.method == "GET":
        return render_template("index.html")

@app.route("/create/discography", methods=["POST"])
def create_discography_playlist():
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
        client_config={"auth_token": request.headers.get("X-PandoraAuthToken")})
    return jsonify({"created": created_playlist_name})

@app.route("/create/similar", methods=["POST"])
def create_similar_artists_playlist():
    if not request.headers.get("X-PandoraAuthToken"):
        return jsonify({}), 401

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

    if not src_artist_id or not similar_artist_ids:
        service = get_service(g.service_name)

        client_config = service.auth_to_config(request.headers.get("X-PandoraAuthToken"))

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
        client_config={"auth_token": request.headers.get("X-PandoraAuthToken")})

    return jsonify({"created": created_playlist_name})

@app.route("/display", methods=["GET", "POST"])
def display_playlist():
    if request.method == "POST":
        id = request.form["id"]
        pandora_client = pandora.Pandora.connect(auth_token=request.headers.get("X-PandoraAuthToken"))
        playlist_info = pandora_client.get_playlist_info(id)
        return jsonify({
            "name": playlist_info["name"],
            "tracks": pandora_client.get_playlist_tracks(playlist_info),
            "duration": playlist_info["duration"]  # Seconds
        })
    elif request.method == "GET":
        id = request.args.get("id")
        return render_template("playlist.html", playlist_id=id)

@app.route("/save/<id>", methods=["POST"])
def save_playlist(id):
    new_tracks = json.loads(request.form["tracks"])

    service = get_service(g.service_name)

    client_config = service.auth_to_config(request.headers.get("X-PandoraAuthToken"))
    service.update_playlist(id, new_tracks, client_config)

    return ""

@app.route("/library/add", methods=["POST"])
def library_add_from_playlist():
    playlist_id = request.form["playlistId"]
    tracks = json.loads(request.form["tracks"])

    service = get_service(g.service_name)

    client_config = service.auth_to_config(request.headers.get("X-PandoraAuthToken"))
    service.add_playlist_tracks_to_library(id, new_tracks, client_config)

    return ""
