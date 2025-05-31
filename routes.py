import os
import secrets
import base64
import json
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, session, flash, jsonify
from urllib.parse import urlencode
import requests
from app import app, db
from models import User
from spotify_client import SpotifyClient
import google.generativeai as genai

# Spotify OAuth configuration
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '3eab9e9e7ff444e8b0a9d1c18468b555')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
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

@app.route('/callback')
def callback():
    """Handle Spotify OAuth callback"""
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    # Check for errors
    if error:
        flash(f'Authorization failed: {error}', 'error')
        return redirect(url_for('index'))
    
    # Verify state parameter
    if not state or state != session.get('oauth_state'):
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
    
    try:
        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()
        token_data = response.json()
        
        access_token = token_data['access_token']
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 3600)
        
        # Get user profile
        spotify_client = SpotifyClient(access_token)
        user_profile = spotify_client.get_user_profile()
        
        if not user_profile:
            flash('Failed to get user profile from Spotify', 'error')
            return redirect(url_for('index'))
        
        # Calculate token expiration
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        # Save or update user in database
        user = User.query.get(user_profile['id'])
        if not user:
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
        
        # Store user ID in session
        session['user_id'] = user.id
        session.pop('oauth_state', None)
        
        flash('Successfully logged in!', 'success')
        return redirect(url_for('dashboard'))
        
    except requests.RequestException as e:
        app.logger.error(f"Token exchange failed: {e}")
        flash('Failed to authenticate with Spotify. Please try again.', 'error')
        return redirect(url_for('index'))

def generate_music_insights(spotify_client):
    """Generate music taste profile insights from user's Spotify data using AI analysis"""
    
    # Check if we already have cached insights for this session
    if 'music_taste_profile' in session and 'profile_timestamp' in session:
        import time
        # Cache for 30 minutes per session to avoid redundant AI calls
        if time.time() - session['profile_timestamp'] < 1800:
            app.logger.info("Using cached music taste profile")
            return session['music_taste_profile']
    
    try:
        # Check if Gemini API key is available
        gemini_api_key = os.environ.get('GOOGLE_API_KEY')
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
            import time
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
        model = genai.GenerativeModel('gemini-1.5-flash')
        
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
    
    # Generate music taste profile insights
    music_insights = generate_music_insights(spotify_client)
    
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

@app.route('/ai-recommendation', methods=['POST'])
def ai_recommendation():
    """Get AI-powered music recommendation"""
    from flask import jsonify
    import google.generativeai as genai
    
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    # Rate limiting: prevent too many AI recommendation requests
    import time
    current_time = time.time()
    last_recommendation_time = session.get('last_recommendation_time', 0)
    
    # Require at least 10 seconds between AI recommendation requests
    if current_time - last_recommendation_time < 10:
        remaining_time = int(10 - (current_time - last_recommendation_time))
        return jsonify({
            'success': False, 
            'message': f'Please wait {remaining_time} seconds before requesting another recommendation.'
        }), 429
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    
    try:
        # Get session adjustment and custom API key if provided
        request_data = request.get_json() or {}
        session_adjustment = request_data.get('session_adjustment')
        custom_gemini_key = request_data.get('custom_gemini_key')
        
        # Require a custom Gemini API key - no fallback to environment key
        gemini_api_key = custom_gemini_key
        if not gemini_api_key:
            return jsonify({
                'success': False, 
                'message': 'Personal Gemini API key required. Please add your API key in AI Settings to use AI recommendations.'
            }), 400
            
        # Determine which model to use based on API key source
        model_name = 'gemini-2.0-flash-exp' if custom_gemini_key else 'gemini-1.5-flash'
        
        spotify_client = SpotifyClient(user.access_token)
        
        # Collect comprehensive user music data
        app.logger.info("Collecting comprehensive user music data for AI recommendation...")
        
        # Get recent listening history (150 tracks)
        recent_tracks = spotify_client.get_recently_played(limit=50) or {'items': []}
        
        # Get additional recent tracks in batches since Spotify limits to 50 per request
        all_recent_tracks = recent_tracks.get('items', [])
        
        # Get more recent tracks using pagination if available
        after = recent_tracks.get('cursors', {}).get('after') if recent_tracks else None
        for _ in range(2):  # Get 2 more batches of 50 tracks each
            if after:
                batch = spotify_client._make_request('GET', f'/me/player/recently-played?limit=50&after={after}') or {'items': []}
                batch_items = batch.get('items', [])
                if batch_items:
                    all_recent_tracks.extend(batch_items)
                    after = batch.get('cursors', {}).get('after')
                else:
                    break
            else:
                break
        
        # Limit to 150 tracks total
        all_recent_tracks = all_recent_tracks[:150]
        
        # Get top tracks across different time ranges
        top_tracks_short = spotify_client.get_top_tracks(time_range='short_term', limit=20) or {'items': []}
        top_tracks_medium = spotify_client.get_top_tracks(time_range='medium_term', limit=20) or {'items': []}
        top_tracks_long = spotify_client.get_top_tracks(time_range='long_term', limit=20) or {'items': []}
        
        # Get top artists across different time ranges
        top_artists_short = spotify_client.get_top_artists(time_range='short_term', limit=20) or {'items': []}
        top_artists_medium = spotify_client.get_top_artists(time_range='medium_term', limit=20) or {'items': []}
        top_artists_long = spotify_client.get_top_artists(time_range='long_term', limit=20) or {'items': []}
        
        # Get saved (liked) tracks
        saved_tracks = spotify_client.get_saved_tracks(limit=50) or {'items': []}
        
        # Get user's playlists for additional context
        playlists = spotify_client.get_user_playlists(limit=20) or {'items': []}
        
        # Prepare comprehensive data for AI
        music_data = {
            'recent_tracks': [{'name': track['track']['name'], 'artist': track['track']['artists'][0]['name'], 
                             'album': track['track']['album']['name'], 'genres': track['track'].get('genres', [])} 
                            for track in all_recent_tracks],
            'top_tracks_last_month': [{'name': track['name'], 'artist': track['artists'][0]['name'], 
                                     'album': track['album']['name'], 'popularity': track.get('popularity', 0)} 
                                    for track in top_tracks_short.get('items', [])],
            'top_tracks_6_months': [{'name': track['name'], 'artist': track['artists'][0]['name'], 
                                   'album': track['album']['name'], 'popularity': track.get('popularity', 0)} 
                                  for track in top_tracks_medium.get('items', [])],
            'top_tracks_all_time': [{'name': track['name'], 'artist': track['artists'][0]['name'], 
                                   'album': track['album']['name'], 'popularity': track.get('popularity', 0)} 
                                  for track in top_tracks_long.get('items', [])],
            'top_artists_last_month': [{'name': artist['name'], 'genres': artist.get('genres', []), 
                                      'popularity': artist.get('popularity', 0)} 
                                     for artist in top_artists_short.get('items', [])],
            'top_artists_6_months': [{'name': artist['name'], 'genres': artist.get('genres', []), 
                                    'popularity': artist.get('popularity', 0)} 
                                   for artist in top_artists_medium.get('items', [])],
            'top_artists_all_time': [{'name': artist['name'], 'genres': artist.get('genres', []), 
                                    'popularity': artist.get('popularity', 0)} 
                                   for artist in top_artists_long.get('items', [])],
            'saved_tracks': [{'name': track['track']['name'], 'artist': track['track']['artists'][0]['name'], 
                            'album': track['track']['album']['name'], 'popularity': track['track'].get('popularity', 0)} 
                           for track in saved_tracks.get('items', [])],
            'playlist_names': [playlist['name'] for playlist in playlists.get('items', []) if playlist.get('name')],
            'total_playlists': len(playlists.get('items', []))
        }
        
        # Extract all unique genres for better context
        all_genres = set()
        for artist_list in [music_data['top_artists_last_month'], music_data['top_artists_6_months'], music_data['top_artists_all_time']]:
            for artist in artist_list:
                all_genres.update(artist.get('genres', []))
        music_data['favorite_genres'] = list(all_genres)
        
        # Get historical feedback to improve recommendations
        from models import UserFeedback, Recommendation
        past_feedback = db.session.query(UserFeedback, Recommendation).join(
            Recommendation, UserFeedback.recommendation_id == Recommendation.id
        ).filter(UserFeedback.user_id == user.id).order_by(UserFeedback.created_at.desc()).limit(10).all()
        
        feedback_insights = []
        for feedback, rec in past_feedback:
            feedback_insights.append({
                'track': f"{rec.track_name} by {rec.artist_name}",
                'sentiment': feedback.sentiment,
                'feedback': feedback.feedback_text,
                'ai_analysis': feedback.ai_processed_feedback
            })
        
        music_data['feedback_history'] = feedback_insights
        
        # Get recent recommendations to avoid repeating them
        recent_recommendations = Recommendation.query.filter_by(user_id=user.id).order_by(Recommendation.created_at.desc()).limit(20).all()
        recently_recommended_tracks = []
        for rec in recent_recommendations:
            recently_recommended_tracks.append(f'"{rec.track_name}" by {rec.artist_name}')
        
        app.logger.info(f"Recently recommended tracks to avoid: {recently_recommended_tracks}")
        
        # Log the collected data for transparency
        app.logger.info(f"Comprehensive data collected:")
        app.logger.info(f"Recent tracks collected: {len(all_recent_tracks)} (requested 150)")
        app.logger.info(f"Recent tracks in data: {len(music_data['recent_tracks'])}")
        app.logger.info(f"Top tracks (short/medium/long): {len(music_data['top_tracks_last_month'])}/{len(music_data['top_tracks_6_months'])}/{len(music_data['top_tracks_all_time'])}")
        app.logger.info(f"Top artists (short/medium/long): {len(music_data['top_artists_last_month'])}/{len(music_data['top_artists_6_months'])}/{len(music_data['top_artists_all_time'])}")
        app.logger.info(f"Saved tracks: {len(music_data['saved_tracks'])}")
        app.logger.info(f"Playlists: {len(music_data['playlist_names'])}")
        app.logger.info(f"Unique genres: {len(music_data['favorite_genres'])}")
        app.logger.info(f"Historical feedback entries: {len(feedback_insights)}")
        
        # Configure Gemini with appropriate model
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel(model_name)
        
        # First, analyze the user's music patterns and psychology
        app.logger.info("Performing psychological and pattern analysis...")
        
        analysis_prompt = f"""Analyze this comprehensive Spotify data to understand the user's musical psychology and patterns:

RECENT LISTENING: {music_data['recent_tracks']}
TOP TRACKS (All periods): {music_data['top_tracks_last_month']} | {music_data['top_tracks_6_months']} | {music_data['top_tracks_all_time']}
TOP ARTISTS (All periods): {music_data['top_artists_last_month']} | {music_data['top_artists_6_months']} | {music_data['top_artists_all_time']}
SAVED TRACKS: {music_data['saved_tracks']}
GENRES: {music_data['favorite_genres']}
PLAYLISTS: {music_data['playlist_names']}

Provide a detailed psychological and musical analysis covering:
1. Musical evolution over time (long-term vs recent preferences)
2. Emotional themes and psychological patterns in their music choices
3. Genre diversity vs consistency patterns
4. Energy levels and moods reflected in their music
5. Any recurring lyrical or musical themes
6. Social vs introspective music preferences
7. Relationship between playlist names and actual listening behavior
8. Overall musical personality profile

Format your response as structured insights, not recommendations."""

        # Get psychological analysis from AI
        analysis_response = model.generate_content(analysis_prompt)
        user_analysis = analysis_response.text.strip()
        
        app.logger.info(f"User psychological analysis: {user_analysis}")
        
        # Create comprehensive prompt for AI recommendation
        session_instruction = f"""

🎯 CRITICAL SESSION PREFERENCE OVERRIDE:
The user has specifically requested: "{session_adjustment}"
This is a TEMPORARY SESSION PREFERENCE that must be prioritized above all other considerations.
You MUST recommend a song that fits this exact request while still considering their taste.""" if session_adjustment else ""

        prompt = f"""Based on this comprehensive Spotify listening data AND psychological analysis, recommend ONE specific song that perfectly matches this user's taste:{session_instruction}

USER PSYCHOLOGICAL & MUSICAL ANALYSIS:
{user_analysis}

RAW LISTENING DATA:

RECENT LISTENING HISTORY (Last 50 tracks):
{music_data['recent_tracks']}

TOP TRACKS BY TIME PERIOD:
Last Month: {music_data['top_tracks_last_month']}
Last 6 Months: {music_data['top_tracks_6_months']}
All Time: {music_data['top_tracks_all_time']}

TOP ARTISTS BY TIME PERIOD:
Last Month: {music_data['top_artists_last_month']}
Last 6 Months: {music_data['top_artists_6_months']}
All Time: {music_data['top_artists_all_time']}

SAVED/LIKED TRACKS (Last 50):
{music_data['saved_tracks']}

MUSIC PREFERENCES:
Favorite Genres: {music_data['favorite_genres']}
Playlist Names: {music_data['playlist_names']}
Total Playlists: {music_data['total_playlists']}

FEEDBACK HISTORY:
{music_data['feedback_history']}

RECENTLY RECOMMENDED TRACKS (DO NOT REPEAT THESE):
{recently_recommended_tracks}

ANALYSIS INSTRUCTIONS:
1. Consider the user's listening patterns across all time periods
2. Identify recurring artists, genres, and musical styles
3. Note any evolution in taste from all-time to recent preferences
4. Factor in both popular and niche tracks they enjoy
5. Consider the diversity vs consistency in their taste
6. Recommend a song that bridges their established preferences with potential new discovery

CRITICAL REQUIREMENTS:
1. DO NOT recommend any song that appears in the "RECENT LISTENING HISTORY" section above
2. DO NOT recommend any song from the "RECENTLY RECOMMENDED TRACKS" list above  
3. The user has already heard these tracks - find something completely NEW
4. Choose a song that matches their taste but is a fresh discovery
5. Avoid overplayed mainstream hits they've likely heard before



Please respond with ONLY the song title and artist in this exact format:
"Song Title" by Artist Name

Do not include any other text, explanations, or formatting."""
        
        # Get AI recommendation based on psychological analysis
        app.logger.info(f"Requesting psychologically-informed AI recommendation from Gemini ({model_name})...")
        app.logger.info(f"Full prompt sent to AI: {prompt}")
        response = model.generate_content(prompt)
        recommendation_text = response.text.strip()
        
        app.logger.info(f"Raw AI response: {recommendation_text}")
        app.logger.info(f"AI recommended: {recommendation_text}")
        
        # Extract song title and artist for better search
        if " by " in recommendation_text:
            parts = recommendation_text.replace('"', '').split(" by ", 1)
            song_title = parts[0].strip()
            artist_name = parts[1].strip()
        else:
            song_title = recommendation_text.replace('"', '').strip()
            artist_name = None
        
        app.logger.info(f"Searching for: '{song_title}' by '{artist_name}'")
        
        # First, do a quick check if this exact song exists
        exact_match_found = False
        
        # Try multiple search strategies for better results
        search_results = None
        
        # Strategy 1: Use Spotify's advanced search with track and artist fields
        if artist_name:
            # Use Spotify's field search syntax: track:"song name" artist:"artist name"
            advanced_query = f'track:"{song_title}" artist:"{artist_name}"'
            app.logger.info(f"Trying search strategy 1 (advanced): '{advanced_query}'")
            search_results = spotify_client.search_tracks(advanced_query, limit=10)
            
            # Check if we got good results and look for exact matches
            if search_results and search_results.get('tracks', {}).get('items'):
                items = search_results['tracks']['items']
                # First check for exact matches
                for item in items:
                    if (item['name'].lower() == song_title.lower() and 
                        any(artist['name'].lower() == artist_name.lower() for artist in item['artists'])):
                        exact_match_found = True
                        search_results['tracks']['items'] = [item]  # Use only the exact match
                        app.logger.info(f"Found exact match: {item['name']} by {item['artists'][0]['name']}")
                        break
                
                if not exact_match_found:
                    # Filter results to only include tracks by the target artist
                    filtered_items = []
                    for item in items:
                        if any(artist_name.lower() in artist['name'].lower() or 
                              artist['name'].lower() in artist_name.lower() 
                              for artist in item['artists']):
                            filtered_items.append(item)
                    
                    if filtered_items:
                        search_results['tracks']['items'] = filtered_items
                        app.logger.info(f"Advanced search found {len(filtered_items)} tracks by {artist_name}")
                    else:
                        search_results = None
        
        # Strategy 2: If no results, try simple concatenation
        if not search_results or not search_results.get('tracks', {}).get('items'):
            if artist_name:
                simple_query = f"{song_title} {artist_name}"
                app.logger.info(f"Trying search strategy 2 (simple): '{simple_query}'")
                search_results = spotify_client.search_tracks(simple_query, limit=10)
        
        # Strategy 3: If still no results, try artist name only to find any songs by that artist
        if not search_results or not search_results.get('tracks', {}).get('items'):
            if artist_name:
                artist_query = f'artist:"{artist_name}"'
                app.logger.info(f"Trying search strategy 3 (artist only): '{artist_query}'")
                search_results = spotify_client.search_tracks(artist_query, limit=20)
        
        # Strategy 4: Last resort - try song title only
        if not search_results or not search_results.get('tracks', {}).get('items'):
            app.logger.info(f"Trying search strategy 4 (title only): '{song_title}'")
            search_results = spotify_client.search_tracks(song_title, limit=10)
        
        # If no exact match was found and we only have alternative tracks, ask AI for a real song
        if (not exact_match_found and search_results and 
            search_results.get('tracks', {}).get('items') and 
            artist_name):
            
            app.logger.warning(f"Could not find exact track '{song_title}' by '{artist_name}' on Spotify")
            
            # Get some real tracks by this artist to help AI pick a real song
            real_tracks = search_results['tracks']['items'][:5]
            track_list = [f"- {track['name']}" for track in real_tracks]
            
            # Ask AI to recommend a real song by {artist_name} that exists on Spotify and matches the user's taste
            real_song_prompt = f"""Your previous recommendation "{recommendation_text}" could not be found on Spotify.

Here are some actual songs by {artist_name} that exist on Spotify:
{chr(10).join(track_list)}

Please recommend ONE real song by {artist_name} that exists on Spotify and matches the user's taste. 

Respond with ONLY the song title in quotes, like: "Song Title"
Do not include the artist name or any other text."""

            try:
                real_song_response = model.generate_content(real_song_prompt)
                real_song_title = real_song_response.text.strip().replace('"', '')
                app.logger.info(f"AI suggested real song: '{real_song_title}' by {artist_name}")
                
                # Search for this real song
                for track in real_tracks:
                    if (real_song_title.lower() in track['name'].lower() or 
                        track['name'].lower() in real_song_title.lower()):
                        search_results['tracks']['items'] = [track]
                        app.logger.info(f"Found real song match: {track['name']} by {track['artists'][0]['name']}")
                        break
                        
            except Exception as e:
                app.logger.error(f"Error getting real song recommendation: {e}")
        
        if search_results and search_results.get('tracks', {}).get('items'):
            search_items = search_results['tracks']['items']
            
            if len(search_items) == 1:
                # Only one result, use it
                recommended_track = search_items[0]
                app.logger.info(f"Single result found: {recommended_track['name']} by {recommended_track['artists'][0]['name']}")
            else:
                # Multiple results - use improved selection logic
                app.logger.info(f"Multiple search results found ({len(search_items)}), using smart selection...")
                
                recommended_track = None
                
                # First, try exact matches
                if artist_name:
                    for track in search_items:
                        track_name_lower = track['name'].lower()
                        artist_name_lower = track['artists'][0]['name'].lower()
                        song_title_lower = song_title.lower()
                        target_artist_lower = artist_name.lower()
                        
                        # Check for exact or very close matches
                        if (track_name_lower == song_title_lower or 
                            song_title_lower in track_name_lower or
                            track_name_lower in song_title_lower) and \
                           (artist_name_lower == target_artist_lower or
                            target_artist_lower in artist_name_lower or
                            artist_name_lower in target_artist_lower):
                            recommended_track = track
                            app.logger.info(f"Found exact match: {track['name']} by {track['artists'][0]['name']}")
                            break
                
                # If no exact match found, use AI selection as fallback
                if not recommended_track:
                    app.logger.info("No exact match found, using AI to select best option...")
                    
                    # Create a simplified prompt for AI selection
                    track_options = []
                    for i, track in enumerate(search_items[:5]):  # Limit to top 5 for better accuracy
                        track_options.append(f"{i + 1}. \"{track['name']}\" by {track['artists'][0]['name']} (Album: {track['album']['name']})")
                    
                    track_selection_prompt = f"""You originally recommended: "{recommendation_text}"

However, that exact song may not exist on Spotify. Here are the closest matches found:

{chr(10).join(track_options)}

Which option number (1-{len(track_options)}) is the best alternative that matches the style and feel you intended with "{song_title}" by "{artist_name}"?

Respond with only the number."""
                    
                    try:
                        selection_response = model.generate_content(track_selection_prompt)
                        selected_option = selection_response.text.strip()
                        app.logger.info(f"AI selection response: '{selected_option}'")
                        
                        # Parse the selection
                        try:
                            option_index = int(selected_option) - 1
                            if 0 <= option_index < len(search_items):
                                recommended_track = search_items[option_index]
                                app.logger.info(f"AI selected option {selected_option}: {recommended_track['name']} by {recommended_track['artists'][0]['name']}")
                            else:
                                app.logger.warning(f"AI selected invalid option: {selected_option}")
                        except ValueError:
                            app.logger.warning(f"AI returned non-numeric selection: {selected_option}")
                    except Exception as e:
                        app.logger.error(f"Error in AI track selection: {e}")
                
                # Final fallback: use first result
                if not recommended_track:
                    app.logger.warning("All selection methods failed, using first result")
                    recommended_track = search_items[0]
            
            # Save recommendation to database
            from models import Recommendation
            
            # Create a detailed reasoning that includes original intent if different
            detailed_reasoning = recommendation_text
            if recommended_track['name'].lower() != song_title.lower():
                detailed_reasoning = f"Originally recommended: \"{recommendation_text}\"\nSelected alternative: \"{recommended_track['name']}\" by {recommended_track['artists'][0]['name']} (closest match on Spotify)"
            
            recommendation = Recommendation(
                user_id=user.id,
                track_name=recommended_track['name'],
                artist_name=recommended_track['artists'][0]['name'],
                track_uri=recommended_track['uri'],
                album_name=recommended_track['album']['name'],
                ai_reasoning=detailed_reasoning,
                psychological_analysis=user_analysis,
                listening_data_snapshot=json.dumps(music_data)
            )
            db.session.add(recommendation)
            db.session.commit()
            
            # Store recommendation ID in session for feedback
            session['current_recommendation_id'] = recommendation.id
            
            # Update the rate limiting timestamp for successful recommendations
            session['last_recommendation_time'] = current_time
            
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
                'ai_reasoning': recommendation_text,
                'ai_input_data': prompt,
                'ai_output_data': recommendation_text,
                'psychological_analysis': user_analysis,
                'recommendation_id': recommendation.id
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Could not find the recommended track: {recommendation_text}'
            })
            
    except Exception as e:
        app.logger.error(f"AI recommendation failed: {e}")
        return jsonify({
            'success': False,
            'message': f'AI recommendation failed: {str(e)}'
        })

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
        
        # Simple sentiment analysis based on keywords
        feedback_lower = feedback_text.lower()
        sentiment = "neutral"
        
        positive_words = ['love', 'like', 'great', 'awesome', 'good', 'amazing', 'perfect', 'excellent', 'fantastic', 'yes']
        negative_words = ['hate', 'dislike', 'bad', 'awful', 'terrible', 'no', "don't like", 'boring', 'annoying']
        
        if any(word in feedback_lower for word in positive_words):
            sentiment = "positive"
        elif any(word in feedback_lower for word in negative_words):
            sentiment = "negative"
        
        # Save feedback to database with simple analysis
        feedback_entry = UserFeedback(
            user_id=user_id,
            recommendation_id=recommendation_id,
            feedback_text=feedback_text,
            sentiment=sentiment,
            ai_processed_feedback=f"User feedback: {feedback_text} (Detected sentiment: {sentiment})"
        )
        db.session.add(feedback_entry)
        db.session.commit()
        
        app.logger.info(f"Feedback saved for user {user_id} on recommendation {recommendation_id}: {sentiment}")
        
        return jsonify({
            'success': True,
            'message': 'Feedback received! Thanks for helping me learn your preferences.',
            'sentiment': sentiment,
            'feedback_id': feedback_entry.id
        })
        
    except Exception as e:
        app.logger.error(f"Error processing chat feedback: {str(e)}")
        return jsonify({'success': False, 'message': 'Error processing feedback'}), 500

@app.route('/track-reasoning', methods=['POST'])
def track_reasoning():
    """Generate detailed reasoning for why a track was recommended"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        recommendation_id = data.get('recommendation_id')
        
        if not recommendation_id:
            return jsonify({'success': False, 'message': 'Recommendation ID required'}), 400
        
        user_id = session['user_id']
        user = User.query.get(user_id)
        
        # Get the recommendation from database
        from models import Recommendation
        recommendation = Recommendation.query.filter_by(id=recommendation_id, user_id=user_id).first()
        
        if not recommendation:
            return jsonify({'success': False, 'message': 'Recommendation not found'}), 404
        
        # For now, return the basic reasoning that was already generated
        # This avoids the API key requirement issue
        basic_reasoning = recommendation.ai_reasoning or "This track was recommended based on your listening patterns and musical preferences."
        
        # If the recommendation has a psychological analysis, use that for more context
        if recommendation.psychological_analysis:
            enhanced_reasoning = f"{basic_reasoning}\n\nBased on your music taste analysis: {recommendation.psychological_analysis[:200]}..."
        else:
            enhanced_reasoning = basic_reasoning
        
        app.logger.info(f"Provided track reasoning for recommendation {recommendation_id}")
        
        return jsonify({
            'success': True,
            'reasoning': enhanced_reasoning,
            'track_info': {
                'name': recommendation.track_name,
                'artist': recommendation.artist_name,
                'album': recommendation.album_name
            }
        })
        
    except Exception as e:
        app.logger.error(f"Track reasoning failed: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to generate reasoning: {str(e)}'
        })

@app.route('/feedback-insights', methods=['POST'])
def feedback_insights():
    """Generate insights from user's historical feedback"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    # Check if we already have cached feedback insights for this session
    if 'feedback_insights_cache' in session and 'feedback_cache_timestamp' in session:
        import time
        # Cache for 20 minutes per session to avoid redundant AI calls
        if time.time() - session['feedback_cache_timestamp'] < 1200:
            app.logger.info("Using cached feedback insights")
            return jsonify(session['feedback_insights_cache'])
    
    try:
        user_id = session['user_id']
        
        # Get all user's feedback entries
        from models import UserFeedback, Recommendation
        feedback_entries = UserFeedback.query.filter_by(user_id=user_id).order_by(UserFeedback.created_at.desc()).all()
        
        if not feedback_entries:
            return jsonify({
                'success': True,
                'insights': 'No feedback yet! Start giving feedback on recommendations to help me learn your preferences.'
            })
        
        # Check if Gemini API key is available
        gemini_api_key = os.environ.get('GOOGLE_API_KEY')
        if not gemini_api_key:
            return jsonify({
                'success': False, 
                'message': 'AI analysis not available - API key required'
            }), 400
        
        # Configure Gemini for feedback analysis
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Prepare feedback data for analysis
        feedback_data = []
        for feedback in feedback_entries:
            recommendation = Recommendation.query.get(feedback.recommendation_id)
            if recommendation:
                feedback_data.append({
                    'track': f"{recommendation.track_name} by {recommendation.artist_name}",
                    'feedback': feedback.feedback_text,
                    'sentiment': feedback.sentiment,
                    'ai_analysis': feedback.ai_processed_feedback
                })
        
        # Create prompt for feedback insights
        insights_prompt = f"""
You are analyzing a user's music feedback to understand their preferences and what the AI system has learned about them.

FEEDBACK HISTORY:
{feedback_data}

Generate a conversational summary of what has been learned about this user's music preferences. Write 2-3 sentences that explain:

1. Key patterns in their likes/dislikes
2. What genres, artists, or musical elements they gravitate toward or avoid
3. How their feedback is helping improve future recommendations

Write in a friendly, casual tone as if explaining to the user what you've learned about their taste. Start with something like "Based on your feedback, I've learned that..." or "Your feedback shows that..."

Keep it concise and insightful - focus on actionable insights that show the AI is adapting to their preferences.
"""
        
        # Generate the insights
        response = model.generate_content(insights_prompt)
        insights_text = response.text.strip()
        
        app.logger.info(f"Generated feedback insights for user {user_id}")
        
        # Cache the result for 20 minutes
        import time
        result = {
            'success': True,
            'insights': insights_text,
            'feedback_count': len(feedback_entries)
        }
        session['feedback_insights_cache'] = result
        session['feedback_cache_timestamp'] = time.time()
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Feedback insights failed: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to generate insights: {str(e)}'
        })


@app.route('/api/current-track')
def api_current_track():
    """API endpoint to get current track info without page reload"""
    if 'access_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    spotify_client = SpotifyClient(session['access_token'])
    
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
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Get optimized user data for context - reduce API calls for stability
        app.logger.info("Collecting optimized user music data for AI playlist creation...")
        
        # Use cached music insights if available to reduce load
        try:
            music_data = generate_music_insights(spotify_client)
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
