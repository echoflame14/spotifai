"""
Spotify Data Cleaner - Programmatic data cleaning for psychological analysis

This module efficiently strips out irrelevant metadata from Spotify API responses
while preserving only the core data needed for psychological and musical analysis.

Based on analysis of Spotify API structure, this removes ~95% of raw data including:
- IDs, URIs, HREFs (technical identifiers)
- External URLs and links
- Available markets (geographical data)
- Image dimensions and URLs
- Track/disc numbers
- ISRC codes and external IDs
- Preview URLs
- Pagination cursors
- Follower counts and duration data
- Explicit flags and play timestamps
- Device information
- Playlist metadata

Preserves ONLY essential psychological indicators:
- Track/artist/album names
- Genres and popularity scores
- Release dates and album types
- Basic playback state (is_playing, shuffle, repeat)
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Fields to completely remove (exact matches)
REMOVE_FIELDS = {
    'id', 'uri', 'href', 'external_urls', 'external_ids', 'available_markets',
    'disc_number', 'track_number', 'is_local', 'is_playable', 'preview_url',
    'restrictions', 'linked_from', 'snapshot_id', 'collaborative', 'public',
    'width', 'height', 'url',  # Image data
    'total', 'next', 'previous', 'cursors', 'limit', 'offset',  # Pagination
    'followers', 'duration_ms', 'explicit', 'played_at',  # Additional removals per user request
    'device', 'device_name', 'device_type', 'progress_ms', 'volume_percent',  # Device info
    'is_collaborative', 'is_public', 'track_count', 'description'  # Playlist metadata
}

# Field patterns to remove (partial matches)
REMOVE_PATTERNS = [
    'external_urls', 'external_ids', '_id', '_uri', '_href', 
    'image.url', 'image.width', 'image.height',
    'owner.id', 'owner.uri', 'owner.href',
    'context.id', 'context.uri', 'context.href',
    'device.', 'followers.', 'duration_', 'played_at', 'explicit'  # Additional patterns
]

# Essential fields to always keep (for safety) - REDUCED SET
KEEP_FIELDS = {
    'name', 'genres', 'popularity', 'release_date', 'album_type', 'is_playing',
    'shuffle_state', 'repeat_state', 'type', 'album', 'artists', 'artist'
}

def should_remove_field(field_name: str, field_path: str = "") -> bool:
    """
    Determine if a field should be removed based on its name and path
    
    Args:
        field_name: The field name to check
        field_path: The full path to the field (for context)
    
    Returns:
        bool: True if the field should be removed
    """
    # Always keep essential fields
    if field_name in KEEP_FIELDS:
        return False
    
    # Remove exact matches
    if field_name in REMOVE_FIELDS:
        return True
    
    # Remove pattern matches
    full_field = f"{field_path}.{field_name}" if field_path else field_name
    for pattern in REMOVE_PATTERNS:
        if pattern in full_field.lower():
            return True
    
    return False

def clean_dict(data: Dict[str, Any], field_path: str = "") -> Dict[str, Any]:
    """
    Recursively clean a dictionary by removing irrelevant fields
    
    Args:
        data: Dictionary to clean
        field_path: Current field path (for context)
    
    Returns:
        Dict: Cleaned dictionary
    """
    if not isinstance(data, dict):
        return data
    
    cleaned = {}
    
    for key, value in data.items():
        current_path = f"{field_path}.{key}" if field_path else key
        
        # Skip fields that should be removed
        if should_remove_field(key, field_path):
            continue
        
        # Recursively clean nested structures
        if isinstance(value, dict):
            cleaned_value = clean_dict(value, current_path)
            if cleaned_value:  # Only add if not empty
                cleaned[key] = cleaned_value
        elif isinstance(value, list):
            cleaned_value = clean_list(value, current_path)
            if cleaned_value:  # Only add if not empty
                cleaned[key] = cleaned_value
        else:
            # Keep primitive values (strings, numbers, booleans, None)
            cleaned[key] = value
    
    return cleaned

def clean_list(data: List[Any], field_path: str = "") -> List[Any]:
    """
    Clean a list by cleaning each item
    
    Args:
        data: List to clean
        field_path: Current field path (for context)
    
    Returns:
        List: Cleaned list
    """
    if not isinstance(data, list):
        return data
    
    cleaned = []
    
    for item in data:
        if isinstance(item, dict):
            cleaned_item = clean_dict(item, field_path)
            if cleaned_item:  # Only add if not empty
                cleaned.append(cleaned_item)
        elif isinstance(item, list):
            cleaned_item = clean_list(item, field_path)
            if cleaned_item:  # Only add if not empty
                cleaned.append(cleaned_item)
        else:
            # Keep primitive values
            cleaned.append(item)
    
    return cleaned

def clean_spotify_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main function to clean comprehensive Spotify data
    
    Args:
        raw_data: Raw Spotify API response data
    
    Returns:
        Dict: Cleaned data with only psychologically relevant information
    """
    logger.info("Starting programmatic Spotify data cleaning...")
    
    if not raw_data:
        logger.warning("No data provided for cleaning")
        return {}
    
    # Calculate original size
    import json
    original_size = len(json.dumps(raw_data, default=str))
    
    # Clean the data
    cleaned_data = clean_dict(raw_data)
    
    # Calculate cleaned size
    cleaned_size = len(json.dumps(cleaned_data, default=str))
    
    # Log size reduction
    reduction_percent = ((original_size - cleaned_size) / original_size) * 100 if original_size > 0 else 0
    
    logger.info(f"Data cleaning complete:")
    logger.info(f"  Original size: {original_size:,} characters")
    logger.info(f"  Cleaned size: {cleaned_size:,} characters")
    logger.info(f"  Reduction: {reduction_percent:.1f}% ({original_size - cleaned_size:,} characters removed)")
    
    return cleaned_data

def clean_current_track(current_track: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Clean current track data specifically"""
    if not current_track:
        return None
    
    return clean_dict(current_track)

def clean_recent_tracks(recent_tracks: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Clean recent tracks data specifically"""
    if not recent_tracks:
        return None
    
    return clean_dict(recent_tracks)

def clean_top_artists(top_artists: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Clean top artists data specifically"""
    if not top_artists:
        return None
    
    return clean_dict(top_artists)

def clean_top_tracks(top_tracks: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Clean top tracks data specifically"""
    if not top_tracks:
        return None
    
    return clean_dict(top_tracks)

def clean_saved_tracks(saved_tracks: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Clean saved tracks data specifically"""
    if not saved_tracks:
        return None
    
    return clean_dict(saved_tracks)

def clean_playlists(playlists: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Clean playlists data specifically"""
    if not playlists:
        return None
    
    return clean_dict(playlists)

def extract_essential_music_context(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract a minimal, essential music context for psychological analysis
    
    This creates an even more focused dataset than the general cleaning,
    specifically for psychological analysis prompts.
    
    Args:
        raw_data: Raw Spotify data
    
    Returns:
        Dict: Minimal essential context
    """
    logger.info("Extracting essential music context for psychological analysis...")
    
    # First clean the data
    cleaned_data = clean_spotify_data(raw_data)
    
    # Then extract the most essential elements
    essential_context = {}
    
    # Current listening context
    if 'current_playback' in cleaned_data:
        current = cleaned_data['current_playback']
        essential_context['current_listening'] = {
            'is_playing': current.get('current_track', {}).get('is_playing', False),
            'track_name': None,
            'artist_name': None,
            'album_name': None
        }
        
        # Extract current track info
        if current.get('current_track', {}).get('item'):
            track = current['current_track']['item']
            essential_context['current_listening']['track_name'] = track.get('name')
            essential_context['current_listening']['album_name'] = track.get('album', {}).get('name')
            if track.get('artists') and len(track['artists']) > 0:
                essential_context['current_listening']['artist_name'] = track['artists'][0].get('name')
    
    # Recent tracks summary
    if 'recent_tracks' in cleaned_data and 'items' in cleaned_data['recent_tracks']:
        recent_items = cleaned_data['recent_tracks']['items'][:10]  # Limit to 10 most recent
        essential_context['recent_tracks'] = []
        
        for item in recent_items:
            track = item.get('track', {})
            if track.get('name'):
                track_summary = {
                    'name': track.get('name'),
                    'artist': track.get('artists', [{}])[0].get('name') if track.get('artists') else None,
                    'album': track.get('album', {}).get('name')
                }
                essential_context['recent_tracks'].append(track_summary)
    
    # Top artists summary (combine all time ranges)
    essential_context['top_artists'] = []
    for time_range in ['short_term', 'medium_term', 'long_term']:
        if f'top_artists' in cleaned_data and time_range in cleaned_data['top_artists']:
            artists = cleaned_data['top_artists'][time_range].get('items', [])[:8]  # Top 8 per range
            for artist in artists:
                if artist.get('name'):
                    artist_summary = {
                        'name': artist.get('name'),
                        'genres': artist.get('genres', [])[:5],  # Top 5 genres
                        'popularity': artist.get('popularity'),
                        'time_range': time_range
                    }
                    essential_context['top_artists'].append(artist_summary)
    
    # Top tracks summary
    essential_context['top_tracks'] = []
    for time_range in ['short_term', 'medium_term', 'long_term']:
        if 'top_tracks' in cleaned_data and time_range in cleaned_data['top_tracks']:
            tracks = cleaned_data['top_tracks'][time_range].get('items', [])[:8]  # Top 8 per range
            for track in tracks:
                if track.get('name'):
                    track_summary = {
                        'name': track.get('name'),
                        'artist': track.get('artists', [{}])[0].get('name') if track.get('artists') else None,
                        'album': track.get('album', {}).get('name'),
                        'popularity': track.get('popularity'),
                        'time_range': time_range
                    }
                    essential_context['top_tracks'].append(track_summary)
    
    # Calculate size reduction for essential context
    import json
    original_size = len(json.dumps(raw_data, default=str))
    essential_size = len(json.dumps(essential_context, default=str))
    reduction_percent = ((original_size - essential_size) / original_size) * 100 if original_size > 0 else 0
    
    logger.info(f"Essential context extraction complete:")
    logger.info(f"  Original size: {original_size:,} characters")
    logger.info(f"  Essential size: {essential_size:,} characters")
    logger.info(f"  Reduction: {reduction_percent:.1f}% ({original_size - essential_size:,} characters removed)")
    
    return essential_context 