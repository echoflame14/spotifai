"""
Playlist creation and management routes.

This module handles AI-powered playlist creation functionality.
"""

from flask import Blueprint, request, session, jsonify, current_app
from datetime import datetime
from models import User, Recommendation, UserAnalysis, db
from spotify_client import SpotifyClient
from utils.spotify_auth import refresh_user_token
from utils.ai_analysis import configure_gemini, check_rate_limit_error
from utils.recommendations import get_enhanced_recent_recommendations
import time
import json
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Create playlist blueprint
playlist_bp = Blueprint('playlist', __name__)

def require_auth():
    """Check if user is authenticated and return user object"""
    if 'user_id' not in session:
        return None
    
    user = User.query.get(session['user_id'])
    if not user:
        session.pop('user_id', None)
        return None
    
    # Check if token needs refresh
    if user.is_token_expired():
        if not refresh_user_token(user):
            return None
    
    return user

@playlist_bp.route('/create-ai-playlist', methods=['POST'])
def create_ai_playlist():
    """Create an AI-generated playlist"""
    user = require_auth()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        playlist_name = data.get('name', 'AI Generated Playlist')
        playlist_description = data.get('description', 'A personalized playlist created by AI')
        song_count = int(data.get('song_count', 10))
        use_session_adjustment = data.get('use_session_adjustment', False)
        custom_gemini_key = data.get('custom_gemini_key')
        
        if not custom_gemini_key:
            return jsonify({
                'success': False,
                'message': 'Personal Gemini API key required. Please add your API key in AI Settings to create playlists.'
            })
        
        # Configure Gemini
        if not configure_gemini(custom_gemini_key):
            return jsonify({
                'success': False,
                'message': 'Failed to configure Gemini API'
            })
        
        spotify_client = SpotifyClient(user.access_token)
        
        # Get comprehensive user analysis for playlist creation
        logger.info("Collecting comprehensive user analysis for AI playlist creation...")
        
        # CHECK FOR COMPREHENSIVE PSYCHOLOGICAL ANALYSIS FIRST - FROM DATABASE
        cached_analysis = UserAnalysis.get_latest_analysis(user.id, 'psychological', max_age_hours=24)
        
        user_analysis = None
        
        if cached_analysis:
            analysis_data = cached_analysis.get_data()
            if isinstance(analysis_data, dict) and analysis_data.get('analysis_ready'):
                logger.info("Using comprehensive psychological analysis from database for playlist creation")
                
                # Extract key insights from comprehensive analysis for playlist prompt
                analysis = analysis_data
                user_analysis = f"""
COMPREHENSIVE USER ANALYSIS FOR PLAYLIST CURATION:
Core Personality: {analysis.get('psychological_profile', {}).get('core_personality', 'Not available')}
Musical Identity: {analysis.get('musical_identity', {}).get('sophistication_level', 'Not available')} | {analysis.get('musical_identity', {}).get('exploration_style', 'Not available')}
Listening Psychology: {analysis.get('listening_psychology', {}).get('mood_regulation', 'Not available')}
Discovery Preferences: {analysis.get('behavioral_insights', {}).get('discovery_preferences', 'Not available')}
Playlist Creation Style: {analysis.get('behavioral_insights', {}).get('playlist_creation_style', 'Not available')}
Recommendation Strategy: {analysis.get('summary_insights', {}).get('recommendation_strategy', 'Not available')}
Key Unique Traits: {', '.join(analysis.get('summary_insights', {}).get('unique_traits', [])[:3])}
Musical Growth Trajectory: {analysis.get('growth_trajectory', {}).get('evolution_pattern', 'Not available')}
Energy Management: {analysis.get('listening_psychology', {}).get('energy_management', 'Not available')}
"""
                logger.info("PLAYLIST: Using comprehensive psychological analysis for enhanced playlist curation")
        
        if not user_analysis:
            # Fallback to basic music insights if comprehensive analysis not available
            try:
                from utils.ai_analysis import generate_basic_insights
                music_data = generate_basic_insights(spotify_client)
                user_analysis = f"User prefers {', '.join(music_data.get('genres', {}).get('examples', ['various genres']))} with favorite artists including {', '.join(music_data.get('top_artists', {}).get('examples', ['various artists']))}."
                logger.info("PLAYLIST: Using basic music insights as fallback for playlist creation")
            except Exception as e:
                logger.error(f"Error getting music insights: {e}")
                # Ultra-minimal fallback
                user_analysis = "User prefers rock, alternative, and pop music with some electronic elements."
        
        # Get enhanced recent recommendations to avoid duplicates in playlist
        rec_tracking = get_enhanced_recent_recommendations(user, hours_back=48, include_artist_counts=True)  # Look back 48 hours for playlists
        recent_recommendations = rec_tracking['formatted_list']
        artist_frequency = rec_tracking['artist_frequency']
        
        # Build a more comprehensive avoidance list for playlists
        all_recent_tracks = []
        if recent_recommendations:
            all_recent_tracks.extend([f'"{rec.track_name}" by {rec.artist_name}' for rec in recent_recommendations])
        
        # Add tracks from recent playlists (if any) to avoid duplicating playlist content
        recent_playlist_recs = Recommendation.query.filter_by(
            user_id=user.id, 
            recommendation_method='playlist'
        ).order_by(Recommendation.created_at.desc()).limit(15).all()
        
        for rec in recent_playlist_recs:
            time_ago = datetime.utcnow() - rec.created_at
            if time_ago.total_seconds() < 7 * 24 * 3600:  # Last 7 days
                all_recent_tracks.append(f'"{rec.track_name}" by {rec.artist_name} (from recent playlist)')
        
        # Create warning for over-recommended artists
        frequent_artists_warning = ""
        over_used_artists = []
        for artist, count in artist_frequency.items():
            if count >= 3:  # More than 3 times in recent period
                over_used_artists.append(f"{artist} ({count} times)")
        
        if over_used_artists:
            frequent_artists_warning = f"\nAVOID OVER-RECOMMENDING THESE ARTISTS: {', '.join(over_used_artists[:8])}"
        
        logger.info(f"Playlist creation: Avoiding {len(all_recent_tracks)} recent tracks and {len(over_used_artists)} overused artists")
        
        # Create comprehensive prompt for generating multiple tracks
        prompt = f"""Based on this user's comprehensive psychological and musical analysis, create a highly personalized playlist of exactly {song_count} specific songs.

USER COMPREHENSIVE PSYCHOLOGICAL & MUSICAL ANALYSIS:
{user_analysis}

{frequent_artists_warning}

RECENTLY RECOMMENDED TRACKS (DO NOT REPEAT THESE):
{all_recent_tracks}

PLAYLIST CONTEXT:
Title: {playlist_name}
Description: {playlist_description}

ENHANCED REQUIREMENTS FOR PSYCHOLOGICAL ALIGNMENT:
1. Recommend exactly {song_count} different, real songs available on Spotify
2. **PSYCHOLOGICAL MATCHING**: Use the comprehensive analysis above to match songs to the user's:
   - Core personality traits and emotional patterns
   - Musical sophistication level and exploration style
   - Mood regulation and energy management preferences
   - Discovery preferences and listening psychology
   - Playlist creation style and behavioral insights
3. **CONTEXTUAL ADAPTATION**: Carefully consider both the playlist title and description to match the intended mood, theme, or occasion while respecting their psychological profile
4. **DIVERSITY & GROWTH**: Balance familiar comfort zone tracks with growth-oriented discoveries based on their exploration style
5. **TEMPORAL FLOW**: Consider how the user manages energy and mood through music sequencing
6. **AVOID REPETITION**: Do not include any tracks from the avoidance list above
7. **ARTIST VARIETY**: Limit artist repetition unless their analysis shows strong loyalty patterns

FORMAT: Respond with ONLY the song list, one per line:
"Song Title 1" by Artist Name 1
"Song Title 2" by Artist Name 2
...and so on.

Do not include explanations, numbering, or additional text."""

        # Generate AI recommendations with timeout protection
        try:
            import threading
            
            response = None
            error_occurred = None
            
            def generate_with_timeout():
                nonlocal response, error_occurred
                try:
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    response = model.generate_content(prompt)
                except Exception as e:
                    error_occurred = e
            
            # Start the generation in a separate thread
            thread = threading.Thread(target=generate_with_timeout)
            thread.daemon = True
            thread.start()
            thread.join(timeout=30)  # 30 second timeout
            
            if thread.is_alive():
                # Thread is still running, timeout occurred
                logger.error("AI generation timed out")
                return jsonify({
                    'success': False,
                    'message': 'Request timed out. Please try again with fewer songs or check your connection.'
                })
            
            if error_occurred:
                raise error_occurred
            
            if response is None:
                raise Exception("No response generated")
                
            ai_recommendations = response.text.strip()
            
        except Exception as e:
            # Check for rate limit errors
            if check_rate_limit_error(e):
                from utils.ai_analysis import extract_rate_limit_details
                error_details = extract_rate_limit_details(str(e))
                logger.warning(f"PLAYLIST: Gemini rate limit detected - {str(e)[:200]}...")
                return jsonify({
                    'success': False, 
                    'message': f'You\'ve reached your Gemini API rate limit. Please wait {error_details["suggested_wait_time"]} before creating another playlist.',
                    'rate_limit_error': True,
                    'suggested_wait_time': error_details['suggested_wait_time'],
                    'retry_seconds': error_details['retry_seconds']
                }), 429
            
            logger.error(f"AI generation failed: {e}")
            return jsonify({
                'success': False,
                'message': 'AI recommendation generation failed. Please try again.'
            })
        
        # Parse the AI response to extract individual tracks
        track_lines = [line.strip() for line in ai_recommendations.split('\n') if line.strip()]
        track_uris = []
        successful_tracks = []
        failed_count = 0
        
        logger.info(f"AI recommended {len(track_lines)} tracks for playlist")
        
        # Search for each recommended track on Spotify with limits
        for i, track_line in enumerate(track_lines[:song_count + 3]):  # Get a few extra in case some fail
            if len(track_uris) >= song_count:  # Stop when we have enough
                break
                
            try:
                # Parse "Song Title" by Artist Name format
                if '" by ' in track_line:
                    parts = track_line.split('" by ')
                    if len(parts) == 2:
                        song_title = parts[0].replace('"', '').strip()
                        artist_name = parts[1].strip()
                        
                        # Search for the track with retry logic
                        search_query = f'track:"{song_title}" artist:"{artist_name}"'
                        search_results = spotify_client.search_tracks(search_query, limit=1)
                        
                        if search_results and search_results.get('tracks', {}).get('items'):
                            track = search_results['tracks']['items'][0]
                            track_uris.append(track['uri'])
                            successful_tracks.append(f"{track['name']} by {track['artists'][0]['name']}")
                            logger.info(f"Found track: {track['name']} by {track['artists'][0]['name']}")
                        else:
                            failed_count += 1
                            logger.warning(f"Could not find track: {song_title} by {artist_name}")
                            
                            # If too many failures, try broader search
                            if failed_count > 2:
                                broad_search = spotify_client.search_tracks(f"{song_title} {artist_name}", limit=1)
                                if broad_search and broad_search.get('tracks', {}).get('items'):
                                    track = broad_search['tracks']['items'][0]
                                    track_uris.append(track['uri'])
                                    successful_tracks.append(f"{track['name']} by {track['artists'][0]['name']}")
                                    
            except Exception as e:
                logger.error(f"Error processing track line '{track_line}': {e}")
                failed_count += 1
                continue
        
        if not track_uris:
            return jsonify({
                'success': False,
                'message': 'Could not find any of the AI-recommended tracks on Spotify'
            })
        
        # Create the playlist
        playlist_result = spotify_client.create_playlist(playlist_name, playlist_description)
        
        if not playlist_result:
            return jsonify({
                'success': False,
                'message': 'Failed to create playlist on Spotify'
            })
        
        playlist_id = playlist_result['id']
        
        # Add tracks to the playlist
        if track_uris:
            add_result = spotify_client.add_tracks_to_playlist(playlist_id, track_uris)
            if not add_result:
                logger.warning("Failed to add some tracks to playlist")
        
        # Save each track as a recommendation for future duplicate prevention
        try:
            for track_uri in track_uris:
                # Get track details from Spotify
                track_search = spotify_client.search_tracks(f"spotify:track:{track_uri.split(':')[-1]}", limit=1)
                if track_search and track_search.get('tracks', {}).get('items'):
                    track = track_search['tracks']['items'][0]
                    
                    # Save as a playlist recommendation
                    playlist_rec = Recommendation(
                        user_id=user.id,
                        track_name=track['name'],
                        artist_name=track['artists'][0]['name'],
                        track_uri=track['uri'],
                        album_name=track['album']['name'],
                        ai_reasoning=f"Added to playlist '{playlist_name}' - {playlist_description[:100]}...",
                        psychological_analysis=user_analysis[:500] + "..." if len(user_analysis) > 500 else user_analysis,  # Truncate if too long
                        listening_data_snapshot="{}",  # Minimal for playlist tracks
                        session_adjustment=playlist_description,
                        recommendation_method='playlist'
                    )
                    db.session.add(playlist_rec)
            
            db.session.commit()
            logger.info(f"Saved {len(track_uris)} playlist tracks to recommendation history")
            
        except Exception as e:
            logger.warning(f"Could not save playlist tracks to recommendation history: {e}")
        
        return jsonify({
            'success': True,
            'playlist_name': playlist_name,
            'playlist_id': playlist_id,
            'playlist_url': playlist_result['external_urls']['spotify'],
            'tracks_added': len(track_uris),
            'tracks_found': successful_tracks,
            'total_requested': song_count,
            'duplicates_avoided': len(all_recent_tracks),
            'artists_diversified': len(over_used_artists)
        })
        
    except Exception as e:
        # Check for rate limit errors in playlist creation
        if check_rate_limit_error(e):
            from utils.ai_analysis import extract_rate_limit_details
            error_details = extract_rate_limit_details(str(e))
            logger.warning(f"PLAYLIST: Gemini rate limit detected in main handler - {str(e)[:200]}...")
            return jsonify({
                'success': False, 
                'message': f'You\'ve reached your Gemini API rate limit. Please wait {error_details["suggested_wait_time"]} before creating another playlist.',
                'rate_limit_error': True,
                'suggested_wait_time': error_details['suggested_wait_time'],
                'retry_seconds': error_details['retry_seconds']
            }), 429
        
        logger.error(f"Playlist creation failed: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to create playlist: {str(e)}'
        }) 