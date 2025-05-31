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
        # Clean the environment variable in case it has extra characters
        env_redirect_uri = env_redirect_uri.strip().rstrip(';').rstrip()
        app.logger.info(f"Using environment SPOTIFY_REDIRECT_URI: '{env_redirect_uri}'")
        return env_redirect_uri
    
    # For Railway deployment, always use the Railway URL
    from flask import request
    if request and request.host:
        if 'railway.app' in request.host:
            app.logger.info(f"Detected Railway deployment, using: '{railway_url}'")
            return railway_url
        else:
            # Dynamic detection for other platforms
            scheme = request.scheme
            host = request.host
            dynamic_uri = f"{scheme}://{host}/callback"
            app.logger.info(f"Using dynamic URI: '{dynamic_uri}'")
            return dynamic_uri
    
    # Default fallback for Railway
    app.logger.info(f"Using Railway fallback: '{railway_url}'")
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
        
        # Session debugging
        app.logger.info(f"=== LOGIN SESSION DEBUG ===")
        app.logger.info(f"Generated state: {state}")
        app.logger.info(f"Session ID: {session.get('session_id', 'no session_id')}")
        app.logger.info(f"Session before OAuth: {dict(session)}")
        app.logger.info(f"Session permanent: {session.permanent}")
        app.logger.info(f"Cookie settings - Secure: {app.config.get('SESSION_COOKIE_SECURE')}")
        app.logger.info(f"Cookie settings - SameSite: {app.config.get('SESSION_COOKIE_SAMESITE')}")
        app.logger.info(f"Cookie settings - Domain: {app.config.get('SESSION_COOKIE_DOMAIN')}")
        app.logger.info("============================")
        
        # Define required scopes including permissions for AI recommendations and playlist creation
        scope = 'user-read-private user-read-email playlist-read-private playlist-modify-public playlist-modify-private user-read-playback-state user-modify-playback-state user-read-currently-playing user-read-recently-played user-top-read user-library-read'
        
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
        error_description = request.args.get('error_description')
        
        app.logger.info(f"=== CALLBACK DEBUG INFO ===")
        app.logger.info(f"Callback URL accessed: {request.url}")
        app.logger.info(f"Received code: {'Yes' if code else 'No'}")
        app.logger.info(f"Code length: {len(code) if code else 0}")
        app.logger.info(f"Received state: {state}")
        app.logger.info(f"Received error: {error}")
        app.logger.info(f"Error description: {error_description}")
        
        # Enhanced session debugging
        app.logger.info(f"=== SESSION STATE DEBUG ===")
        app.logger.info(f"Session state: {session.get('oauth_state')}")
        app.logger.info(f"Full session contents: {dict(session)}")
        app.logger.info(f"Session permanent: {session.permanent}")
        app.logger.info(f"Session modified: {session.modified}")
        app.logger.info(f"Request cookies: {request.cookies}")
        app.logger.info("============================")
        
        app.logger.info(f"Request URL: {request.url}")
        app.logger.info(f"Request headers: {dict(request.headers)}")
        app.logger.info(f"All request args: {dict(request.args)}")
        app.logger.info(f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}")
        app.logger.info(f"========================")
        
        # Check for errors from Spotify
        if error:
            error_msg = f"Spotify authorization error: {error}"
            if error_description:
                error_msg += f" - {error_description}"
            
            app.logger.error(error_msg)
            
            # Provide specific error messages for common issues
            if error == 'access_denied':
                flash('You denied access to Spotify. Please try again and grant permissions.', 'error')
            elif error == 'invalid_client':
                flash('Invalid client configuration. Please contact support.', 'error')
            elif error == 'invalid_request':
                flash('Invalid authorization request. Please try again.', 'error')
            else:
                flash(f'Authorization failed: {error_msg}', 'error')
            
            return redirect(url_for('index'))
        
        # Check if we received an authorization code
        if not code:
            app.logger.error("No authorization code received from Spotify")
            flash('No authorization code received from Spotify. Please try again.', 'error')
            return redirect(url_for('index'))
        
        # Verify state parameter
        session_state = session.get('oauth_state')
        if not state or state != session_state:
            app.logger.error(f"State mismatch - Received: '{state}', Expected: '{session_state}'")
            app.logger.error(f"State comparison: received={repr(state)}, session={repr(session_state)}")
            flash('Security check failed (invalid state). Please try again.', 'error')
            return redirect(url_for('index'))
        
        app.logger.info("State validation passed")
        
        # Exchange code for access token
        token_url = 'https://accounts.spotify.com/api/token'
        
        # Prepare authorization header
        if not SPOTIFY_CLIENT_SECRET:
            app.logger.error("SPOTIFY_CLIENT_SECRET is not set")
            flash('Server configuration error. Please contact support.', 'error')
            return redirect(url_for('index'))
        
        auth_string = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
        auth_bytes = auth_string.encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
        
        headers = {
            'Authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        # Use the same dynamic redirect URI for consistency
        redirect_uri = get_redirect_uri()
        
        # Ensure redirect_uri is clean (remove any potential trailing characters)
        redirect_uri = redirect_uri.strip().rstrip(';').rstrip()
        
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri
        }
        
        app.logger.info("=== TOKEN EXCHANGE DEBUG INFO ===")
        app.logger.info(f"Token URL: {token_url}")
        app.logger.info(f"Redirect URI: '{redirect_uri}'")
        app.logger.info(f"Redirect URI length: {len(redirect_uri)}")
        app.logger.info(f"Redirect URI repr: {repr(redirect_uri)}")
        app.logger.info(f"Client ID: {SPOTIFY_CLIENT_ID}")
        app.logger.info(f"Client Secret length: {len(SPOTIFY_CLIENT_SECRET) if SPOTIFY_CLIENT_SECRET else 0}")
        app.logger.info(f"Auth header length: {len(auth_b64)}")
        app.logger.info(f"Authorization code length: {len(code)}")
        app.logger.info(f"Request data grant_type: {data['grant_type']}")
        app.logger.info(f"Request data redirect_uri: '{data['redirect_uri']}'")
        app.logger.info(f"Request data code length: {len(data['code'])}")
        app.logger.info(f"Request headers: {headers}")
        app.logger.info("===============================")
        
        try:
            app.logger.info("Sending token exchange request to Spotify...")
            response = requests.post(token_url, headers=headers, data=data, timeout=30)
            app.logger.info(f"Token exchange response status: {response.status_code}")
            app.logger.info(f"Token exchange response time: {response.elapsed.total_seconds():.2f}s")
            
            if response.status_code != 200:
                app.logger.error(f"Token exchange failed with status {response.status_code}")
                app.logger.error(f"Response content: {response.text}")
                app.logger.error(f"Response headers: {dict(response.headers)}")
                app.logger.error(f"Request data sent: {data}")
                app.logger.error(f"Auth string components - Client ID: {SPOTIFY_CLIENT_ID}, Secret length: {len(SPOTIFY_CLIENT_SECRET)}")
                
                # Provide specific error messages based on status code
                if response.status_code == 400:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('error_description', 'Bad request to Spotify')
                        app.logger.error(f"Spotify API error details: {error_data}")
                    except:
                        error_msg = 'Invalid request to Spotify API'
                    flash(f'Authentication failed: {error_msg}', 'error')
                elif response.status_code == 401:
                    flash('Invalid client credentials. Please check your Spotify app configuration.', 'error')
                else:
                    flash('Failed to authenticate with Spotify. Please try again.', 'error')
                
                return redirect(url_for('index'))
            
            try:
                token_data = response.json()
                app.logger.info("Successfully received token data from Spotify")
                app.logger.info(f"Token data keys: {list(token_data.keys())}")
            except ValueError as e:
                app.logger.error(f"Failed to parse token response as JSON: {e}")
                app.logger.error(f"Raw response: {response.text}")
                flash('Invalid response from Spotify. Please try again.', 'error')
                return redirect(url_for('index'))
            
            access_token = token_data.get('access_token')
            refresh_token = token_data.get('refresh_token')
            expires_in = token_data.get('expires_in', 3600)
            
            if not access_token:
                app.logger.error("No access token in Spotify response")
                app.logger.error(f"Token response: {token_data}")
                flash('Invalid token response from Spotify. Please try again.', 'error')
                return redirect(url_for('index'))
            
            app.logger.info(f"Access token received (length: {len(access_token)})")
            app.logger.info(f"Refresh token: {'Yes' if refresh_token else 'No'}")
            app.logger.info(f"Expires in: {expires_in} seconds")
            
            # Validate access token format before using it
            if not access_token or len(access_token) < 50:
                app.logger.error(f"Invalid access token format - Length: {len(access_token) if access_token else 0}")
                flash('Invalid access token received from Spotify. Please try again.', 'error')
                return redirect(url_for('index'))
            
            # Get user profile with enhanced debugging
            app.logger.info("=== USER PROFILE RETRIEVAL DEBUG ===")
            app.logger.info(f"Access token (first 20 chars): {access_token[:20]}...")
            app.logger.info("Attempting to get user profile from Spotify...")
            
            try:
                spotify_client = SpotifyClient(access_token)
                user_profile = spotify_client.get_user_profile()
                
                app.logger.info(f"User profile request completed - Result: {'Success' if user_profile else 'Failed'}")
                
                if not user_profile:
                    app.logger.error("Failed to get user profile from Spotify")
                    app.logger.error("This could indicate an invalid access token or API issue")
                    app.logger.error(f"Access token being used: {access_token[:30]}...")
                    
                    # Try to make a direct test request to Spotify to debug the issue
                    test_headers = {'Authorization': f'Bearer {access_token}'}
                    try:
                        test_response = requests.get('https://api.spotify.com/v1/me', headers=test_headers, timeout=10)
                        app.logger.error(f"Direct test request status: {test_response.status_code}")
                        app.logger.error(f"Direct test response: {test_response.text}")
                        app.logger.error(f"Direct test headers: {dict(test_response.headers)}")
                    except Exception as test_e:
                        app.logger.error(f"Direct test request failed: {test_e}")
                    
                    flash('Failed to get user profile from Spotify. Please try again.', 'error')
                    return redirect(url_for('index'))
                
            except Exception as profile_e:
                app.logger.error(f"Exception during user profile retrieval: {str(profile_e)}")
                app.logger.error(f"Exception type: {type(profile_e).__name__}")
                import traceback
                app.logger.error(f"Profile retrieval traceback: {traceback.format_exc()}")
                flash('Error retrieving user profile. Please try again.', 'error')
                return redirect(url_for('index'))
            
            app.logger.info("===================================")
            
            app.logger.info(f"Successfully retrieved user profile for: {user_profile.get('id')}")
            app.logger.info(f"User profile keys: {list(user_profile.keys())}")
            
            # Calculate token expiration
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            # Save or update user in database
            user = User.query.get(user_profile['id'])
            if not user:
                app.logger.info(f"Creating new user: {user_profile['id']}")
                user = User(id=user_profile['id'])
            else:
                app.logger.info(f"Updating existing user: {user_profile['id']}")
            
            user.display_name = user_profile.get('display_name', '')
            user.email = user_profile.get('email', '')
            user.image_url = user_profile['images'][0]['url'] if user_profile.get('images') and len(user_profile['images']) > 0 else None
            user.access_token = access_token
            user.refresh_token = refresh_token
            user.token_expires_at = expires_at
            user.last_login = datetime.utcnow()
            
            try:
                db.session.add(user)
                db.session.commit()
                app.logger.info(f"User data saved to database: {user.id}")
            except Exception as e:
                app.logger.error(f"Failed to save user to database: {e}")
                db.session.rollback()
                flash('Failed to save user data. Please try again.', 'error')
                return redirect(url_for('index'))
            
            # Store user ID in session
            session['user_id'] = user.id
            session.pop('oauth_state', None)
            
            app.logger.info(f"User {user.id} successfully authenticated and logged in")
            flash('Successfully logged in!', 'success')
            return redirect(url_for('dashboard'))
            
        except requests.RequestException as e:
            app.logger.error(f"Token exchange request failed: {str(e)}")
            app.logger.error(f"Request exception type: {type(e).__name__}")
            flash('Network error during authentication. Please try again.', 'error')
            return redirect(url_for('index'))
            
    except Exception as e:
        app.logger.error(f"Callback processing failed: {str(e)}")
        app.logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        app.logger.error(f"Traceback: {traceback.format_exc()}")
        flash('An unexpected error occurred during authentication. Please try again.', 'error')
        return redirect(url_for('index'))

def generate_music_taste_insights(spotify_client, gemini_api_key=None):
    """Generate comprehensive music taste insights from user's Spotify data using extensive AI analysis"""
    
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
        
        # Get COMPREHENSIVE music data for ultra-detailed analysis
        app.logger.info("Collecting comprehensive music data for ultra-detailed psychological profile...")
        
        # Get extensive listening history
        recent_tracks = spotify_client.get_recently_played(limit=50) or {'items': []}
        
        # Get detailed artist data across all time ranges
        top_artists_short = spotify_client.get_top_artists(time_range='short_term', limit=30) or {'items': []}
        top_artists_medium = spotify_client.get_top_artists(time_range='medium_term', limit=30) or {'items': []}
        top_artists_long = spotify_client.get_top_artists(time_range='long_term', limit=30) or {'items': []}
        
        # Get detailed track data across all time ranges
        top_tracks_short = spotify_client.get_top_tracks(time_range='short_term', limit=30) or {'items': []}
        top_tracks_medium = spotify_client.get_top_tracks(time_range='medium_term', limit=30) or {'items': []}
        top_tracks_long = spotify_client.get_top_tracks(time_range='long_term', limit=30) or {'items': []}
        
        # Get current listening context
        current_track = spotify_client.get_current_track()
        
        # Analyze listening patterns and extract genres
        all_artists = (
            top_artists_short.get('items', []) + 
            top_artists_medium.get('items', []) + 
            top_artists_long.get('items', [])
        )
        
        # Comprehensive genre analysis
        genre_frequency = {}
        for artist in all_artists:
            for genre in artist.get('genres', []):
                genre_frequency[genre] = genre_frequency.get(genre, 0) + 1
        
        # Sort genres by frequency
        sorted_genres = sorted(genre_frequency.items(), key=lambda x: x[1], reverse=True)
        top_genres = [genre for genre, count in sorted_genres[:50]]
        
        # Analyze artist popularity patterns
        artist_popularity_data = []
        for artist in all_artists[:50]:
            artist_popularity_data.append({
                'name': artist['name'],
                'popularity': artist.get('popularity', 0),
                'genres': artist.get('genres', []),
                'followers': artist.get('followers', {}).get('total', 0)
            })
        
        # Analyze track characteristics
        track_analysis = []
        all_tracks = (
            top_tracks_short.get('items', []) + 
            top_tracks_medium.get('items', []) + 
            top_tracks_long.get('items', [])
        )
        
        for track in all_tracks[:50]:
            track_analysis.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'popularity': track.get('popularity', 0),
                'duration_ms': track.get('duration_ms', 0),
                'explicit': track.get('explicit', False),
                'release_date': track.get('album', {}).get('release_date', 'Unknown'),
                'album_type': track.get('album', {}).get('album_type', 'Unknown')
            })
        
        # Analyze recent listening patterns and behavior
        recent_listening_analysis = {
            'total_tracks': len(recent_tracks.get('items', [])),
            'unique_artists': len(set([item['track']['artists'][0]['name'] for item in recent_tracks.get('items', [])])),
            'repeat_behavior': {},
            'listening_times': [],
            'track_skipping_patterns': []
        }
        
        # Analyze repeat listening behavior
        track_play_counts = {}
        for item in recent_tracks.get('items', []):
            track_key = f"{item['track']['name']} - {item['track']['artists'][0]['name']}"
            track_play_counts[track_key] = track_play_counts.get(track_key, 0) + 1
        
        repeated_tracks = {k: v for k, v in track_play_counts.items() if v > 1}
        recent_listening_analysis['repeat_behavior'] = repeated_tracks
        
        # Analyze temporal listening patterns
        for item in recent_tracks.get('items', []):
            if item.get('played_at'):
                recent_listening_analysis['listening_times'].append(item['played_at'])
        
        # Prepare comprehensive data for AI analysis
        comprehensive_music_data = {
            'current_listening_context': {
                'current_track': current_track,
                'recent_tracks_sample': [
                    {
                        'name': item['track']['name'],
                        'artist': item['track']['artists'][0]['name'],
                        'album': item['track']['album']['name'],
                        'played_at': item.get('played_at'),
                        'duration_ms': item['track'].get('duration_ms', 0),
                        'popularity': item['track'].get('popularity', 0),
                        'explicit': item['track'].get('explicit', False)
                    }
                    for item in recent_tracks.get('items', [])[:30]
                ]
            },
            'artist_preferences': {
                'short_term_favorites': [
                    {
                        'name': artist['name'],
                        'genres': artist.get('genres', []),
                        'popularity': artist.get('popularity', 0),
                        'followers': artist.get('followers', {}).get('total', 0)
                    }
                    for artist in top_artists_short.get('items', [])[:20]
                ],
                'medium_term_favorites': [
                    {
                        'name': artist['name'],
                        'genres': artist.get('genres', []),
                        'popularity': artist.get('popularity', 0),
                        'followers': artist.get('followers', {}).get('total', 0)
                    }
                    for artist in top_artists_medium.get('items', [])[:20]
                ],
                'long_term_favorites': [
                    {
                        'name': artist['name'],
                        'genres': artist.get('genres', []),
                        'popularity': artist.get('popularity', 0),
                        'followers': artist.get('followers', {}).get('total', 0)
                    }
                    for artist in top_artists_long.get('items', [])[:20]
                ],
                'total_unique_artists': len(set([artist['name'] for artist in all_artists])),
                'artist_loyalty_patterns': artist_popularity_data
            },
            'track_preferences': {
                'short_term_tracks': track_analysis[:15],
                'medium_term_tracks': track_analysis[15:30],
                'long_term_tracks': track_analysis[30:45],
                'track_characteristics': {
                    'average_popularity': sum([t.get('popularity', 0) for t in all_tracks]) / len(all_tracks) if all_tracks else 0,
                    'explicit_content_ratio': sum([1 for t in all_tracks if t.get('explicit')]) / len(all_tracks) if all_tracks else 0,
                    'average_duration_minutes': sum([t.get('duration_ms', 0) for t in all_tracks]) / len(all_tracks) / 60000 if all_tracks else 0
                }
            },
            'genre_analysis': {
                'primary_genres': top_genres[:15],
                'secondary_genres': top_genres[15:30],
                'niche_genres': top_genres[30:45],
                'genre_diversity_score': len(top_genres),
                'genre_frequency_distribution': dict(sorted_genres[:30]),
                'genre_evolution': {
                    'short_term_genres': list(set([genre for artist in top_artists_short.get('items', []) for genre in artist.get('genres', [])]))[:15],
                    'medium_term_genres': list(set([genre for artist in top_artists_medium.get('items', []) for genre in artist.get('genres', [])]))[:15],
                    'long_term_genres': list(set([genre for artist in top_artists_long.get('items', []) for genre in artist.get('genres', [])]))[:15]
                }
            },
            'listening_behavior_analysis': recent_listening_analysis,
            'musical_evolution_patterns': {
                'consistency_score': len(set([artist['name'] for artist in top_artists_long.get('items', [])[:15]]).intersection(
                    set([artist['name'] for artist in top_artists_short.get('items', [])[:15]])
                )),
                'discovery_tendency': len([artist for artist in top_artists_short.get('items', [])[:25] 
                                         if artist['name'] not in [a['name'] for a in top_artists_long.get('items', [])[:25]]]),
                'mainstream_vs_niche_preference': {
                    'mainstream_tracks': len([t for t in all_tracks if t.get('popularity', 0) > 70]),
                    'niche_tracks': len([t for t in all_tracks if t.get('popularity', 0) < 30]),
                    'total_tracks_analyzed': len(all_tracks)
                }
            }
        }
        
        # Generate ultra-detailed AI insights using the most advanced model
        ai_insights = generate_ultra_detailed_psychological_analysis(comprehensive_music_data, gemini_api_key)
        
        if ai_insights:
            # Cache the result in session for 30 minutes
            session['music_taste_profile'] = ai_insights
            session['profile_timestamp'] = time.time()
            app.logger.info("Cached new ultra-detailed psychological music profile")
            return ai_insights
        else:
            # Fallback to basic insights if AI fails
            return generate_basic_insights(spotify_client)
            
    except Exception as e:
        app.logger.error(f"Error generating comprehensive music insights: {e}")
        return generate_basic_insights(spotify_client)

def generate_ultra_detailed_psychological_analysis(comprehensive_music_data, gemini_api_key):
    """Use Gemini 2.5 Flash Preview 5/20 to generate extremely comprehensive psychological and musical insights"""
    try:
        import google.generativeai as genai
        
        # Clear any previous configuration and set new API key
        try:
            genai.configure(api_key="")  # Clear with empty key first
        except:
            pass  # Ignore errors when clearing
        
        genai.configure(api_key=gemini_api_key)
        # Use the most advanced model available
        model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
        
        # Create an extremely detailed prompt for comprehensive analysis
        prompt = f"""
You are an expert music psychologist and data analyst. Analyze this comprehensive Spotify listening data to create the most detailed psychological and musical profile possible. Be specific, insightful, and thorough.

COMPREHENSIVE LISTENING DATA:
{json.dumps(comprehensive_music_data, indent=2)}

ANALYSIS REQUIREMENTS:
Create an extremely detailed analysis covering ALL of these sections. Be specific with examples and provide deep insights.

1. **CORE PSYCHOLOGICAL PROFILE**
   - Personality traits revealed through music choices
   - Emotional patterns and coping mechanisms
   - Cognitive preferences and thinking styles
   - Risk tolerance and openness to new experiences
   - Social vs. solitary listening patterns
   - Life phase indicators (based on genre evolution)

2. **MUSICAL IDENTITY ANALYSIS**
   - Musical sophistication level and complexity preferences
   - Genre loyalty vs. exploration patterns
   - Artist discovery behavior and risk-taking
   - Mainstream vs. underground positioning
   - Cultural identity markers in music choices
   - Generational musical influences

3. **LISTENING BEHAVIOR PSYCHOLOGY**
   - Mood regulation patterns through music
   - Energy level management preferences
   - Concentration and focus music patterns
   - Social context preferences (party vs. personal)
   - Temporal listening habits and routines
   - Replay behavior and emotional attachment patterns

4. **GENRE EVOLUTION & GROWTH PATTERNS**
   - Musical journey and evolution over time
   - Comfort zone vs. exploration balance
   - Seasonal or cyclical preferences
   - Life event impact on musical taste
   - Prediction of future musical directions

5. **ARTIST RELATIONSHIP PATTERNS**
   - Loyalty vs. novelty-seeking balance
   - Fan behavior and dedication levels
   - Discovery pathway preferences
   - Artist popularity comfort zones
   - International vs. domestic preferences

6. **DEEP MUSICAL INSIGHTS**
   - Lyrical vs. instrumental preferences
   - Production style preferences
   - Era and vintage preferences
   - Technical complexity appreciation
   - Collaborative vs. solo artist preferences

7. **EMOTIONAL INTELLIGENCE MARKERS**
   - Emotional range in musical choices
   - Maturity indicators in taste evolution
   - Stress response musical patterns
   - Celebration and joy expression through music
   - Introspection and contemplation preferences

8. **PREDICTIVE BEHAVIORAL INSIGHTS**
   - Likely music discovery methods
   - Recommended genres for exploration
   - Optimal recommendation timing
   - Social sharing likelihood
   - Concert attendance probability

Respond with a detailed JSON object:
{{
    "psychological_profile": {{
        "core_personality": "[Detailed analysis of personality traits with specific examples from their data]",
        "emotional_patterns": "[Deep dive into emotional regulation and expression through music]",
        "cognitive_style": "[Analysis of thinking patterns revealed through musical choices]",
        "social_tendencies": "[Social vs. private listening patterns and implications]",
        "life_phase_indicators": "[What their music reveals about their current life stage]"
    }},
    "musical_identity": {{
        "sophistication_level": "[Assessment of musical knowledge and complexity appreciation]",
        "exploration_style": "[How they discover and adopt new music]",
        "cultural_positioning": "[Their place in musical culture and communities]",
        "authenticity_markers": "[What reveals their genuine vs. social music preferences]",
        "identity_evolution": "[How their musical identity has changed over time]"
    }},
    "listening_psychology": {{
        "mood_regulation": "[How they use music for emotional management]",
        "energy_management": "[Music choices for different energy states]",
        "focus_patterns": "[Music for concentration, work, relaxation]",
        "ritual_behaviors": "[Repeated listening patterns and their meanings]",
        "attachment_style": "[How they form emotional connections to music]"
    }},
    "growth_trajectory": {{
        "evolution_pattern": "[Their musical journey and development over time]",
        "future_predictions": "[Likely future musical directions based on patterns]",
        "exploration_readiness": "[How open they are to new musical experiences]",
        "influence_susceptibility": "[How external factors affect their musical choices]"
    }},
    "behavioral_insights": {{
        "recommendation_optimal_timing": "[Best times and contexts for music recommendations]",
        "discovery_preferences": "[How they prefer to find new music]",
        "social_sharing_likelihood": "[Probability and style of sharing music with others]",
        "purchase_behavior": "[Likelihood of buying music, merch, or concert tickets]",
        "playlist_creation_style": "[How they organize and curate their music]"
    }},
    "summary_insights": {{
        "key_findings": ["[5-7 most important insights about this user]"],
        "unique_traits": ["[3-5 things that make this user's taste unique]"],
        "recommendation_strategy": "[Optimal approach for recommending music to this user]",
        "psychological_type": "[Overall psychological archetype this user represents]"
    }},
    "analysis_confidence": {{
        "data_richness": "[Assessment of how much data was available for analysis]",
        "insight_confidence": "[Confidence level in the psychological insights]",
        "prediction_reliability": "[How reliable the behavioral predictions are]"
    }},
    "analysis_ready": true
}}

CRITICAL INSTRUCTIONS:
- Be extremely specific and use actual data points from their listening history
- Mention specific artists, genres, and patterns you observe
- Connect musical choices to psychological theories and behavioral science
- Provide actionable insights for music recommendations
- Be honest about data limitations and confidence levels
- Keep each section substantive (3-5 sentences minimum per field)
- Use psychological and musicological terminology appropriately
- Ground insights in the actual data provided, not generalizations
"""

        app.logger.info("Generating ultra-detailed psychological music analysis with Gemini 2.5 Flash Preview...")
        start_time = time.time()
        
        response = model.generate_content(prompt)
        duration = time.time() - start_time
        
        if response and response.text:
            # Parse the JSON response
            import re
            
            # Extract JSON from the response
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                insights_json = json.loads(json_match.group())
                app.logger.info(f"Ultra-detailed psychological analysis generated successfully in {duration:.2f}s")
                app.logger.info(f"Analysis includes {len(insights_json)} main sections with deep psychological insights")
                return insights_json
            else:
                app.logger.warning("Could not extract JSON from ultra-detailed analysis response")
                return None
        else:
            app.logger.warning("Empty response from ultra-detailed psychological analysis")
            return None
            
    except Exception as e:
        app.logger.error(f"Error in ultra-detailed psychological analysis: {e}")
        return None

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
        
        # Clear any previous configuration and set new API key
        try:
            genai.configure(api_key="")  # Clear with empty key first
        except:
            pass  # Ignore errors when clearing
        
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
        
        # Create comprehensive prompt for musical analysis that matches frontend expectations
        prompt = f"""
Analyze this user's comprehensive Spotify listening data and provide detailed musical expertise insights.

MUSIC DATA:
{json.dumps(music_data, indent=2)}

Respond ONLY with a JSON object in this exact format:
{{
    "genre_mastery": {{
        "primary_expertise": "[Detailed analysis of their main genre expertise and sophistication level. Include specific genres they've mastered and their depth of knowledge]"
    }},
    "artist_dynamics": {{
        "loyalty_patterns": "[Analysis of how they relate to artists - are they loyal fans or explorers? Do they follow artists' entire discographies or cherry-pick hits?]"
    }},
    "musical_sophistication": {{
        "technical_appreciation": "[Assessment of their ability to appreciate musical complexity, production quality, instrumentation, etc. Are they casual listeners or do they notice technical details?]"
    }},
    "listening_contexts": {{
        "primary_contexts": "[Analysis of when and how they listen to music - for focus, energy, mood regulation, social settings, etc.]"
    }},
    "insights_summary": {{
        "unique_taste_markers": [
            "[First unique aspect of their musical taste]",
            "[Second unique aspect of their musical taste]",
            "[Third unique aspect of their musical taste]",
            "[Fourth unique aspect of their musical taste]",
            "[Fifth unique aspect of their musical taste]"
        ]
    }},
    "analysis_ready": true
}}

Guidelines:
- Be specific and use actual data from their listening history
- Mention specific artists, genres, and patterns you observe
- Each section should be 2-3 detailed sentences
- Focus on musical expertise and sophistication rather than personality
- Use technical music terms appropriately
- Be insightful about their musical journey and evolution
- The unique_taste_markers should be specific, actionable insights
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
    """Main dashboard showing user's music with comprehensive AI analysis"""
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
    
    # Check if we have cached analyses
    psychological_analysis = session.get('psychological_analysis')
    musical_analysis = session.get('musical_analysis')
    
    # Generate comprehensive music insights without API key for now (will be generated client-side with user's key)
    music_insights = generate_music_taste_insights(spotify_client)
    
    return render_template('dashboard.html', 
                         user=user, 
                         current_track=current_track,
                         playback_state=playback_state,
                         music_insights=music_insights,
                         psychological_analysis=psychological_analysis,
                         musical_analysis=musical_analysis)

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
        # Mark the recommendation as played if we have the current recommendation ID
        current_rec_id = session.get('current_recommendation_id')
        if current_rec_id:
            recommendation = Recommendation.query.get(current_rec_id)
            if recommendation and recommendation.user_id == user.id:
                recommendation.mark_as_played()
                app.logger.info(f"Marked recommendation {current_rec_id} as played")
        
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
        # Clear any previous configuration and set new API key
        try:
            genai.configure(api_key="")  # Clear with empty key first
        except:
            pass  # Ignore errors when clearing
        
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
            # Check for rate limit errors in feedback analysis
            error_str = str(e).lower()
            if any(rate_limit_indicator in error_str for rate_limit_indicator in [
                'rate limit', 'quota', '429', 'too many requests', 'resource_exhausted'
            ]):
                app.logger.warning(f"FEEDBACK: Gemini rate limit detected - {str(e)}")
                return jsonify({
                    'success': False, 
                    'message': 'You\'ve reached your Gemini API rate limit. Please wait a few minutes before providing feedback to allow your quota to refresh.',
                    'rate_limit_error': True,
                    'suggested_wait_time': '2-3 minutes'
                }), 429
            
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
        # Check for rate limit errors in overall feedback processing
        error_str = str(e).lower()
        if any(rate_limit_indicator in error_str for rate_limit_indicator in [
            'rate limit', 'quota', '429', 'too many requests', 'resource_exhausted'
        ]):
            app.logger.warning(f"FEEDBACK: Gemini rate limit detected in main handler - {str(e)}")
            return jsonify({
                'success': False, 
                'message': 'You\'ve reached your Gemini API rate limit. Please wait a few minutes before providing feedback to allow your quota to refresh.',
                'rate_limit_error': True,
                'suggested_wait_time': '2-3 minutes'
            }), 429
        
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
    """Process user feedback entries to generate AI-powered insights with memory optimization"""
    if not feedbacks:
        return "No feedback available yet. Start rating songs to get personalized insights!"
    
    # If no API key, fall back to enhanced basic insights
    if not gemini_api_key:
        return generate_enhanced_basic_feedback_insights(feedbacks)
    
    try:
        # Memory optimization: limit and chunk feedback processing
        max_feedbacks_to_process = min(len(feedbacks), 15)  # Reduced from 25 to prevent OOM
        chunk_size = 5  # Process 5 feedback entries at a time
        
        app.logger.info(f"Processing {max_feedbacks_to_process} feedback entries in chunks of {chunk_size}")
        
        # Get comprehensive feedback data in smaller chunks
        import google.generativeai as genai
        
        # Clear any previous configuration and set new API key
        try:
            genai.configure(api_key="")  # Clear with empty key first
        except:
            pass  # Ignore errors when clearing
        
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
        
        chunk_insights = []
        feedbacks_to_process = feedbacks[:max_feedbacks_to_process]
        
        # Process feedback in chunks to reduce memory usage
        for i in range(0, len(feedbacks_to_process), chunk_size):
            chunk = feedbacks_to_process[i:i + chunk_size]
            app.logger.info(f"Processing feedback chunk {i//chunk_size + 1}/{(len(feedbacks_to_process) + chunk_size - 1)//chunk_size}")
            
            # Prepare minimal feedback data for this chunk
            feedback_data = []
            for feedback in chunk:
                from models import Recommendation
                recommendation = Recommendation.query.get(feedback.recommendation_id)
                if recommendation:
                    feedback_entry = {
                        'track_name': recommendation.track_name,
                        'artist_name': recommendation.artist_name,
                        'sentiment': feedback.sentiment,
                        'feedback_text': feedback.feedback_text,
                        'was_played': recommendation.was_played,
                        'recommendation_method': recommendation.recommendation_method
                    }
                    feedback_data.append(feedback_entry)
            
            # Create concise prompt for chunk analysis
            chunk_prompt = f"""
Analyze this set of {len(feedback_data)} music feedback entries and provide key insights in 2-3 sentences:

FEEDBACK DATA:
{json.dumps(feedback_data, indent=1)}

Focus on:
- Musical preference patterns
- Recommendation performance
- Key learning points

Provide a concise summary in 150 words or less.
"""
            
            try:
                response = model.generate_content(chunk_prompt)
                if response and response.text:
                    chunk_insight = response.text.strip()
                    chunk_insights.append(chunk_insight)
                    app.logger.info(f"Generated chunk insight ({len(chunk_insight)} characters)")
                else:
                    app.logger.warning(f"No response for chunk {i//chunk_size + 1}")
            except Exception as e:
                app.logger.error(f"Error processing chunk {i//chunk_size + 1}: {e}")
                continue
        
        # If we have chunk insights, combine them into a final summary
        if chunk_insights:
            app.logger.info("Generating final comprehensive summary from chunk insights")
            
            # Create final summary prompt with reduced size
            final_prompt = f"""
Based on these individual feedback analysis chunks, create a comprehensive but concise music taste profile:

CHUNK INSIGHTS:
{chr(10).join([f"Chunk {i+1}: {insight}" for i, insight in enumerate(chunk_insights)])}

TOTAL FEEDBACK ANALYZED: {max_feedbacks_to_process} entries

Create a comprehensive analysis covering:
1. **Musical Taste Patterns**: Key preferences and patterns identified
2. **Recommendation Performance**: How well the AI is learning their taste
3. **Learning Insights**: Specific improvements and discoveries
4. **Future Directions**: Recommended musical exploration paths

Limit response to 400-500 words. Be specific but concise.
"""
            
            response = model.generate_content(final_prompt)
            if response and response.text:
                final_insights = response.text.strip()
                app.logger.info(f"Generated final comprehensive insights ({len(final_insights)} characters)")
                return final_insights
            else:
                app.logger.warning("Failed to generate final summary, combining chunk insights")
                return " ".join(chunk_insights)
        else:
            app.logger.warning("No chunk insights generated, using enhanced fallback")
            return generate_enhanced_basic_feedback_insights(feedbacks)
            
    except Exception as e:
        app.logger.error(f"Error generating AI feedback insights: {e}")
        return generate_enhanced_basic_feedback_insights(feedbacks)

def generate_enhanced_basic_feedback_insights(feedbacks):
    """Generate enhanced detailed feedback insights when AI is not available"""
    if not feedbacks:
        return "No feedback available yet. Start rating songs to get personalized insights!"
    
    # Comprehensive statistical analysis
    positive_count = sum(1 for f in feedbacks if f.sentiment and 'positive' in f.sentiment.lower())
    negative_count = sum(1 for f in feedbacks if f.sentiment and 'negative' in f.sentiment.lower())
    neutral_count = len(feedbacks) - positive_count - negative_count
    total_feedback = len(feedbacks)
    
    # Analyze artists and tracks
    artists_mentioned = {}
    tracks_with_feedback = []
    recent_feedback_trends = []
    
    for feedback in feedbacks[-10:]:  # Last 10 feedback entries
        from models import Recommendation
        recommendation = Recommendation.query.get(feedback.recommendation_id)
        if recommendation:
            artist = recommendation.artist_name
            artists_mentioned[artist] = artists_mentioned.get(artist, 0) + 1
            tracks_with_feedback.append({
                'track': recommendation.track_name,
                'artist': artist,
                'sentiment': feedback.sentiment,
                'played': recommendation.was_played
            })
            recent_feedback_trends.append(feedback.sentiment or 'neutral')
    
    # Generate comprehensive insights
    insights = []
    
    # Overall feedback patterns
    if total_feedback >= 5:
        feedback_ratio = positive_count / total_feedback
        if feedback_ratio > 0.7:
            insights.append(f"**Excellent Recommendation Success Rate**: You've expressed positive sentiment on {positive_count} out of {total_feedback} recommendations ({feedback_ratio:.1%} success rate), indicating the AI is learning your taste exceptionally well.")
        elif feedback_ratio > 0.5:
            insights.append(f"**Good Learning Progress**: With {positive_count} positive responses out of {total_feedback} total feedback entries ({feedback_ratio:.1%}), the system is steadily improving at understanding your musical preferences.")
        else:
            insights.append(f"**Calibration Phase**: The AI is still learning your unique taste profile. Out of {total_feedback} feedback entries, {positive_count} were positive, {negative_count} were negative, and {neutral_count} were neutral. This feedback is crucial for improvement.")
    
    # Artist preference analysis
    if artists_mentioned:
        favorite_artists = sorted(artists_mentioned.items(), key=lambda x: x[1], reverse=True)[:3]
        if len(favorite_artists) >= 2:
            insights.append(f"**Artist Preference Patterns**: Based on your feedback, you've engaged most with recommendations featuring {', '.join([f'{artist} ({count} times)' for artist, count in favorite_artists])}. This helps the AI understand your artist affinity patterns.")
    
    # Recent trends analysis
    if len(recent_feedback_trends) >= 5:
        recent_positive = recent_feedback_trends.count('positive')
        recent_negative = recent_feedback_trends.count('negative')
        if recent_positive > recent_negative:
            insights.append(f"**Recent Improvement Trend**: Your last {len(recent_feedback_trends)} feedback entries show {recent_positive} positive responses, suggesting the recommendation system is getting significantly better at matching your taste preferences.")
        elif recent_negative > recent_positive:
            insights.append(f"**Learning Opportunity Detected**: Your recent feedback shows {recent_negative} negative responses out of {len(recent_feedback_trends)} entries. This pattern indicates the system needs to adjust its approach to better align with your current musical preferences.")
    
    # Engagement analysis
    played_tracks = sum(1 for track in tracks_with_feedback if track['played'])
    if played_tracks > 0:
        play_rate = played_tracks / len(tracks_with_feedback)
        insights.append(f"**Listening Engagement Analysis**: You've actually played {played_tracks} out of {len(tracks_with_feedback)} recently recommended tracks ({play_rate:.1%} play rate), which provides valuable behavioral data beyond just sentiment feedback.")
    
    # Learning and improvement notes
    insights.append(f"**Comprehensive Learning Profile**: With {total_feedback} total feedback entries analyzed, the system has built a detailed preference profile including sentiment patterns, artist affinities, and listening behaviors. Each piece of feedback helps refine future recommendations to better match your evolving musical taste.")
    
    # Future recommendations guidance
    if negative_count > 0:
        insights.append(f"**Adaptive Learning Focus**: The {negative_count} negative feedback entries provide crucial information about musical directions to avoid, helping the AI eliminate unsuitable recommendation patterns and focus on styles that resonate with your preferences.")
    
    return " ".join(insights)

def generate_basic_feedback_insights(feedbacks):
    """Generate basic feedback insights when AI is not available (kept for compatibility)"""
    return generate_enhanced_basic_feedback_insights(feedbacks)

@app.route('/feedback-insights', methods=['GET', 'POST'])
def get_feedback_insights():
    logger.debug('Fetching feedback insights')
    
    # Log memory usage before processing
    try:
        import psutil
        process = psutil.Process()
        memory_before = process.memory_info().rss / 1024 / 1024  # MB
        app.logger.info(f"Memory usage before feedback processing: {memory_before:.1f}MB")
    except Exception:
        memory_before = None
    
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
        
        # Log memory usage after processing
        if memory_before:
            try:
                memory_after = process.memory_info().rss / 1024 / 1024  # MB
                memory_diff = memory_after - memory_before
                app.logger.info(f"Memory usage after feedback processing: {memory_after:.1f}MB (diff: {memory_diff:+.1f}MB)")
                
                # Warning if memory usage increased significantly
                if memory_diff > 50:  # More than 50MB increase
                    app.logger.warning(f"High memory increase during feedback processing: {memory_diff:.1f}MB")
            except Exception:
                pass
        
        logger.debug('Successfully generated feedback insights')
        return jsonify({'insights': insights, 'ai_powered': bool(gemini_api_key)})

    except Exception as e:
        logger.error(f'Error getting feedback insights: {str(e)}', exc_info=True)
        return jsonify({'error': 'Failed to get feedback insights'}), 500

@app.route('/api/current-track')
def api_current_track():
    """API endpoint to get current track information"""
    try:
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        
        user = User.query.get(session['user_id'])
        if not user or not user.access_token:
            return jsonify({'error': 'User not found or no access token'}), 401
        
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
        app.logger.error(f"Error getting current track: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/performance-toggle', methods=['POST'])
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
        # You can customize this logic based on your performance requirements
        if 'user_id' in session:
            user = User.query.get(session['user_id'])
            if user:
                # Enable lightning mode for certain conditions
                # Example: users who have made recent recommendations, have cached data, etc.
                recent_recommendations = Recommendation.query.filter_by(
                    user_id=user.id
                ).filter(
                    Recommendation.created_at > datetime.utcnow() - timedelta(hours=1)
                ).count()
                
                if recent_recommendations > 0:
                    config['lightning_enabled'] = True
                    config['mode'] = 'lightning'
                    config['cached_data'] = True
                    
                # Check if user has recent profile data (you might have this in your database)
                # For now, we'll assume profile might be cached if user has recent activity
                if recent_recommendations > 2:
                    config['cached_profile'] = True
        
        # You can add more sophisticated logic here based on:
        # - Server load
        # - Time of day
        # - User preferences
        # - Available API quotas
        
        return jsonify(config)
        
    except Exception as e:
        app.logger.error(f"Error in performance toggle: {str(e)}")
        # Return default safe configuration on error
        return jsonify({
            'endpoint': '/ai-recommendation',
            'mode': 'standard',
            'lightning_enabled': False,
            'cached_data': False,
            'cached_profile': False
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
        
        # Clear any previous configuration and set new API key
        try:
            genai.configure(api_key="")  # Clear with empty key first
        except:
            pass  # Ignore errors when clearing
        
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
        
        # Get enhanced recent recommendations to avoid duplicates in playlist
        rec_tracking = get_enhanced_recent_recommendations(user, hours_back=48, include_artist_counts=True)  # Look back 48 hours for playlists
        recent_recommendations = rec_tracking['formatted_list']
        artist_frequency = rec_tracking['artist_frequency']
        
        # Build a more comprehensive avoidance list for playlists
        all_recent_tracks = []
        if recent_recommendations:
            all_recent_tracks.extend(recent_recommendations)
        
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
        
        app.logger.info(f"Playlist creation: Avoiding {len(all_recent_tracks)} recent tracks and {len(over_used_artists)} overused artists")
        
        # Create comprehensive prompt for generating multiple tracks
        prompt = f"""Based on this user's comprehensive Spotify listening data and psychological analysis, recommend exactly {song_count} specific songs for a personalized playlist.

USER PSYCHOLOGICAL & MUSICAL ANALYSIS:
{user_analysis}

{frequent_artists_warning}

RECENTLY RECOMMENDED TRACKS (DO NOT REPEAT THESE):
{all_recent_tracks}

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
            # Use threading.Timer for cross-platform timeout (Windows compatible)
            import threading
            
            response = None
            error_occurred = None
            
            def generate_with_timeout():
                nonlocal response, error_occurred
                try:
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
                app.logger.error("AI generation timed out")
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
                        psychological_analysis=f"Playlist: {user_analysis[:200]}...",
                        listening_data_snapshot="{}",  # Minimal for playlist tracks
                        session_adjustment=playlist_description,
                        recommendation_method='playlist'
                    )
                    db.session.add(playlist_rec)
            
            db.session.commit()
            app.logger.info(f"Saved {len(track_uris)} playlist tracks to recommendation history")
            
        except Exception as e:
            app.logger.warning(f"Could not save playlist tracks to recommendation history: {e}")
        
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
        error_str = str(e).lower()
        if any(rate_limit_indicator in error_str for rate_limit_indicator in [
            'rate limit', 'quota', '429', 'too many requests', 'resource_exhausted'
        ]):
            app.logger.warning(f"PLAYLIST: Gemini rate limit detected - {str(e)}")
            return jsonify({
                'success': False, 
                'message': 'You\'ve reached your Gemini API rate limit. Please wait a few minutes before creating another playlist to allow your quota to refresh.',
                'rate_limit_error': True,
                'suggested_wait_time': '2-3 minutes'
            }), 429
        
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

@app.route('/ai-recommendation', methods=['POST'])
def ai_recommendation():
    """Enhanced standard AI recommendation with improved duplicate prevention"""
    from flask import jsonify, session, request
    import json, time
    import google.generativeai as genai
    
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    
    # Get request data safely
    request_data = request.get_json() or {}
    
    # Get Gemini API key from request (optional for backward compatibility)
    gemini_api_key = request_data.get('gemini_api_key') or request_data.get('custom_gemini_key')
    
    # Get session adjustment if provided
    session_adjustment = request_data.get('session_adjustment', '').strip()
    if session_adjustment:
        session['session_adjustment'] = session_adjustment
    else:
        session_adjustment = session.get('session_adjustment', '')
    
    # Configure Gemini if API key is provided
    if gemini_api_key:
        # Debug logging to verify API key
        key_preview = gemini_api_key[:8] + "..." if len(gemini_api_key) > 8 else gemini_api_key
        app.logger.info(f"STANDARD: Attempting to configure Gemini with API key: {key_preview}")
        
        # Configure Gemini with user's API key only - do not use environment variables
        try:
            # Clear any previous configuration and set new API key
            try:
                genai.configure(api_key="")  # Clear with empty key first
            except:
                pass  # Ignore errors when clearing
            
            # Configure with user's API key
            genai.configure(api_key=gemini_api_key)
                
            app.logger.info("STANDARD: Successfully configured Gemini with user API key")
        except Exception as config_error:
            app.logger.error(f"Failed to configure Gemini with user API key: {config_error}")
            return jsonify({
                'success': False, 
                'message': f'Failed to configure Gemini API: {str(config_error)}',
                'api_error': True
            }), 400
        
        app.logger.info("STANDARD: Using provided Gemini API key for enhanced recommendations")
    else:
        app.logger.warning("STANDARD: No Gemini API key provided - using basic recommendations")
        # Return a message asking for API key for full functionality
        return jsonify({
            'success': False, 
            'message': 'Gemini API key required for AI recommendations. Please add your API key in the settings.',
            'requires_api_key': True
        }), 400
    
    # Rate limiting
    total_start_time = time.time()
    current_time = time.time()
    last_rec_time = session.get('last_recommendation_time', 0)
    if current_time - last_rec_time < 2:  # 2 second minimum between recommendations
        return jsonify({
            'success': False, 
            'message': 'Please wait a moment before requesting another recommendation.'
        }), 429
    
    try:
        # Collect music data
        app.logger.info("STANDARD: Starting enhanced AI recommendation...")
        app.logger.info("STANDARD: Collecting music data...")
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
                },
                'top_genres': []
            }
        
        data_collection_duration = time.time() - data_collection_start
        app.logger.info(f"STANDARD: Data collection complete - {data_collection_duration:.2f}s")
        
        # Get enhanced recent recommendations to avoid duplicates
        rec_tracking = get_enhanced_recent_recommendations(user, hours_back=24)
        recent_recommendations = rec_tracking['formatted_list']
        artist_frequency = rec_tracking['artist_frequency']
        diversity_warning = rec_tracking['warning_message']
        # NEW: Get explicit blacklist for better duplicate prevention
        blacklist_tracks = rec_tracking['blacklist_tracks']
        
        app.logger.info(f"STANDARD: Found {rec_tracking['total_count']} recent recommendations for duplicate prevention")
        if diversity_warning:
            app.logger.info(f"STANDARD: Diversity warning - {diversity_warning}")
        
        # Generate user profile
        app.logger.info("STANDARD: Generating user profile...")
        profile_start = time.time()
        
        # Create model AFTER configuration with fresh API key
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        profile_prompt = f"""
Analyze this user's Spotify data and create a concise psychological music profile:

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
            user_profile = profile_response.text.strip() if profile_response and profile_response.text else "Music lover with diverse taste who enjoys discovering new sounds."
        except Exception as e:
            # Check for rate limit errors in profile generation
            error_str = str(e).lower()
            if any(rate_limit_indicator in error_str for rate_limit_indicator in [
                'rate limit', 'quota', '429', 'too many requests', 'resource_exhausted'
            ]):
                app.logger.warning(f"STANDARD: Gemini rate limit detected during profile generation - {str(e)}")
                return jsonify({
                    'success': False, 
                    'message': 'You\'ve reached your Gemini API rate limit. Please wait a few minutes before requesting another recommendation to allow your quota to refresh.',
                    'rate_limit_error': True,
                    'suggested_wait_time': '2-3 minutes'
                }), 429
            
            app.logger.warning(f"Profile generation failed: {e}")
            user_profile = "Music lover with diverse taste who enjoys discovering new sounds."
        
        profile_duration = time.time() - profile_start
        app.logger.info(f"STANDARD: User profile complete - {profile_duration:.2f}s")

        # Generate AI recommendation
        app.logger.info("STANDARD: Generating AI recommendation...")
        recommendation_start = time.time()
        
        # Create comprehensive prompt for recommendation
        recommendation_prompt = f"""
Based on this user's comprehensive music data, recommend ONE specific song that perfectly matches their taste.

USER PSYCHOLOGICAL PROFILE:
{user_profile}

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
            recommendation_response = model.generate_content(recommendation_prompt)
            ai_recommendation_text = recommendation_response.text.strip() if recommendation_response and recommendation_response.text else None
            
            if not ai_recommendation_text:
                raise Exception("Empty AI recommendation response")
                
            app.logger.info(f"AI recommended: {ai_recommendation_text}")
            
        except Exception as e:
            # Check for rate limit errors in recommendation generation
            error_str = str(e).lower()
            if any(rate_limit_indicator in error_str for rate_limit_indicator in [
                'rate limit', 'quota', '429', 'too many requests', 'resource_exhausted'
            ]):
                app.logger.warning(f"STANDARD: Gemini rate limit detected during recommendation - {str(e)}")
                return jsonify({
                    'success': False, 
                    'message': 'You\'ve reached your Gemini API rate limit. Please wait a few minutes before requesting another recommendation to allow your quota to refresh.',
                    'rate_limit_error': True,
                    'suggested_wait_time': '2-3 minutes'
                }), 429
            
            app.logger.error(f"AI recommendation generation failed: {e}")
            return jsonify({
                'success': False, 
                'message': 'Failed to generate AI recommendation. Please try again.'
            }), 500
        
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
            app.logger.error(f"Failed to parse AI recommendation: {ai_recommendation_text}")
            return jsonify({
                'success': False, 
                'message': 'Failed to parse AI recommendation. Please try again.'
            }), 500
        
        # Search for the track on Spotify
        app.logger.info(f"STANDARD: Searching Spotify for: {song_title} by {artist_name}")
        spotify_client = SpotifyClient(user.access_token)
        
        # Try exact search first
        search_query = f'track:"{song_title}" artist:"{artist_name}"'
        search_results = spotify_client.search_tracks(search_query, limit=5)
        
        if not search_results or not search_results.get('tracks', {}).get('items'):
            # Try broader search
            app.logger.info("STANDARD: Exact search failed, trying broader search")
            search_query = f"{song_title} {artist_name}"
            search_results = spotify_client.search_tracks(search_query, limit=5)
        
        if not search_results or not search_results.get('tracks', {}).get('items'):
            app.logger.error(f"STANDARD: Could not find track on Spotify: {song_title} by {artist_name}")
            return jsonify({
                'success': False, 
                'message': f'Could not find "{song_title}" by {artist_name} on Spotify. Please try again.'
            }), 404
        
        # Use structured LLM to select best match if multiple results
        from structured_llm import structured_llm
        selection_result = structured_llm.select_spotify_result(
            model, song_title, artist_name, search_results['tracks']['items']
        )
        
        selected_track = selection_result.selected_result
        app.logger.info(f"STANDARD: Selected track: {selected_track.track_name} by {selected_track.artist_name}")
        
        recommendation_duration = time.time() - recommendation_start
        app.logger.info(f"STANDARD: AI recommendation complete - {recommendation_duration:.2f}s")
        
        # Generate detailed reasoning for the recommendation
        reasoning_prompt = f"""
Explain in 2-3 sentences why you recommended "{selected_track.track_name}" by {selected_track.artist_name} for this user.

Consider their:
- Psychological profile: {user_profile}
- Current musical context: {music_data['current_track']['item']['name']
                          if isinstance(music_data['current_track'], dict) and music_data['current_track'].get('item')
                          else 'None'}
- Session context: {session_adjustment if session_adjustment else 'General discovery'}

Keep it personal and insightful.
"""
        
        try:
            reasoning_response = model.generate_content(reasoning_prompt)
            ai_reasoning = reasoning_response.text.strip() if reasoning_response and reasoning_response.text else f"This track perfectly complements your musical taste and current listening mood."
        except Exception as e:
            app.logger.warning(f"Failed to generate reasoning: {e}")
            ai_reasoning = f"This track was selected based on your musical preferences and listening patterns."
        
        # Save recommendation to database
        recommendation = Recommendation(
            user_id=user.id,
            track_name=selected_track.track_name,
            artist_name=selected_track.artist_name,
            track_uri=selected_track.track_uri,
            album_name=selected_track.album_name,
            ai_reasoning=ai_reasoning,
            psychological_analysis=user_profile,
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
        
        # Store recommendation ID in session for feedback
        session['current_recommendation_id'] = recommendation.id
        session['last_recommendation_time'] = current_time
        
        total_duration = time.time() - total_start_time
        app.logger.info(f"STANDARD: Total recommendation process complete - {total_duration:.2f}s")
        
        # Return successful recommendation
        return jsonify({
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
                'total_duration': round(total_duration, 2),
                'data_collection': round(data_collection_duration, 2),
                'profile_generation': round(profile_duration, 2),
                'recommendation_generation': round(recommendation_duration, 2),
                'duplicate_prevention': {
                    'tracks_avoided': len(blacklist_tracks),
                    'total_recent_recommendations': rec_tracking['total_count']
                }
            },
            'psychological_analysis': user_profile,
            'session_context': session_adjustment if session_adjustment else None
        })
        
    except Exception as e:
        app.logger.error(f"Enhanced standard AI recommendation failed: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'AI recommendation failed: {str(e)}'}), 500

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
        app.logger.info(f"DUPLICATE PREVENTION: Analyzing {len(all_recent_recs)} total recommendations from last 72 hours")
        
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
    
    # Create explicit track blacklist for the AI prompt (ENHANCEMENT: Bug Fix #1)
    blacklist_tracks = []
    
    # Get ALL recent recommendations for comprehensive blacklist (not just display_recs)
    for rec in recent_recs:
        # Add track to blacklist
        blacklist_tracks.append(f'"{rec.track_name}" by {rec.artist_name}')
    
    app.logger.info(f"DUPLICATE PREVENTION: Found {total_count} recommendations in last {hours_back}h, showing {len(display_recs)} in prompt")
    app.logger.info(f"DUPLICATE PREVENTION: Created blacklist with {len(blacklist_tracks)} tracks")
    
    return {
        'formatted_list': display_recs,  # Limited for prompt display
        'artist_frequency': artist_frequency,
        'total_count': total_count,  # Accurate total count
        'warning_message': warning_message,
        'blacklist_tracks': blacklist_tracks  # Explicit track blacklist only
    }
    
@app.route('/api/generate-psychological-analysis', methods=['POST'])
def api_generate_psychological_analysis():
    """Generate a comprehensive psychological analysis of the user's music taste"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        data = request.get_json()
        custom_gemini_key = data.get('custom_gemini_key') if data else None
        
        if not custom_gemini_key:
            return jsonify({'success': False, 'message': 'Gemini API key required'}), 400
        
        # Initialize Spotify client
        spotify_client = SpotifyClient(
            access_token=user.access_token
        )
        
        # Collect comprehensive music data
        app.logger.info("Collecting comprehensive music data for psychological analysis...")
        
        # Get current track and playback state
        current_track = spotify_client.get_current_track()
        playback_state = spotify_client.get_playback_state()
        
        # Get listening history and preferences
        recent_tracks = spotify_client.get_recent_tracks(limit=50)
        top_artists_short = spotify_client.get_top_artists(time_range='short_term', limit=50)
        top_artists_medium = spotify_client.get_top_artists(time_range='medium_term', limit=50)
        top_artists_long = spotify_client.get_top_artists(time_range='long_term', limit=50)
        top_tracks_short = spotify_client.get_top_tracks(time_range='short_term', limit=50)
        top_tracks_medium = spotify_client.get_top_tracks(time_range='medium_term', limit=50)
        top_tracks_long = spotify_client.get_top_tracks(time_range='long_term', limit=50)
        
        # Get saved tracks and playlists
        saved_tracks = spotify_client.get_saved_tracks(limit=50)
        user_playlists = spotify_client.get_user_playlists(limit=50)
        
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
        analysis = generate_ultra_detailed_psychological_analysis(comprehensive_music_data, custom_gemini_key)
        
        if analysis:
            app.logger.info("Psychological analysis generated successfully")
            return jsonify({'success': True, 'analysis': analysis})
        else:
            app.logger.error("Failed to generate psychological analysis")
            return jsonify({'success': False, 'message': 'Failed to generate analysis'}), 500
            
    except Exception as e:
        app.logger.error(f"Error in psychological analysis API: {str(e)}")
        return jsonify({'success': False, 'message': f'Internal server error: {str(e)}'}), 500

@app.route('/api/generate-musical-analysis', methods=['POST'])
def api_generate_musical_analysis():
    """Generate comprehensive musical analysis for the user"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'})
        
        custom_gemini_key = data.get('custom_gemini_key')
        if not custom_gemini_key:
            return jsonify({'success': False, 'message': 'Gemini API key is required'})
        
        # Get user from session
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': 'User not authenticated'})
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        
        spotify_client = SpotifyClient(user.access_token)
        
        # Check if token is valid
        if not spotify_client.get_current_playback():
            # Token might be expired, try to refresh
            if user.refresh_token:
                refresh_result = refresh_user_token(user)
                if not refresh_result:
                    return jsonify({'success': False, 'message': 'Unable to refresh Spotify token'})
                spotify_client = SpotifyClient(user.access_token)
        
        # Generate comprehensive music analysis
        music_data = {
            'top_artists': spotify_client.get_top_artists(limit=50, time_range='medium_term'),
            'top_tracks': spotify_client.get_top_tracks(limit=50, time_range='medium_term'),
            'recent_tracks': spotify_client.get_recently_played(limit=50),
            'saved_tracks': spotify_client.get_saved_tracks(limit=50),
            'playlists': spotify_client.get_user_playlists(limit=30)
        }
        
        # Generate analysis using Gemini
        analysis = generate_ai_music_analysis(music_data, custom_gemini_key)
        
        return jsonify({
            'success': True,
            'analysis': analysis
        })
        
    except Exception as e:
        app.logger.error(f"Musical analysis generation failed: {str(e)}")
        return jsonify({'success': False, 'message': f'Analysis generation failed: {str(e)}'})

@app.route('/api/loading-phrases', methods=['POST'])
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
        
        if user_id:
            user = User.query.get(user_id)
            if user:
                # Get basic user info for personalization
                spotify_client = SpotifyClient(user.access_token)
                try:
                    # Try to get recent listening context
                    recent_tracks = spotify_client.get_recently_played(limit=5)
                    if recent_tracks and 'items' in recent_tracks and recent_tracks['items']:
                        recent_genres = []
                        recent_artists = []
                        for item in recent_tracks['items'][:3]:
                            track = item.get('track', {})
                            if track.get('artists'):
                                recent_artists.append(track['artists'][0]['name'])
                        user_context = f"Recently listened to artists like {', '.join(recent_artists[:3])}"
                except:
                    # If we can't get recent tracks, use generic context
                    user_context = "music lover"
        
        # Configure Gemini
        genai.configure(api_key=custom_gemini_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Create prompt for loading phrases
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
        app.logger.info(f"Loading phrases generated in {duration:.2f}s")
        
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
            app.logger.error(f"Failed to parse loading phrases response: {str(e)}")
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
        app.logger.error(f"Loading phrases generation failed: {str(e)}")
        
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
    
@app.route('/test-callback')
def test_callback():
    """Test endpoint to verify callback URL is accessible"""
    app.logger.info("=== TEST CALLBACK ACCESSED ===")
    app.logger.info(f"Request URL: {request.url}")
    app.logger.info(f"Request args: {dict(request.args)}")
    app.logger.info(f"Request headers: {dict(request.headers)}")
    app.logger.info("=============================")
    
    return f"""
    <h1>Callback Test Successful!</h1>
    <p>If you can see this page, the callback URL is working.</p>
    <p>Request URL: {request.url}</p>
    <p>Args received: {dict(request.args)}</p>
    <p>Timestamp: {datetime.utcnow()}</p>
    """

@app.route('/debug-oauth')
def debug_oauth():
    """Debug endpoint to show OAuth configuration"""
    redirect_uri = get_redirect_uri()
    
    debug_info = {
        'current_time': datetime.utcnow().isoformat(),
        'app_host': request.host,
        'app_url': request.url,
        'client_id': SPOTIFY_CLIENT_ID,
        'client_secret_length': len(SPOTIFY_CLIENT_SECRET) if SPOTIFY_CLIENT_SECRET else 0,
        'redirect_uri': redirect_uri,
        'environment_redirect_uri': os.environ.get('SPOTIFY_REDIRECT_URI', 'NOT SET'),
        'scopes': 'user-read-private user-read-email playlist-read-private playlist-modify-public playlist-modify-private user-read-playback-state user-modify-playback-state user-read-currently-playing user-read-recently-played user-top-read user-library-read'
    }
    
    # Generate test authorization URL
    state = secrets.token_urlsafe(16)
    auth_params = {
        'response_type': 'code',
        'client_id': SPOTIFY_CLIENT_ID,
        'scope': debug_info['scopes'],
        'redirect_uri': redirect_uri,
        'state': state
    }
    auth_url = 'https://accounts.spotify.com/authorize?' + urlencode(auth_params)
    debug_info['test_auth_url'] = auth_url
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>OAuth Debug Information</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
            .container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .debug-item {{ margin: 10px 0; padding: 10px; background: #f8f9fa; border-left: 4px solid #007bff; }}
            .critical {{ border-left-color: #dc3545; background: #f8d7da; }}
            .success {{ border-left-color: #28a745; background: #d4edda; }}
            .warning {{ border-left-color: #ffc107; background: #fff3cd; }}
            .btn {{ display: inline-block; padding: 10px 20px; background: #1db954; color: white; text-decoration: none; border-radius: 4px; margin: 5px; }}
            pre {{ background: #f1f1f1; padding: 10px; border-radius: 4px; overflow-x: auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 Spotify OAuth Debug Information</h1>
            
            <div class="debug-item {'success' if debug_info['client_secret_length'] > 0 else 'critical'}">
                <strong>Client Credentials:</strong><br>
                Client ID: {debug_info['client_id']}<br>
                Client Secret: {'✅ Present (' + str(debug_info['client_secret_length']) + ' chars)' if debug_info['client_secret_length'] > 0 else '❌ Missing'}
            </div>
            
            <div class="debug-item success">
                <strong>Redirect URI Configuration:</strong><br>
                Current: {debug_info['redirect_uri']}<br>
                Environment: {debug_info['environment_redirect_uri']}
            </div>
            
            <div class="debug-item">
                <strong>App Information:</strong><br>
                Host: {debug_info['app_host']}<br>
                Current URL: {debug_info['app_url']}<br>
                Timestamp: {debug_info['current_time']}
            </div>
            
            <div class="debug-item warning">
                <strong>⚠️ Important Spotify Dashboard Check:</strong><br>
                In your <a href="https://developer.spotify.com/dashboard" target="_blank">Spotify Developer Dashboard</a>, 
                ensure the Redirect URI is EXACTLY:<br>
                <code>{debug_info['redirect_uri']}</code>
            </div>
            
            <h2>🧪 Test Endpoints</h2>
            <a href="/test-callback" class="btn" target="_blank">Test Callback URL</a>
            <a href="/test-callback?code=test123&state=test456" class="btn" target="_blank">Test Callback with Params</a>
            
            <h2>🔗 Test Authorization</h2>
            <p>Click this link to test the OAuth flow:</p>
            <a href="{debug_info['test_auth_url']}" class="btn" target="_blank">Test Spotify Authorization</a>
            
            <h2>📋 Configuration Details</h2>
            <pre>{json.dumps(debug_info, indent=2)}</pre>
            
            <h2>🏥 Troubleshooting Steps</h2>
            <ol>
                <li>Verify the Redirect URI in Spotify Dashboard matches exactly: <code>{debug_info['redirect_uri']}</code></li>
                <li>Test the callback URL directly: <a href="/test-callback" target="_blank">/test-callback</a></li>
                <li>Check if users are getting authorization errors on Spotify's side</li>
                <li>Verify your Client ID and Secret are correct</li>
                <li>Ensure your app has the correct scopes requested</li>
            </ol>
        </div>
    </body>
    </html>
    """
    
    return html
    
@app.route('/test-session')
def test_session():
    """Test session persistence and debugging"""
    # Log request details
    app.logger.info("=== SESSION TEST ===")
    app.logger.info(f"Session status: {'NEW' if not session else 'EXISTING'}")
    app.logger.info(f"Session contents: {dict(session)}")
    app.logger.info(f"Request cookies: {dict(request.cookies)}")
    app.logger.info("===================")
    
    # Test session persistence
    if 'test_time' not in session:
        session['test_time'] = time.time()
        session['test_counter'] = 1
    else:
        session['test_counter'] = session.get('test_counter', 0) + 1
    
    return jsonify({
        'session_working': True,
        'test_time': session['test_time'],
        'test_counter': session['test_counter'],
        'session_data': dict(session),
        'cookies': dict(request.cookies)
    })

@app.route('/test-spotify-auth')
def test_spotify_auth():
    """Test Spotify API connectivity with current session token"""
    app.logger.info("=== SPOTIFY AUTH TEST ===")
    
    if 'user_id' not in session:
        return jsonify({
            'error': 'No active session',
            'message': 'Please log in first'
        }), 401
    
    try:
        user = User.query.get(session['user_id'])
        if not user or not user.access_token:
            return jsonify({
                'error': 'No access token',
                'message': 'User found but no access token available'
            }), 401
        
        app.logger.info(f"Testing with user: {user.id}")
        app.logger.info(f"Token length: {len(user.access_token)}")
        app.logger.info(f"Token expires at: {user.token_expires_at}")
        
        # Test direct API call
        headers = {'Authorization': f'Bearer {user.access_token}'}
        response = requests.get('https://api.spotify.com/v1/me', headers=headers, timeout=10)
        
        app.logger.info(f"API test response status: {response.status_code}")
        app.logger.info(f"API test response: {response.text}")
        
        if response.status_code == 200:
            profile_data = response.json()
            return jsonify({
                'success': True,
                'user_id': profile_data.get('id'),
                'display_name': profile_data.get('display_name'),
                'api_status': 'working'
            })
        else:
            return jsonify({
                'error': 'API call failed',
                'status_code': response.status_code,
                'response': response.text
            }), response.status_code
            
    except Exception as e:
        app.logger.error(f"Spotify auth test failed: {e}")
        return jsonify({
            'error': 'Test failed',
            'exception': str(e)
        }), 500
    
    app.logger.info("========================")
    