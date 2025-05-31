import os
import secrets
import base64
import json
import time
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, session, flash, jsonify
from urllib.parse import urlencode
import requests
from app import app, db
from models import User, UserFeedback, Recommendation
from spotify_client import SpotifyClient
import google.generativeai as genai
import logging
from structured_llm import structured_llm

# Get logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def log_llm_timing(operation_name):
    """Decorator to log LLM operation timing"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            app.logger.info(f"LLM OPERATION START: {operation_name}")
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                app.logger.info(f"LLM OPERATION SUCCESS: {operation_name} - Duration: {duration:.2f}s")
                return result
            except Exception as e:
                duration = time.time() - start_time
                app.logger.error(f"LLM OPERATION FAILED: {operation_name} - Duration: {duration:.2f}s - Error: {str(e)}")
                raise
        return wrapper
    return decorator

# Spotify OAuth configuration
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '3eab9e9e7ff444e8b0a9d1c18468b555')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
app.logger.info(f"Loaded Spotify credentials - Client ID: {SPOTIFY_CLIENT_ID[:5]}... Client Secret: {'Present' if SPOTIFY_CLIENT_SECRET else 'Missing'}")

# Dynamic redirect URI based on request
def get_redirect_uri():
    """Get the appropriate redirect URI - use consistent URL for all devices"""
    # Force Railway URL for production
    railway_url = 'https://spotifai.up.railway.app/callback'
    
    # Use environment variable if explicitly set
    env_redirect_uri = os.environ.get('SPOTIFY_REDIRECT_URI')
    if env_redirect_uri:
        app.logger.info(f"Using environment SPOTIFY_REDIRECT_URI: {env_redirect_uri}")
        return env_redirect_uri
    
    # For Railway deployment, always use the Railway URL
    from flask import request
    if request and request.host:
        if 'railway.app' in request.host:
            app.logger.info(f"Detected Railway deployment, using: {railway_url}")
            return railway_url
        else:
            # Dynamic detection for other platforms
            scheme = request.scheme
            host = request.host
            dynamic_uri = f"{scheme}://{host}/callback"
            app.logger.info(f"Using dynamic URI: {dynamic_uri}")
            return dynamic_uri
    
    # Default fallback for Railway
    app.logger.info(f"Using Railway fallback: {railway_url}")
    return railway_url

SPOTIFY_REDIRECT_URI = os.environ.get('SPOTIFY_REDIRECT_URI', 'https://spotifai.up.railway.app/callback')

@app.route('/')
def index():
    """Landing page - redirect to dashboard if authenticated, otherwise show login"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login')
def login():
    """Initiate Spotify OAuth flow"""
    try:
        # Generate random state for security
        state = secrets.token_urlsafe(16)
        session['oauth_state'] = state
        
        # Define required scopes including permissions for AI recommendations
        scope = 'user-read-private user-read-email playlist-read-private user-read-playback-state user-modify-playback-state user-read-currently-playing user-read-recently-played user-top-read user-library-read'
        
        # Get dynamic redirect URI for mobile compatibility
        redirect_uri = get_redirect_uri()
        
        # Debug: Log the parameters being used
        app.logger.info(f"=== OAUTH DEBUG INFO ===")
        app.logger.info(f"Client ID: {SPOTIFY_CLIENT_ID}")
        app.logger.info(f"Redirect URI: {redirect_uri}")
        app.logger.info(f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}")
        app.logger.info(f"Request Host: {request.host}")
        app.logger.info(f"Request URL: {request.url}")
        app.logger.info(f"State: {state}")
        app.logger.info(f"Environment SPOTIFY_REDIRECT_URI: {os.environ.get('SPOTIFY_REDIRECT_URI', 'NOT SET')}")
        app.logger.info(f"========================")
        
        # Build authorization URL
        auth_params = {
            'response_type': 'code',
            'client_id': SPOTIFY_CLIENT_ID,
            'scope': scope,
            'redirect_uri': redirect_uri,
            'state': state
        }
        
        auth_url = 'https://accounts.spotify.com/authorize?' + urlencode(auth_params)
        app.logger.info(f"Full Authorization URL: {auth_url}")
        
        return redirect(auth_url)
    except Exception as e:
        app.logger.error(f"Login initialization failed: {str(e)}")
        flash('Failed to initialize login process. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/callback')
def callback():
    """Handle Spotify OAuth callback"""
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        
        app.logger.info(f"=== CALLBACK DEBUG INFO ===")
        app.logger.info(f"Received code: {'Yes' if code else 'No'}")
        app.logger.info(f"Received state: {state}")
        app.logger.info(f"Received error: {error}")
        app.logger.info(f"Session state: {session.get('oauth_state')}")
        app.logger.info(f"Request URL: {request.url}")
        app.logger.info(f"Request headers: {dict(request.headers)}")
        app.logger.info(f"========================")
        
        # Check for errors
        if error:
            app.logger.error(f"Authorization failed with error: {error}")
            flash(f'Authorization failed: {error}', 'error')
            return redirect(url_for('index'))
        
        # Verify state parameter
        if not state or state != session.get('oauth_state'):
            app.logger.error(f"State mismatch - Received: {state}, Expected: {session.get('oauth_state')}")
            flash('Invalid state parameter. Please try again.', 'error')
            return redirect(url_for('index'))
        
        # Exchange code for access token
        token_url = 'https://accounts.spotify.com/api/token'
        
        # Prepare authorization header
        auth_string = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
        auth_bytes = auth_string.encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
        
        headers = {
            'Authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        # Use the same dynamic redirect URI for consistency
        redirect_uri = get_redirect_uri()
        
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri
        }
        
        app.logger.info("=== TOKEN EXCHANGE DEBUG INFO ===")
        app.logger.info(f"Token URL: {token_url}")
        app.logger.info(f"Redirect URI: {redirect_uri}")
        app.logger.info(f"Client ID: {SPOTIFY_CLIENT_ID}")
        app.logger.info(f"Client Secret length: {len(SPOTIFY_CLIENT_SECRET) if SPOTIFY_CLIENT_SECRET else 0}")
        app.logger.info(f"Auth header length: {len(auth_b64)}")
        app.logger.info(f"Request data: {data}")
        app.logger.info(f"Request headers: {headers}")
        app.logger.info("===============================")
        
        try:
            response = requests.post(token_url, headers=headers, data=data)
            app.logger.info(f"Token exchange response status: {response.status_code}")
            
            if response.status_code != 200:
                app.logger.error(f"Token exchange failed with status {response.status_code}")
                app.logger.error(f"Response content: {response.text}")
                app.logger.error(f"Request data: {data}")
                app.logger.error(f"Auth string length: {len(auth_string)}")
                app.logger.error(f"Full response headers: {dict(response.headers)}")
                flash('Failed to authenticate with Spotify. Please try again.', 'error')
                return redirect(url_for('index'))
            
            token_data = response.json()
            app.logger.info("Successfully received token data")
            
            access_token = token_data['access_token']
            refresh_token = token_data.get('refresh_token')
            expires_in = token_data.get('expires_in', 3600)
            
            # Get user profile
            spotify_client = SpotifyClient(access_token)
            user_profile = spotify_client.get_user_profile()
            
            if not user_profile:
                app.logger.error("Failed to get user profile from Spotify")
                flash('Failed to get user profile from Spotify', 'error')
                return redirect(url_for('index'))
            
            app.logger.info(f"Successfully retrieved user profile for: {user_profile.get('id')}")
            
            # Calculate token expiration
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            # Save or update user in database
            user = User.query.get(user_profile['id'])
            if not user:
                app.logger.info(f"Creating new user: {user_profile['id']}")
                user = User(id=user_profile['id'])
            
            user.display_name = user_profile.get('display_name', '')
            user.email = user_profile.get('email', '')
            user.image_url = user_profile['images'][0]['url'] if user_profile.get('images') and len(user_profile['images']) > 0 else None
            user.access_token = access_token
            user.refresh_token = refresh_token
            user.token_expires_at = expires_at
            user.last_login = datetime.utcnow()
            
            db.session.add(user)
            db.session.commit()
            app.logger.info(f"User data saved to database: {user.id}")
            
            # Store user ID in session
            session['user_id'] = user.id
            session.pop('oauth_state', None)
            
            flash('Successfully logged in!', 'success')
            return redirect(url_for('dashboard'))
            
        except requests.RequestException as e:
            app.logger.error(f"Token exchange request failed: {str(e)}")
            flash('Failed to authenticate with Spotify. Please try again.', 'error')
            return redirect(url_for('index'))
            
    except Exception as e:
        app.logger.error(f"Callback processing failed: {str(e)}")
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('index'))

def generate_music_taste_insights(spotify_client, gemini_api_key=None):
    """Generate music taste insights from user's Spotify data using AI analysis"""
    
    # Check if we already have cached insights for this session
    if 'music_taste_profile' in session and 'profile_timestamp' in session:
        # Cache for 30 minutes per session to avoid redundant AI calls
        if time.time() - session['profile_timestamp'] < 1800:
            app.logger.info("Using cached music taste profile")
            return session['music_taste_profile']
    
    try:
        # Only proceed with AI analysis if API key is provided
        if not gemini_api_key:
            # Return basic stats without AI analysis
            return generate_basic_insights(spotify_client)
        
        # Get comprehensive music data
        recent_tracks = spotify_client.get_recently_played(limit=30) or {'items': []}
        top_artists_short = spotify_client.get_top_artists(time_range='short_term', limit=15) or {'items': []}
        top_artists_medium = spotify_client.get_top_artists(time_range='medium_term', limit=15) or {'items': []}
        top_tracks_short = spotify_client.get_top_tracks(time_range='short_term', limit=15) or {'items': []}
        top_tracks_medium = spotify_client.get_top_tracks(time_range='medium_term', limit=15) or {'items': []}
        
        # Prepare data for AI analysis
        music_data = {
            'recent_tracks': [
                {
                    'name': item['track']['name'],
                    'artist': item['track']['artists'][0]['name'],
                    'genres': item['track']['artists'][0].get('genres', []) if len(item['track']['artists']) > 0 else []
                }
                for item in recent_tracks.get('items', [])[:20]
            ],
            'top_artists_recent': [
                {
                    'name': artist['name'],
                    'genres': artist.get('genres', []),
                    'popularity': artist.get('popularity', 0)
                }
                for artist in top_artists_short.get('items', [])[:10]
            ],
            'top_artists_overall': [
                {
                    'name': artist['name'],
                    'genres': artist.get('genres', []),
                    'popularity': artist.get('popularity', 0)
                }
                for artist in top_artists_medium.get('items', [])[:10]
            ],
            'top_tracks_recent': [
                {
                    'name': track['name'],
                    'artist': track['artists'][0]['name'],
                    'popularity': track.get('popularity', 0)
                }
                for track in top_tracks_short.get('items', [])[:10]
            ],
            'top_tracks_overall': [
                {
                    'name': track['name'],
                    'artist': track['artists'][0]['name'],
                    'popularity': track.get('popularity', 0)
                }
                for track in top_tracks_medium.get('items', [])[:10]
            ]
        }
        
        # Generate AI insights
        ai_insights = generate_ai_music_analysis(music_data, gemini_api_key)
        
        if ai_insights:
            # Cache the result in session for 30 minutes
            session['music_taste_profile'] = ai_insights
            session['profile_timestamp'] = time.time()
            app.logger.info("Cached new music taste profile")
            return ai_insights
        else:
            # Fallback to basic insights if AI fails
            return generate_basic_insights(spotify_client)
            
    except Exception as e:
        app.logger.error(f"Error generating music insights: {e}")
        return generate_basic_insights(spotify_client)

def generate_basic_insights(spotify_client):
    """Generate basic insights without AI analysis"""
    try:
        # Get basic music data
        recent_tracks = spotify_client.get_recently_played(limit=20) or {'items': []}
        top_artists_short = spotify_client.get_top_artists(time_range='short_term', limit=10) or {'items': []}
        
        # Extract basic stats
        recent_track_count = len(recent_tracks.get('items', []))
        top_artists_count = len(top_artists_short.get('items', []))
        
        # Extract top genres from artists
        genres = set()
        for artist in top_artists_short.get('items', [])[:5]:
            genres.update(artist.get('genres', []))
        
        # Get top artists names
        top_artist_names = [artist['name'] for artist in top_artists_short.get('items', [])[:3]]
        
        # Get recent track info
        recent_track_names = [item['track']['name'] for item in recent_tracks.get('items', [])[:3]]
        
        return {
            'recent_tracks': {
                'count': recent_track_count,
                'examples': recent_track_names,
                'description': f"Analyzed {recent_track_count} recent listening sessions"
            },
            'top_artists': {
                'count': top_artists_count,
                'examples': top_artist_names,
                'description': f"Identified {len(top_artist_names)} core artists in your rotation"
            },
            'genres': {
                'count': len(genres),
                'examples': list(genres)[:3],
                'description': f"Discovered {len(genres)} distinct musical genres in your taste"
            },
            'analysis_ready': False
        }
    except Exception as e:
        app.logger.error(f"Error generating basic insights: {e}")
        return {
            'recent_tracks': {
                'count': 0,
                'examples': [],
                'description': "Analyzing your listening patterns..."
            },
            'top_artists': {
                'count': 0,
                'examples': [],
                'description': "Understanding your artist preferences..."
            },
            'genres': {
                'count': 0,
                'examples': [],
                'description': "Mapping your musical landscape..."
            },
            'analysis_ready': False
        }

def generate_ai_music_analysis(music_data, gemini_api_key):
    """Use Gemini AI to generate detailed music taste insights"""
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
        
        # Create insightful, data-driven prompt for music analysis
        prompt = f"""
Analyze this user's Spotify listening data and provide thoughtful insights about their musical preferences and patterns. Be conversational and informative while remaining positive.

MUSIC DATA:
{json.dumps(music_data, indent=2)}

Respond ONLY with a JSON object in this exact format:
{{
    "user_taste_profile": "[2-3 sentences describing their overall music preferences with specific data points. Include genre patterns, favorite artists, or listening habits. Focus on what makes their taste unique and interesting]",
    "recent_mood_analysis": "[1-2 sentences examining their recent listening patterns. Mention specific trends, energy levels, or genre shifts. Connect these patterns to their current musical journey with positive insights]",
    "analysis_ready": true
}}

Guidelines:
- Include specific numbers and data points (e.g., "Your 15 top artists span 8 different genres")
- Mention actual song titles, artists, or genres from their data
- Make thoughtful connections between musical choices and personality traits
- Observe patterns in their listening evolution over time
- Be insightful about contradictions or interesting combinations in their taste
- Comment on emotional themes or energy levels in their recent tracks
- Keep the tone engaging and perceptive, not clinical or overly sarcastic

Example tone:
"With artists ranging from System of a Down to Jim Croce in your top rotation, you're clearly someone who values emotional authenticity over genre boundaries"
"Your recent shift from high-energy metal to introspective tracks suggests you're processing some significant changes in your life"
"The fact that you have both classical pieces and nu-metal in heavy rotation indicates a complex relationship with intensity and calm"
"""
        
        app.logger.info("Generating AI music taste analysis...")
        response = model.generate_content(prompt)
        
        if response and response.text:
            # Parse the JSON response
            import re
            
            # Extract JSON from the response
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                insights_json = json.loads(json_match.group())
                app.logger.info("AI music analysis generated successfully")
                return insights_json
            else:
                app.logger.warning("Could not extract JSON from AI response")
                return None
        else:
            app.logger.warning("Empty response from AI music analysis")
            return None
            
    except Exception as e:
        app.logger.error(f"Error in AI music analysis: {e}")
        return None

@app.route('/dashboard')
def dashboard():
    """Main dashboard showing user's music"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.pop('user_id', None)
        flash('User not found. Please log in again.', 'error')
        return redirect(url_for('index'))
    
    # Check if token needs refresh
    if user.is_token_expired():
        # Try to refresh token
        if not refresh_user_token(user):
            flash('Session expired. Please log in again.', 'error')
            return redirect(url_for('logout'))
    
    spotify_client = SpotifyClient(user.access_token)
    
    # Get currently playing track
    current_track = spotify_client.get_current_track()
    
    # Get playback state
    playback_state = spotify_client.get_playback_state()
    
    # Generate basic music insights without API key (AI analysis happens client-side)
    music_insights = generate_music_taste_insights(spotify_client)
    
    return render_template('dashboard.html', 
                         user=user, 
                         current_track=current_track,
                         playback_state=playback_state,
                         music_insights=music_insights)

@app.route('/play', methods=['GET', 'POST'])
def play():
    """Resume playback"""
    if 'user_id' not in session:
        if request.method == 'POST':
            return jsonify({'error': 'Not authenticated'}), 401
        return redirect(url_for('index'))
    
    user = User.query.get(session['user_id'])
    if not user:
        if request.method == 'POST':
            return jsonify({'error': 'User not found'}), 404
        return redirect(url_for('index'))
    
    spotify_client = SpotifyClient(user.access_token)
    success = spotify_client.play()
    
    if request.method == 'POST':
        return jsonify({'success': success})
    
    if success:
        flash('Playback resumed', 'success')
    else:
        flash('Failed to resume playback. Make sure Spotify is open on a device.', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/pause', methods=['GET', 'POST'])
def pause():
    """Pause playback"""
    if 'user_id' not in session:
        if request.method == 'POST':
            return jsonify({'error': 'Not authenticated'}), 401
        return redirect(url_for('index'))
    
    user = User.query.get(session['user_id'])
    if not user:
        if request.method == 'POST':
            return jsonify({'error': 'User not found'}), 404
        return redirect(url_for('index'))
    
    spotify_client = SpotifyClient(user.access_token)
    success = spotify_client.pause()
    
    if request.method == 'POST':
        return jsonify({'success': success})
    
    if success:
        flash('Playback paused', 'success')
    else:
        flash('Failed to pause playback', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/play-recommendation', methods=['POST'])
def play_recommendation():
    """Play the AI recommended track"""
    from flask import jsonify
    
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    
    track_uri = request.json.get('track_uri')
    if not track_uri:
        return jsonify({'success': False, 'message': 'Track URI required'}), 400
    
    spotify_client = SpotifyClient(user.access_token)
    
    # Check for available devices first
    devices = spotify_client.get_devices()
    if not devices or not devices.get('devices'):
        return jsonify({
            'success': False, 
            'message': 'No Spotify devices found. Please open the Spotify app on your phone, computer, or any device, then try again.'
        })
    
    success = spotify_client.play_track(track_uri)
    
    if success:
        return jsonify({'success': True, 'message': 'Playing recommended track'})
    else:
        return jsonify({
            'success': False, 
            'message': 'Failed to play track. Make sure you have Spotify Premium and an active device.'
        })

@app.route('/chat_feedback', methods=['POST'])
def chat_feedback():
    """Process user chat feedback on recommendations"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        feedback_text = data.get('feedback_text', '').strip()
        recommendation_id = data.get('recommendation_id') or session.get('current_recommendation_id')
        
        if not feedback_text:
            return jsonify({'success': False, 'message': 'Feedback text is required'}), 400
        
        if not recommendation_id:
            return jsonify({'success': False, 'message': 'No active recommendation to provide feedback on'}), 400
        
        user_id = session['user_id']
        
        # Get the recommendation from database
        from models import Recommendation, UserFeedback
        recommendation = Recommendation.query.filter_by(id=recommendation_id, user_id=user_id).first()
        
        if not recommendation:
            return jsonify({'success': False, 'message': 'Recommendation not found'}), 404
        
        # Get user's custom Gemini API key from request data (not session)
        custom_gemini_key = data.get('custom_gemini_key')
        if not custom_gemini_key:
            return jsonify({'success': False, 'message': 'AI analysis not available - API key required'}), 400
        
        # Configure Gemini for feedback analysis - USE FASTER MODEL
        genai.configure(api_key=custom_gemini_key)
        model = genai.GenerativeModel('gemini-1.5-flash')  # Much faster than 2.5-flash-preview
        
        # Create SIMPLIFIED prompt for analyzing user feedback (reduced complexity)
        feedback_analysis_prompt = f"""Analyze this music feedback quickly:

TRACK: "{recommendation.track_name}" by {recommendation.artist_name}
FEEDBACK: "{feedback_text}"

Return JSON:
{{
    "sentiment": "positive/negative/neutral",
    "key_insights": ["insight1", "insight2"],
    "preference_note": "brief summary of what this reveals about user taste"
}}"""
        
        app.logger.info("FEEDBACK ANALYSIS START (OPTIMIZED)")
        feedback_start = time.time()
        
        # Log simplified analysis details
        feedback_prompt_size = len(feedback_analysis_prompt)
        app.logger.info(f"OPTIMIZED FEEDBACK PROMPT SIZE: {feedback_prompt_size:,} characters (reduced)")
        app.logger.debug(f"Analyzing feedback for track: {recommendation.track_name} by {recommendation.artist_name}")
        app.logger.debug(f"User feedback: {feedback_text}")
        
        # Get AI analysis of the feedback with timeout
        app.logger.debug("Sending FAST feedback analysis to Gemini 1.5 Flash...")
        try:
            response = model.generate_content(feedback_analysis_prompt)
            feedback_duration = time.time() - feedback_start
            
            ai_analysis = response.text.strip()
            analysis_response_size = len(ai_analysis)
            
            app.logger.info(f"FAST FEEDBACK ANALYSIS COMPLETE - Duration: {feedback_duration:.2f}s, Response: {analysis_response_size} characters")
            
            # Quick sentiment extraction (simplified)
            sentiment = "neutral"
            ai_lower = ai_analysis.lower()
            if "positive" in ai_lower or '"sentiment": "positive"' in ai_lower:
                sentiment = "positive"
            elif "negative" in ai_lower or '"sentiment": "negative"' in ai_lower:
                sentiment = "negative"
                
        except Exception as e:
            app.logger.error(f"Fast feedback analysis failed: {e}")
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
            user_id=user_id,
            recommendation_id=recommendation_id,
            feedback_text=feedback_text,
            sentiment=sentiment,
            ai_processed_feedback=ai_analysis
        )
        db.session.add(feedback_entry)
        db.session.commit()
        
        app.logger.info(f"OPTIMIZED Feedback saved for user {user_id} on recommendation {recommendation_id}: {sentiment} (processed in {feedback_duration:.2f}s)")
        
        # Performance comparison log
        old_avg_time = 7.5  # Previous average from logs
        speedup = old_avg_time / feedback_duration if feedback_duration > 0 else 1
        app.logger.info(f"FEEDBACK PERFORMANCE: {feedback_duration:.2f}s (estimated {speedup:.1f}x faster than before)")
        
        return jsonify({
            'success': True,
            'message': f'Feedback processed in {feedback_duration:.1f}s - {speedup:.1f}x faster!',
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
        app.logger.error(f"Error processing chat feedback: {str(e)}")
        return jsonify({'success': False, 'message': 'Error processing feedback'}), 500

@app.route('/track-reasoning/<recommendation_id>')
def get_track_reasoning(recommendation_id):
    app.logger.debug(f'=== TRACK REASONING REQUEST ===')
    app.logger.debug(f'Recommendation ID: {recommendation_id}')
    app.logger.debug(f'User session: {session.get("user_id", "None")}')
    
    try:
        # Validate recommendation ID format
        try:
            rec_id = int(recommendation_id)
        except ValueError:
            app.logger.error(f'Invalid recommendation ID format: {recommendation_id}')
            return jsonify({'error': 'Invalid recommendation ID'}), 400
        
        app.logger.debug(f'Querying database for recommendation ID: {rec_id}')
        recommendation = Recommendation.query.get(rec_id)
        
        if not recommendation:
            app.logger.warning(f'No recommendation found with ID {rec_id}')
            app.logger.debug(f'Total recommendations in database: {Recommendation.query.count()}')
            return jsonify({'error': 'Recommendation not found'}), 404

        app.logger.debug(f'Found recommendation: "{recommendation.track_name}" by {recommendation.artist_name}')
        app.logger.debug(f'AI reasoning length: {len(recommendation.ai_reasoning) if recommendation.ai_reasoning else 0} characters')
        
        if not recommendation.ai_reasoning:
            app.logger.warning(f'Recommendation {rec_id} has no AI reasoning text')
            return jsonify({'reasoning': 'No reasoning available for this recommendation.'})
        
        app.logger.debug(f'Successfully returning reasoning for recommendation {rec_id}')
        return jsonify({'reasoning': recommendation.ai_reasoning})

    except Exception as e:
        app.logger.error(f'Error getting track reasoning for ID {recommendation_id}: {str(e)}', exc_info=True)
        return jsonify({'error': 'Failed to get track reasoning'}), 500

def process_feedback_insights(feedbacks, gemini_api_key=None):
    """Process user feedback entries to generate AI-powered conversational insights"""
    if not feedbacks:
        return "No feedback available yet. Start rating songs to get personalized insights!"
    
    # If no API key, fall back to basic insights
    if not gemini_api_key:
        return generate_basic_feedback_insights(feedbacks)
    
    try:
        # Prepare feedback data for AI analysis
        feedback_data = []
        for feedback in feedbacks[:10]:  # Limit to recent 10 feedback entries
            # Get the recommendation details
            from models import Recommendation
            recommendation = Recommendation.query.get(feedback.recommendation_id)
            if recommendation:
                feedback_entry = {
                    'track_name': recommendation.track_name,
                    'artist_name': recommendation.artist_name,
                    'feedback_text': feedback.feedback_text,
                    'sentiment': feedback.sentiment,
                    'created_at': feedback.created_at.isoformat() if feedback.created_at else None
                }
                feedback_data.append(feedback_entry)
        
        # Generate AI insights using Gemini
        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')  # Fast model for quick insights
        
        # Create conversational prompt for feedback analysis
        prompt = f"""
Analyze this user's feedback on music recommendations and create a conversational, friendly summary of what you've learned about their taste. Be personal, insightful, and encouraging.

FEEDBACK DATA:
{json.dumps(feedback_data, indent=2)}

Create a conversational response (2-3 sentences max) that:
1. Shows you understand their music preferences based on their feedback
2. Mentions specific patterns you've noticed (genres, artists, moods they like/dislike)
3. Sounds encouraging and personal, like talking to a friend
4. Acknowledges how their feedback is helping you learn

Examples of good tone:
- "I'm picking up that you really vibe with indie rock but aren't feeling the heavier metal tracks I've been suggesting..."
- "You seem to love anything with strong vocals and emotional depth - I've noticed you light up for artists like..."
- "I can tell you're in a more mellow mood lately based on your recent feedback..."

Respond with ONLY the conversational insight text, no other formatting or labels.
"""
        
        app.logger.info("Generating AI-powered feedback insights...")
        response = model.generate_content(prompt)
        
        if response and response.text:
            ai_insights = response.text.strip()
            app.logger.info("AI feedback insights generated successfully")
            return ai_insights
        else:
            app.logger.warning("AI feedback analysis failed, using fallback")
            return generate_basic_feedback_insights(feedbacks)
            
    except Exception as e:
        app.logger.error(f"Error generating AI feedback insights: {e}")
        return generate_basic_feedback_insights(feedbacks)

def generate_basic_feedback_insights(feedbacks):
    """Generate basic feedback insights when AI is not available"""
    # Count sentiments
    positive_count = sum(1 for f in feedbacks if f.sentiment and 'positive' in f.sentiment.lower())
    negative_count = sum(1 for f in feedbacks if f.sentiment and 'negative' in f.sentiment.lower())
    total_feedback = len(feedbacks)
    
    # Create insights summary
    if positive_count > negative_count:
        sentiment_summary = f"You've been loving most recommendations ({positive_count} positive out of {total_feedback} total)"
    elif negative_count > positive_count:
        sentiment_summary = f"You've been selective with recommendations ({negative_count} not quite right out of {total_feedback} total)"
    else:
        sentiment_summary = f"You've given mixed feedback on {total_feedback} recommendations"
    
    # Add learning note
    learning_note = "Based on your feedback, I'm learning your preferences and will improve future recommendations to better match your taste."
    
    return f"{sentiment_summary}. {learning_note}"

@app.route('/feedback-insights', methods=['GET', 'POST'])
def get_feedback_insights():
    logger.debug('Fetching feedback insights')
    try:
        # Get user's feedback history
        user_id = session.get('user_id')
        if not user_id:
            logger.warning('No user_id in session')
            return jsonify({'error': 'Not authenticated'}), 401

        feedbacks = UserFeedback.query.filter_by(user_id=user_id).all()
        logger.debug(f'Found {len(feedbacks)} feedback entries for user {user_id}')

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

@app.route('/api/current-track')
def api_current_track():
    """API endpoint to get current track info without page reload"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Check if token needs refresh
    if user.is_token_expired():
        if not refresh_user_token(user):
            return jsonify({'error': 'Token expired'}), 401
    
    spotify_client = SpotifyClient(user.access_token)
    
    current_track = spotify_client.get_current_track()
    playback_state = spotify_client.get_playback_state()
    
    return jsonify({
        'current_track': current_track,
        'playback_state': playback_state
    })

@app.route('/create-ai-playlist', methods=['POST'])
def create_ai_playlist():
    """Create an AI-generated playlist"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    from models import Recommendation, UserFeedback
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    
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
        
        spotify_client = SpotifyClient(user.access_token)
        
        # Generate AI-powered track recommendations for the playlist
        import google.generativeai as genai
        genai.configure(api_key=custom_gemini_key)
        model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
        
        # Get optimized user data for context - reduce API calls for stability
        app.logger.info("Collecting optimized user music data for AI playlist creation...")
        
        # Use cached music insights if available to reduce load
        try:
            music_data = generate_music_taste_insights(spotify_client)
            user_analysis = music_data.get('ai_analysis', 'No detailed analysis available')
            app.logger.info("Using cached music taste profile for playlist creation")
        except Exception as e:
            app.logger.error(f"Error getting music insights: {e}")
            # Ultra-minimal fallback
            user_analysis = "User prefers rock, alternative, and pop music with some electronic elements."
        
        # Get recent recommendations to avoid duplicates
        recent_recommendations = Recommendation.query.filter_by(user_id=user.id).order_by(Recommendation.created_at.desc()).limit(20).all()
        recent_tracks_list = [f'"{rec.track_name}" by {rec.artist_name}' for rec in recent_recommendations]
        
        # Get simplified user feedback insights - limit to prevent memory issues
        feedback_insights = ""
        try:
            feedback_entries = UserFeedback.query.filter_by(user_id=user.id).order_by(UserFeedback.created_at.desc()).limit(5).all()
            if feedback_entries:
                feedback_summary = []
                for feedback in feedback_entries[:3]:  # Only use top 3 to reduce load
                    rec = Recommendation.query.get(feedback.recommendation_id)
                    if rec:
                        feedback_summary.append(f"User {feedback.sentiment or 'neutral'} feedback on {rec.track_name} by {rec.artist_name}")
                
                if feedback_summary:
                    feedback_insights = f"RECENT FEEDBACK: {'; '.join(feedback_summary)}\n\n"
        except Exception as e:
            app.logger.warning(f"Could not load feedback insights: {e}")
            pass
        
        # Create comprehensive prompt for generating multiple tracks
        prompt = f"""Based on this user's comprehensive Spotify listening data and psychological analysis, recommend exactly {song_count} specific songs for a personalized playlist.

USER PSYCHOLOGICAL & MUSICAL ANALYSIS:
{user_analysis}

{feedback_insights}RECENTLY RECOMMENDED TRACKS (DO NOT REPEAT THESE):
{recent_tracks_list}

PLAYLIST TITLE: {playlist_name}
PLAYLIST DESCRIPTION AND ADDITIONAL GUIDANCE:
{playlist_description}

REQUIREMENTS:
1. Recommend exactly {song_count} different songs
2. Each song should be a real, existing track on Spotify
3. Variety is important - don't repeat artists unless the user heavily favors them
4. Consider the user's taste evolution and current preferences
5. Include both familiar genres and potential discoveries
6. IMPORTANT: Pay special attention to both the playlist title and description above. Adjust your recommendations to match that mood, theme, genre, or style while still respecting the user's musical taste
7. Format each song as: "Song Title" by Artist Name

Please respond with ONLY the song list, one song per line, in this exact format:
"Song Title 1" by Artist Name 1
"Song Title 2" by Artist Name 2
...and so on.

Do not include any other text, explanations, or formatting."""

        # Generate AI recommendations with timeout protection
        try:
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("AI generation timed out")
            
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(30)  # 30 second timeout
            
            response = model.generate_content(prompt)
            ai_recommendations = response.text.strip()
            
            signal.alarm(0)  # Cancel timeout
            
        except TimeoutError:
            app.logger.error("AI generation timed out")
            return jsonify({
                'success': False,
                'message': 'Request timed out. Please try again with fewer songs or check your connection.'
            })
        except Exception as e:
            app.logger.error(f"AI generation failed: {e}")
            return jsonify({
                'success': False,
                'message': 'AI recommendation generation failed. Please try again.'
            })
        
        # Parse the AI response to extract individual tracks
        track_lines = [line.strip() for line in ai_recommendations.split('\n') if line.strip()]
        track_uris = []
        successful_tracks = []
        failed_count = 0
        
        app.logger.info(f"AI recommended {len(track_lines)} tracks for playlist")
        
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
                            app.logger.info(f"Found track: {track['name']} by {track['artists'][0]['name']}")
                        else:
                            failed_count += 1
                            app.logger.warning(f"Could not find track: {song_title} by {artist_name}")
                            
                            # If too many failures, try broader search
                            if failed_count > 2:
                                broad_search = spotify_client.search_tracks(f"{song_title} {artist_name}", limit=1)
                                if broad_search and broad_search.get('tracks', {}).get('items'):
                                    track = broad_search['tracks']['items'][0]
                                    track_uris.append(track['uri'])
                                    successful_tracks.append(f"{track['name']} by {track['artists'][0]['name']}")
                                    
            except Exception as e:
                app.logger.error(f"Error processing track line '{track_line}': {e}")
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
                app.logger.warning("Failed to add some tracks to playlist")
        
        return jsonify({
            'success': True,
            'playlist_name': playlist_name,
            'playlist_id': playlist_id,
            'playlist_url': playlist_result['external_urls']['spotify'],
            'tracks_added': len(track_uris),
            'tracks_found': successful_tracks,
            'total_requested': song_count
        })
        
    except Exception as e:
        app.logger.error(f"Playlist creation failed: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to create playlist: {str(e)}'
        })

@app.route('/logout')
def logout():
    """Log out user"""
    session.pop('user_id', None)
    session.pop('oauth_state', None)
    # Clear any cached music insights to ensure no data persists
    session.pop('music_taste_profile', None)
    session.pop('profile_timestamp', None)
    session.pop('current_recommendation_id', None)
    session.pop('last_recommendation_time', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

def refresh_user_token(user):
    """Refresh user's access token"""
    if not user.refresh_token:
        return False
    
    token_url = 'https://accounts.spotify.com/api/token'
    
    auth_string = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    auth_bytes = auth_string.encode('utf-8')
    auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
    
    headers = {
        'Authorization': f'Basic {auth_b64}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': user.refresh_token
    }
    
    try:
        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()
        token_data = response.json()
        
        user.access_token = token_data['access_token']
        if 'refresh_token' in token_data:
            user.refresh_token = token_data['refresh_token']
        
        expires_in = token_data.get('expires_in', 3600)
        user.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        db.session.commit()
        return True
        
    except requests.RequestException as e:
        app.logger.error(f"Token refresh failed: {e}")
        return False

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', 
                         error_title='Page Not Found',
                         error_message='The page you are looking for does not exist.'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html',
                         error_title='Internal Server Error',
                         error_message='Something went wrong. Please try again later.'), 500

@app.route('/test-server', methods=['GET', 'POST'])
def test_server():
    """Simple test endpoint to verify server connectivity"""
    app.logger.info("=== TEST SERVER ENDPOINT HIT ===")
    app.logger.info(f"Method: {request.method}")
    app.logger.info(f"Headers: {dict(request.headers)}")
    if request.method == 'POST':
        app.logger.info(f"Body: {request.get_data()}")
    app.logger.info("=== END TEST ===")
    return jsonify({'status': 'server is working', 'method': request.method})

# Import Lightning mode functionality
try:
    from llm_optimization import data_optimizer, hyper_optimized_llm_manager, cache_manager
    app.logger.info("Lightning mode (hyper fast) modules loaded successfully")
    OPTIMIZATION_AVAILABLE = True
except ImportError as e:
    app.logger.warning(f"Lightning mode modules not available: {e}")
    OPTIMIZATION_AVAILABLE = False

@app.route('/api/performance-toggle', methods=['POST'])
def toggle_performance_mode():
    """Lightning mode is the only supported mode"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if OPTIMIZATION_AVAILABLE:
        return jsonify({
            'success': True,
            'mode': 'lightning',
            'endpoint': '/ai-recommendation-lightning',
            'message': 'Lightning mode (hyper fast) is active'
        })
    else:
        return jsonify({
            'success': True,
            'mode': 'standard',
            'endpoint': '/ai-recommendation',
            'message': 'Using standard AI recommendation mode (Lightning mode optimization not available)'
        })

@app.route('/api/performance-stats', methods=['GET'])
def get_performance_stats():
    """Get performance statistics for Lightning mode"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        user_id = session['user_id']
        
        # Check if optimization is available
        if not OPTIMIZATION_AVAILABLE:
            return jsonify({
                'success': True,
                'stats': {
                    'cache_status': {'cached_entries': 0},
                    'total_recommendations': 0,
                    'current_mode': 'Lightning (hyper fast)',
                    'note': 'Lightning mode optimization not available'
                }
            })
        
        # Get cache statistics
        cache_stats = cache_manager.get_cache_stats()
        
        # Get total recommendations for this user
        total_recommendations = Recommendation.query.filter_by(user_id=user_id).count()
        
        return jsonify({
            'success': True,
            'stats': {
                'cache_status': cache_stats,
                'total_recommendations': total_recommendations,
                'current_mode': 'Lightning (hyper fast)',
                'optimization_available': True
            }
        })
    except Exception as e:
        app.logger.error(f"Failed to get performance stats: {e}")
        return jsonify({'success': False, 'message': 'Failed to get performance stats'}), 500

def generate_conversational_reasoning(recommended_track, user_profile, music_data, gemini_api_key):
    """Generate conversational AI reasoning using the most advanced model"""
    try:
        # Use the most advanced model available
        model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
        
        # Create a more varied and genuine conversational prompt
        prompt = f"""
You are recommending music to a friend. Write ONE short, enthusiastic sentence explaining why they'll love this song.

THEIR MUSIC TASTE:
{user_profile}

RECENT LISTENING:
- Recent tracks: {[f"{track['name']} by {track['artist']}" for track in music_data.get('recent_tracks', [])[:3]]}
- Top genres: {music_data.get('top_genres', 'Various genres')}

RECOMMENDED SONG:
"{recommended_track['name']}" by {recommended_track['artists'][0]['name']}

Write exactly ONE sentence (maximum 20 words) explaining why they'll love this song. Be specific and enthusiastic but VERY concise.

Examples of good responses:
- "Perfect heavy riffs and emotional vocals that match your Skillet obsession!"
- "This has the electronic chaos and aggression you love in your metal tracks!"
- "Combines the anthemic energy of your favorites with modern production!"

Your response (ONE sentence, max 20 words):
"""

        response = model.generate_content(prompt)
        
        if response and response.text:
            # Ensure it's really just one sentence
            result = response.text.strip()
            # Take only the first sentence if multiple were generated
            if '.' in result:
                result = result.split('.')[0] + '.'
            # Limit to roughly 20 words
            words = result.split()
            if len(words) > 25:
                result = ' '.join(words[:25]) + '...'
            return result
        else:
            # Fallback if the advanced model fails
            return f"Perfect match for your taste - combines everything you love!"
            
    except Exception as e:
        app.logger.error(f"Advanced conversational reasoning failed: {str(e)}")
        # Enhanced fallback that's still conversational
        fallback_styles = [
            f"Exactly the energy and style you've been loving lately!",
            f"Perfect match for your taste - you'll be obsessed!",
            f"Has that exact vibe you chase in your favorite tracks!",
            f"Combines everything you love in one incredible song!"
        ]
        
        import random
        return random.choice(fallback_styles)

@app.route('/api/generate-conversational-reasoning', methods=['POST'])
def generate_conversational_reasoning_api():
    """Generate conversational reasoning for a recommendation separately"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # Get request data
    request_data = request.get_json() or {}
    gemini_api_key = request_data.get('gemini_api_key')
    recommendation_id = request_data.get('recommendation_id')
    
    if not gemini_api_key:
        return jsonify({'success': False, 'message': 'Gemini API key required'}), 400
    
    if not recommendation_id:
        return jsonify({'success': False, 'message': 'Recommendation ID required'}), 400

    # Configure genai
    genai.configure(api_key=gemini_api_key)

    try:
        # Get the recommendation from the database
        recommendation = Recommendation.query.get(recommendation_id)
        if not recommendation or recommendation.user_id != user.id:
            return jsonify({'success': False, 'message': 'Recommendation not found'}), 404

        # Get user's music data (use cached if available when optimization is available)
        spotify_client = SpotifyClient(user.access_token)
        
        if OPTIMIZATION_AVAILABLE:
            # Use optimized caching when available
            cached_music_data = cache_manager.get_cached_data(user.id, 'music_data')
            
            if cached_music_data:
                music_data = cached_music_data
            else:
                music_data = data_optimizer.collect_optimized_spotify_data(spotify_client)
                cache_manager.cache_data(user.id, 'music_data', music_data)
        else:
            # Fallback: collect basic music data without optimization
            app.logger.info("Using fallback data collection (optimization modules not available)")
            try:
                # Get basic music data
                current_track = spotify_client.get_current_track()
                recent_tracks = spotify_client.get_recently_played(limit=10)
                top_artists_short = spotify_client.get_top_artists(time_range='short_term', limit=5)
                top_artists_medium = spotify_client.get_top_artists(time_range='medium_term', limit=5)
                
                music_data = {
                    'current_track': current_track,
                    'recent_tracks': recent_tracks.get('items', []) if recent_tracks else [],
                    'top_artists': {
                        'short_term': top_artists_short.get('items', []) if top_artists_short else [],
                        'medium_term': top_artists_medium.get('items', []) if top_artists_medium else []
                    },
                    'top_tracks': {
                        'short_term': spotify_client.get_top_tracks(time_range='short_term', limit=5).get('items', []) if spotify_client.get_top_tracks(time_range='short_term', limit=5) else [],
                        'medium_term': spotify_client.get_top_tracks(time_range='medium_term', limit=5).get('items', []) if spotify_client.get_top_tracks(time_range='medium_term', limit=5) else []
                    }
                }
            except Exception as e:
                app.logger.warning(f"Fallback data collection failed: {e}")
                # Minimal fallback
                music_data = {
                    'current_track': None,
                    'recent_tracks': [],
                    'top_artists': {
                        'short_term': [],
                        'medium_term': []
                    },
                    'top_tracks': {
                        'short_term': [],
                        'medium_term': []
                    }
                }

        # Create track object from the recommendation
        recommended_track = {
            'name': recommendation.track_name,
            'artists': [{'name': recommendation.artist_name}]
        }

        # Extract user profile from the psychological analysis
        user_profile = recommendation.psychological_analysis.replace("Lightning profile: ", "") if recommendation.psychological_analysis else "Music lover with diverse taste"

        # Generate conversational reasoning
        start_time = time.time()
        ai_reasoning_text = generate_conversational_reasoning(
            recommended_track, user_profile, music_data, gemini_api_key
        )
        duration = time.time() - start_time

        # Update the recommendation with the new reasoning
        recommendation.ai_reasoning = ai_reasoning_text
        db.session.commit()

        app.logger.info(f"Generated conversational reasoning in {duration:.2f}s for recommendation {recommendation_id}")

        return jsonify({
            'success': True,
            'ai_reasoning': ai_reasoning_text,
            'generation_time': round(duration, 2)
        })

    except Exception as e:
        app.logger.error(f"Failed to generate conversational reasoning: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Failed to generate reasoning: {str(e)}'}), 500

@app.route('/ai-recommendation-lightning', methods=['POST'])
def ai_recommendation_lightning():
    """Lightning-fast AI recommendation using optimized models and cached data"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # Check if optimization modules are available
    if not OPTIMIZATION_AVAILABLE:
        return jsonify({
            'success': False, 
            'message': 'Lightning mode optimization modules are not available. Please install the required dependencies or use the standard recommendation endpoint.'
        }), 503

    # Get gemini API key
    request_data = request.get_json() or {}
    gemini_api_key = request_data.get('gemini_api_key')
    session_adjustment = request_data.get('session_adjustment', '')
    
    if not gemini_api_key:
        return jsonify({'success': False, 'message': 'Gemini API key required'}), 400

    # Configure genai
    genai.configure(api_key=gemini_api_key)

    try:
        total_start_time = time.time()
        current_time = time.time()
        
        # Rate limiting check
        last_rec_time = session.get('last_recommendation_time', 0)
        if current_time - last_rec_time < 1:  # 1 second minimum between recommendations
            return jsonify({
                'success': False, 
                'message': 'Please wait a moment before requesting another recommendation.'
            }), 429

        # Initialize Spotify client
        spotify_client = SpotifyClient(user.access_token)
        
        # Use hyper-optimized data collection with caching
        app.logger.info("LIGHTNING: Starting hyper-optimized data collection...")
        data_collection_start = time.time()
        
        # Check for cached music data
        cached_music_data = cache_manager.get_cached_data(user.id, 'music_data')
        
        if cached_music_data:
            app.logger.info("LIGHTNING: Using cached music data")
            music_data = cached_music_data
        else:
            app.logger.info("LIGHTNING: Collecting fresh music data")
            music_data = data_optimizer.collect_optimized_spotify_data(spotify_client)
            cache_manager.cache_data(user.id, 'music_data', music_data)
        
        data_collection_duration = time.time() - data_collection_start
        app.logger.info(f"LIGHTNING: Data collection complete - {data_collection_duration:.2f}s")
        
        # Get recent recommendations to avoid duplicates
        recent_recommendations = []
        recent_recs = Recommendation.query.filter_by(user_id=user.id)\
                                         .order_by(Recommendation.id.desc())\
                                         .limit(10).all()
        recent_recommendations = [f"{rec.track_name} by {rec.artist_name}" for rec in recent_recs]
        
        # Get optimized recommendation using hyper-fast approach
        app.logger.info("LIGHTNING: Generating optimized recommendation...")
        optimization_start = time.time()
        
        optimization_result = hyper_optimized_llm_manager.get_lightning_recommendation(
            music_data, 
            gemini_api_key,
            session_adjustment=session_adjustment,
            recent_recommendations=recent_recommendations,
            user_id=user.id
        )
        
        if not optimization_result['success']:
            return jsonify({
                'success': False, 
                'message': f'AI recommendation failed: {optimization_result["error"]}'
            }), 500
        
        recommendation_text = optimization_result['recommendation']
        user_profile = optimization_result['user_profile']
        optimization_stats = optimization_result['stats']
        
        optimization_duration = time.time() - optimization_start
        app.logger.info(f"LIGHTNING: Recommendation generation complete - {optimization_duration:.2f}s")
        
        # Parse recommendation to extract song and artist
        app.logger.info("LIGHTNING: Parsing recommendation...")
        parse_start = time.time()
        
        # Use the same fast model for parsing
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        parse_prompt = f"""
Extract the song title and artist name from this recommendation text. Return only in this exact format:
SONG: [song title]
ARTIST: [artist name]

Recommendation text: {recommendation_text}
"""
        
        try:
            parse_response = model.generate_content(parse_prompt)
            parse_text = parse_response.text.strip()
            
            # Extract song and artist
            song_line = [line for line in parse_text.split('\n') if line.startswith('SONG:')]
            artist_line = [line for line in parse_text.split('\n') if line.startswith('ARTIST:')]
            
            if song_line and artist_line:
                song_title = song_line[0].replace('SONG:', '').strip()
                artist_name = artist_line[0].replace('ARTIST:', '').strip()
                parse_confidence = 0.9
            else:
                # Fallback parsing
                lines = parse_text.split('\n')
                if len(lines) >= 2:
                    song_title = lines[0].replace('SONG:', '').strip()
                    artist_name = lines[1].replace('ARTIST:', '').strip()
                    parse_confidence = 0.6
                else:
                    raise Exception("Could not parse recommendation")
                    
        except Exception as e:
            app.logger.warning(f"LIGHTNING: Parse failed, using fallback: {str(e)}")
            # Simple text parsing fallback
            if '"' in recommendation_text:
                parts = recommendation_text.split('"')
                if len(parts) >= 3:
                    song_title = parts[1]
                    remaining = parts[2]
                    if ' by ' in remaining:
                        artist_name = remaining.split(' by ')[1].split('.')[0].split(',')[0].strip()
                    else:
                        artist_name = "Unknown Artist"
                    parse_confidence = 0.3
                else:
                    song_title = "Unknown Song"
                    artist_name = "Unknown Artist"
                    parse_confidence = 0.1
            else:
                song_title = "Unknown Song"
                artist_name = "Unknown Artist"
                parse_confidence = 0.1
        
        parse_duration = time.time() - parse_start
        app.logger.info(f"LIGHTNING: Parsing complete - {parse_duration:.2f}s - '{song_title}' by {artist_name}")
        
        # Search for the track on Spotify
        app.logger.info("LIGHTNING: Searching Spotify...")
        search_start = time.time()
        
        spotify_client = SpotifyClient(user.access_token)
        
        # Use simple concatenated search query
        search_query = f"{song_title} {artist_name}"
        app.logger.info(f"LIGHTNING: Search query: {search_query}")
        
        # Get more results for LLM to choose from
        search_results = spotify_client.search_tracks(search_query, limit=10)
        
        if not search_results or not search_results.get('tracks', {}).get('items'):
            app.logger.error(f"LIGHTNING: No search results for '{search_query}'")
            search_duration = time.time() - search_start
            app.logger.info(f"LIGHTNING: Search complete - {search_duration:.2f}s")
            
            return jsonify({
                'success': False,
                'message': f'Could not find the AI-recommended track "{song_title}" by {artist_name} on Spotify. Please try another recommendation.',
                'ai_recommendation': recommendation_text,
                'search_attempted': True
            }), 404
        
        # Use LLM to select the best result
        app.logger.info("LIGHTNING: LLM selecting best result...")
        selection_start = time.time()
        
        try:
            selection_result = structured_llm.select_spotify_result(
                model, song_title, artist_name, search_results['tracks']['items']
            )
            
            selected_track_data = selection_result.selected_result
            selection_confidence = selection_result.confidence
            
            # Convert back to Spotify API format
            recommended_track = {
                'id': selected_track_data.track_id,
                'name': selected_track_data.track_name,
                'artists': [{'name': selected_track_data.artist_name}],
                'album': {
                    'name': selected_track_data.album_name,
                    'images': [{'url': selected_track_data.album_image_url}] if selected_track_data.album_image_url else []
                },
                'uri': selected_track_data.track_uri,
                'external_urls': {'spotify': selected_track_data.external_url},
                'preview_url': selected_track_data.preview_url
            }
            
            match_score = selected_track_data.match_score
            selection_reasoning = selected_track_data.reasoning
            
            app.logger.info(f"LIGHTNING: Selected track - '{recommended_track['name']}' by {recommended_track['artists'][0]['name']} (match score: {match_score:.2f}, confidence: {selection_confidence:.2f})")
            app.logger.info(f"LIGHTNING: Selection reasoning - {selection_reasoning}")
            
        except Exception as e:
            app.logger.warning(f"LIGHTNING: LLM selection failed, using first result: {str(e)}")
            # Fallback to first result
            recommended_track = search_results['tracks']['items'][0]
            match_score = 0.5
            selection_confidence = 0.5
            selection_reasoning = "Fallback selection: Used first search result due to AI processing failure"
        
        selection_duration = time.time() - selection_start
        search_duration = time.time() - search_start
        app.logger.info(f"LIGHTNING: Result selection complete - {selection_duration:.2f}s")
        app.logger.info(f"LIGHTNING: Total search complete - {search_duration:.2f}s")
        
        # Save recommendation to database with placeholder reasoning (will be generated separately)
        app.logger.info("LIGHTNING: Saving recommendation to database...")
        save_start = time.time()
        
        recommendation = Recommendation(
            user_id=user.id,
            track_name=recommended_track['name'],
            artist_name=recommended_track['artists'][0]['name'],
            track_uri=recommended_track['uri'],
            album_name=recommended_track['album']['name'],
            ai_reasoning="Generating personalized explanation...",  # Placeholder
            psychological_analysis=f"Lightning profile: {user_profile}",
            listening_data_snapshot=json.dumps(music_data)
        )
        db.session.add(recommendation)
        db.session.commit()
        
        session['current_recommendation_id'] = recommendation.id
        session['last_recommendation_time'] = current_time
        
        save_duration = time.time() - save_start
        total_duration = time.time() - total_start_time
        
        # Log lightning performance
        app.logger.info(">" * 60)
        app.logger.info("LIGHTNING AI RECOMMENDATION PERFORMANCE SUMMARY")
        app.logger.info(">" * 60)
        app.logger.info(f"Data Collection:     {data_collection_duration:.2f}s")
        app.logger.info(f"Profile (Cached):    {optimization_stats['profile_duration']:.2f}s")
        app.logger.info(f"Recommendation:      {optimization_stats['rec_duration']:.2f}s")
        app.logger.info(f"Track Parsing:       {parse_duration:.2f}s")
        app.logger.info(f"Spotify Search:      {search_duration - selection_duration:.2f}s")
        app.logger.info(f"Result Selection:    {selection_duration:.2f}s")
        app.logger.info(f"Database Save:       {save_duration:.2f}s")
        app.logger.info(f"Total LLM Time:      {optimization_stats['total_llm_duration'] + parse_duration + selection_duration:.2f}s")
        app.logger.info(f"Total Search Time:   {search_duration:.2f}s")
        app.logger.info(f"Total Request Time:  {total_duration:.2f}s")
        app.logger.info(f"Model Used:          {optimization_stats['models_used'][0]}")
        app.logger.info(f"Approach:            lightning_structured_search_immediate")
        app.logger.info(f"Cached Profile:      {optimization_stats['cached_profile']}")
        app.logger.info(f"Match Score:         {match_score:.2f}")
        app.logger.info(f"Parse Confidence:    {parse_confidence:.2f}")
        app.logger.info(f"Selection Confidence:{selection_confidence:.2f}")
        app.logger.info(f"Performance Gain:    ~{61/total_duration:.1f}x faster than original")
        app.logger.info(">" * 60)
        
        return jsonify({
            'success': True,
            'track': {
                'name': recommended_track['name'],
                'artist': recommended_track['artists'][0]['name'],
                'album': recommended_track['album']['name'],
                'image': recommended_track['album']['images'][0]['url'] if recommended_track['album']['images'] else None,
                'uri': recommended_track['uri'],
                'external_url': recommended_track['external_urls']['spotify'],
                'preview_url': recommended_track.get('preview_url')
            },
            'ai_reasoning': "Generating personalized explanation...",  # Placeholder
            'user_profile': user_profile,
            'recommendation_id': recommendation.id,
            'exact_match': match_score >= 0.5,
            'ai_recommendation': recommendation_text,
            'requires_reasoning_generation': True,  # Signal to frontend to generate reasoning
            'performance_stats': {
                'total_duration': round(total_duration, 2),
                'profile_duration': round(optimization_stats['profile_duration'], 2),
                'rec_duration': round(optimization_stats['rec_duration'], 2),
                'parse_duration': round(parse_duration, 2),
                'selection_duration': round(selection_duration, 2),
                'save_duration': round(save_duration, 2),
                'total_llm_duration': round(optimization_stats['total_llm_duration'] + parse_duration + selection_duration, 2),
                'search_duration': round(search_duration, 2),
                'model_used': optimization_stats['models_used'][0],
                'approach': 'lightning_structured_search_immediate',
                'cached_profile': optimization_stats['cached_profile'],
                'cached_data': cached_music_data is not None,
                'match_score': round(match_score, 2),
                'parse_confidence': round(parse_confidence, 2),
                'selection_confidence': round(selection_confidence, 2),
                'performance_gain_estimate': f"{61/total_duration:.1f}x faster"
            }
        })
        
    except Exception as e:
        app.logger.error(f"Lightning AI recommendation failed: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'AI recommendation failed: {str(e)}'}), 500

@app.route('/api/generate-music-taste-profile', methods=['POST'])
def generate_music_taste_profile():
    """Generate AI music taste profile using user's Gemini API key"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    
    try:
        # Get custom Gemini API key from request
        request_data = request.get_json() or {}
        custom_gemini_key = request_data.get('custom_gemini_key')
        
        if not custom_gemini_key:
            return jsonify({
                'success': False, 
                'message': 'Gemini API key required for AI analysis'
            }), 400
        
        # Initialize Spotify client
        spotify_client = SpotifyClient(user.access_token)
        
        # Generate music taste insights with the provided API key
        app.logger.info("Generating music taste profile with user's API key...")
        insights = generate_music_taste_insights(spotify_client, custom_gemini_key)
        
        if insights and insights.get('analysis_ready'):
            app.logger.info("Music taste profile generated successfully")
            return jsonify({
                'success': True,
                'insights': insights
            })
        else:
            app.logger.warning("Music taste profile generation returned basic insights only")
            return jsonify({
                'success': False,
                'message': 'AI analysis failed, only basic insights available',
                'basic_insights': insights
            })
            
    except Exception as e:
        app.logger.error(f"Error generating music taste profile: {str(e)}", exc_info=True)
        return jsonify({
            'success': False, 
            'message': f'Failed to generate music taste profile: {str(e)}'
        }), 500

@app.route('/ai-recommendation', methods=['POST'])
def ai_recommendation():
    """Standard AI recommendation endpoint - fallback when Lightning mode is not available"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # Get gemini API key
    request_data = request.get_json() or {}
    gemini_api_key = request_data.get('gemini_api_key')
    session_adjustment = request_data.get('session_adjustment', '')
    
    if not gemini_api_key:
        return jsonify({'success': False, 'message': 'Gemini API key required'}), 400

    # Configure genai
    genai.configure(api_key=gemini_api_key)

    try:
        total_start_time = time.time()
        current_time = time.time()
        
        # Rate limiting check
        last_rec_time = session.get('last_recommendation_time', 0)
        if current_time - last_rec_time < 2:  # 2 second minimum between recommendations for standard mode
            return jsonify({
                'success': False, 
                'message': 'Please wait a moment before requesting another recommendation.'
            }), 429

        # Initialize Spotify client
        spotify_client = SpotifyClient(user.access_token)
        
        app.logger.info("STANDARD: Starting standard AI recommendation...")
        
        # Collect basic music data (without optimization)
        app.logger.info("STANDARD: Collecting music data...")
        data_collection_start = time.time()
        
        try:
            # Get user's music data
            current_track = spotify_client.get_current_track()
            recent_tracks = spotify_client.get_recently_played(limit=20)
            top_artists_short = spotify_client.get_top_artists(time_range='short_term', limit=10)
            top_artists_medium = spotify_client.get_top_artists(time_range='medium_term', limit=10)
            top_tracks_short = spotify_client.get_top_tracks(time_range='short_term', limit=10)
            top_tracks_medium = spotify_client.get_top_tracks(time_range='medium_term', limit=10)
            
            # Prepare music data
            music_data = {
                'current_track': current_track,
                'recent_tracks': recent_tracks.get('items', []) if recent_tracks else [],
                'top_artists': {
                    'short_term': top_artists_short.get('items', []) if top_artists_short else [],
                    'medium_term': top_artists_medium.get('items', []) if top_artists_medium else []
                },
                'top_tracks': {
                    'short_term': top_tracks_short.get('items', []) if top_tracks_short else [],
                    'medium_term': top_tracks_medium.get('items', []) if top_tracks_medium else []
                }
            }
            
            # Extract genres
            all_genres = set()
            for artist in music_data['top_artists']['short_term'][:5]:
                all_genres.update(artist.get('genres', []))
            for artist in music_data['top_artists']['medium_term'][:5]:
                all_genres.update(artist.get('genres', []))
            
            music_data['top_genres'] = list(all_genres)[:10]
            
        except Exception as e:
            app.logger.warning(f"Error collecting music data: {e}")
            # Minimal fallback
            music_data = {
                'current_track': None,
                'recent_tracks': [],
                'top_artists': {
                    'short_term': [],
                    'medium_term': []
                },
                'top_tracks': {
                    'short_term': [],
                    'medium_term': []
                }
            }
        
        data_collection_duration = time.time() - data_collection_start
        app.logger.info(f"STANDARD: Data collection complete - {data_collection_duration:.2f}s")
        
        # Get recent recommendations to avoid duplicates
        recent_recommendations = []
        recent_recs = Recommendation.query.filter_by(user_id=user.id)\
                                         .order_by(Recommendation.id.desc())\
                                         .limit(10).all()
        recent_recommendations = [f"{rec.track_name} by {rec.artist_name}" for rec in recent_recs]
        
        # Generate user profile
        app.logger.info("STANDARD: Generating user profile...")
        profile_start = time.time()
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        profile_prompt = f"""
Analyze this user's Spotify data and create a concise psychological music profile:

RECENT TRACKS: {[f"{track['track']['name']} by {track['track']['artists'][0]['name']}" for track in music_data['recent_tracks'][:10]]}
TOP ARTISTS: {[artist['name'] for artist in music_data['top_artists']['short_term'][:8]]}
TOP GENRES: {music_data['top_genres'][:8]}
CURRENT TRACK: {music_data['current_track']['item']['name'] + ' by ' + music_data['current_track']['item']['artists'][0]['name'] if music_data['current_track'] and music_data['current_track'].get('item') else 'None'}

Create a 2-3 sentence psychological profile focusing on:
- Musical personality traits
- Emotional connections to music
- Discovery preferences

Keep it conversational and insightful.
"""
        
        try:
            profile_response = model.generate_content(profile_prompt)
            user_profile = profile_response.text.strip() if profile_response and profile_response.text else "Music lover with diverse taste who enjoys discovering new sounds."
        except Exception as e:
            app.logger.warning(f"Profile generation failed: {e}")
            user_profile = "Music lover with diverse taste who enjoys discovering new sounds."
        
        profile_duration = time.time() - profile_start
        app.logger.info(f"STANDARD: User profile complete - {profile_duration:.2f}s")
        
        # Generate recommendation
        app.logger.info("STANDARD: Generating AI recommendation...")
        rec_start = time.time()
        
        rec_prompt = f"""
Based on this user's music data, recommend ONE specific song that perfectly matches their taste.

USER PROFILE: {user_profile}

MUSIC DATA:
- Recent tracks: {[f"{track['track']['name']} by {track['track']['artists'][0]['name']}" for track in music_data['recent_tracks'][:8]]}
- Top artists: {[artist['name'] for artist in music_data['top_artists']['short_term'][:8]]}
- Top genres: {music_data['top_genres'][:8]}

RECENT RECOMMENDATIONS (DO NOT REPEAT): {recent_recommendations}

SESSION ADJUSTMENT: {session_adjustment}

Recommend exactly ONE song in this format:
SONG: [song title]
ARTIST: [artist name]
REASON: [one sentence explaining why this matches their taste]

The song should:
- Match their established preferences
- Introduce slight variation to keep things interesting
- Be available on Spotify
- Not repeat recent recommendations
"""
        
        try:
            rec_response = model.generate_content(rec_prompt)
            recommendation_text = rec_response.text.strip() if rec_response and rec_response.text else ""
        except Exception as e:
            app.logger.error(f"Recommendation generation failed: {e}")
            return jsonify({'success': False, 'message': f'AI recommendation failed: {str(e)}'}), 500
        
        rec_duration = time.time() - rec_start
        app.logger.info(f"STANDARD: Recommendation generation complete - {rec_duration:.2f}s")
        
        # Parse recommendation
        app.logger.info("STANDARD: Parsing recommendation...")
        parse_start = time.time()
        
        try:
            # Extract song and artist
            song_line = [line for line in recommendation_text.split('\n') if line.startswith('SONG:')]
            artist_line = [line for line in recommendation_text.split('\n') if line.startswith('ARTIST:')]
            reason_line = [line for line in recommendation_text.split('\n') if line.startswith('REASON:')]
            
            if song_line and artist_line:
                song_title = song_line[0].replace('SONG:', '').strip()
                artist_name = artist_line[0].replace('ARTIST:', '').strip()
                ai_reasoning = reason_line[0].replace('REASON:', '').strip() if reason_line else "Perfect match for your taste!"
            else:
                raise Exception("Could not parse recommendation")
                
        except Exception as e:
            app.logger.warning(f"STANDARD: Parse failed, using fallback: {str(e)}")
            # Simple fallback parsing
            if '"' in recommendation_text:
                parts = recommendation_text.split('"')
                if len(parts) >= 3:
                    song_title = parts[1]
                    remaining = parts[2]
                    if ' by ' in remaining:
                        artist_name = remaining.split(' by ')[1].split('.')[0].split(',')[0].strip()
                    else:
                        artist_name = "Unknown Artist"
                    ai_reasoning = "Great match for your taste!"
                else:
                    song_title = "Unknown Song"
                    artist_name = "Unknown Artist"
                    ai_reasoning = "Perfect discovery for you!"
            else:
                song_title = "Unknown Song"
                artist_name = "Unknown Artist"
                ai_reasoning = "Perfect discovery for you!"
        
        parse_duration = time.time() - parse_start
        app.logger.info(f"STANDARD: Parsing complete - {parse_duration:.2f}s - '{song_title}' by {artist_name}")
        
        # Search for the track on Spotify
        app.logger.info("STANDARD: Searching Spotify...")
        search_start = time.time()
        
        search_query = f"{song_title} {artist_name}"
        app.logger.info(f"STANDARD: Search query: {search_query}")
        
        search_results = spotify_client.search_tracks(search_query, limit=5)
        
        if not search_results or not search_results.get('tracks', {}).get('items'):
            app.logger.error(f"STANDARD: No search results for '{search_query}'")
            search_duration = time.time() - search_start
            app.logger.info(f"STANDARD: Search complete - {search_duration:.2f}s")
            
            return jsonify({
                'success': False,
                'message': f'Could not find the AI-recommended track "{song_title}" by {artist_name} on Spotify. Please try another recommendation.',
                'ai_recommendation': recommendation_text,
                'search_attempted': True
            }), 404
        
        # Use the first result (simplified selection)
        recommended_track = search_results['tracks']['items'][0]
        search_duration = time.time() - search_start
        app.logger.info(f"STANDARD: Search complete - {search_duration:.2f}s")
        
        # Save recommendation to database
        app.logger.info("STANDARD: Saving recommendation to database...")
        save_start = time.time()
        
        recommendation = Recommendation(
            user_id=user.id,
            track_name=recommended_track['name'],
            artist_name=recommended_track['artists'][0]['name'],
            track_uri=recommended_track['uri'],
            album_name=recommended_track['album']['name'],
            ai_reasoning=ai_reasoning,
            psychological_analysis=f"Standard profile: {user_profile}",
            listening_data_snapshot=json.dumps(music_data)
        )
        db.session.add(recommendation)
        db.session.commit()
        
        session['current_recommendation_id'] = recommendation.id
        session['last_recommendation_time'] = current_time
        
        save_duration = time.time() - save_start
        total_duration = time.time() - total_start_time
        
        # Log standard performance
        app.logger.info("=" * 60)
        app.logger.info("STANDARD AI RECOMMENDATION PERFORMANCE SUMMARY")
        app.logger.info("=" * 60)
        app.logger.info(f"Data Collection:     {data_collection_duration:.2f}s")
        app.logger.info(f"User Profile:        {profile_duration:.2f}s")
        app.logger.info(f"Recommendation:      {rec_duration:.2f}s")
        app.logger.info(f"Track Parsing:       {parse_duration:.2f}s")
        app.logger.info(f"Spotify Search:      {search_duration:.2f}s")
        app.logger.info(f"Database Save:       {save_duration:.2f}s")
        app.logger.info(f"Total Request Time:  {total_duration:.2f}s")
        app.logger.info(f"Mode:                Standard (non-optimized)")
        app.logger.info(f"Model Used:          gemini-1.5-flash")
        app.logger.info("=" * 60)
        
        return jsonify({
            'success': True,
            'track': {
                'name': recommended_track['name'],
                'artist': recommended_track['artists'][0]['name'],
                'album': recommended_track['album']['name'],
                'image': recommended_track['album']['images'][0]['url'] if recommended_track['album']['images'] else None,
                'uri': recommended_track['uri'],
                'external_url': recommended_track['external_urls']['spotify'],
                'preview_url': recommended_track.get('preview_url')
            },
            'ai_reasoning': ai_reasoning,
            'user_profile': user_profile,
            'recommendation_id': recommendation.id,
            'ai_recommendation': recommendation_text,
            'performance_stats': {
                'total_duration': round(total_duration, 2),
                'profile_duration': round(profile_duration, 2),
                'rec_duration': round(rec_duration, 2),
                'parse_duration': round(parse_duration, 2),
                'search_duration': round(search_duration, 2),
                'save_duration': round(save_duration, 2),
                'model_used': 'gemini-1.5-flash',
                'mode': 'standard'
            }
        })
        
    except Exception as e:
        app.logger.error(f"Standard AI recommendation failed: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'AI recommendation failed: {str(e)}'}), 500
