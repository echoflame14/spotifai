"""
API routes for various endpoints.

This module handles miscellaneous API endpoints that don't fit in other categories.
"""

from flask import Blueprint, request, session, jsonify
from app import app
from models import User
from spotify_client import SpotifyClient
from utils.spotify_auth import refresh_user_token
from utils.ai_analysis import configure_gemini
import time
import json
import logging
import google.generativeai as genai

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
        
        if user_id:
            user = User.query.get(user_id)
            if user:
                # CHECK FOR COMPREHENSIVE PSYCHOLOGICAL ANALYSIS FIRST
                from models import UserAnalysis
                cached_analysis = UserAnalysis.get_latest_analysis(user.id, 'psychological', max_age_hours=24)
                
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
                    spotify_client = SpotifyClient(user.access_token)
                    try:
                        # Try to get recent listening context
                        recent_tracks = spotify_client.get_recently_played(limit=5)
                        if recent_tracks and 'items' in recent_tracks and recent_tracks['items']:
                            recent_artists = []
                            for item in recent_tracks['items'][:3]:
                                track = item.get('track', {})
                                if track.get('artists'):
                                    recent_artists.append(track['artists'][0]['name'])
                            user_context = f"Recently listened to artists like {', '.join(recent_artists[:3])}"
                            logger.info("LOADING: Using basic listening context for loading phrases")
                    except:
                        # If we can't get recent tracks, use generic context
                        user_context = "music lover"
                        logger.info("LOADING: Using generic context for loading phrases")
        
        # Configure Gemini
        if not configure_gemini(custom_gemini_key):
            return jsonify({'success': False, 'message': 'Failed to configure Gemini API'})
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Create enhanced prompt for loading phrases with psychological context
        if comprehensive_analysis:
            prompt = f"""Generate 1 exceptionally creative and personalized funny one-liner for a music recommendation AI loading screen.

USER PSYCHOLOGICAL CONTEXT:
{user_context}

COMPREHENSIVE ANALYSIS INSIGHTS:
- Musical Identity: {comprehensive_analysis.get('musical_identity', {}).get('sophistication_level', 'Music enthusiast')}
- Discovery Style: {comprehensive_analysis.get('behavioral_insights', {}).get('discovery_preferences', 'Open to new music')}
- Listening Psychology: {comprehensive_analysis.get('listening_psychology', {}).get('mood_regulation', 'Uses music for emotional balance')}
- Unique Traits: {', '.join(comprehensive_analysis.get('summary_insights', {}).get('unique_traits', ['Musical explorer'])[:2])}

PERSONALIZATION INSTRUCTIONS:
- Reference their specific musical sophistication level and discovery preferences
- Align with their listening psychology and unique traits
- Make it feel like the AI truly understands their musical personality
- Use their psychological profile to craft a joke that resonates

AVOID these repetitive themes:
- Generic "analyzing your taste" messages
- Overused "musical DNA" references
- Basic "crazy" or "wild" taste comments

Instead, be creative with these diverse themes (pick ONE that fits their psychology):
- Music discovery adventure metaphors (for exploratory users)
- AI robot/technology humor about music (for tech-savvy users)
- Studio/recording session jokes (for sophisticated listeners)
- Musical instrument humor (for technically-minded users)
- Genre-mixing comedy (for diverse taste users)
- Artist collaboration jokes (for social listeners)
- Music production humor (for detail-oriented users)

Requirements:
- Create 1 outstanding one-sentence headline (6-12 words)
- Make it genuinely funny with a clever punchline or twist
- Personalize it to their specific psychological profile above
- Make it feel like the AI has a quirky personality AND knows them personally
- Keep it encouraging and music-focused

Return ONLY a JSON object with this exact structure:
{{
    "phrases": [
        {{
            "headline": "One personalized, creative, and funny sentence"
        }}
    ]
}}"""
        else:
            # Fallback prompt for users without comprehensive analysis
            prompt = f"""Generate 1 exceptionally creative and varied funny one-liner for a music recommendation AI loading screen.
The user is a {user_context if user_context else "music enthusiast"}.

AVOID these repetitive themes:
- Anything about "crazy" or "wild" tastes
- Generic "analyzing your taste" messages
- Overused "musical DNA" references

Instead, be creative with these diverse themes (pick ONE):
- Music discovery adventure metaphors
- AI robot/technology humor about music
- Musical journey/quest references  
- Studio/recording session jokes
- Concert/performance analogies
- Music streaming/technology puns
- Musical instrument humor
- Genre-mixing comedy
- Artist collaboration jokes
- Music production humor

Requirements:
- Create 1 outstanding one-sentence headline (6-12 words)
- Make it genuinely funny with a clever punchline or twist
- Use fresh, original humor - avoid clichés
- Pick a completely different theme than typical "analyzing taste" messages
- Make it feel like the AI has a quirky personality
- Keep it encouraging and music-focused

Return ONLY a JSON object with this exact structure:
{{
    "phrases": [
        {{
            "headline": "One fresh, creative, and funny sentence"
        }}
    ]
}}"""

        start_time = time.time()
        
        # Generate phrases
        response = model.generate_content(prompt)
        
        duration = time.time() - start_time
        logger.info(f"Loading phrases generated in {duration:.2f}s")
        
        # Parse response
        try:
            # Extract JSON from response
            response_text = response.text.strip()
            
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
            
            return jsonify({
                'success': True,
                'phrases': phrases_data['phrases'],
                'generation_time': duration
            })
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse loading phrases response: {str(e)}")
            # Return fallback phrases
            fallback_phrases = [
                {
                    "headline": "Tuning the recommendation algorithm like a vintage guitar"
                }
            ]
            
            return jsonify({
                'success': True,
                'phrases': fallback_phrases,
                'generation_time': duration,
                'fallback_used': True
            })
            
    except Exception as e:
        logger.error(f"Loading phrases generation failed: {str(e)}")
        
        # Return fallback phrases on error
        fallback_phrases = [
            {
                "headline": "Teaching robots to appreciate good music takes time"
            }
        ]
        
        return jsonify({
            'success': True,
            'phrases': fallback_phrases,
            'fallback_used': True,
            'error': str(e)
        }) 