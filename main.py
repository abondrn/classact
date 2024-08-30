import os
import json
import argparse
import random

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


def fetch_song_features(sp, song_ids):
    """Fetch song features in bulk and save to individual JSON files."""
    os.makedirs('spotify/features', exist_ok=True)
    for i in tqdm(range(0, len(song_ids), 100), desc="Fetching Song Features"):
        batch = song_ids[i:i + 100]
        features = sp.audio_features(batch)
        for feature in features:
            if feature:
                feature_filepath = f'spotify/features/{feature["id"]}.json'
                save_json(feature_filepath, feature)


def pull(sp):
    """Interactive command to fetch playlists, tracks, artists, and song features."""
    user_playlists = fetch_user_playlists(sp)
    
    # Load existing artist data
    artist_filepath = 'spotify/artists/artists_data.json'
    existing_artist_data = load_json(artist_filepath) if os.path.exists(artist_filepath) else []
    existing_artist_ids = {artist['id'] for artist in existing_artist_data}

    # Process each playlist
    all_unique_artists = set()
    all_song_ids = set()

    for playlist in tqdm(user_playlists, desc="Processing Playlists"):
        unique_artists = fetch_and_save_playlist_tracks(sp, playlist, existing_artist_ids)
        all_unique_artists.update(unique_artists)

        # Collect song IDs for fetching features later
        playlist_filepath = f'spotify/playlists/{playlist["id"]}.json'
        playlist_tracks = load_json(playlist_filepath)
        for track in playlist_tracks:
            if track['track']:
                all_song_ids.add(track['track']['id'])

    # Fetch and save artist data
    fetch_and_save_artist_data(sp, all_unique_artists, artist_filepath)

    # Fetch and save song features
    fetch_song_features(sp, list(all_song_ids))


def refresh(sp):
    """Command to refresh existing playlists and liked songs by fetching new tracks only."""
    # Load existing artist data
    artist_filepath = 'spotify/artists/artists_data.json'
    existing_artist_data = load_json(artist_filepath) if os.path.exists(artist_filepath) else []
    existing_artist_ids = {artist['id'] for artist in existing_artist_data}

    # Refresh all downloaded playlists
    playlist_dir = 'spotify/playlists'
    all_unique_artists = set()
    all_song_ids = set()

    if os.path.exists(playlist_dir):
        for filename in os.listdir(playlist_dir):
            if filename.endswith('.json'):
                playlist_id = filename.replace('.json', '')
                print(f"Refreshing playlist {playlist_id}...")
                playlist_tracks = []
                offset = 0
                while True:
                    response = sp.playlist_tracks(playlist_id, limit=100, offset=offset)
                    tracks = response['items']
                    playlist_tracks.extend(tracks)
                    offset += len(tracks)
                    if len(tracks) == 0:
                        break

                # Save updated playlist tracks
                playlist_filepath = os.path.join(playlist_dir, filename)
                save_json(playlist_filepath, playlist_tracks)

                # Collect unique artist IDs from the tracks
                for track in playlist_tracks:
                    if track['track'] and track['track']['artists']:
                        for artist in track['track']['artists']:
                            if artist['id'] not in existing_artist_ids:
                                all_unique_artists.add(artist['id'])

                # Collect song IDs for fetching features later
                for track in playlist_tracks:
                    if track['track']:
                        all_song_ids.add(track['track']['id'])

    # Fetch and save artist data
    fetch_and_save_artist_data(sp, all_unique_artists, artist_filepath)

    # Fetch and save song features
    fetch_song_features(sp, list(all_song_ids))


def play_song(sp, device_id, song_id):
    """Play a song on a Spotify device."""
    sp.start_playback(device_id=device_id, uris=[f'spotify:track:{song_id}'])


def stop_playback(sp, device_id):
    """Stop playback on the Spotify device."""
    sp.pause_playback(device_id=device_id)


def load_local_playlists():
    """Load playlists stored locally."""
    playlists = []
    playlists_dir = 'spotify/playlists'
    if os.path.exists(playlists_dir):
        for file in os.listdir(playlists_dir):
            if file.endswith('.json'):
                filepath = os.path.join(playlists_dir, file)
                playlists.append(load_json(filepath))
    return playlists


def load_local_liked_songs():
    """Load liked songs stored locally."""
    liked_songs_path = 'spotify/liked_songs.json'
    if os.path.exists(liked_songs_path):
        return load_json(liked_songs_path)
    return []


def tag(sp):
    """Command to play a random liked song and prompt the user to tag it to a playlist."""
    # Ensure user is logged into a Spotify device (like Spotify desktop or mobile app)
    devices = sp.devices()
    if not devices['devices']:
        print("No active Spotify device found. Please open Spotify on one of your devices.")
        return
    device_id = devices['devices'][0]['id']  # Use the first available device

    # Load liked songs and playlists from local storage
    liked_songs = load_local_liked_songs()
    user_playlists = load_local_playlists()

    if not liked_songs:
        print("No liked songs found locally. Please use the 'pull' or 'refresh' command to download them first.")
        return

    if not user_playlists:
        print("No playlists found locally. Please use the 'pull' or 'refresh' command to download them first.")
        return

    print(f"Found {len(liked_songs)} liked songs and {len(user_playlists)} playlists.")

    # Loop to play a random liked song and prompt the user
    while True:
        # Select a random liked song
        random_song = random.choice(liked_songs)
        song_id = random_song['track']['id']
        song_name = random_song['track']['name']
        artist_name = random_song['track']['artists'][0]['name']

        print(f"Playing: {song_name} by {artist_name}")
        play_song(sp, device_id, song_id)

        # Prompt user to tag the song or skip
        print("Available playlists:")
        for idx, playlist in enumerate(user_playlists):
            print(f"{idx + 1}. {playlist['name']}")

        print("Enter the number of the playlist to add the song to, 's' to skip, or 'q' to quit.")
        user_input = input("Your choice: ").strip().lower()

        if user_input == 'q':
            print("Quitting the tagging process.")
            stop_playback(sp, device_id)
            break
        elif user_input == 's':
            print(f"Skipping {song_name}.")
        elif user_input.isdigit() and 1 <= int(user_input) <= len(user_playlists):
            playlist_idx = int(user_input) - 1
            playlist_id = user_playlists[playlist_idx]['id']
            sp.playlist_add_items(playlist_id, [song_id])
            print(f"Added {song_name} to {user_playlists[playlist_idx]['name']}.")
        else:
            print("Invalid input. Please try again.")
        
        # Stop the song after making a decision
        stop_playback(sp, device_id)


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Spotify Playlist and Song Data CLI')
    parser.add_argument('command', choices=['pull', 'refresh', 'tag'], help='Command to execute')
    args = parser.parse_args()

    # Load configuration
    config = load_config('config.yaml')
    CLIENT_ID = config['spotify']['client_id']
    CLIENT_SECRET = config['spotify']['client_secret']
    REDIRECT_URI = config['spotify']['redirect_uri']

    # Authenticate with Spotify
    sp = authenticate_spotify(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI)

    # Execute the chosen command
    if args.command == 'pull':
        pull(sp)
    elif args.command == 'refresh':
        refresh(sp)
    elif args.command == 'tag':
        tag(sp)


if __name__ == '__main__':
    main()