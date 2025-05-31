"""
AI-powered recommendation and analysis routes.

This module handles all AI-related functionality including recommendations,
psychological analysis, musical analysis, and feedback processing.
"""

from flask import Blueprint, request, session, jsonify, render_template, current_app
from datetime import datetime
from models import User, Recommendation, UserFeedback, UserAnalysis, db
from spotify_client import SpotifyClient
from utils.spotify_auth import refresh_user_token
from utils.ai_analysis import (
    generate_ultra_detailed_psychological_analysis,
    generate_ai_music_analysis,
    configure_gemini,
    check_rate_limit_error,
    extract_rate_limit_details
)
from utils.recommendations import generate_ai_recommendation, get_enhanced_recent_recommendations
from utils.feedback import process_feedback_insights
import time
import json
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Create AI blueprint
ai_bp = Blueprint('ai', __name__)

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

@ai_bp.route('/ai-recommendation', methods=['POST'])
def ai_recommendation():
    """Enhanced standard AI recommendation with improved duplicate prevention"""
    user = require_auth()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    # Get request data safely
    request_data = request.get_json() or {}
    
    # Get Gemini API key from request
    gemini_api_key = request_data.get('gemini_api_key') or request_data.get('custom_gemini_key')
    
    if not gemini_api_key:
        return jsonify({
            'success': False, 
            'message': 'Gemini API key required for AI recommendations. Please add your API key in the settings.',
            'requires_api_key': True
        }), 400
    
    # Configure Gemini
    if not configure_gemini(gemini_api_key):
        return jsonify({
            'success': False, 
            'message': 'Failed to configure Gemini API',
            'api_error': True
        }), 400
    
    # Get session adjustment if provided
    session_adjustment = request_data.get('session_adjustment', '').strip()
    if session_adjustment:
        session['session_adjustment'] = session_adjustment
    else:
        session_adjustment = session.get('session_adjustment', '')
    
    # Rate limiting
    current_time = time.time()
    last_rec_time = session.get('last_recommendation_time', 0)
    if current_time - last_rec_time < 2:  # 2 second minimum between recommendations
        return jsonify({
            'success': False, 
            'message': 'Please wait a moment before requesting another recommendation.'
        }), 429
    
    try:
        total_start_time = time.time()
        
        # Generate recommendation using utility function
        result = generate_ai_recommendation(user, gemini_api_key, session_adjustment)
        
        if result['success']:
            # Store recommendation ID in session for feedback
            session['current_recommendation_id'] = result['recommendation_id']
            session['last_recommendation_time'] = current_time
            
            total_duration = time.time() - total_start_time
            
            # Transform the response to match frontend expectations
            frontend_response = {
                'success': True,
                'track': {
                    'name': result['track_name'],
                    'artist': result['artist_name'],
                    'album': result['album_name'],
                    'uri': result['track_uri'],
                    'image': result.get('album_image_url'),
                    'external_url': f"https://open.spotify.com/track/{result['track_uri'].split(':')[-1]}" if result['track_uri'] else None
                },
                'ai_reasoning': result['ai_reasoning'],
                'recommendation_id': result['recommendation_id'],
                'confidence': result.get('confidence', 0),
                'match_score': result.get('match_score', 0),
                'data_quality': result.get('data_quality', {}),
                'performance_stats': {
                    'total_duration': round(total_duration, 2),
                    'mode': 'enhanced'
                }
            }
            
            logger.info(f"AI recommendation completed successfully in {total_duration:.2f}s")
            return jsonify(frontend_response)
        else:
            # Check for rate limit errors
            if 'rate_limit_error' in result:
                return jsonify(result), 429
            return jsonify(result), 500
            
    except Exception as e:
        # Check for rate limit errors in main handler
        if check_rate_limit_error(e):
            logger.warning(f"AI RECOMMENDATION: Gemini rate limit detected - {str(e)}")
            return jsonify({
                'success': False, 
                'message': 'You\'ve reached your Gemini API rate limit. Please wait a few minutes before requesting another recommendation.',
                'rate_limit_error': True,
                'suggested_wait_time': '2-3 minutes'
            }), 429
        
        logger.error(f"AI recommendation failed: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'AI recommendation failed: {str(e)}'}), 500

@ai_bp.route('/chat_feedback', methods=['POST'])
def chat_feedback():
    """Process user chat feedback on recommendations"""
    user = require_auth()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        feedback_text = data.get('feedback_text', '').strip()
        recommendation_id = data.get('recommendation_id') or session.get('current_recommendation_id')
        
        if not feedback_text:
            return jsonify({'success': False, 'message': 'Feedback text is required'}), 400
        
        if not recommendation_id:
            return jsonify({'success': False, 'message': 'No active recommendation to provide feedback on'}), 400
        
        # Get the recommendation from database
        recommendation = Recommendation.query.filter_by(id=recommendation_id, user_id=user.id).first()
        
        if not recommendation:
            return jsonify({'success': False, 'message': 'Recommendation not found'}), 404
        
        # Get user's custom Gemini API key from request data
        custom_gemini_key = data.get('custom_gemini_key')
        if not custom_gemini_key:
            return jsonify({'success': False, 'message': 'AI analysis not available - API key required'}), 400
        
        # Configure Gemini for feedback analysis
        if not configure_gemini(custom_gemini_key):
            return jsonify({'success': False, 'message': 'Failed to configure Gemini API'}), 400
        
        model = genai.GenerativeModel('gemini-1.5-flash')  # Use faster model
        
        # Create simplified prompt for analyzing user feedback
        feedback_analysis_prompt = f"""Analyze this music feedback quickly:

TRACK: "{recommendation.track_name}" by {recommendation.artist_name}
FEEDBACK: "{feedback_text}"

Return JSON:
{{
    "sentiment": "positive/negative/neutral",
    "key_insights": ["insight1", "insight2"],
    "preference_note": "brief summary of what this reveals about user taste"
}}"""
        
        logger.info("FEEDBACK ANALYSIS START (OPTIMIZED)")
        feedback_start = time.time()
        
        try:
            response = model.generate_content(feedback_analysis_prompt)
            feedback_duration = time.time() - feedback_start
            
            ai_analysis = response.text.strip()
            logger.info(f"FAST FEEDBACK ANALYSIS COMPLETE - Duration: {feedback_duration:.2f}s")
            
            # Quick sentiment extraction
            sentiment = "neutral"
            ai_lower = ai_analysis.lower()
            if "positive" in ai_lower or '"sentiment": "positive"' in ai_lower:
                sentiment = "positive"
            elif "negative" in ai_lower or '"sentiment": "negative"' in ai_lower:
                sentiment = "negative"
                
        except Exception as e:
            # Check for rate limit errors
            if check_rate_limit_error(e):
                error_details = extract_rate_limit_details(str(e))
                logger.warning(f"FEEDBACK: Gemini rate limit detected - {str(e)[:200]}...")
                return jsonify({
                    'success': False, 
                    'message': f'You\'ve reached your Gemini API rate limit. Please wait {error_details["suggested_wait_time"]} before providing feedback.',
                    'rate_limit_error': True,
                    'suggested_wait_time': error_details['suggested_wait_time'],
                    'retry_seconds': error_details['retry_seconds']
                }), 429
            
            logger.error(f"Fast feedback analysis failed: {e}")
            # Fallback to simple keyword sentiment analysis
            feedback_lower = feedback_text.lower()
            if any(word in feedback_lower for word in ['love', 'great', 'awesome', 'like', 'good', 'perfect']):
                sentiment = "positive"
                ai_analysis = f"Quick analysis: User expressed positive sentiment about {recommendation.track_name}"
            elif any(word in feedback_lower for word in ['hate', 'bad', 'awful', 'dislike', 'terrible', 'boring']):
                sentiment = "negative"
                ai_analysis = f"Quick analysis: User expressed negative sentiment about {recommendation.track_name}"
            else:
                sentiment = "neutral"
                ai_analysis = f"Quick analysis: User provided neutral feedback about {recommendation.track_name}"
            feedback_duration = time.time() - feedback_start
        
        # Save feedback to database
        feedback_entry = UserFeedback(
            user_id=user.id,
            recommendation_id=recommendation_id,
            feedback_text=feedback_text,
            sentiment=sentiment,
            ai_processed_feedback=ai_analysis
        )
        db.session.add(feedback_entry)
        db.session.commit()
        
        logger.info(f"Feedback saved for user {user.id} on recommendation {recommendation_id}: {sentiment} (processed in {feedback_duration:.2f}s)")
        
        return jsonify({
            'success': True,
            'message': f'Feedback processed in {feedback_duration:.1f}s',
            'sentiment': sentiment,
            'ai_analysis': ai_analysis,
            'feedback_id': feedback_entry.id,
            'performance': {
                'duration': round(feedback_duration, 2),
                'model_used': 'gemini-1.5-flash',
                'optimization': 'fast_mode'
            }
        })
        
    except Exception as e:
        # Check for rate limit errors in overall feedback processing
        if check_rate_limit_error(e):
            error_details = extract_rate_limit_details(str(e))
            logger.warning(f"FEEDBACK: Gemini rate limit detected in main handler - {str(e)[:200]}...")
            return jsonify({
                'success': False, 
                'message': f'You\'ve reached your Gemini API rate limit. Please wait {error_details["suggested_wait_time"]} before providing feedback.',
                'rate_limit_error': True,
                'suggested_wait_time': error_details['suggested_wait_time'],
                'retry_seconds': error_details['retry_seconds']
            }), 429
        
        logger.error(f"Error processing chat feedback: {str(e)}")
        return jsonify({'success': False, 'message': 'Error processing feedback'}), 500

@ai_bp.route('/track-reasoning/<recommendation_id>')
def get_track_reasoning(recommendation_id):
    logger.debug(f'=== TRACK REASONING REQUEST ===')
    logger.debug(f'Recommendation ID: {recommendation_id}')
    logger.debug(f'User session: {session.get("user_id", "None")}')
    
    try:
        # Validate recommendation ID format
        try:
            rec_id = int(recommendation_id)
        except ValueError:
            logger.error(f'Invalid recommendation ID format: {recommendation_id}')
            return jsonify({'error': 'Invalid recommendation ID'}), 400
        
        logger.debug(f'Querying database for recommendation ID: {rec_id}')
        recommendation = Recommendation.query.get(rec_id)
        
        if not recommendation:
            logger.warning(f'No recommendation found with ID {rec_id}')
            return jsonify({'error': 'Recommendation not found'}), 404

        logger.debug(f'Found recommendation: "{recommendation.track_name}" by {recommendation.artist_name}')
        
        if not recommendation.ai_reasoning:
            logger.warning(f'Recommendation {rec_id} has no AI reasoning text')
            return jsonify({'reasoning': 'No reasoning available for this recommendation.'})
        
        return jsonify({'reasoning': recommendation.ai_reasoning})

    except Exception as e:
        logger.error(f'Error getting track reasoning for ID {recommendation_id}: {str(e)}', exc_info=True)
        return jsonify({'error': 'Failed to get track reasoning'}), 500

@ai_bp.route('/feedback-insights', methods=['GET', 'POST'])
def get_feedback_insights():
    logger.debug('Fetching feedback insights')
    
    try:
        user = require_auth()
        if not user:
            logger.warning('No user in session')
            return jsonify({'error': 'Not authenticated'}), 401

        feedbacks = UserFeedback.query.filter_by(user_id=user.id).all()
        logger.debug(f'Found {len(feedbacks)} feedback entries for user {user.id}')

        if not feedbacks:
            logger.info('No feedback found for user')
            return jsonify({'insights': None})

        # Get Gemini API key for AI analysis (if provided)
        gemini_api_key = None
        if request.method == 'POST':
            request_data = request.get_json() or {}
            gemini_api_key = request_data.get('custom_gemini_key')

        # Process feedback for insights (with or without AI)
        insights = process_feedback_insights(feedbacks, gemini_api_key)
        
        logger.debug('Successfully generated feedback insights')
        return jsonify({'insights': insights, 'ai_powered': bool(gemini_api_key)})

    except Exception as e:
        logger.error(f'Error getting feedback insights: {str(e)}', exc_info=True)
        return jsonify({'error': 'Failed to get feedback insights'}), 500

@ai_bp.route('/api/generate-psychological-analysis', methods=['POST'])
def api_generate_psychological_analysis():
    """Generate a comprehensive psychological analysis of the user's music taste"""
    try:
        user = require_auth()
        if not user:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        
        data = request.get_json()
        custom_gemini_key = data.get('custom_gemini_key') if data else None
        
        if not custom_gemini_key:
            return jsonify({'success': False, 'message': 'Gemini API key required'}), 400
        
        # Initialize Spotify client
        spotify_client = SpotifyClient(user.access_token)
        
        # Collect comprehensive music data with reduced limits to prevent timeouts
        logger.info("Collecting comprehensive music data for psychological analysis...")
        
        try:
            # Get current track and playback state with error handling
            current_track = spotify_client.get_current_track()
            playback_state = spotify_client.get_playback_state()
            
            # Get listening history and preferences with REDUCED limits
            recent_tracks = spotify_client.get_recent_tracks(limit=20)
            top_artists_short = spotify_client.get_top_artists(time_range='short_term', limit=20)
            top_artists_medium = spotify_client.get_top_artists(time_range='medium_term', limit=20)
            top_artists_long = spotify_client.get_top_artists(time_range='long_term', limit=20)
            top_tracks_short = spotify_client.get_top_tracks(time_range='short_term', limit=20)
            top_tracks_medium = spotify_client.get_top_tracks(time_range='medium_term', limit=20)
            top_tracks_long = spotify_client.get_top_tracks(time_range='long_term', limit=20)
            
            # Get saved tracks and playlists with reduced limits
            saved_tracks = spotify_client.get_saved_tracks(limit=20)
            user_playlists = spotify_client.get_user_playlists(limit=20)
            
            logger.info("Successfully collected all Spotify data for psychological analysis")
            
        except Exception as spotify_error:
            logger.error(f"Error collecting Spotify data: {str(spotify_error)}")
            return jsonify({'success': False, 'message': 'Failed to collect music data from Spotify'}), 500
        
        # Aggregate comprehensive data
        comprehensive_music_data = {
            'current_track': current_track,
            'playback_state': playback_state,
            'recent_tracks': recent_tracks,
            'top_artists': {
                'short_term': top_artists_short,
                'medium_term': top_artists_medium,
                'long_term': top_artists_long
            },
            'top_tracks': {
                'short_term': top_tracks_short,
                'medium_term': top_tracks_medium,
                'long_term': top_tracks_long
            },
            'saved_tracks': saved_tracks,
            'user_playlists': user_playlists
        }
        
        # Generate psychological analysis
        try:
            # Check for cached detailed psychological analysis first - now from database
            cached_analysis = UserAnalysis.get_latest_analysis(user.id, 'psychological', max_age_hours=24)
            
            if cached_analysis:
                logger.info("Using cached detailed psychological analysis from database")
                return jsonify({'success': True, 'analysis': cached_analysis.get_data(), 'from_cache': True})
            
            # Generate new analysis
            analysis = generate_ultra_detailed_psychological_analysis(comprehensive_music_data, custom_gemini_key)
            
            if analysis:
                # Save the detailed analysis to database
                UserAnalysis.save_analysis(user.id, 'psychological', analysis)
                logger.info("Psychological analysis generated successfully and saved to database")
                
                # Also update the basic cache used by recommendations for immediate use
                if analysis.get('psychological_profile', {}).get('core_personality'):
                    basic_summary = analysis['psychological_profile']['core_personality'][:200] + "..."
                    session['cached_psychological_analysis'] = basic_summary
                    session['cached_psychological_timestamp'] = time.time()
                    logger.info("Updated basic psychological cache for immediate recommendations")
                
                return jsonify({'success': True, 'analysis': analysis, 'from_cache': False})
            else:
                logger.error("Failed to generate psychological analysis")
                return jsonify({'success': False, 'message': 'Failed to generate analysis'}), 500
                
        except Exception as analysis_error:
            logger.error(f"Error during psychological analysis generation: {str(analysis_error)}")
            return jsonify({'success': False, 'message': f'Analysis generation failed: {str(analysis_error)}'}), 500
            
    except Exception as e:
        logger.error(f"Error in psychological analysis API: {str(e)}")
        return jsonify({'success': False, 'message': f'Internal server error: {str(e)}'}), 500

@ai_bp.route('/api/generate-musical-analysis', methods=['POST'])
def api_generate_musical_analysis():
    """Generate comprehensive musical analysis for the user"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'})
        
        custom_gemini_key = data.get('custom_gemini_key')
        if not custom_gemini_key:
            return jsonify({'success': False, 'message': 'Gemini API key is required'})
        
        user = require_auth()
        if not user:
            return jsonify({'success': False, 'message': 'User not authenticated'})
        
        # Check for cached musical analysis first to avoid unnecessary API calls
        cached_musical_analysis = UserAnalysis.get_latest_analysis(user.id, 'musical', max_age_hours=24)
        
        if cached_musical_analysis:
            logger.info("Using cached musical analysis from database")
            return jsonify({'success': True, 'analysis': cached_musical_analysis.get_data(), 'from_cache': True})
        
        spotify_client = SpotifyClient(user.access_token)
        
        # Generate comprehensive music analysis
        try:
            music_data = {
                'top_artists': spotify_client.get_top_artists(time_range='medium_term', limit=50),
                'top_tracks': spotify_client.get_top_tracks(time_range='medium_term', limit=50),
                'recent_tracks': spotify_client.get_recently_played(limit=50),
                'saved_tracks': spotify_client.get_saved_tracks(limit=50),
                'playlists': spotify_client.get_user_playlists(limit=30)
            }
        except Exception as spotify_error:
            logger.error(f"Error collecting Spotify data for musical analysis: {str(spotify_error)}")
            return jsonify({'success': False, 'message': 'Failed to collect music data from Spotify'})
        
        # Generate analysis using Gemini
        try:
            analysis = generate_ai_music_analysis(music_data, custom_gemini_key)
            
            if analysis:
                # Save the musical analysis to database
                UserAnalysis.save_analysis(user.id, 'musical', analysis)
                logger.info("Musical analysis generated successfully and saved to database")
                
                return jsonify({
                    'success': True,
                    'analysis': analysis,
                    'from_cache': False
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Failed to generate musical analysis. Please try again.'
                })
        
        except Exception as analysis_error:
            # Check for rate limit errors
            if check_rate_limit_error(analysis_error):
                error_details = extract_rate_limit_details(str(analysis_error))
                
                logger.warning(f"MUSICAL ANALYSIS: Gemini rate limit detected - {str(analysis_error)[:200]}...")
                return jsonify({
                    'success': False, 
                    'message': f'You\'ve reached your Gemini API rate limit. Please wait {error_details["suggested_wait_time"]} before generating another analysis.',
                    'rate_limit_error': True,
                    'suggested_wait_time': error_details['suggested_wait_time'],
                    'retry_seconds': error_details['retry_seconds']
                }), 429
            
            logger.error(f"Musical analysis generation failed: {str(analysis_error)}")
            return jsonify({
                'success': False, 
                'message': f'Analysis generation failed: {str(analysis_error)}'
            })
        
    except Exception as e:
        # Check for rate limit errors in main handler
        if check_rate_limit_error(e):
            error_details = extract_rate_limit_details(str(e))
            
            logger.warning(f"MUSICAL ANALYSIS: Gemini rate limit detected in main handler - {str(e)[:200]}...")
            return jsonify({
                'success': False, 
                'message': f'You\'ve reached your Gemini API rate limit. Please wait {error_details["suggested_wait_time"]} before generating another analysis.',
                'rate_limit_error': True,
                'suggested_wait_time': error_details['suggested_wait_time'],
                'retry_seconds': error_details['retry_seconds']
            }), 429
        
        logger.error(f"Musical analysis generation failed: {str(e)}")
        return jsonify({'success': False, 'message': f'Analysis generation failed: {str(e)}'})

@ai_bp.route('/api/clear-analysis-cache', methods=['POST'])
def clear_analysis_cache():
    """Clear cached analyses to force fresh generation"""
    try:
        user = require_auth()
        if not user:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
        # Clear all analysis caches
        caches_cleared = []
        
        # Clear session caches
        if 'cached_psychological_analysis' in session:
            session.pop('cached_psychological_analysis', None)
            session.pop('cached_psychological_timestamp', None)
            caches_cleared.append('basic_psychological_session')
        
        # Clear database analyses
        db_analyses = UserAnalysis.query.filter_by(user_id=user.id).all()
        for analysis in db_analyses:
            caches_cleared.append(f'{analysis.analysis_type}_database')
            db.session.delete(analysis)
        
        if db_analyses:
            db.session.commit()
        
        logger.info(f"Cleared analysis caches: {caches_cleared}")
        
        return jsonify({
            'success': True,
            'message': f'Cleared {len(caches_cleared)} cache(s)',
            'caches_cleared': caches_cleared
        })
        
    except Exception as e:
        logger.error(f"Error clearing analysis cache: {str(e)}")
        return jsonify({'success': False, 'message': f'Failed to clear cache: {str(e)}'}), 500 