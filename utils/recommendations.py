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

logger = logging.getLogger(__name__)

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
        logger.info("STANDARD: Starting enhanced AI recommendation...")
        data_collection_start = time.time()
        
        spotify_client = SpotifyClient(user.access_token)
        
        try:
            # Get user's current music context
            current_track = spotify_client.get_current_track()
            recent_tracks = spotify_client.get_recently_played(limit=20)
            top_artists_short = spotify_client.get_top_artists(time_range='short_term', limit=10)
            top_artists_medium = spotify_client.get_top_artists(time_range='medium_term', limit=10)
            top_tracks_short = spotify_client.get_top_tracks(time_range='short_term', limit=10)
            top_tracks_medium = spotify_client.get_top_tracks(time_range='medium_term', limit=10)
            
            # Extract top genres from artists
            all_artists = (top_artists_short.get('items', []) + top_artists_medium.get('items', []))[:15]
            top_genres = []
            for artist in all_artists:
                top_genres.extend(artist.get('genres', []))
            
            # Get unique genres, keeping order
            seen = set()
            unique_genres = []
            for genre in top_genres:
                if genre not in seen:
                    seen.add(genre)
                    unique_genres.append(genre)
            
            music_data = {
                'current_track': current_track,
                'recent_tracks': recent_tracks.get('items', []),
                'top_artists': {
                    'short_term': top_artists_short.get('items', []),
                    'medium_term': top_artists_medium.get('items', [])
                },
                'top_tracks': {
                    'short_term': top_tracks_short.get('items', []),
                    'medium_term': top_tracks_medium.get('items', [])
                },
                'top_genres': unique_genres[:15]
            }
            
        except Exception as e:
            logger.warning(f"Error collecting music data: {e}")
            # Minimal fallback
            music_data = {
                'current_track': None,
                'recent_tracks': [],
                'top_artists': {'short_term': [], 'medium_term': []},
                'top_tracks': {'short_term': [], 'medium_term': []},
                'top_genres': []
            }
        
        data_collection_duration = time.time() - data_collection_start
        logger.info(f"STANDARD: Data collection complete - {data_collection_duration:.2f}s")
        
        # Get enhanced recent recommendations to avoid duplicates
        rec_tracking = get_enhanced_recent_recommendations(user, hours_back=24)
        blacklist_tracks = rec_tracking['blacklist_tracks']
        diversity_warning = rec_tracking['warning_message']
        
        logger.info(f"STANDARD: Found {rec_tracking['total_count']} recent recommendations for duplicate prevention")
        
        # CHECK FOR COMPREHENSIVE MUSIC TASTE ANALYSIS FIRST - NOW FROM DATABASE
        cached_analysis = UserAnalysis.get_latest_analysis(user.id, 'psychological', max_age_hours=24)
        
        psychological_profile = None
        
        if cached_analysis:
            analysis_data = cached_analysis.get_data()
            if isinstance(analysis_data, dict) and analysis_data.get('analysis_ready'):
                logger.info("STANDARD: Using comprehensive psychological analysis from database for recommendations")
                
                # Extract key insights from comprehensive analysis for recommendation prompt
                analysis = analysis_data
                psychological_profile = f"""
COMPREHENSIVE USER ANALYSIS:
Core Personality: {analysis.get('psychological_profile', {}).get('core_personality', 'Not available')}
Musical Identity: {analysis.get('musical_identity', {}).get('sophistication_level', 'Not available')} | {analysis.get('musical_identity', {}).get('exploration_style', 'Not available')}
Listening Psychology: {analysis.get('listening_psychology', {}).get('mood_regulation', 'Not available')}
Discovery Preferences: {analysis.get('behavioral_insights', {}).get('discovery_preferences', 'Not available')}
Recommendation Strategy: {analysis.get('summary_insights', {}).get('recommendation_strategy', 'Not available')}
Key Unique Traits: {', '.join(analysis.get('summary_insights', {}).get('unique_traits', [])[:3])}
"""
        
        if not psychological_profile:
            # Check for basic cached psychological analysis as fallback
            cached_psych_analysis = session.get('cached_psychological_analysis')
            cached_psych_timestamp = session.get('cached_psychological_timestamp', 0)
            psych_cache_valid = (time.time() - cached_psych_timestamp) < 1800
            
            if cached_psych_analysis and psych_cache_valid:
                logger.info("STANDARD: Using cached basic psychological analysis")
                psychological_profile = cached_psych_analysis
            else:
                logger.info("STANDARD: No valid cached analysis, generating basic profile...")
                # Generate basic psychological profile for recommendations
                profile_start = time.time()
                
                # Create model AFTER configuration with fresh API key
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                profile_prompt = f"""
Analyze this user's Spotify data and create a concise psychological music profile for recommendations:

RECENT TRACKS: {[f"{track['track']['name']} by {track['track']['artists'][0]['name']}" for track in music_data['recent_tracks'][:10]]}
TOP ARTISTS: {[artist['name'] for artist in music_data['top_artists']['short_term'][:8]]}
TOP GENRES: {music_data['top_genres'][:8]}
CURRENT TRACK: {music_data['current_track']['item']['name'] + ' by ' + music_data['current_track']['item']['artists'][0]['name']
                if isinstance(music_data['current_track'], dict) and music_data['current_track'].get('item')
                else 'None'}

Create a 2-3 sentence psychological profile focusing on:
- Musical personality traits
- Emotional connections to music
- Discovery preferences

Keep it conversational and insightful.
"""
                
                try:
                    profile_response = model.generate_content(profile_prompt)
                    psychological_profile = profile_response.text.strip() if profile_response and profile_response.text else "Music lover with diverse taste who enjoys discovering new sounds."
                    
                    # Cache the basic profile for 30 minutes
                    session['cached_psychological_analysis'] = psychological_profile
                    session['cached_psychological_timestamp'] = time.time()
                    logger.info("STANDARD: Generated and cached basic psychological profile")
                    
                except Exception as e:
                    from utils.ai_analysis import check_rate_limit_error
                    if check_rate_limit_error(e):
                        logger.warning(f"STANDARD: Gemini rate limit detected during profile generation - {str(e)}")
                        return {
                            'success': False, 
                            'message': 'You\'ve reached your Gemini API rate limit. Please wait a few minutes before requesting another recommendation.',
                            'rate_limit_error': True,
                            'suggested_wait_time': '2-3 minutes'
                        }
                    
                    logger.warning(f"Profile generation failed: {e}")
                    psychological_profile = "Music lover with diverse taste who enjoys discovering new sounds."
                
                profile_duration = time.time() - profile_start
                logger.info(f"STANDARD: User profile complete - {profile_duration:.2f}s")

        # Generate AI recommendation
        logger.info("STANDARD: Generating AI recommendation...")
        recommendation_start = time.time()
        
        # Create comprehensive prompt for recommendation including psychological analysis
        recommendation_prompt = f"""
Based on this user's comprehensive music data and psychological analysis, recommend ONE specific song that perfectly matches their taste.

USER PSYCHOLOGICAL PROFILE:
{psychological_profile}

CURRENT MUSICAL CONTEXT:
- Current track: {music_data['current_track']['item']['name'] + ' by ' + music_data['current_track']['item']['artists'][0]['name']
                if isinstance(music_data['current_track'], dict) and music_data['current_track'].get('item')
                else 'None'}
- Recent tracks: {[f"{track['track']['name']} by {track['track']['artists'][0]['name']}" for track in music_data['recent_tracks'][:5]]}
- Top artists: {[artist['name'] for artist in music_data['top_artists']['short_term'][:5]]}
- Top genres: {music_data['top_genres'][:5]}

SESSION CONTEXT:
{f"User adjustment: {session_adjustment}" if session_adjustment else "No specific session adjustment"}

STRICT AVOIDANCE LIST (DO NOT RECOMMEND ANY OF THESE):
{blacklist_tracks[:20]}  

{diversity_warning}

REQUIREMENTS:
1. Recommend exactly ONE song
2. Must be a real, existing song available on Spotify
3. Should perfectly match their psychological profile and current taste
4. Must NOT be any song from the avoidance list above
5. Format: "Song Title" by Artist Name

Respond with ONLY the song recommendation in this exact format:
"Song Title" by Artist Name

Do not include any explanation, reasoning, or additional text.
"""

        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            recommendation_response = model.generate_content(recommendation_prompt)
            ai_recommendation_text = recommendation_response.text.strip() if recommendation_response and recommendation_response.text else None
            
            if not ai_recommendation_text:
                raise Exception("Empty AI recommendation response")
                
            logger.info(f"AI recommended: {ai_recommendation_text}")
            
        except Exception as e:
            from utils.ai_analysis import check_rate_limit_error
            if check_rate_limit_error(e):
                logger.warning(f"STANDARD: Gemini rate limit detected during recommendation - {str(e)}")
                return {
                    'success': False, 
                    'message': 'You\'ve reached your Gemini API rate limit. Please wait a few minutes before requesting another recommendation.',
                    'rate_limit_error': True,
                    'suggested_wait_time': '2-3 minutes'
                }
            
            logger.error(f"AI recommendation generation failed: {e}")
            return {
                'success': False, 
                'message': 'Failed to generate AI recommendation. Please try again.'
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
        
        # Search for the track on Spotify
        logger.info(f"STANDARD: Searching Spotify for: {song_title} by {artist_name}")
        
        # Try exact search first
        search_query = f'track:"{song_title}" artist:"{artist_name}"'
        search_results = spotify_client.search_tracks(search_query, limit=5)
        
        if not search_results or not search_results.get('tracks', {}).get('items'):
            # Try broader search
            logger.info("STANDARD: Exact search failed, trying broader search")
            search_query = f"{song_title} {artist_name}"
            search_results = spotify_client.search_tracks(search_query, limit=5)
        
        if not search_results or not search_results.get('tracks', {}).get('items'):
            logger.error(f"STANDARD: Could not find track on Spotify: {song_title} by {artist_name}")
            return {
                'success': False, 
                'message': f'Could not find "{song_title}" by {artist_name} on Spotify. Please try again.'
            }
        
        # Use structured LLM to select best match if multiple results
        selection_result = structured_llm.select_spotify_result(
            genai.GenerativeModel('gemini-1.5-flash'), song_title, artist_name, search_results['tracks']['items']
        )
        
        selected_track = selection_result.selected_result
        logger.info(f"STANDARD: Selected track: {selected_track.track_name} by {selected_track.artist_name}")
        
        recommendation_duration = time.time() - recommendation_start
        logger.info(f"STANDARD: AI recommendation complete - {recommendation_duration:.2f}s")
        
        # Generate detailed reasoning for the recommendation
        reasoning_prompt = f"""
Explain in 2-3 sentences why you recommended "{selected_track.track_name}" by {selected_track.artist_name} for this user.

Consider their:
- Psychological profile: {psychological_profile}
- Current musical context: {music_data['current_track']['item']['name']
                          if isinstance(music_data['current_track'], dict) and music_data['current_track'].get('item')
                          else 'None'}
- Session context: {session_adjustment if session_adjustment else 'General discovery'}

Keep it personal and insightful.
"""
        
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            reasoning_response = model.generate_content(reasoning_prompt)
            ai_reasoning = reasoning_response.text.strip() if reasoning_response and reasoning_response.text else f"This track perfectly complements your musical taste and current listening mood."
        except Exception as e:
            logger.warning(f"Failed to generate reasoning: {e}")
            ai_reasoning = f"This track was selected based on your musical preferences and listening patterns."
        
        # Save recommendation to database
        recommendation = Recommendation(
            user_id=user.id,
            track_name=selected_track.track_name,
            artist_name=selected_track.artist_name,
            track_uri=selected_track.track_uri,
            album_name=selected_track.album_name,
            ai_reasoning=ai_reasoning,
            psychological_analysis=psychological_profile,
            listening_data_snapshot=json.dumps({
                'recent_tracks_count': len(music_data['recent_tracks']),
                'top_genres': music_data['top_genres'][:5],
                'current_track': music_data['current_track']['item']['name']
                                if isinstance(music_data['current_track'], dict) and music_data['current_track'].get('item')
                                else None
            }),
            session_adjustment=session_adjustment,
            recommendation_method='standard'
        )
        db.session.add(recommendation)
        db.session.commit()
        
        logger.info(f"STANDARD: Recommendation saved to database with ID {recommendation.id}")
        
        # Return successful recommendation
        return {
            'success': True,
            'track': {
                'name': selected_track.track_name,
                'artist': selected_track.artist_name,
                'album': selected_track.album_name,
                'uri': selected_track.track_uri,
                'external_url': selected_track.external_url,
                'preview_url': selected_track.preview_url,
                'image_url': selected_track.album_image_url
            },
            'reasoning': ai_reasoning,
            'recommendation_id': recommendation.id,
            'performance': {
                'data_collection': round(data_collection_duration, 2),
                'profile_generation': round(profile_duration if 'profile_duration' in locals() else 0, 2),
                'recommendation_generation': round(recommendation_duration, 2),
                'duplicate_prevention': {
                    'tracks_avoided': len(blacklist_tracks),
                    'total_recent_recommendations': rec_tracking['total_count']
                },
                'used_comprehensive_analysis': bool(cached_analysis and cached_analysis.get_data().get('analysis_ready', False) if cached_analysis else False),
                'used_basic_analysis': bool(not cached_analysis and cached_psych_analysis and psych_cache_valid if 'cached_psych_analysis' in locals() and 'psych_cache_valid' in locals() else False)
            },
            'psychological_analysis': psychological_profile,
            'session_context': session_adjustment if session_adjustment else None
        }
        
    except Exception as e:
        logger.error(f"AI recommendation generation failed: {str(e)}", exc_info=True)
        return {
            'success': False, 
            'message': f'AI recommendation failed: {str(e)}'
        } 