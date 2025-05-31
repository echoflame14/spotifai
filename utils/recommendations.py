"""
AI recommendation utilities.

This module handles AI recommendation generation and duplicate prevention.
"""

import json
import time
from datetime import datetime, timedelta
from flask import session
from models import Recommendation, UserAnalysis, db
from spotify_client import SpotifyClient
from utils.ai_analysis import configure_gemini, log_llm_timing
from structured_llm import structured_llm
import google.generativeai as genai
import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

def normalize_artist_name(name: str) -> str:
    """Normalize artist names for better matching"""
    if not name:
        return ""
    
    # Common normalizations
    normalized = name.strip().lower()
    normalized = normalized.replace("&", "and")
    normalized = normalized.replace("feat.", "featuring")
    normalized = normalized.replace("ft.", "featuring")
    normalized = normalized.replace("'", "")
    normalized = normalized.replace('"', "")
    
    return normalized

def validate_track_match(requested_song: str, requested_artist: str, 
                        selected_song: str, selected_artist: str) -> dict:
    """Validate how well the selected track matches the requested one"""
    
    song_similarity = SequenceMatcher(None, 
                                    requested_song.lower().strip(), 
                                    selected_song.lower().strip()).ratio()
    
    artist_similarity = SequenceMatcher(None, 
                                      normalize_artist_name(requested_artist), 
                                      normalize_artist_name(selected_artist)).ratio()
    
    # Calculate overall match quality
    overall_score = (song_similarity * 0.4) + (artist_similarity * 0.6)
    
    return {
        'song_similarity': song_similarity,
        'artist_similarity': artist_similarity,
        'overall_score': overall_score,
        'is_good_match': overall_score > 0.7,
        'is_acceptable_match': overall_score > 0.5,
        'artist_mismatch_warning': artist_similarity < 0.6
    }

def get_enhanced_recent_recommendations(user, hours_back=24, include_artist_counts=True):
    """
    Get enhanced recent recommendations with better formatting and artist frequency tracking
    """
    # Get ALL recent recommendations within the time period, not just 15
    recent_recs = user.get_recent_recommendations(hours_back=hours_back, limit=None)
    
    if not recent_recs:
        return {
            'formatted_list': [],
            'artist_frequency': {},
            'total_count': 0,
            'warning_message': "",
            'blacklist_tracks': []
        }
    
    # Count artist frequency for diversity warnings - get ALL recommendations in 72 hours
    artist_frequency = {}
    if include_artist_counts:
        # Get ALL recommendations in the last 72 hours for accurate artist frequency counting
        all_recent_recs = user.get_recent_recommendations(hours_back=72, limit=None)
        logger.info(f"DUPLICATE PREVENTION: Analyzing {len(all_recent_recs)} total recommendations from last 72 hours")
        
        for rec in all_recent_recs:
            artist_lower = rec.artist_name.lower().strip()
            artist_frequency[artist_lower] = artist_frequency.get(artist_lower, 0) + 1
    
    # Get the actual total count of recommendations in the specified time period
    total_count = len(recent_recs)
    
    # For display purposes, limit to the most recent 15 for the formatted list
    # but keep the accurate total count for warnings
    display_recs = recent_recs[:15] if len(recent_recs) > 15 else recent_recs
    
    # Generate warning message based on the ACTUAL total count
    warning_message = ""
    if total_count >= 10:
        warning_message = f"User has received {total_count} recommendations in the last {hours_back} hours. Prioritize diversity and avoid repetition."
    elif total_count >= 5:
        warning_message = f"User has {total_count} recent recommendations. Ensure variety in your suggestion."
    
    # Create explicit track blacklist for the AI prompt
    blacklist_tracks = []
    
    # Get ALL recent recommendations for comprehensive blacklist (not just display_recs)
    for rec in recent_recs:
        # Add track to blacklist
        blacklist_tracks.append(f'"{rec.track_name}" by {rec.artist_name}')
    
    logger.info(f"DUPLICATE PREVENTION: Found {total_count} recommendations in last {hours_back}h, showing {len(display_recs)} in prompt")
    logger.info(f"DUPLICATE PREVENTION: Created blacklist with {len(blacklist_tracks)} tracks")
    
    return {
        'formatted_list': display_recs,  # Limited for prompt display
        'artist_frequency': artist_frequency,
        'total_count': total_count,  # Accurate total count
        'warning_message': warning_message,
        'blacklist_tracks': blacklist_tracks  # Explicit track blacklist only
    }

@log_llm_timing("ai_recommendation")
def generate_ai_recommendation(user, gemini_api_key, session_adjustment=""):
    """Generate AI recommendation for user with comprehensive analysis"""
    try:
        # Collect music data
        logger.info("ENHANCED: Starting ultra-comprehensive AI recommendation...")
        data_collection_start = time.time()
        
        spotify_client = SpotifyClient(user.access_token)
        
        try:
            # Get user's current music context with enhanced data
            current_track = spotify_client.get_current_track()
            playback_state = spotify_client.get_playback_state()
            
            # ENHANCED: Get maximum recent tracks (50 is Spotify API limit)
            recent_tracks = spotify_client.get_recently_played(limit=50)
            
            # ENHANCED: Get comprehensive top data for all time ranges
            top_artists_short = spotify_client.get_top_artists(time_range='short_term', limit=50)
            top_artists_medium = spotify_client.get_top_artists(time_range='medium_term', limit=50) 
            top_artists_long = spotify_client.get_top_artists(time_range='long_term', limit=50)
            top_tracks_short = spotify_client.get_top_tracks(time_range='short_term', limit=50)
            top_tracks_medium = spotify_client.get_top_tracks(time_range='medium_term', limit=50)
            top_tracks_long = spotify_client.get_top_tracks(time_range='long_term', limit=50)
            
            # ENHANCED: Get more saved tracks and user library data
            saved_tracks = spotify_client.get_saved_tracks(limit=50)
            user_playlists = spotify_client.get_user_playlists(limit=50)
            
            # ENHANCED: Get audio features for analysis (with enhanced error handling and batching)
            try:
                if recent_tracks and recent_tracks.get('items'):
                    track_ids_for_features = [item['track']['id'] for item in recent_tracks['items'][:30] if item.get('track', {}).get('id')]
                else:
                    track_ids_for_features = []
                
                if top_tracks_short or top_tracks_medium or top_tracks_long:
                    track_ids_for_features.extend([track['id'] for tracks_data in [top_tracks_short, top_tracks_medium, top_tracks_long] for track in tracks_data.get('items', [])[:15] if track.get('id')])
                
                # Remove duplicates while preserving order
                seen = set()
                unique_track_ids = []
                for track_id in track_ids_for_features:
                    if track_id not in seen:
                        seen.add(track_id)
                        unique_track_ids.append(track_id)
                
                if unique_track_ids:
                    logger.info(f"ENHANCED: Getting audio features for {len(unique_track_ids)} tracks")
                    
                    # Split into smaller batches to avoid quota issues
                    batch_size = 50  # Reduced from 100 to be more conservative
                    audio_features_data = {}
                    
                    for i in range(0, len(unique_track_ids), batch_size):
                        batch_ids = unique_track_ids[i:i + batch_size]
                        logger.info(f"ENHANCED: Processing audio features batch {i//batch_size + 1}/{(len(unique_track_ids) + batch_size - 1)//batch_size} ({len(batch_ids)} tracks)")
                        
                        try:
                            audio_features_response = spotify_client.get_audio_features(batch_ids)
                            
                            if audio_features_response and audio_features_response.get('audio_features'):
                                for j, features in enumerate(audio_features_response['audio_features']):
                                    if features and (i + j) < len(unique_track_ids):
                                        audio_features_data[unique_track_ids[i + j]] = features
                                logger.info(f"ENHANCED: Successfully retrieved audio features for batch ({len([f for f in audio_features_response['audio_features'] if f])} valid features)")
                            else:
                                logger.warning(f"ENHANCED: No audio features returned for batch {i//batch_size + 1}")
                                
                            # Add small delay between batches to respect rate limits
                            if i + batch_size < len(unique_track_ids):
                                time.sleep(0.1)
                                
                        except Exception as batch_error:
                            logger.warning(f"ENHANCED: Audio features batch {i//batch_size + 1} failed: {batch_error}")
                            if "403" in str(batch_error) or "Forbidden" in str(batch_error):
                                logger.warning("ENHANCED: 403 error suggests quota limitations or development mode restrictions")
                                break  # Stop trying if we hit 403 errors
                            continue  # Try next batch for other errors
                            
                    if audio_features_data:
                        logger.info(f"ENHANCED: Successfully retrieved audio features for {len(audio_features_data)} total tracks")
                    else:
                        logger.warning("ENHANCED: No audio features retrieved - continuing without audio analysis")
                    
            except Exception as e:
                logger.warning(f"ENHANCED: Audio features unavailable: {e}")
                if "403" in str(e) or "Forbidden" in str(e):
                    logger.warning("ENHANCED: This may be due to Spotify app quota limitations or development mode restrictions")
                    logger.info("ENHANCED: Consider applying for extended Web API access if you need audio features for production use")
                logger.info("ENHANCED: Continuing without audio features - recommendations will use genre and artist analysis instead")
                audio_features_data = {}
            
            # Extract comprehensive genres from all artists
            all_artists = []
            for artists_data in [top_artists_short, top_artists_medium, top_artists_long]:
                all_artists.extend(artists_data.get('items', []))
            
            # Get unique genres with frequency counting
            genre_frequency = {}
            for artist in all_artists:
                for genre in artist.get('genres', []):
                    genre_frequency[genre] = genre_frequency.get(genre, 0) + 1
            
            # Sort genres by frequency
            top_genres = sorted(genre_frequency.items(), key=lambda x: x[1], reverse=True)
            
            # ENHANCED: Analyze listening patterns and behavior
            listening_patterns = analyze_listening_patterns(recent_tracks, current_track, playback_state)
            
            # ENHANCED: Create comprehensive music data structure
            music_data = {
                'current_track': current_track,
                'playback_state': playback_state,
                'recent_tracks': recent_tracks.get('items', []),
                'recent_tracks_count': len(recent_tracks.get('items', [])),
                'top_artists': {
                    'short_term': top_artists_short.get('items', []),
                    'medium_term': top_artists_medium.get('items', []),
                    'long_term': top_artists_long.get('items', [])
                },
                'top_tracks': {
                    'short_term': top_tracks_short.get('items', []),
                    'medium_term': top_tracks_medium.get('items', []),
                    'long_term': top_tracks_long.get('items', [])
                },
                'saved_tracks': saved_tracks.get('items', []),
                'saved_tracks_count': saved_tracks.get('total', 0),
                'user_playlists': user_playlists.get('items', []),
                'playlist_count': user_playlists.get('total', 0),
                'top_genres': [genre for genre, count in top_genres[:25]],  # Top 25 genres
                'genre_frequency': dict(top_genres[:25]),
                'audio_features': audio_features_data,
                'listening_patterns': listening_patterns
            }
            
        except Exception as e:
            logger.warning(f"Error collecting enhanced music data: {e}")
            # Fallback to basic data
            music_data = {
                'current_track': None,
                'recent_tracks': [],
                'recent_tracks_count': 0,
                'top_artists': {'short_term': [], 'medium_term': [], 'long_term': []},
                'top_tracks': {'short_term': [], 'medium_term': [], 'long_term': []},
                'saved_tracks': [],
                'saved_tracks_count': 0,
                'user_playlists': [],
                'playlist_count': 0,
                'top_genres': [],
                'genre_frequency': {},
                'audio_features': {},
                'listening_patterns': {}
            }
        
        data_collection_duration = time.time() - data_collection_start
        logger.info(f"ENHANCED: Comprehensive data collection complete - {data_collection_duration:.2f}s")
        
        # Get enhanced recent recommendations to avoid duplicates
        rec_tracking = get_enhanced_recent_recommendations(user, hours_back=24)
        blacklist_tracks = rec_tracking['blacklist_tracks']
        diversity_warning = rec_tracking['warning_message']
        
        logger.info(f"ENHANCED: Found {rec_tracking['total_count']} recent recommendations for duplicate prevention")
        
        # CHECK FOR COMPREHENSIVE MUSIC TASTE ANALYSIS FIRST - NOW FROM DATABASE
        cached_analysis = UserAnalysis.get_latest_analysis(user.id, 'psychological', max_age_hours=24)
        
        psychological_profile = None
        if cached_analysis and cached_analysis.is_recent(hours=24):
            logger.info("ENHANCED: Using comprehensive psychological analysis from database for recommendations")
            
            # Handle both string (JSON) and dict formats for analysis_data
            analysis_data = cached_analysis.analysis_data
            if isinstance(analysis_data, str):
                try:
                    analysis_data = json.loads(analysis_data)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("ENHANCED: Failed to parse cached analysis data as JSON")
                    analysis_data = {}
            
            psychological_profile = analysis_data.get('comprehensive_analysis', 
                                   analysis_data.get('analysis', 'No comprehensive analysis available'))
            
            print("\n" + "="*80)
            print("RECOMMENDATIONS - USING CACHED PSYCHOLOGICAL ANALYSIS:")
            print("="*80)
            print(f"Analysis created: {cached_analysis.created_at}")
            print(f"Analysis ready: {cached_analysis.analysis_ready}")
            print(f"Core personality preview: {str(psychological_profile)[:200]}...")
            print("="*80 + "\n")
            
        else:
            # Check for basic psychological analysis as fallback  
            cached_psych_analysis = UserAnalysis.get_latest_analysis(user.id, 'basic_psychological', max_age_hours=48)
            psych_cache_valid = cached_psych_analysis and cached_psych_analysis.is_recent(hours=48)
            
            if cached_psych_analysis and psych_cache_valid:
                logger.info("ENHANCED: Using cached basic psychological analysis")
                psychological_profile = cached_psych_analysis.analysis_data.get('profile', 'Basic psychological profile not available')
            else:
                logger.info("ENHANCED: No valid cached analysis, generating enhanced basic profile...")
                # Generate enhanced psychological profile for recommendations
                profile_start = time.time()
                
                # Configure Gemini
                configure_gemini(gemini_api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                # ENHANCED: Create much more comprehensive profile prompt
                profile_prompt = create_enhanced_psychological_profile_prompt(music_data)
                
                # LOG THE ENHANCED PSYCHOLOGICAL PROFILE PROMPT
                print("\n" + "="*80)
                print("RECOMMENDATIONS - ENHANCED PSYCHOLOGICAL PROFILE PROMPT SENT TO GEMINI:")
                print("="*80)
                print(profile_prompt)
                print("="*80 + "\n")
                
                try:
                    response = model.generate_content(profile_prompt)
                    psychological_profile = response.text.strip()
                    
                    print("\n" + "="*80)
                    print("RECOMMENDATIONS - ENHANCED PSYCHOLOGICAL PROFILE RESPONSE FROM GEMINI:")
                    print("="*80)
                    print(psychological_profile)
                    print("="*80 + "\n")
                    
                    profile_duration = time.time() - profile_start
                    logger.info(f"ENHANCED: Generated enhanced psychological profile in {profile_duration:.2f}s")
                    
                    # Save enhanced profile to database for future use
                    try:
                        enhanced_profile_analysis = UserAnalysis(
                            user_id=user.id,
                            analysis_type='enhanced_psychological',
                            analysis_data={'profile': psychological_profile},
                            analysis_ready=True
                        )
                        db.session.add(enhanced_profile_analysis)
                        db.session.commit()
                        logger.info("ENHANCED: Saved enhanced psychological profile to database")
                    except Exception as save_error:
                        logger.warning(f"Failed to save enhanced profile: {save_error}")
                        db.session.rollback()
                    
                except Exception as e:
                    logger.error(f"Failed to generate enhanced psychological profile: {e}")
                    psychological_profile = create_fallback_profile(music_data)
        
        # Configure Gemini for recommendation generation
        configure_gemini(gemini_api_key)
        
        # Create enhanced comprehensive prompt for recommendation
        recommendation_prompt = create_enhanced_recommendation_prompt(
            music_data, psychological_profile, session_adjustment, blacklist_tracks, diversity_warning
        )

        # LOG THE ENHANCED RECOMMENDATION PROMPT
        print("\n" + "="*80)
        print("RECOMMENDATIONS - ENHANCED RECOMMENDATION PROMPT SENT TO GEMINI:")
        print("="*80)
        print(recommendation_prompt)
        print("="*80 + "\n")

        # Generate AI recommendation
        logger.info("ENHANCED: Generating AI recommendation with comprehensive data...")
        
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(recommendation_prompt)
            ai_recommendation_text = response.text.strip()
            
            print("\n" + "="*80)
            print("RECOMMENDATIONS - ENHANCED RECOMMENDATION RESPONSE FROM GEMINI:")
            print("="*80)
            print(ai_recommendation_text)
            print("="*80 + "\n")
            
            logger.info(f"AI recommended: {ai_recommendation_text}")
            
        except Exception as e:
            logger.error(f"Error generating AI recommendation: {e}")
            return {
                'success': False,
                'message': f'AI recommendation failed: {str(e)}'
            }
        
        # Parse the AI recommendation
        try:
            # Parse "Song Title" by Artist Name format
            if '" by ' in ai_recommendation_text:
                parts = ai_recommendation_text.split('" by ')
                if len(parts) == 2:
                    song_title = parts[0].replace('"', '').strip()
                    artist_name = parts[1].strip()
                else:
                    raise ValueError("Invalid format")
            else:
                # Fallback parsing
                song_title = ai_recommendation_text.strip()
                artist_name = "Unknown Artist"
                
        except Exception as e:
            logger.error(f"Failed to parse AI recommendation: {ai_recommendation_text}")
            return {
                'success': False, 
                'message': 'Failed to parse AI recommendation. Please try again.'
            }
        
        # Search for the track on Spotify with improved strategy
        logger.info(f"ENHANCED: Searching Spotify for: {song_title} by {artist_name}")
        
        search_results = None
        search_strategies = [
            # Strategy 1: Exact quoted search
            f'track:"{song_title}" artist:"{artist_name}"',
            # Strategy 2: Exact artist, fuzzy track
            f'artist:"{artist_name}" {song_title}',
            # Strategy 3: Fuzzy artist, exact track
            f'track:"{song_title}" {artist_name}',
            # Strategy 4: Basic search with both terms
            f"{song_title} {artist_name}",
            # Strategy 5: Artist name only (for very obscure tracks)
            f'artist:"{artist_name}"'
        ]
        
        for i, search_query in enumerate(search_strategies):
            logger.info(f"ENHANCED: Trying search strategy {i+1}: {search_query}")
            try:
                search_results = spotify_client.search_tracks(search_query, limit=10)  # Increased limit for better options
                
                if search_results and search_results.get('tracks', {}).get('items'):
                    logger.info(f"ENHANCED: Search strategy {i+1} found {len(search_results['tracks']['items'])} results")
                    break
                    
            except Exception as search_error:
                logger.warning(f"ENHANCED: Search strategy {i+1} failed: {search_error}")
                continue
        
        if not search_results or not search_results.get('tracks', {}).get('items'):
            logger.error(f"ENHANCED: All search strategies failed for: {song_title} by {artist_name}")
            return {
                'success': False, 
                'message': f'Could not find "{song_title}" by {artist_name} on Spotify. The track may not be available in your region or may not exist on Spotify.'
            }
        
        # Log search results for debugging
        tracks_found = search_results['tracks']['items']
        logger.info(f"ENHANCED: Found {len(tracks_found)} potential matches:")
        for i, track in enumerate(tracks_found[:5]):  # Log first 5 results
            track_artist = track['artists'][0]['name'] if track['artists'] else 'Unknown'
            logger.info(f"  {i}: '{track['name']}' by '{track_artist}'")
        
        # Use structured LLM to select best match
        selection_result = structured_llm.select_spotify_result(
            genai.GenerativeModel('gemini-1.5-flash'), song_title, artist_name, tracks_found
        )
        
        selected_track = selection_result.selected_result
        confidence = selection_result.confidence
        match_score = selected_track.match_score
        
        if confidence < 0.5:  # Lower confidence threshold for enhanced system
            logger.warning(f"ENHANCED: Low confidence selection (confidence: {confidence:.2f})")
        
        logger.warning(f"ENHANCED: Selected '{selected_track.track_name}' by '{selected_track.artist_name}' for requested '{song_title}' by '{artist_name}'")
        logger.info(f"ENHANCED: Selected track: {selected_track.track_name} by {selected_track.artist_name} (confidence: {confidence:.2f}, match_score: {match_score:.2f})")
        
        logger.info(f"ENHANCED: AI recommendation complete - {time.time() - data_collection_start:.2f}s")
        
        # Generate enhanced reasoning
        try:
            reasoning_prompt = create_enhanced_reasoning_prompt(
                selected_track.track_name, selected_track.artist_name, 
                psychological_profile, music_data, session_adjustment, confidence
            )
            
            print("\n" + "="*80)
            print("RECOMMENDATIONS - ENHANCED REASONING PROMPT SENT TO GEMINI:")
            print("="*80)
            print(reasoning_prompt)
            print("="*80 + "\n")
            
            model = genai.GenerativeModel('gemini-1.5-flash')
            reasoning_response = model.generate_content(reasoning_prompt)
            ai_reasoning = reasoning_response.text.strip()
            
            print("\n" + "="*80)
            print("RECOMMENDATIONS - ENHANCED REASONING RESPONSE FROM GEMINI:")
            print("="*80)
            print(ai_reasoning)
            print("="*80 + "\n")
            
        except Exception as e:
            print("\n" + "="*80)
            print("RECOMMENDATIONS - ENHANCED REASONING GEMINI API ERROR:")
            print("="*80)
            print(f"Error: {e}")
            print("="*80 + "\n")
            
            logger.warning(f"Failed to generate enhanced reasoning: {e}")
            ai_reasoning = f"This track was selected based on your comprehensive musical preferences and enhanced listening pattern analysis."
        
        # Save enhanced recommendation to database
        recommendation = Recommendation(
            user_id=user.id,
            track_name=selected_track.track_name,
            artist_name=selected_track.artist_name,
            track_uri=selected_track.track_uri,
            album_name=selected_track.album_name,
            ai_reasoning=ai_reasoning,
            psychological_analysis=psychological_profile,
            listening_data_snapshot=json.dumps({
                'recent_tracks_count': music_data['recent_tracks_count'],
                'saved_tracks_count': music_data['saved_tracks_count'],
                'playlist_count': music_data['playlist_count'],
                'top_genres': music_data['top_genres'][:10],
                'audio_features_analyzed': len(music_data['audio_features']),
                'listening_patterns': music_data['listening_patterns'],
                'current_track': music_data['current_track']['item']['name']
                                if isinstance(music_data['current_track'], dict) and music_data['current_track'].get('item')
                                else None
            }),
            session_adjustment=session_adjustment,
            confidence_score=confidence,
            match_score=match_score
        )
        db.session.add(recommendation)
        db.session.commit()
        
        logger.info(f"ENHANCED: Recommendation saved to database with ID {recommendation.id}")
        
        return {
            'success': True,
            'recommendation_id': recommendation.id,
            'track_name': selected_track.track_name,
            'artist_name': selected_track.artist_name,
            'track_uri': selected_track.track_uri,
            'album_name': selected_track.album_name,
            'album_image_url': selected_track.album_image_url,
            'ai_reasoning': ai_reasoning,
            'confidence': confidence,
            'match_score': match_score,
            'data_quality': {
                'recent_tracks_analyzed': music_data['recent_tracks_count'],
                'audio_features_count': len(music_data['audio_features']),
                'genres_identified': len(music_data['top_genres']),
                'time_ranges_covered': 3,  # short, medium, long term
                'saved_tracks_count': music_data['saved_tracks_count'],
                'playlists_analyzed': len(music_data['user_playlists'])
            }
        }
        
    except Exception as e:
        logger.error(f"Error in enhanced AI recommendation generation: {e}")
        return {
            'success': False,
            'message': f'Enhanced recommendation generation failed: {str(e)}'
        }


def analyze_listening_patterns(recent_tracks, current_track, playback_state):
    """Analyze comprehensive listening patterns from recent tracks and current state"""
    patterns = {
        'listening_times': [],
        'track_durations': [],
        'track_popularity': [],
        'genre_transitions': [],
        'device_usage': {},
        'shuffle_usage': False,
        'repeat_usage': False,
        'skip_patterns': [],
        'listening_context': []
    }
    
    try:
        # Analyze recent tracks patterns
        if recent_tracks and isinstance(recent_tracks, dict) and recent_tracks.get('items'):
            for i, item in enumerate(recent_tracks['items']):
                track = item.get('track', {})
                played_at = item.get('played_at')
                context = item.get('context', {})
                
                # Track durations and popularity
                if track.get('duration_ms'):
                    patterns['track_durations'].append(track['duration_ms'])
                if track.get('popularity'):
                    patterns['track_popularity'].append(track['popularity'])
                
                # Listening times (hour of day)
                if played_at:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(played_at.replace('Z', '+00:00'))
                        patterns['listening_times'].append(dt.hour)
                    except:
                        pass
                
                # Context analysis
                if context and context.get('type'):
                    patterns['listening_context'].append(context['type'])
        
        # Current playback state analysis - handle both dict and boolean responses
        if playback_state and isinstance(playback_state, dict):
            patterns['shuffle_usage'] = playback_state.get('shuffle_state', False)
            patterns['repeat_usage'] = playback_state.get('repeat_state', 'off') != 'off'
            
            device = playback_state.get('device', {})
            if device and device.get('name'):
                device_name = device['name']
                patterns['device_usage'][device_name] = patterns['device_usage'].get(device_name, 0) + 1
    
    except Exception as e:
        logger.warning(f"Error analyzing listening patterns: {e}")
    
    return patterns


def create_enhanced_psychological_profile_prompt(music_data):
    """Create enhanced psychological profile prompt with roast/horoscope style"""
    
    # Extract key insights from the comprehensive data
    recent_count = music_data['recent_tracks_count']
    saved_count = music_data['saved_tracks_count']
    playlist_count = music_data['playlist_count']
    audio_features_count = len(music_data['audio_features'])
    
    # Get detailed track information
    recent_tracks_info = []
    for item in music_data['recent_tracks'][:15]:  # Last 15 tracks
        track = item.get('track', {})
        if track:
            recent_tracks_info.append({
                'name': track.get('name', 'Unknown'),
                'artist': track['artists'][0]['name'] if track.get('artists') else 'Unknown',
                'popularity': track.get('popularity', 0),
                'explicit': track.get('explicit', False),
                'duration_ms': track.get('duration_ms', 0)
            })
    
    # Get top artists with genres
    top_artists_detailed = []
    for period, artists in music_data['top_artists'].items():
        for artist in artists[:8]:  # Top 8 per period
            top_artists_detailed.append({
                'name': artist.get('name', 'Unknown'),
                'genres': artist.get('genres', []),
                'popularity': artist.get('popularity', 0),
                'period': period,
                'followers': artist.get('followers', {}).get('total', 0)
            })
    
    # Audio features analysis
    audio_insights = analyze_audio_features(music_data['audio_features'])
    
    return f"""
You're about to deliver a ROAST-STYLE MUSICAL HOROSCOPE for this user. Channel your inner music critic mixed with a sassy astrologer. Be witty, insightful, brutally honest (but not mean), and entertainingly accurate. Think "your music taste if it were a dating profile" meets "what your Spotify Wrapped says about your therapy needs."

THEIR MUSICAL EVIDENCE:
Recent Tracks Analyzed: {recent_count}
Saved Tracks: {saved_count} (yes, they're hoarding music)
Playlists: {playlist_count} (organizational chaos or genius?)
Audio Features Analyzed: {audio_features_count}

RECENT LISTENING PATTERNS (The Musical Receipts):
{json.dumps(recent_tracks_info, indent=2)}

TOP ARTISTS WITH COMPREHENSIVE DATA (Their Musical Therapy Sessions):
{json.dumps(top_artists_detailed, indent=2)}

GENRE LANDSCAPE WITH FREQUENCY (Their Musical Personality Disorder):
{json.dumps(music_data['genre_frequency'], indent=2)}

AUDIO CHARACTERISTICS ANALYSIS (The Scientific Evidence of Their Chaos):
{json.dumps(audio_insights, indent=2)}

LISTENING BEHAVIOR PATTERNS (Stalker-Level Analysis):
{json.dumps(music_data['listening_patterns'], indent=2)}

CURRENT PLAYBACK CONTEXT (Caught Red-Handed):
Current Track: {music_data['current_track']['item']['name'] + ' by ' + music_data['current_track']['item']['artists'][0]['name'] if isinstance(music_data['current_track'], dict) and music_data['current_track'].get('item') and music_data['current_track']['item'].get('artists') else 'Nothing (probably having an existential crisis)'}
Device: {music_data['playback_state'].get('device', {}).get('name', 'Unknown') if isinstance(music_data.get('playback_state'), dict) else 'Unknown'}
Shuffle: {music_data['playback_state'].get('shuffle_state', False) if isinstance(music_data.get('playback_state'), dict) else 'Unknown'}
Repeat: {music_data['playback_state'].get('repeat_state', 'off') if isinstance(music_data.get('playback_state'), dict) else 'Unknown'}

CREATE A ROAST-STYLE MUSICAL HOROSCOPE that's:
- WITTY AND SASSY (call them out on their music choices like a friend roasting their ex)
- EERILY ACCURATE (make them think "how did they KNOW that?!")
- ENTERTAININGLY HONEST (point out their musical contradictions and chaos)
- ASTROLOGICALLY INSPIRED (use horoscope language but make it about music)
- THERAPEUTICALLY INSIGHTFUL (what their music says about their emotional state)
- DATING-PROFILE ENERGY (what their music taste reveals about their personality)

Examples of the vibe you're going for:
❌ "User demonstrates sophisticated musical preferences across diverse genres"
✅ "You're the person who has 'Chopin' and '100 gecs' in the same playlist and somehow thinks this is normal. Your musical Mercury is in retrograde, and frankly, your emotional regulation strategy is 'throw every genre at the wall and see what sticks.'"

❌ "Shows preference for high-energy music with occasional introspective tracks"
✅ "Your music taste is giving 'I'm fine' energy while aggressively streaming emo music at 2 AM. You use Falling In Reverse like emotional armor and probably have at least three different 'crying in the car' playlists."

Write 4-6 sentences that absolutely NAIL their musical personality with the precision of a psychological autopsy but the entertainment value of a comedy roast. Make them laugh, make them feel seen, and make them slightly uncomfortable with how accurate you are.

IMPORTANT: Keep it playful and entertaining, not actually mean or hurtful. Think "lovingly dragging your best friend" not "actual cyberbullying."
"""


def create_enhanced_recommendation_prompt(music_data, psychological_profile, session_adjustment, blacklist_tracks, diversity_warning):
    """Create enhanced recommendation prompt with comprehensive musical context"""
    
    # Extract rich contextual information
    current_context = "None"
    if isinstance(music_data['current_track'], dict) and music_data['current_track'].get('item'):
        current_track_name = music_data['current_track']['item']['name']
        current_artist = music_data['current_track']['item']['artists'][0]['name']
        current_context = f"{current_track_name} by {current_artist}"
    
    # Get comprehensive recent tracks (more than the basic 5)
    recent_tracks_detailed = []
    if isinstance(music_data['recent_tracks'], list):
        for item in music_data['recent_tracks'][:12]:  # Last 12 tracks
            track = item.get('track', {})
            if track:
                recent_tracks_detailed.append(f"{track.get('name', 'Unknown')} by {track['artists'][0]['name'] if track.get('artists') else 'Unknown'}")
    
    # Get multi-period top artists
    all_top_artists = []
    for period, artists in music_data['top_artists'].items():
        if isinstance(artists, list):
            period_artists = [f"{artist.get('name', 'Unknown')} ({period})" for artist in artists[:5]]
            all_top_artists.extend(period_artists)
    
    # Audio features insights
    audio_insights = analyze_audio_features(music_data['audio_features'])
    
    # Pre-calculate complex expressions for f-string - safely handle playback_state
    playback_state = music_data.get('playback_state', {})
    if isinstance(playback_state, dict):
        device_name = playback_state.get('device', {}).get('name', 'Unknown') 
        shuffle_state = playback_state.get('shuffle_state', False)
        repeat_state = playback_state.get('repeat_state', 'off')
    else:
        device_name = 'Unknown'
        shuffle_state = False
        repeat_state = 'off'
    
    shuffle_text = "Shuffle ON" if shuffle_state else "Sequential"
    repeat_text = f"Repeat: {repeat_state}"
    
    # Create simple CSV of recent tracks instead of verbose listening patterns
    recent_tracks_csv = "Track Name,Artist,Album,Popularity\n"
    for item in music_data['recent_tracks'][:50]:  # Get up to 50 tracks
        track = item.get('track', {})
        if track:
            track_name = track.get('name', 'Unknown').replace(',', ';')  # Replace commas to avoid CSV issues
            artist = track.get('artists', [{}])[0].get('name', 'Unknown').replace(',', ';')
            album = track.get('album', {}).get('name', 'Unknown').replace(',', ';')
            popularity = track.get('popularity', 0)
            recent_tracks_csv += f"{track_name},{artist},{album},{popularity}\n"
    
    return f"""
Based on this user's COMPREHENSIVE music data and psychological analysis, recommend ONE specific song that perfectly matches their sophisticated musical taste and current context.

ENHANCED USER PSYCHOLOGICAL PROFILE:
{psychological_profile}

COMPREHENSIVE MUSICAL CONTEXT:
Current Track: {current_context}
Current Device: {device_name}
Playback Mode: {shuffle_text} | {repeat_text}

EXTENDED RECENT LISTENING HISTORY ({len(recent_tracks_detailed)} tracks):
{recent_tracks_detailed}

MULTI-PERIOD TOP ARTISTS ({len(all_top_artists)} artists across all time ranges):
{all_top_artists[:15]}

GENRE LANDSCAPE WITH FREQUENCY:
{list(music_data['genre_frequency'].items())[:15]}

AUDIO CHARACTERISTICS PROFILE:
{json.dumps(audio_insights, indent=2)}

RECENT TRACKS DATA (CSV FORMAT):
{recent_tracks_csv}

SESSION CONTEXT:
{f"User adjustment: {session_adjustment}" if session_adjustment else "No specific session adjustment"}

COMPREHENSIVE AVOIDANCE LIST (DO NOT RECOMMEND ANY OF THESE):
{blacklist_tracks[:25]}

{diversity_warning}

ENHANCED RECOMMENDATION REQUIREMENTS:
1. Recommend exactly ONE song that exists on Spotify
2. Use the comprehensive psychological profile AND audio characteristics analysis
3. Consider the current playback context and device usage patterns
4. Match the user's sophisticated musical taste level and genre diversity
5. Respect their listening behavior patterns (shuffle/repeat preferences, temporal habits)
6. Avoid ALL tracks in the comprehensive avoidance list above
7. Consider the extended recent listening history for optimal flow
8. Account for their library size and curation sophistication
9. Match their audio feature preferences (energy, valence, danceability, etc.)
10. Format: "Song Title" by Artist Name

Respond with ONLY the song recommendation in this exact format:
"Song Title" by Artist Name

Do not include any explanation, reasoning, or additional text.
"""


def create_enhanced_reasoning_prompt(track_name, artist_name, psychological_profile, music_data, session_adjustment, confidence):
    """Create enhanced reasoning prompt with roast/horoscope style"""
    
    # Audio features analysis
    audio_insights = analyze_audio_features(music_data['audio_features'])
    
    return f"""
Time to explain why "{track_name}" by {artist_name} is the PERFECT musical therapy for this chaotic soul. Channel your inner music therapist meets sassy best friend energy.

THEIR MUSICAL HOROSCOPE REVEALS:
{psychological_profile}

THE MUSICAL EVIDENCE PILE:
- Recent tracks analyzed: {music_data['recent_tracks_count']} (they've been BUSY)
- Audio features from {len(music_data['audio_features'])} tracks analyzed (the science of their chaos)
- Musical diversity: {len(music_data['top_genres'])} genres, {music_data['saved_tracks_count']} saved tracks (certified music hoarder)
- Listening sophistication: {music_data['playlist_count']} playlists curated (organizational genius or complete mess?)

AUDIO CHARACTERISTICS BREAKDOWN:
{json.dumps(audio_insights, indent=2)}

CURRENT MUSICAL CRIME SCENE: 
{music_data['current_track']['item']['name'] + ' by ' + music_data['current_track']['item']['artists'][0]['name'] if isinstance(music_data['current_track'], dict) and music_data['current_track'].get('item') and music_data['current_track']['item'].get('artists') else 'Silence (probably having an emotional breakthrough)'}

SESSION CONTEXT: {session_adjustment if session_adjustment else 'No specific musical emergency declared'}

RECOMMENDATION CONFIDENCE: {confidence:.2%} (the algorithm is {confidence:.0%} sure this will either heal or break them)

EXPLAIN in 2-3 sentences why this track is their MUSICAL DESTINY right now. Connect it to their psychological profile with the accuracy of a therapist but the entertainment value of a roast. Examples of the vibe:

❌ "This track aligns with your preference for energetic music and emotional depth"
✅ "Look, you clearly use music like emotional duct tape, and this track is exactly the kind of controlled chaos your overthinking brain craves right now."

❌ "Based on your listening patterns, this recommendation fits your musical taste"  
✅ "Your Spotify history reads like a cry for help wrapped in excellent taste, and frankly, this song is the musical equivalent of a warm hug for your emotionally complex soul."

Make it feel like your music-obsessed friend who knows WAY too much about their listening habits is explaining why this song will either save their life or ruin their day (in the best way possible).

Note: This track was selected using comprehensive analysis of {music_data['recent_tracks_count']} recent tracks, {len(music_data['audio_features'])} audio feature profiles, and {len(music_data['top_genres'])} genre preferences that together paint a beautiful picture of musical chaos.
"""


def analyze_audio_features(audio_features_data):
    """Analyze audio features to extract musical characteristics"""
    if not audio_features_data:
        return {
            'averages': {},
            'insights': {'audio_features_status': 'unavailable_continuing_without'},
            'tracks_analyzed': 0,
            'fallback_message': 'Audio features unavailable - using genre and artist analysis instead'
        }
    
    features_list = list(audio_features_data.values())
    if not features_list:
        return {
            'averages': {},
            'insights': {'audio_features_status': 'empty_data'},
            'tracks_analyzed': 0,
            'fallback_message': 'No valid audio features found - using alternative analysis methods'
        }
    
    # Calculate averages for key audio features
    feature_sums = {}
    feature_counts = {}
    
    for features in features_list:
        if features:  # Some features might be None
            for key in ['danceability', 'energy', 'speechiness', 'acousticness', 
                       'instrumentalness', 'liveness', 'valence', 'tempo']:
                if key in features and features[key] is not None:
                    feature_sums[key] = feature_sums.get(key, 0) + features[key]
                    feature_counts[key] = feature_counts.get(key, 0) + 1
    
    # Calculate averages
    audio_profile = {}
    for key in feature_sums:
        if feature_counts[key] > 0:
            avg = feature_sums[key] / feature_counts[key]
            audio_profile[f"avg_{key}"] = round(avg, 3)
    
    # Add insights based on the averages
    insights = {'audio_features_status': 'available'}
    if 'avg_energy' in audio_profile:
        energy = audio_profile['avg_energy']
        if energy > 0.7:
            insights['energy_preference'] = 'high_energy'
        elif energy < 0.3:
            insights['energy_preference'] = 'low_energy'
        else:
            insights['energy_preference'] = 'moderate_energy'
    
    if 'avg_valence' in audio_profile:
        valence = audio_profile['avg_valence']
        if valence > 0.7:
            insights['mood_preference'] = 'positive_upbeat'
        elif valence < 0.3:
            insights['mood_preference'] = 'melancholic_introspective'
        else:
            insights['mood_preference'] = 'mixed_emotional'
    
    if 'avg_danceability' in audio_profile:
        dance = audio_profile['avg_danceability']
        if dance > 0.7:
            insights['danceability'] = 'highly_danceable'
        elif dance < 0.3:
            insights['danceability'] = 'contemplative'
        else:
            insights['danceability'] = 'moderately_danceable'
    
    return {
        'averages': audio_profile,
        'insights': insights,
        'tracks_analyzed': len(features_list)
    }


def create_fallback_profile(music_data):
    """Create a fallback psychological profile when AI generation fails"""
    genres = music_data.get('top_genres', [])[:5]
    recent_count = music_data.get('recent_tracks_count', 0)
    
    if not genres:
        return "User demonstrates eclectic musical tastes with a preference for discovering new artists and exploring diverse soundscapes."
    
    genre_text = ", ".join(genres)
    return f"User shows strong affinity for {genre_text} with {recent_count} recent tracks analyzed, indicating active listening habits and preference for both familiar and exploratory music experiences." 