"""
API routes for various endpoints.

This module handles miscellaneous API endpoints that don't fit in other categories.
"""

from flask import Blueprint, request, session, jsonify, current_app
from models import User
from spotify_client import SpotifyClient
from utils.spotify_auth import refresh_user_token
from utils.ai_analysis import configure_gemini
import time
import json
import logging
import google.generativeai as genai
from utils.recommendations import get_user_feedback_insights

logger = logging.getLogger(__name__)

# Create API blueprint
api_bp = Blueprint('api', __name__)

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

@api_bp.route('/api/current-track')
def api_current_track():
    """API endpoint to get current track information"""
    try:
        user = require_auth()
        if not user:
            return jsonify({'error': 'Not authenticated'}), 401
        
        spotify_client = SpotifyClient(user.access_token)
        current_track = spotify_client.get_current_track()
        
        if current_track:
            return jsonify({
                'success': True,
                'track': current_track
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No track currently playing'
            })
            
    except Exception as e:
        logger.error(f"Error getting current track: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/api/performance-toggle', methods=['POST'])
def performance_toggle():
    """API endpoint to get performance configuration for AI recommendations"""
    try:
        # Default configuration
        config = {
            'endpoint': '/ai-recommendation',
            'mode': 'standard',
            'lightning_enabled': False,
            'cached_data': False,
            'cached_profile': False
        }
        
        # Check if lightning mode should be enabled based on various factors
        if 'user_id' in session:
            user = User.query.get(session['user_id'])
            if user:
                # Enable lightning mode for certain conditions
                from models import Recommendation
                from datetime import datetime, timedelta
                recent_recommendations = Recommendation.query.filter_by(
                    user_id=user.id
                ).filter(
                    Recommendation.created_at > datetime.utcnow() - timedelta(hours=1)
                ).count()
                
                if recent_recommendations > 0:
                    config['lightning_enabled'] = True
                    config['mode'] = 'lightning'
                    config['cached_data'] = True
                    
                # Check if user has recent profile data
                if recent_recommendations > 2:
                    config['cached_profile'] = True
        
        return jsonify(config)
        
    except Exception as e:
        logger.error(f"Error in performance toggle: {str(e)}")
        # Return default safe configuration on error
        return jsonify({
            'endpoint': '/ai-recommendation',
            'mode': 'standard',
            'lightning_enabled': False,
            'cached_data': False,
            'cached_profile': False
        })

@api_bp.route('/api/loading-phrases', methods=['POST'])
def api_loading_phrases():
    """Generate dynamic loading phrases for the spinner using Gemini AI"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'})
        
        custom_gemini_key = data.get('custom_gemini_key')
        if not custom_gemini_key:
            return jsonify({'success': False, 'message': 'Gemini API key is required'})
        
        # Get user from session for personalization
        user_id = session.get('user_id')
        user_context = ""
        comprehensive_analysis = None
        user = None
        used_phrases = []
        
        if user_id:
            user = User.query.get(user_id)
            if user:
                # Get previously used phrases to avoid repetition
                used_phrases = user.get_used_loading_phrases()
                logger.info(f"User has {len(used_phrases)} previously used loading phrases")
                
                # CHECK FOR COMPREHENSIVE PSYCHOLOGICAL ANALYSIS FIRST
                from models import UserAnalysis
                cached_analysis = UserAnalysis.get_latest_analysis(user.id, 'psychological', max_age_hours=24)
                
                # ENHANCED: Also get feedback insights for loading phrase personalization
                feedback_insights = get_user_feedback_insights(user, limit=10)
                logger.info(f"LOADING: Retrieved feedback insights - {feedback_insights['summary']}")
                
                # ENHANCED: Get recent tracks for more personalized loading phrases
                recent_tracks_context = ""
                spotify_client = SpotifyClient(user.access_token)
                try:
                    recent_tracks = spotify_client.get_recently_played(limit=50)
                    if recent_tracks and 'items' in recent_tracks and recent_tracks['items']:
                        # Format recent tracks for prompt
                        recent_songs = []
                        for item in recent_tracks['items'][:50]:
                            track = item.get('track', {})
                            if track and track.get('name') and track.get('artists'):
                                track_name = track['name']
                                artist_name = track['artists'][0]['name']
                                recent_songs.append(f'"{track_name}" by {artist_name}')
                        
                        if recent_songs:
                            # ENHANCED: Limit to 10 most recent for prompt efficiency
                            recent_tracks_context = f"""
RECENT LISTENING HISTORY (10 MOST RECENT TRACKS):
{chr(10).join([f'{i+1}. {song}' for i, song in enumerate(recent_songs[:10])])}"""
                            logger.info(f"LOADING: Retrieved {len(recent_songs[:10])} recent tracks for personalization")
                    else:
                        recent_tracks_context = "\nRECENT TRACKS: No recent listening data available"
                        logger.info("LOADING: No recent tracks found")
                except Exception as e:
                    recent_tracks_context = "\nRECENT TRACKS: Unable to retrieve recent listening data"
                    logger.warning(f"LOADING: Failed to get recent tracks: {e}")
                
                if cached_analysis:
                    analysis_data = cached_analysis.get_data()
                    if isinstance(analysis_data, dict) and analysis_data.get('analysis_ready'):
                        logger.info("Using comprehensive psychological analysis for personalized loading phrases")
                        comprehensive_analysis = analysis_data
                        
                        # Extract key personality traits for loading phrase personalization
                        personality = analysis_data.get('psychological_profile', {}).get('core_personality', '')
                        musical_identity = analysis_data.get('musical_identity', {}).get('sophistication_level', '')
                        discovery_style = analysis_data.get('behavioral_insights', {}).get('discovery_preferences', '')
                        
                        user_context = f"User with {personality[:100]} musical personality, {musical_identity[:50]} sophistication, who {discovery_style[:100]}"
                        logger.info("LOADING: Using comprehensive analysis for personalized loading phrases")
                
                if not comprehensive_analysis:
                    # Fallback to basic recent listening context
                    try:
                        # Try to get recent listening context (using already fetched data)
                        if recent_tracks_context and "RECENT LISTENING HISTORY" in recent_tracks_context:
                            # Use the recent tracks we already fetched for context
                            user_context = f"Recently listened to music including recent tracks analysis"
                            logger.info("LOADING: Using comprehensive recent tracks context for loading phrases")
                        else:
                            # If we couldn't get recent tracks, use generic context
                            user_context = "music lover"
                            logger.info("LOADING: Using generic context for loading phrases")
                    except:
                        # If we can't get recent tracks, use generic context
                        user_context = "music lover"
                        logger.info("LOADING: Using generic context for loading phrases")
        
        # Configure Gemini
        if not configure_gemini(custom_gemini_key):
            return jsonify({'success': False, 'message': 'Failed to configure Gemini API'})
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Create a list of used phrases for the prompt
        used_phrases_text = ""
        if used_phrases:
            used_phrases_text = f"\n\nDO NOT REPEAT these previously used phrases:\n{chr(10).join([f'- {phrase}' for phrase in used_phrases[-20:]])}\n"
        
        # Create enhanced prompt for loading phrases with psychological context
        if comprehensive_analysis:
            # ENHANCED: Create feedback learning context for loading phrases
            feedback_context = ""
            if feedback_insights and feedback_insights.get('has_feedback'):
                feedback_context = f"""
FEEDBACK LEARNING CONTEXT:
- Total Feedback Analyzed: {feedback_insights.get('total_feedback', 0)} entries
- Success Rate: {feedback_insights.get('positive_count', 0)}/{feedback_insights.get('total_feedback', 0)} positive responses
- Learning Status: {feedback_insights.get('learning_note', 'Learning phase')}
- Positive Patterns: {', '.join(feedback_insights.get('positive_patterns', [])[:2])}
- Negative Patterns: {', '.join(feedback_insights.get('negative_patterns', [])[:2])}"""
            else:
                feedback_context = "\nFEEDBACK LEARNING: No feedback data yet - initial recommendation"
            
            prompt = f"""Generate 1 creative, personalized loading phrase for a music AI.

USER CONTEXT: {user_context}
{feedback_context}
{recent_tracks_context}

INSTRUCTIONS:
- Create ONE funny 6-12 word headline
- Reference their recent tracks or feedback learning if available  
- Make it feel like the AI knows them personally
- Be witty but encouraging
{used_phrases_text}

EXAMPLES:
- "Debugging after your brutal feedback on my last pick..."
- "Noticed your Kanye obsession - calculating ego-friendly recommendations..."
- "Learning from your 85% approval rate to avoid disasters..."

Return ONLY this JSON:
{{
    "phrases": [
        {{
            "headline": "Your one creative, personalized sentence here"
        }}
    ]
}}"""
        else:
            # ENHANCED: Include basic feedback insights even for fallback prompt
            basic_feedback_context = ""
            if feedback_insights and feedback_insights.get('has_feedback'):
                success_rate = int((feedback_insights.get('positive_count', 0) / feedback_insights.get('total_feedback', 1)) * 100)
                basic_feedback_context = f"""
FEEDBACK LEARNING STATUS:
- Total Feedback: {feedback_insights.get('total_feedback', 0)} responses
- Success Rate: {success_rate}% positive feedback
- Learning Note: {feedback_insights.get('learning_note', 'Learning phase')}"""
            else:
                basic_feedback_context = "\nFEEDBACK STATUS: No previous feedback - fresh start!"
            
            # Fallback prompt for users without comprehensive analysis
            prompt = f"""Generate 1 creative loading phrase for a music AI.

USER: {user_context if user_context else "music enthusiast"}
{basic_feedback_context}
{recent_tracks_context}

INSTRUCTIONS:
- Create ONE funny 6-12 word headline
- Reference recent tracks or feedback if available
- Be witty and personal
{used_phrases_text}

EXAMPLES:
- "Getting better at reading your musical mind..."
- "Remembering you actually liked that last song..."
- "Noticed your Taylor Swift marathon this week..."

Return ONLY this JSON:
{{
    "phrases": [
        {{
            "headline": "Your creative, personalized sentence here"
        }}
    ]
}}"""

        start_time = time.time()
        
        # Generate phrases
        response = model.generate_content(prompt)
        
        duration = time.time() - start_time
        logger.info(f"Loading phrases generated in {duration:.2f}s")
        
        # Log the raw response for debugging
        logger.info(f"LOADING PHRASES: Raw response: {response.text[:200]}...")
        
        # Parse response
        try:
            # Extract JSON from response
            response_text = response.text.strip()
            
            # Log the response text before parsing
            logger.info(f"LOADING PHRASES: Response text to parse: {response_text[:100]}...")
            
            # Remove markdown code blocks if present
            if response_text.startswith('```json'):
                response_text = response_text[7:-3]
            elif response_text.startswith('```'):
                response_text = response_text[3:-3]
            
            phrases_data = json.loads(response_text)
            
            # Validate structure
            if 'phrases' not in phrases_data or len(phrases_data['phrases']) != 1:
                raise ValueError("Invalid phrases structure")
            
            for phrase in phrases_data['phrases']:
                if 'headline' not in phrase:
                    raise ValueError("Missing headline in phrase")
            
            # Add the generated phrase to the user's used phrases list
            generated_phrase = phrases_data['phrases'][0]['headline']
            if user:
                was_added = user.add_used_loading_phrase(generated_phrase)
                logger.info(f"Added new loading phrase to user's list: '{generated_phrase}' (was new: {was_added})")
            
            logger.info(f"LOADING PHRASES: Successfully generated: '{generated_phrase}'")
            
            return jsonify({
                'success': True,
                'phrases': phrases_data['phrases'],
                'generation_time': duration,
                'phrases_avoided': len(used_phrases)
            })
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse loading phrases response: {str(e)}")
            logger.error(f"Raw response was: {response.text}")
            # Return fallback phrases
            fallback_phrases = [
                {
                    "headline": "Tuning the recommendation algorithm like a vintage guitar"
                }
            ]
            
            # Still add the fallback phrase to the user's list if applicable
            if user:
                user.add_used_loading_phrase(fallback_phrases[0]['headline'])
                logger.info(f"Added fallback loading phrase to user's list")
            
            return jsonify({
                'success': True,
                'phrases': fallback_phrases,
                'generation_time': duration,
                'fallback_used': True,
                'phrases_avoided': len(used_phrases)
            })
            
    except Exception as e:
        # Check for rate limit errors specifically
        from utils.ai_analysis import check_rate_limit_error, extract_rate_limit_details
        if check_rate_limit_error(e):
            error_details = extract_rate_limit_details(str(e))
            logger.warning(f"LOADING PHRASES: Gemini rate limit detected - {str(e)[:200]}...")
            
            # Return fallback phrases for rate limit errors
            fallback_phrases = [
                {
                    "headline": "Taking a brief pause to respect the API rate limits"
                }
            ]
            
            if user:
                user.add_used_loading_phrase(fallback_phrases[0]['headline'])
                logger.info("Added rate-limit fallback phrase to user's list")
            
            return jsonify({
                'success': True,
                'phrases': fallback_phrases,
                'generation_time': 0,
                'fallback_used': True,
                'rate_limit_error': True,
                'suggested_wait_time': error_details['suggested_wait_time']
            })
        
        logger.error(f"Loading phrases generation failed: {str(e)}")
        
        # Return fallback phrases on error
        fallback_phrases = [
            {
                "headline": "Tuning the recommendation algorithm like a vintage guitar"
            }
        ]
        
        return jsonify({
            'success': True,
            'phrases': fallback_phrases,
            'generation_time': 0,
            'fallback_used': True
        })

@api_bp.route('/api/clear-loading-phrases', methods=['POST'])
def clear_loading_phrases():
    """Clear the user's used loading phrases list"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Get current count before clearing
        used_phrases = user.get_used_loading_phrases()
        phrase_count = len(used_phrases)
        
        # Clear the used phrases list
        user.clear_used_loading_phrases()
        
        logger.info(f"Cleared {phrase_count} used loading phrases for user {user_id}")
        
        return jsonify({
            'success': True,
            'message': f'Cleared {phrase_count} used loading phrases',
            'phrases_cleared': phrase_count
        })
        
    except Exception as e:
        logger.error(f"Error clearing loading phrases: {str(e)}")
        return jsonify({'success': False, 'message': f'Failed to clear phrases: {str(e)}'}), 500

@api_bp.route('/api/used-loading-phrases', methods=['GET'])
def get_used_loading_phrases():
    """Get the current list of used loading phrases for the user (debug endpoint)"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        used_phrases = user.get_used_loading_phrases()
        
        return jsonify({
            'success': True,
            'used_phrases': used_phrases,
            'total_count': len(used_phrases)
        })
        
    except Exception as e:
        logger.error(f"Error getting used loading phrases: {str(e)}")
        return jsonify({'success': False, 'message': f'Failed to get phrases: {str(e)}'}), 500 