#!/usr/bin/env python3
"""
Test script to collect comprehensive Spotify data for analysis
This will help us understand the data structure and determine what to keep/remove
"""

import json
import os
import sys
from datetime import datetime

# Add the project directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from spotify_client import SpotifyClient
from models import User
from app import app, db

def collect_comprehensive_spotify_data(user_access_token):
    """Collect all Spotify data we use in the app"""
    
    spotify_client = SpotifyClient(user_access_token)
    
    print("🎵 Collecting comprehensive Spotify data...")
    
    data = {
        'collection_timestamp': datetime.utcnow().isoformat(),
        'collection_purpose': 'Analyze data structure to determine what data is relevant for psychological analysis',
        'endpoints_tested': []
    }
    
    # 1. Current playback state
    print("📱 Getting current playback state...")
    try:
        current_track = spotify_client.get_current_track()
        playback_state = spotify_client.get_playback_state()
        data['current_playback'] = {
            'current_track': current_track,
            'playback_state': playback_state
        }
        data['endpoints_tested'].append('current_track')
        data['endpoints_tested'].append('playback_state')
        print(f"   ✅ Current track: {'Playing' if current_track else 'Not playing'}")
    except Exception as e:
        print(f"   ❌ Error getting current playback: {e}")
        data['current_playback'] = {'error': str(e)}
    
    # 2. Recently played tracks
    print("🕒 Getting recently played tracks...")
    try:
        recent_tracks = spotify_client.get_recently_played(limit=50)
        data['recent_tracks'] = recent_tracks
        data['endpoints_tested'].append('recently_played')
        track_count = len(recent_tracks.get('items', [])) if recent_tracks else 0
        print(f"   ✅ Found {track_count} recent tracks")
    except Exception as e:
        print(f"   ❌ Error getting recent tracks: {e}")
        data['recent_tracks'] = {'error': str(e)}
    
    # 3. Top artists (all time ranges)
    print("🎤 Getting top artists...")
    data['top_artists'] = {}
    for time_range in ['short_term', 'medium_term', 'long_term']:
        try:
            top_artists = spotify_client.get_top_artists(time_range=time_range, limit=50)
            data['top_artists'][time_range] = top_artists
            artist_count = len(top_artists.get('items', [])) if top_artists else 0
            print(f"   ✅ {time_range}: {artist_count} artists")
        except Exception as e:
            print(f"   ❌ Error getting {time_range} artists: {e}")
            data['top_artists'][time_range] = {'error': str(e)}
    data['endpoints_tested'].append('top_artists')
    
    # 4. Top tracks (all time ranges)
    print("🎵 Getting top tracks...")
    data['top_tracks'] = {}
    for time_range in ['short_term', 'medium_term', 'long_term']:
        try:
            top_tracks = spotify_client.get_top_tracks(time_range=time_range, limit=50)
            data['top_tracks'][time_range] = top_tracks
            track_count = len(top_tracks.get('items', [])) if top_tracks else 0
            print(f"   ✅ {time_range}: {track_count} tracks")
        except Exception as e:
            print(f"   ❌ Error getting {time_range} tracks: {e}")
            data['top_tracks'][time_range] = {'error': str(e)}
    data['endpoints_tested'].append('top_tracks')
    
    # 5. Saved tracks (liked songs)
    print("❤️ Getting saved tracks...")
    try:
        saved_tracks = spotify_client.get_saved_tracks(limit=50)
        data['saved_tracks'] = saved_tracks
        data['endpoints_tested'].append('saved_tracks')
        track_count = len(saved_tracks.get('items', [])) if saved_tracks else 0
        print(f"   ✅ Found {track_count} saved tracks")
    except Exception as e:
        print(f"   ❌ Error getting saved tracks: {e}")
        data['saved_tracks'] = {'error': str(e)}
    
    # 6. User playlists
    print("📋 Getting user playlists...")
    try:
        user_playlists = spotify_client.get_user_playlists(limit=50)
        data['user_playlists'] = user_playlists
        data['endpoints_tested'].append('user_playlists')
        playlist_count = len(user_playlists.get('items', [])) if user_playlists else 0
        print(f"   ✅ Found {playlist_count} playlists")
    except Exception as e:
        print(f"   ❌ Error getting playlists: {e}")
        data['user_playlists'] = {'error': str(e)}
    
    # 7. Available devices
    print("📱 Getting available devices...")
    try:
        devices = spotify_client.get_devices()
        data['devices'] = devices
        data['endpoints_tested'].append('devices')
        device_count = len(devices.get('devices', [])) if devices else 0
        print(f"   ✅ Found {device_count} devices")
    except Exception as e:
        print(f"   ❌ Error getting devices: {e}")
        data['devices'] = {'error': str(e)}
    
    # 8. User profile
    print("👤 Getting user profile...")
    try:
        user_profile = spotify_client.get_user_profile()
        data['user_profile'] = user_profile
        data['endpoints_tested'].append('user_profile')
        print(f"   ✅ User: {user_profile.get('display_name', 'Unknown') if user_profile else 'Error'}")
    except Exception as e:
        print(f"   ❌ Error getting user profile: {e}")
        data['user_profile'] = {'error': str(e)}
    
    print(f"\n🔍 Total endpoints tested: {len(set(data['endpoints_tested']))}")
    return data

def analyze_data_structure(data):
    """Analyze the collected data to understand its structure"""
    
    print("\n📊 ANALYZING DATA STRUCTURE...")
    
    analysis = {
        'analysis_timestamp': datetime.utcnow().isoformat(),
        'total_endpoints': len(set(data.get('endpoints_tested', []))),
        'data_size_analysis': {},
        'field_frequency': {},
        'potentially_irrelevant_fields': [],
        'essential_fields': []
    }
    
    # Calculate data sizes
    total_size = len(json.dumps(data, indent=2))
    analysis['data_size_analysis']['total_characters'] = total_size
    analysis['data_size_analysis']['total_mb'] = round(total_size / (1024 * 1024), 3)
    
    print(f"📏 Total data size: {total_size:,} characters ({analysis['data_size_analysis']['total_mb']} MB)")
    
    # Analyze field frequency across all data
    def count_fields(obj, prefix=""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                field_name = f"{prefix}.{key}" if prefix else key
                analysis['field_frequency'][field_name] = analysis['field_frequency'].get(field_name, 0) + 1
                count_fields(value, field_name)
        elif isinstance(obj, list) and obj:
            count_fields(obj[0], prefix)  # Analyze first item as representative
    
    count_fields(data)
    
    # Identify potentially irrelevant fields
    irrelevant_patterns = [
        'id', 'uri', 'href', 'external_urls', 'external_ids', 
        'available_markets', 'disc_number', 'track_number',
        'is_local', 'is_playable', 'preview_url', 'restrictions',
        'linked_from', 'album.id', 'album.uri', 'album.href',
        'artist.id', 'artist.uri', 'artist.href', 'images.url',
        'images.width', 'images.height', 'owner.id', 'owner.uri',
        'collaborative', 'public', 'snapshot_id', 'tracks.href',
        'tracks.total'
    ]
    
    for field in analysis['field_frequency']:
        for pattern in irrelevant_patterns:
            if pattern in field.lower():
                analysis['potentially_irrelevant_fields'].append(field)
                break
    
    # Identify essential fields for psychological analysis
    essential_patterns = [
        'name', 'genres', 'popularity', 'followers.total', 'duration_ms',
        'explicit', 'release_date', 'album_type', 'artist', 'album.name',
        'played_at', 'is_playing', 'progress_ms', 'shuffle_state',
        'repeat_state', 'volume_percent', 'device.name', 'device.type'
    ]
    
    for field in analysis['field_frequency']:
        for pattern in essential_patterns:
            if pattern in field.lower() and field not in analysis['potentially_irrelevant_fields']:
                analysis['essential_fields'].append(field)
                break
    
    print(f"🔍 Total unique fields found: {len(analysis['field_frequency'])}")
    print(f"❌ Potentially irrelevant fields: {len(analysis['potentially_irrelevant_fields'])}")
    print(f"✅ Essential fields: {len(analysis['essential_fields'])}")
    
    return analysis

def main():
    """Main function to run the data collection and analysis"""
    
    print("🚀 SPOTIFY DATA COLLECTION & ANALYSIS")
    print("=" * 50)
    
    # Check if we have a user token to test with
    # You'll need to manually set this or get it from the database
    with app.app_context():
        # Try to get the first user from the database
        user = User.query.first()
        
        if not user or not user.access_token:
            print("❌ No user with access token found in database.")
            print("💡 Please log in through the web interface first, then run this script.")
            return
        
        print(f"👤 Testing with user: {user.display_name or user.id}")
        
        # Collect comprehensive data
        spotify_data = collect_comprehensive_spotify_data(user.access_token)
        
        # Analyze the data structure
        analysis = analyze_data_structure(spotify_data)
        
        # Write full data to file
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        data_filename = f"spotify_data_full_{timestamp}.json"
        with open(data_filename, 'w') as f:
            json.dump(spotify_data, f, indent=2, default=str)
        print(f"\n💾 Full data written to: {data_filename}")
        
        # Write analysis to file
        analysis_filename = f"spotify_data_analysis_{timestamp}.json"
        with open(analysis_filename, 'w') as f:
            json.dump(analysis, f, indent=2, default=str)
        print(f"📊 Analysis written to: {analysis_filename}")
        
        # Write summary
        summary_filename = f"spotify_data_summary_{timestamp}.txt"
        with open(summary_filename, 'w') as f:
            f.write("SPOTIFY DATA COLLECTION SUMMARY\n")
            f.write("=" * 40 + "\n\n")
            f.write(f"Collection Time: {spotify_data['collection_timestamp']}\n")
            f.write(f"Total Endpoints: {len(set(spotify_data.get('endpoints_tested', [])))}\n")
            f.write(f"Data Size: {analysis['data_size_analysis']['total_characters']:,} characters\n")
            f.write(f"Data Size: {analysis['data_size_analysis']['total_mb']} MB\n\n")
            
            f.write("POTENTIALLY IRRELEVANT FIELDS:\n")
            f.write("-" * 30 + "\n")
            for field in sorted(analysis['potentially_irrelevant_fields']):
                f.write(f"- {field}\n")
            
            f.write(f"\nESSENTIAL FIELDS:\n")
            f.write("-" * 30 + "\n")
            for field in sorted(analysis['essential_fields']):
                f.write(f"+ {field}\n")
            
            f.write(f"\nFIELD FREQUENCY (TOP 20):\n")
            f.write("-" * 30 + "\n")
            sorted_fields = sorted(analysis['field_frequency'].items(), key=lambda x: x[1], reverse=True)
            for field, count in sorted_fields[:20]:
                f.write(f"{count:3d}x {field}\n")
        
        print(f"📝 Summary written to: {summary_filename}")
        
        print("\n✅ COLLECTION COMPLETE!")
        print(f"📁 Files created:")
        print(f"   • {data_filename} - Full raw data")
        print(f"   • {analysis_filename} - Structural analysis")
        print(f"   • {summary_filename} - Human-readable summary")
        print(f"\n💡 Next steps:")
        print(f"   1. Review the summary file to understand data structure")
        print(f"   2. Use insights to create programmatic data cleaning")
        print(f"   3. Replace LLM cleaning with efficient programmatic cleaning")

if __name__ == "__main__":
    main() 