import requests
import logging

class SpotifyClient:
    """Client for interacting with Spotify Web API"""
    
    def __init__(self, access_token):
        self.access_token = access_token
        self.base_url = 'https://api.spotify.com/v1'
        self.headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
    
    def _make_request(self, method, endpoint, **kwargs):
        """Make a request to Spotify API with error handling"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.request(method, url, headers=self.headers, **kwargs)
            
            if response.status_code == 204:  # No content
                return True
            
            if response.status_code in [200, 201]:
                if response.content:
                    try:
                        return response.json()
                    except ValueError:
                        return True
                return True
            
            logging.error(f"Spotify API error: {response.status_code} - {response.text}")
            return None
            
        except requests.RequestException as e:
            logging.error(f"Request failed: {e}")
            return None
    
    def get_user_profile(self):
        """Get current user's profile"""
        return self._make_request('GET', '/me')
    
    def get_user_playlists(self, limit=20):
        """Get current user's playlists"""
        return self._make_request('GET', f'/me/playlists?limit={limit}')
    
    def get_current_track(self):
        """Get currently playing track"""
        return self._make_request('GET', '/me/player/currently-playing')
    
    def get_playback_state(self):
        """Get current playback state"""
        return self._make_request('GET', '/me/player')
    
    def play(self, device_id=None):
        """Resume playback"""
        endpoint = '/me/player/play'
        if device_id:
            endpoint += f'?device_id={device_id}'
        
        result = self._make_request('PUT', endpoint)
        return result is not None
    
    def pause(self, device_id=None):
        """Pause playback"""
        endpoint = '/me/player/pause'
        if device_id:
            endpoint += f'?device_id={device_id}'
        
        result = self._make_request('PUT', endpoint)
        return result is not None
    
    def next_track(self, device_id=None):
        """Skip to next track"""
        endpoint = '/me/player/next'
        if device_id:
            endpoint += f'?device_id={device_id}'
        
        result = self._make_request('POST', endpoint)
        return result is not None
    
    def previous_track(self, device_id=None):
        """Skip to previous track"""
        endpoint = '/me/player/previous'
        if device_id:
            endpoint += f'?device_id={device_id}'
        
        result = self._make_request('POST', endpoint)
        return result is not None
    
    def set_volume(self, volume_percent, device_id=None):
        """Set playback volume (0-100)"""
        endpoint = f'/me/player/volume?volume_percent={volume_percent}'
        if device_id:
            endpoint += f'&device_id={device_id}'
        
        result = self._make_request('PUT', endpoint)
        return result is not None
    
    def get_devices(self):
        """Get available devices"""
        return self._make_request('GET', '/me/player/devices')
    
    def get_playlist_tracks(self, playlist_id, limit=50):
        """Get tracks from a playlist"""
        return self._make_request('GET', f'/playlists/{playlist_id}/tracks?limit={limit}')
    
    def get_recently_played(self, limit=20):
        """Get user's recently played tracks"""
        return self._make_request('GET', f'/me/player/recently-played?limit={limit}')
    
    def get_top_tracks(self, time_range='medium_term', limit=20):
        """Get user's top tracks (short_term, medium_term, long_term)"""
        return self._make_request('GET', f'/me/top/tracks?time_range={time_range}&limit={limit}')
    
    def get_top_artists(self, time_range='medium_term', limit=20):
        """Get user's top artists (short_term, medium_term, long_term)"""
        return self._make_request('GET', f'/me/top/artists?time_range={time_range}&limit={limit}')
    
    def get_saved_tracks(self, limit=20):
        """Get user's saved (liked) tracks"""
        return self._make_request('GET', f'/me/tracks?limit={limit}')
    
    def search_tracks(self, query, limit=1):
        """Search for tracks"""
        from urllib.parse import quote
        encoded_query = quote(query)
        return self._make_request('GET', f'/search?q={encoded_query}&type=track&limit={limit}')
    
    def play_track(self, track_uri, device_id=None):
        """Play a specific track"""
        endpoint = '/me/player/play'
        if device_id:
            endpoint += f'?device_id={device_id}'
        
        data = {'uris': [track_uri]}
        result = self._make_request('PUT', endpoint, json=data)
        return result is not None
    
    def create_playlist(self, name, description="", public=False):
        """Create a new playlist for the user"""
        # First get user profile to get user ID
        profile = self.get_user_profile()
        if not profile:
            return None
        
        user_id = profile['id']
        data = {
            'name': name,
            'description': description,
            'public': public
        }
        
        return self._make_request('POST', f'/users/{user_id}/playlists', json=data)
    
    def add_tracks_to_playlist(self, playlist_id, track_uris):
        """Add tracks to a playlist"""
        data = {
            'uris': track_uris
        }
        
        return self._make_request('POST', f'/playlists/{playlist_id}/tracks', json=data)
