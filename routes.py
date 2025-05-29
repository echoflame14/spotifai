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
SPOTIFY_REDIRECT_URI = os.environ.get('SPOTIFY_REDIRECT_URI', 'https://deb2334e-2767-4af0-932d-2c07564b350b-00-3cd1k0h3k7xtx.worf.replit.dev/callback')

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
    
    # Debug: Log the parameters being used
    app.logger.info(f"Client ID: {SPOTIFY_CLIENT_ID}")
    app.logger.info(f"Redirect URI: {SPOTIFY_REDIRECT_URI}")
    app.logger.info(f"State: {state}")
    
    # Build authorization URL
    auth_params = {
        'response_type': 'code',
        'client_id': SPOTIFY_CLIENT_ID,
        'scope': scope,
        'redirect_uri': SPOTIFY_REDIRECT_URI,
        'state': state
    }
    
    auth_url = 'https://accounts.spotify.com/authorize?' + urlencode(auth_params)
    app.logger.info(f"Authorization URL: {auth_url}")
    
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
    
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': SPOTIFY_REDIRECT_URI
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
    
    return render_template('dashboard.html', 
                         user=user, 
                         current_track=current_track,
                         playback_state=playback_state)

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
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    
    try:
        # Check if Gemini API key is available
        gemini_api_key = os.environ.get('GEMINI_API_KEY')
        if not gemini_api_key:
            return jsonify({
                'success': False, 
                'message': 'Gemini API key not configured. Please provide your API key.'
            }), 400
        
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
        
        # Configure Gemini
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
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
        prompt = f"""Based on this comprehensive Spotify listening data AND psychological analysis, recommend ONE specific song that perfectly matches this user's taste:

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

ANALYSIS INSTRUCTIONS:
1. Consider the user's listening patterns across all time periods
2. Identify recurring artists, genres, and musical styles
3. Note any evolution in taste from all-time to recent preferences
4. Factor in both popular and niche tracks they enjoy
5. Consider the diversity vs consistency in their taste
6. Recommend a song that bridges their established preferences with potential new discovery

Please respond with ONLY the song title and artist in this exact format:
"Song Title" by Artist Name

Do not include any other text, explanations, or formatting."""
        
        # Get AI recommendation based on psychological analysis
        app.logger.info("Requesting psychologically-informed AI recommendation from Gemini...")
        app.logger.info(f"Full prompt sent to AI: {prompt}")
        response = model.generate_content(prompt)
        recommendation_text = response.text.strip()
        
        app.logger.info(f"Raw AI response: {recommendation_text}")
        app.logger.info(f"AI recommended: {recommendation_text}")
        
        # Search for the recommended track on Spotify with more results for better AI selection
        search_results = spotify_client.search_tracks(recommendation_text, limit=10)
        
        if search_results and search_results.get('tracks', {}).get('items'):
            search_items = search_results['tracks']['items']
            
            if len(search_items) == 1:
                # Only one result, use it
                recommended_track = search_items[0]
            else:
                # Multiple results - let AI select the best match
                app.logger.info(f"Multiple search results found, using AI to select best match...")
                
                # Create a prompt for AI to select the best track
                track_options = []
                for i, track in enumerate(search_items[:10]):
                    track_options.append({
                        'option_number': i + 1,
                        'track_name': track['name'],
                        'artist_name': track['artists'][0]['name'],
                        'album_name': track['album']['name'],
                        'spotify_uri': track['uri']
                    })
                
                track_selection_prompt = f"""
You recommended: "{recommendation_text}"

Here are the search results from Spotify:
{json.dumps(track_options, indent=2)}

Your original recommendation was "{recommendation_text}". 

Look at the track_name and artist_name for each option. Which option number (1-{len(track_options)}) contains the exact song you intended to recommend?

CRITICAL: If you recommended "The Drug In Me Is You" by Falling In Reverse, find the option where track_name is "The Drug In Me Is You" (not "Raised By Wolves" or any other song).

Respond with ONLY the option number (just the number, nothing else).
"""
                
                selection_response = model.generate_content(track_selection_prompt)
                selected_option = selection_response.text.strip()
                
                app.logger.info(f"AI selection response: '{selected_option}'")
                
                # Parse the option number and get the track
                recommended_track = None
                try:
                    option_num = int(selected_option)
                    if 1 <= option_num <= len(search_items):
                        recommended_track = search_items[option_num - 1]
                        app.logger.info(f"AI selected option {option_num}: {recommended_track['name']} by {recommended_track['artists'][0]['name']}")
                    else:
                        app.logger.warning(f"AI selected invalid option {option_num}, using first result")
                        recommended_track = search_items[0]
                except ValueError:
                    app.logger.warning(f"AI returned non-numeric response '{selected_option}', using first result")
                    recommended_track = search_items[0]
                
                # If AI selection fails, use first result as fallback
                if not recommended_track:
                    app.logger.warning("AI track selection failed, using first result")
                    recommended_track = search_items[0]
            
            # Save recommendation to database
            from models import Recommendation
            recommendation = Recommendation(
                user_id=user.id,
                track_name=recommended_track['name'],
                artist_name=recommended_track['artists'][0]['name'],
                track_uri=recommended_track['uri'],
                album_name=recommended_track['album']['name'],
                ai_reasoning=recommendation_text,
                psychological_analysis=user_analysis,
                listening_data_snapshot=json.dumps(music_data)
            )
            db.session.add(recommendation)
            db.session.commit()
            
            # Store recommendation ID in session for feedback
            session['current_recommendation_id'] = recommendation.id
            
            return jsonify({
                'success': True,
                'track': {
                    'name': recommended_track['name'],
                    'artist': recommended_track['artists'][0]['name'],
                    'album': recommended_track['album']['name'],
                    'image': recommended_track['album']['images'][0]['url'] if recommended_track['album']['images'] else None,
                    'uri': recommended_track['uri'],
                    'external_url': recommended_track['external_urls']['spotify']
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
        
        # Use AI to analyze the feedback and extract insights
        gemini_api_key = os.environ.get('GEMINI_API_KEY')
        if not gemini_api_key:
            return jsonify({'success': False, 'message': 'AI analysis not available'}), 500
        
        # Configure Gemini for feedback analysis
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Create prompt for analyzing user feedback
        feedback_analysis_prompt = f"""
Analyze this user feedback about a music recommendation and extract key insights:

RECOMMENDED TRACK: "{recommendation.track_name}" by {recommendation.artist_name}
ORIGINAL AI REASONING: {recommendation.ai_reasoning}
USER FEEDBACK: "{feedback_text}"

Please analyze:
1. Sentiment (positive, negative, neutral)
2. Specific reasons for the user's reaction
3. What this reveals about their music preferences
4. How future recommendations should be adjusted
5. Key patterns or preferences to remember

Provide a structured analysis in JSON format:
{{
    "sentiment": "positive/negative/neutral",
    "key_insights": ["insight1", "insight2", "insight3"],
    "preference_adjustments": ["adjustment1", "adjustment2"],
    "recommendation_feedback": "summary of what worked or didn't work"
}}
"""
        
        # Get AI analysis of the feedback
        response = model.generate_content(feedback_analysis_prompt)
        ai_analysis = response.text.strip()
        
        # Extract sentiment from AI analysis (simplified)
        sentiment = "neutral"
        if "positive" in ai_analysis.lower():
            sentiment = "positive"
        elif "negative" in ai_analysis.lower():
            sentiment = "negative"
        
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
        
        app.logger.info(f"Feedback saved for user {user_id} on recommendation {recommendation_id}: {sentiment}")
        
        return jsonify({
            'success': True,
            'message': 'Feedback received and analyzed!',
            'sentiment': sentiment,
            'ai_analysis': ai_analysis,
            'feedback_id': feedback_entry.id
        })
        
    except Exception as e:
        app.logger.error(f"Error processing chat feedback: {str(e)}")
        return jsonify({'success': False, 'message': 'Error processing feedback'}), 500


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
