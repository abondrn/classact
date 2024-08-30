import os
import json

import yaml
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from tqdm import tqdm


def load_config(filepath='config.yaml'):
    """Load the YAML configuration file."""
    with open(filepath, 'r') as file:
        return yaml.safe_load(file)


def save_json(filepath, data):
    """Save data to a JSON file."""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)


def load_json(filepath):
    """Load data from a JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def authenticate_spotify(client_id, client_secret, redirect_uri, scope='playlist-read-private'):
    """Authenticate the user with Spotify using OAuth."""
    return spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=client_id,
                                                     client_secret=client_secret,
                                                     redirect_uri=redirect_uri,
                                                     scope=scope))


def fetch_user_playlists(sp):
    """Fetch all playlists created by the user."""
    user_id = sp.current_user()["id"]
    playlists = []
    offset = 0
    while True:
        response = sp.current_user_playlists(limit=50, offset=offset)
        playlists.extend(response['items'])
        offset += len(response['items'])
        if len(response['items']) == 0:
            break
    # Filter playlists that are owned by the user
    return [playlist for playlist in playlists if playlist['owner']['id'] == user_id]


def confirm_prompt(prompt_text):
    """Prompt the user with a yes/no question and handle different variations of input."""
    yes_responses = {"yes", "y", "ye", "yeah", "yep", "sure", "ok", "okay"}
    no_responses = {"no", "n", "nah", "nope", "cancel"}
    
    while True:
        response = input(f"{prompt_text} (yes/no): ").strip().lower()
        if response in yes_responses:
            return True
        elif response in no_responses:
            return False
        else:
            print("Please respond with 'yes' or 'no'.")


def fetch_and_save_playlist_tracks(sp, playlist, existing_artist_ids):
    """Fetch tracks from a playlist and save them to a JSON file."""
    playlist_id = playlist['id']
    playlist_name = playlist['name']

    if not confirm_prompt(f"Do you want to download the playlist '{playlist_name}'?"):
        print(f"Skipping playlist '{playlist_name}'")
        return set()

    playlist_tracks = []
    offset = 0
    while True:
        response = sp.playlist_tracks(playlist_id, limit=100, offset=offset)
        tracks = response['items']
        playlist_tracks.extend(tracks)
        offset += len(tracks)
        if len(tracks) == 0:
            break

    # Save tracks to a local JSON file
    os.makedirs('spotify/playlists', exist_ok=True)
    playlist_filepath = f'spotify/playlists/{playlist_id}.json'
    save_json(playlist_filepath, playlist_tracks)

    # Collect unique artist IDs from the tracks
    unique_artists = set()
    for track in playlist_tracks:
        if track['track'] and track['track']['artists']:
            for artist in track['track']['artists']:
                if artist['id'] not in existing_artist_ids:
                    unique_artists.add(artist['id'])
    return unique_artists


def fetch_and_save_artist_data(sp, unique_artists, artist_filepath):
    """Fetch artist data in bulk and save to a JSON file."""
    artist_data = load_json(artist_filepath) if os.path.exists(artist_filepath) else []
    existing_artist_ids = {artist['id'] for artist in artist_data}

    new_artist_ids = unique_artists - existing_artist_ids
    new_artist_data = []

    # Spotify API limits bulk artist lookup to 50 at a time
    for i in tqdm(range(0, len(new_artist_ids), 50), desc="Fetching Artist Data"):
        batch = list(new_artist_ids)[i:i + 50]
        response = sp.artists(batch)
        new_artist_data.extend(response['artists'])

    # Append new data and save
    artist_data.extend(new_artist_data)
    os.makedirs('spotify/artists', exist_ok=True)
    save_json(artist_filepath, artist_data)


def main():
    # Load configuration
    config = load_config('config.yaml')
    CLIENT_ID = config['spotify']['client_id']
    CLIENT_SECRET = config['spotify']['client_secret']
    REDIRECT_URI = config['spotify']['redirect_uri']

    # Authenticate with Spotify
    sp = authenticate_spotify(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI)

    # Fetch user's playlists
    user_playlists = fetch_user_playlists(sp)

    # Load existing artist data
    artist_filepath = 'spotify/artists/artists_data.json'
    existing_artist_data = load_json(artist_filepath) if os.path.exists(artist_filepath) else []
    existing_artist_ids = {artist['id'] for artist in existing_artist_data}

    # Process each playlist
    all_unique_artists = set()
    for playlist in tqdm(user_playlists, desc="Processing Playlists"):
        unique_artists = fetch_and_save_playlist_tracks(sp, playlist, existing_artist_ids)
        all_unique_artists.update(unique_artists)

    # Fetch and save artist data
    fetch_and_save_artist_data(sp, all_unique_artists, artist_filepath)

    print(f"Data saved for {len(user_playlists)} playlists and {len(all_unique_artists)} unique artists.")


if __name__ == '__main__':
    main()